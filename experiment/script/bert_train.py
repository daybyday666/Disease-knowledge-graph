import os
import argparse
import json
import csv
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer
from bert_crf_model import BERTCRF
from dataset import read_bio, save_vocab
from train import extract_entities, entity_level_prf, token_level_prf
import math
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

class BertNERDataset(Dataset):
    def __init__(self, samples, tokenizer, tag2id, max_len=512):
        self.samples = samples
        self.tokenizer = tokenizer
        self.tag2id = tag2id
        self.id2tag = {v:k for k,v in tag2id.items()}
        self.max_len = max_len

    def __len__(self):
        return len(self.samples)

    def _align(self, chars, tags):
        # 简单做法: 每个原始字符分词，用第一个 WordPiece 继承标签，其余子词标记为 pad_idx(0) 或者 'O'
        # 因 tag2id 中 0 已经是 <PAD>，保持与原 BiLSTM 一致。
        tokens = []
        label_ids = []
        for ch, tag in zip(chars, tags):
            wp = self.tokenizer.tokenize(ch)
            if not wp:
                wp = [self.tokenizer.unk_token]
            tokens.extend(wp)
            # 第一个子词赋原标签，其余子词设为 'O'，以免破坏实体边界 (更保守)
            first_tag_id = self.tag2id.get(tag, self.tag2id.get('O'))
            tokens_extra = len(wp) - 1
            label_ids.append(first_tag_id)
            for _ in range(tokens_extra):
                label_ids.append(self.tag2id.get('O'))
        # 截断
        tokens = tokens[:self.max_len-2]
        label_ids = label_ids[:self.max_len-2]
        # 加上 [CLS] [SEP]
        tokens = [self.tokenizer.cls_token] + tokens + [self.tokenizer.sep_token]
        label_ids = [self.tag2id.get('O')] + label_ids + [self.tag2id.get('O')]
        attn_mask = [1]*len(tokens)
        return tokens, label_ids, attn_mask

    def __getitem__(self, idx):
        chars, tags = self.samples[idx]
        tokens, label_ids, attn_mask = self._align(chars, tags)
        encoding = self.tokenizer.convert_tokens_to_ids(tokens)
        return {
            'input_ids': torch.tensor(encoding, dtype=torch.long),
            'labels': torch.tensor(label_ids, dtype=torch.long),
            'attention_mask': torch.tensor(attn_mask, dtype=torch.long)
        }

def collate_fn(batch, pad_id, pad_tag_id):
    max_len = max(len(x['input_ids']) for x in batch)
    input_ids = []
    labels = []
    attn_mask = []
    for item in batch:
        l = len(item['input_ids'])
        pad_n = max_len - l
        input_ids.append(torch.cat([item['input_ids'], torch.full((pad_n,), pad_id, dtype=torch.long)]))
        labels.append(torch.cat([item['labels'], torch.full((pad_n,), pad_tag_id, dtype=torch.long)]))
        attn_mask.append(torch.cat([item['attention_mask'], torch.zeros(pad_n, dtype=torch.long)]))
    input_ids = torch.stack(input_ids)
    labels = torch.stack(labels)
    attn_mask = torch.stack(attn_mask)
    return input_ids, labels, attn_mask


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pretrained', type=str, default='bert-base-chinese')
    ap.add_argument('--epochs', type=int, default=5)
    ap.add_argument('--batch-size', type=int, default=8)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--dropout', type=float, default=0.1)
    ap.add_argument('--max-len', type=int, default=256)
    ap.add_argument('--save-dir', type=str, default=None, help='模型与指标输出目录，默认使用项目 model 目录')
    ap.add_argument('--strict-bio', action='store_true')
    ap.add_argument('--enforce-bio', action='store_true')
    ap.add_argument('--no-plot', action='store_true')
    ap.add_argument('--debug', action='store_true')
    ap.add_argument('--metrics-jsonl', type=str, default='bert_metrics.jsonl', help='记录逐轮指标的JSONL文件')
    ap.add_argument('--freeze-emb', action='store_true', help='冻结BERT embeddings')
    ap.add_argument('--freeze-layers', type=int, default=0, help='冻结前N个BERT encoder层')
    ap.add_argument('--patience', type=int, default=3, help='实体F1早停耐心')
    return ap.parse_args()


