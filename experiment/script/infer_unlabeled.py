import os
import json
import argparse
import torch
from transformers import AutoTokenizer
from bert_crf_model import BERTCRF
from dataset import build_vocab, read_bio, load_vocab
from model import BiLSTMCRF

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# 复用训练阶段的实体抽取逻辑 (简化版)
def bio_tags_to_spans(tags):
    spans = []
    start = None
    cur_type = None
    for i, t in enumerate(tags):
        if t.startswith('B-'):
            if start is not None:
                spans.append((start, i, cur_type))
            start = i
            cur_type = t[2:]
        elif t.startswith('I-'):
            if start is None:
                # 异常 I 开头，转为 B
                start = i
                cur_type = t[2:]
        else:  # O
            if start is not None:
                spans.append((start, i, cur_type))
                start = None
                cur_type = None
    if start is not None:
        spans.append((start, len(tags), cur_type))
    return spans

def load_tag_vocab(train_bio_path, dev_bio_path):
    # 重新构建标签映射 (和训练一致) - 依赖 train.bio/dev.bio 存在
    samples = read_bio(train_bio_path) + read_bio(dev_bio_path)
    _, tag2id = build_vocab(samples)
    id2tag = {v: k for k, v in tag2id.items()}
    return tag2id, id2tag

def decode_document(model, tokenizer, id2tag, text, max_len):
    # 按训练时逻辑: 逐字符送入 tokenizer (保留首子词标签，其他视作O). 推理阶段无需标签, 但需对输入切块避免超长。
    chars = list(text)
    all_tags = []
    device = next(model.parameters()).device
    i = 0
    while i < len(chars):
        window = chars[i:i+max_len-2]  # 预留 [CLS][SEP]
        tokens = []
        mapping = []  # 记录第一个子词对应的原始字符index
        for idx, ch in enumerate(window):
            wp = tokenizer.tokenize(ch)
            if not wp:
                wp = [tokenizer.unk_token]
            tokens.extend(wp)
            mapping.extend([i+idx])  # 只保留第一个子词位置映射 (标签级 granularity 与训练一致)
            # 其余子词忽略 (默认O)
        tokens = tokens[:max_len-2]
        # 构建 input
        tokens_full = [tokenizer.cls_token] + tokens + [tokenizer.sep_token]
        input_ids = tokenizer.convert_tokens_to_ids(tokens_full)
        attn_mask = [1]*len(input_ids)
        input_ids = torch.tensor([input_ids], dtype=torch.long, device=device)
        attn_mask = torch.tensor([attn_mask], dtype=torch.long, device=device)
        with torch.no_grad():
            paths = model(input_ids, attention_mask=attn_mask, tags=None)
        path = paths[0]  # 含 [CLS][SEP] 位置标签 id
        # 去除首尾
        pred_ids = path[1:1+len(tokens)]
        pred_tags = [id2tag.get(tid, 'O') for tid in pred_ids]
        # 由于我们只映射首子词 -> 字符, pred_tags 长度 == len(mapping)
        # 回填到 all_tags (其余子词默认为O，已经不在 mapping)
        for mi, tag in zip(mapping, pred_tags):
            # 确保扩展 list
            if mi >= len(all_tags):
                all_tags.extend(['O'] * (mi - len(all_tags) + 1))
            all_tags[mi] = tag
        i += (max_len - 2)
    # 填充剩余 O
    if len(all_tags) < len(chars):
        all_tags.extend(['O'] * (len(chars) - len(all_tags)))
    return all_tags[:len(chars)]

def decode_document_bilstm(model, char2id, id2tag, text, max_len, device):
    chars = list(text)
    tags = []
    i = 0
    while i < len(chars):
        window = chars[i:i+max_len]
        x = [char2id.get(c, char2id.get('<UNK>', 1)) for c in window]
        x_tensor = torch.tensor([x], dtype=torch.long, device=device)
        mask = torch.tensor([[1]*len(x)], dtype=torch.uint8, device=device)
        with torch.no_grad():
            paths = model(x_tensor, tags=None, mask=mask)
        pred_ids = paths[0]
        tags.extend([id2tag.get(tid, 'O') for tid in pred_ids])
        i += max_len
    return tags[:len(chars)]