def main():
    args = parse_args()
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.normpath(os.path.join(base, '..', 'data'))
    model_dir_default = os.path.normpath(os.path.join(base, '..', 'model'))
    train_path = os.path.join(data_dir, 'train.bio')
    dev_path = os.path.join(data_dir, 'dev.bio')
    if args.save_dir is None:
        args.save_dir = model_dir_default
    train_samples = read_bio(train_path)
    dev_samples = read_bio(dev_path)
    from dataset import build_vocab
    char2id, tag2id = build_vocab(train_samples + dev_samples)
    id2tag = {v:k for k,v in tag2id.items()}
    pad_tag_id = tag2id['<PAD>']

    tokenizer = AutoTokenizer.from_pretrained(args.pretrained)

    train_ds = BertNERDataset(train_samples, tokenizer, tag2id, max_len=args.max_len)
    dev_ds = BertNERDataset(dev_samples, tokenizer, tag2id, max_len=args.max_len)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id, pad_tag_id))
    dev_loader = DataLoader(dev_ds, batch_size=args.batch_size, shuffle=False,
                            collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id, pad_tag_id))

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = BERTCRF(args.pretrained, tag_size=len(tag2id), pad_idx=pad_tag_id, id2tag=id2tag,
                    dropout=args.dropout, enforce_bio=args.enforce_bio, strict_bio=args.strict_bio,
                    freeze_embeddings=args.freeze_emb, freeze_encoder_layers=args.freeze_layers).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    metrics_csv = os.path.join(args.save_dir, 'bert_metrics.csv')
    if not os.path.exists(args.save_dir):
        os.makedirs(args.save_dir, exist_ok=True)
    if not os.path.exists(metrics_csv):
        with open(metrics_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['epoch','loss','ent_p','ent_r','ent_f1','tok_p','tok_r','tok_f1'])

    metrics_jsonl_path = os.path.join(args.save_dir, args.metrics_jsonl)
    open(metrics_jsonl_path, 'a', encoding='utf-8').close()

    best_f1 = 0.0
    best_epoch = 0
    patience_counter = 0
    max_patience = args.patience
    history = {'epoch': [], 'loss': [], 'f1': []}

    for epoch in range(1, args.epochs+1):
        model.train()
        total_loss = 0.0
        train_iter = train_loader
        if tqdm is not None:
            train_iter = tqdm(train_loader, desc=f'Epoch {epoch}/{args.epochs}', ncols=100)
        for batch in train_iter:
            input_ids, labels, attn_mask = [x.to(device) for x in batch]
            loss = model(input_ids, attention_mask=attn_mask, tags=labels)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            if tqdm is not None:
                train_iter.set_postfix(loss=f'{loss.item():.4f}')
        avg_loss = total_loss / max(1, len(train_loader))
        if args.debug and (math.isinf(avg_loss) or avg_loss > 1e4):
            print('[WARN][DEBUG] 异常高loss，请检查。')

        # 验证
        model.eval()
        gold_tags_all, pred_tags_all = [], []
        with torch.no_grad():
            for batch in dev_loader:
                input_ids, labels, attn_mask = [x.to(device) for x in batch]
                paths = model(input_ids, attention_mask=attn_mask, tags=None)
                for i, path in enumerate(paths):
                    seq_len = int(attn_mask[i].sum().item())
                    valid_len = seq_len - 2
                    lab_seq = labels[i][1:1+valid_len].tolist()
                    pred_seq = path[1:1+valid_len]
                    gold_tags = [id2tag.get(t, 'O') for t in lab_seq]
                    pred_tags = [id2tag.get(t, 'O') for t in pred_seq]
                    gold_tags_all.append(gold_tags)
                    pred_tags_all.append(pred_tags)
        ent_p, ent_r, ent_f1, gold_ents, pred_ents = entity_level_prf(gold_tags_all, pred_tags_all)
        tok_p, tok_r, tok_f1 = token_level_prf(gold_tags_all, pred_tags_all)
        print(f"[BERT] Epoch {epoch:02d}: loss={avg_loss:.4f} ENT_P={ent_p:.4f} ENT_R={ent_r:.4f} ENT_F1={ent_f1:.4f} TOK_F1={tok_f1:.4f}")

        # 写 CSV
        with open(metrics_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([epoch, f'{avg_loss:.6f}', f'{ent_p:.6f}', f'{ent_r:.6f}', f'{ent_f1:.6f}', f'{tok_p:.6f}', f'{tok_r:.6f}', f'{tok_f1:.6f}'])
        # 写 JSONL
        with open(metrics_jsonl_path, 'a', encoding='utf-8') as jf:
            jf.write(json.dumps({
                'epoch': epoch,
                'train_loss': avg_loss,
                'dev_entity_precision': ent_p,
                'dev_entity_recall': ent_r,
                'dev_entity_f1': ent_f1,
                'dev_token_precision': tok_p,
                'dev_token_recall': tok_r,
                'dev_token_f1': tok_f1
            }, ensure_ascii=False) + '\n')

        history['epoch'].append(epoch)
        history['loss'].append(avg_loss)
        history['f1'].append(ent_f1)

        if ent_f1 > best_f1:
            best_f1 = ent_f1
            best_epoch = epoch
            patience_counter = 0
            torch.save(model.state_dict(), os.path.join(args.save_dir, 'best_bert_crf.pt'))
        else:
            patience_counter += 1
            if patience_counter >= max_patience:
                print(f"[早停] 连续 {max_patience} 轮实体F1未提升, 提前停止。最佳F1={best_f1:.4f} @ epoch {best_epoch}")
                break

    print(f"BERT-CRF 训练完成，最佳实体F1={best_f1:.4f}")

    # 绘图
    if not args.no_plot:
        if plt is None:
            print('[提示] 未安装 matplotlib，无法绘制曲线。')
        else:
            plt.figure(figsize=(8,4))
            plt.subplot(1,2,1)
            plt.plot(history['epoch'], history['loss'], marker='o')
            plt.title('Train Loss')
            plt.xlabel('Epoch'); plt.ylabel('Loss')
            plt.subplot(1,2,2)
            plt.plot(history['epoch'], history['f1'], marker='o', color='green')
            plt.title('Dev Entity F1')
            plt.xlabel('Epoch'); plt.ylabel('F1')
            plt.tight_layout()
            fig_path = os.path.join(args.save_dir, 'bert_metrics.png')
            plt.savefig(fig_path, dpi=150)
            print(f'[可视化] 曲线保存: {fig_path}')

if __name__ == '__main__':
    main()