def deduplicate_entities(entities):
    # 基于 (label,start,end,text) 去重
    seen = set()
    uniq = []
    for e in entities:
        key = (e['label'], e['start_offset'], e['end_offset'], e['text'])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', choices=['bert','bilstm'], default='bert', help='选择推理架构')
    # 通用
    parser.add_argument('--input', type=str, default='all.jsonl')
    parser.add_argument('--output', type=str, default='predicted_unlabeled.jsonl')
    parser.add_argument('--max-len', type=int, default=256, help='BERT: 含[CLS][SEP]; BiLSTM: slice长度')
    parser.add_argument('--device', type=str, default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--global-dedup', action='store_true', help='跨文档(label,text) 去重')
    parser.add_argument('--no-progress', action='store_true', help='关闭进度条显示')
    # BERT 相关
    parser.add_argument('--bert-model', type=str, default='best_bert_crf.pt', help='BERT 权重 state_dict')
    parser.add_argument('--pretrained', type=str, default='bert-base-chinese')
    parser.add_argument('--train-bio', type=str, default='train.bio')
    parser.add_argument('--dev-bio', type=str, default='dev.bio')
    parser.add_argument('--strict-bio', action='store_true')
    parser.add_argument('--enforce-bio', action='store_true')
    # BiLSTM 相关
    parser.add_argument('--bilstm-model', type=str, default='best_model.pt', help='BiLSTM-CRF 权重')
    parser.add_argument('--char-vocab', type=str, default='char_vocab.txt')
    parser.add_argument('--tag-vocab', type=str, default='tag_vocab.txt')
    parser.add_argument('--emb-dim', type=int, default=128)
    parser.add_argument('--hidden-dim', type=int, default=256)
    args = parser.parse_args()

    device = torch.device(args.device)

    # =============== 加载模型与标签映射 ===============
    if args.arch == 'bert':
        if not os.path.exists(args.bert-model if hasattr(args,'bert-model') else getattr(args,'bert_model','best_bert_crf.pt')):
            pass  # 简化校验，下面统一用变量
        for p in [args.train_bio, args.dev_bio, args.bert_model]:
            if not os.path.exists(p):
                raise FileNotFoundError(f'缺失文件: {p}')
        tag2id, id2tag = load_tag_vocab(args.train_bio, args.dev_bio)
        pad_tag_id = tag2id['<PAD>']
        tokenizer = AutoTokenizer.from_pretrained(args.pretrained)
        model = BERTCRF(args.pretrained, tag_size=len(tag2id), pad_idx=pad_tag_id, id2tag=id2tag,
                        dropout=0.0, enforce_bio=args.enforce_bio, strict_bio=args.strict_bio).to(device)
        state = torch.load(args.bert_model, map_location=device)
        model.load_state_dict(state)
        decoder = lambda text: decode_document(model, tokenizer, id2tag, text, args.max_len)
    else:  # bilstm
        # 需要 char_vocab / tag_vocab / best_model.pt
        for p in [args.char_vocab, args.tag_vocab, args.bilstm_model]:
            if not os.path.exists(p):
                raise FileNotFoundError(f'缺失文件: {p}')
        char2id = load_vocab(args.char_vocab)
        tag2id = load_vocab(args.tag_vocab)
        id2tag = {v:k for k,v in tag2id.items()}
        pad_idx = tag2id['<PAD>'] if '<PAD>' in tag2id else 0
        model = BiLSTMCRF(vocab_size=len(char2id), tag_size=len(tag2id), emb_dim=args.emb_dim,
                          hidden_dim=args.hidden_dim, pad_idx=pad_idx, dropout=0.0,
                          enforce_bio=args.enforce_bio, id2tag=id2tag).to(device)
        state = torch.load(args.bilstm_model, map_location=device)
        model.load_state_dict(state)
        model.eval()
        decoder = lambda text: decode_document_bilstm(model, char2id, id2tag, text, args.max_len, device)

    model.eval()

    # =============== 进度准备 ===============
    total_lines = sum(1 for _ in open(args.input, 'r', encoding='utf-8'))
    total = 0
    predicted_docs = 0
    total_entities = 0
    global_seen = set()

    fin = open(args.input, 'r', encoding='utf-8')
    fout = open(args.output, 'w', encoding='utf-8')

    iterator = fin
    use_bar = (not args.no_progress) and (tqdm is not None)
    if use_bar:
        iterator = tqdm(fin, total=total_lines, desc=f'Infer-{args.arch}', ncols=100)

    for raw in iterator:
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        ents = obj.get('entities', [])
        if ents:  # 有gold跳过
            continue
        text = obj.get('text', '')
        if not text:
            continue
        total += 1
        tags = decoder(text)
        spans = bio_tags_to_spans(tags)
        pred_entities = []
        for (s, e, tp) in spans:
            mention = text[s:e]
            if args.global_dedup:
                gk = (tp, mention)
                if gk in global_seen:
                    continue
                global_seen.add(gk)
            pred_entities.append({
                'id': None,
                'label': tp,
                'start_offset': s,
                'end_offset': e,
                'text': mention,
                'confidence': None
            })
        pred_entities = deduplicate_entities(pred_entities)
        if pred_entities:
            obj['predicted_entities'] = pred_entities
            predicted_docs += 1
            total_entities += len(pred_entities)
            fout.write(json.dumps(obj, ensure_ascii=False) + '\n')
        if use_bar:
            iterator.set_postfix({
                'docs': total,
                'pred_docs': predicted_docs,
                'entities': total_entities
            })

    fin.close()
    fout.close()
    if use_bar:
        iterator.close()

    print(f'[完成] 架构={args.arch} 总行={total_lines} 推理未标注文档={total} 生成预测文档={predicted_docs} 实体总数={total_entities} -> {args.output}')

if __name__ == '__main__':
    main()
