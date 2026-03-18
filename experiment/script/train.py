import os
import math
import csv
import json
import argparse
import torch
from torch.utils.data import DataLoader
from dataset import read_bio, build_vocab, NERDataset, pad_batch, save_vocab
from model import BiLSTMCRF
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


############################################
# 评估工具函数
############################################
def extract_entities(tag_seq):
    """从单个标签序列中抽取实体 (start, end, type)。end为开区间。
    规则: B-X 开启; 后续连续 I-X 归入; 其它标签结束当前实体。"""
    entities = []
    start, ent_type = None, None
    for i, tag in enumerate(tag_seq):
        if tag.startswith('B-'):
            # 结束旧实体
            if start is not None:
                entities.append((start, i, ent_type))
            start = i
            ent_type = tag[2:]
        elif tag.startswith('I-') and start is not None and tag[2:] == ent_type:
            # 延续
            pass
        else:
            if start is not None:
                entities.append((start, i, ent_type))
                start, ent_type = None, None
    if start is not None:
        entities.append((start, len(tag_seq), ent_type))
    return entities


def entity_level_prf(gold_tag_seqs, pred_tag_seqs):
    """实体级 micro-F1 (逐样本累加 TP/FP/FN，避免全局set去重丢计数)。"""
    tp = fp = fn = 0
    gold_entities_all = []
    pred_entities_all = []
    for g, p in zip(gold_tag_seqs, pred_tag_seqs):
        g_ents = extract_entities(g)
        p_ents = extract_entities(p)
        gold_entities_all.extend(g_ents)
        pred_entities_all.extend(p_ents)
        g_set = set(g_ents)
        p_set = set(p_ents)
        tp += len(g_set & p_set)
        fp += len(p_set - g_set)
        fn += len(g_set - p_set)
    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    return precision, recall, f1, gold_entities_all, pred_entities_all


def token_level_prf(gold_tag_seqs, pred_tag_seqs):
    """标签(token)级 micro-F1，主要用于对比。忽略长度不等部分的多余预测。"""
    tp = fp = fn = 0
    for g, p in zip(gold_tag_seqs, pred_tag_seqs):
        L = min(len(g), len(p))
        for i in range(L):
            if g[i] == p[i]:
                if g[i] != 'O':
                    tp += 1
            else:
                if p[i] != 'O':
                    fp += 1
                if g[i] != 'O':
                    fn += 1
        # 预测长出来的部分
        for extra in p[L:]:
            if extra != 'O':
                fp += 1
        for extra in g[L:]:
            if extra != 'O':
                fn += 1
    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    return precision, recall, f1


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', type=int, default=30, help='训练轮数')
    ap.add_argument('--no-plot', action='store_true', help='不生成曲线图')
    ap.add_argument('--save-dir', type=str, default='.', help='输出目录')
    ap.add_argument('--debug', action='store_true', help='输出调试信息(标签范围/样本示例)')
    ap.add_argument('--emb-dim', type=int, default=128, help='字符Embedding维度')
    ap.add_argument('--hidden-dim', type=int, default=256, help='BiLSTM隐藏维度(双向拼接后)')
    ap.add_argument('--dropout', type=float, default=0.3, help='LSTM输出后FC前的dropout')
    ap.add_argument('--patience', type=int, default=5, help='早停耐心(实体F1未提升轮数)')
    ap.add_argument('--lr', type=float, default=1e-3, help='初始学习率')
    ap.add_argument('--lr-decay-epoch', type=int, default=10, help='在该epoch后触发一次LR衰减(若>0)')
    ap.add_argument('--lr-gamma', type=float, default=0.1, help='LR衰减因子')
    ap.add_argument('--augment', action='store_true', help='启用简单同义词替换数据增强(占位)')
    ap.add_argument('--type-metrics', action='store_true', help='输出按实体类型的P/R/F1')
    ap.add_argument('--enforce-bio', action='store_true', help='训练时CRF施加BIO转移约束并解码后纠正非法I开头')
    ap.add_argument('--plateau', action='store_true', help='使用ReduceLROnPlateau基于dev实体F1调整学习率')
    return ap.parse_args()


def main():
    args = parse_args()
    base = os.path.dirname(os.path.abspath(__file__))
    train_path = os.path.join(base, 'train.bio')
    dev_path = os.path.join(base, 'dev.bio')
    train_samples = read_bio(train_path)
    dev_samples = read_bio(dev_path)
    # 简单数据增强: 针对训练样本进行同义词替换（字符级替换仅示例）
    if args.augment:
        synonym_map = {
            '检': ['检', '查'],  # 示例: 扩充‘检测’中的‘检’为‘查’ (演示)
            '疗': ['疗', '治'],  # ‘治疗’ -> ‘治’
            '痛': ['痛', '疼'],
            '痒': ['痒', '瘙'],
        }
        augmented = []
        for chars, tags in train_samples:
            augmented.append((chars, tags))
            # 简单生成 1 条增强样本
            new_chars = chars.copy()
            changed = False
            for i, ch in enumerate(new_chars):
                if ch in synonym_map:
                    repl_list = synonym_map[ch]
                    if len(repl_list) > 1:
                        # 选择不同的替代
                        alt = repl_list[1]
                        if alt != ch:
                            new_chars[i] = alt
                            changed = True
            if changed:
                augmented.append((new_chars, tags))  # 标签位置不变（长度不变场景）
        train_samples = augmented
    char2id, tag2id = build_vocab(train_samples + dev_samples)
    save_vocab(os.path.join(base, 'char_vocab.txt'), char2id)
    save_vocab(os.path.join(base, 'tag_vocab.txt'), tag2id)
    train_ds = NERDataset(train_samples, char2id, tag2id)
    dev_ds = NERDataset(dev_samples, char2id, tag2id)
    train_loader = DataLoader(train_ds, batch_size=8, shuffle=True, collate_fn=lambda b: pad_batch(b, pad_idx=0))
    dev_loader = DataLoader(dev_ds, batch_size=8, shuffle=False, collate_fn=lambda b: pad_batch(b, pad_idx=0))
    device = torch.device('cpu')
    id2tag = {v:k for k,v in tag2id.items()}
    model = BiLSTMCRF(vocab_size=len(char2id), tag_size=len(tag2id), emb_dim=args.emb_dim, hidden_dim=args.hidden_dim, pad_idx=0, dropout=args.dropout, enforce_bio=args.enforce_bio, id2tag=id2tag).to(device)
    # 若需要插入dropout，可在模型中修改；这里临时在 loss 前后不处理（保持结构简单）。
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = None
    if args.plateau:
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=2, verbose=True, min_lr=1e-5)
    elif args.lr_decay_epoch > 0:
        def lr_lambda(current_epoch):
            if current_epoch > args.lr_decay_epoch:
                return args.lr_gamma
            return 1.0
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lr_lambda)
    best_dev_f1 = 0.0
    patience = 0
    max_patience = args.patience
    EPOCHS = args.epochs

    metrics_csv = os.path.join(args.save_dir, 'metrics.csv')
    metrics_jsonl = os.path.join(args.save_dir, 'metrics.jsonl')
    if not os.path.exists(args.save_dir):
        os.makedirs(args.save_dir, exist_ok=True)
    # 初始化文件头
    if not os.path.exists(metrics_csv):
        with open(metrics_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['epoch', 'train_loss', 'dev_entity_p', 'dev_entity_r', 'dev_entity_f1', 'dev_token_p', 'dev_token_r', 'dev_token_f1'])
    open(metrics_jsonl, 'a', encoding='utf-8').close()

    history = {'epoch': [], 'train_loss': [], 'dev_f1': []}

    if args.debug:
        print('[DEBUG] 标签映射(tag2id):', tag2id)
        # 打印一条样本的原始字符与标签
        sample_chars, sample_tags = train_samples[0]
        print('[DEBUG] 样本0长度:', len(sample_chars))
        print('[DEBUG] 样本0标签序列(前50):', sample_tags[:50])

    for epoch in range(1, EPOCHS+1):
        model.train()
        total_loss = 0.0
        iterable = train_loader
        if tqdm is not None:
            iterable = tqdm(train_loader, desc=f'Epoch {epoch}/{EPOCHS}', ncols=100)
        for batch_idx, (x, y, mask) in enumerate(iterable):
            x, y, mask = x.to(device), y.to(device), mask.to(device)
            loss = model(x, y, mask)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            total_loss += loss.item()
            if tqdm is not None:
                iterable.set_postfix(loss=f'{loss.item():.4f}')
            if args.debug and batch_idx == 0 and epoch == 1:
                print('[DEBUG] 首批 input max token id:', int(x.max()))
                print('[DEBUG] 首批 tag max id:', int(y.max()))
                print('[DEBUG] 首批 mask 第一行:', mask[0].tolist()[:60])
        avg_loss = total_loss / max(1, len(train_loader))
        if args.debug and (math.isinf(avg_loss) or avg_loss > 1e4):
            print('[WARN][DEBUG] 异常高的loss, 请检查数据/标签/CRF实现。')
        # 验证
        model.eval()
        gold_tags_all, pred_tags_all = [], []
        with torch.no_grad():
            for x, y, mask in dev_loader:
                x, y, mask = x.to(device), y.to(device), mask.to(device)
                paths = model(x, tags=None, mask=mask)
                for i, path in enumerate(paths):
                    seq_len = int(mask[i].sum().item())
                    gold_ids = y[i][:seq_len].tolist()
                    id2tag = {v: k for k, v in tag2id.items()}
                    gold_tags = [id2tag.get(g, 'O') for g in gold_ids]
                    # 过滤越界标签 (可能由于路径回溯早停导致长度略短)
                    pred_tags = [id2tag.get(p, 'O') for p in path[:len(gold_tags)]]
                    # 若预测比gold短，用 'O' 补齐
                    if len(pred_tags) < len(gold_tags):
                        pred_tags += ['O'] * (len(gold_tags) - len(pred_tags))
                    gold_tags_all.append(gold_tags)
                    pred_tags_all.append(pred_tags)
        # 实体级 (micro) 指标
        ent_p, ent_r, ent_f1, gold_ents, pred_ents = entity_level_prf(gold_tags_all, pred_tags_all)
        # token级 (micro) 指标
        tok_p, tok_r, tok_f1 = token_level_prf(gold_tags_all, pred_tags_all)
        print(f"Epoch {epoch:02d}: loss={avg_loss:.4f} ENT_P={ent_p:.4f} ENT_R={ent_r:.4f} ENT_F1={ent_f1:.4f} | TOK_F1={tok_f1:.4f}")

        type_metrics = None
        if args.type_metrics:
            # 统计类别级指标：遍历实体列表 (start,end,type)
            from collections import defaultdict
            type_tp = defaultdict(int); type_fp = defaultdict(int); type_fn = defaultdict(int)
            # 将gold与pred按样本拆分再统计：已在实体抽取阶段gold_ents/pred_ents是整体列表，直接用集合交并
            gold_set = set(gold_ents); pred_set = set(pred_ents)
            inter = gold_set & pred_set
            for (s,e,t) in inter: type_tp[t]+=1
            for (s,e,t) in (pred_set - gold_set): type_fp[t]+=1
            for (s,e,t) in (gold_set - pred_set): type_fn[t]+=1
            type_metrics = {}
            for t in sorted(set([x[2] for x in gold_ents+pred_ents])):
                tp_t, fp_t, fn_t = type_tp[t], type_fp[t], type_fn[t]
                p_t = tp_t / (tp_t + fp_t + 1e-8)
                r_t = tp_t / (tp_t + fn_t + 1e-8)
                f1_t = 2*p_t*r_t/(p_t+r_t+1e-8)
                type_metrics[t] = {'p': p_t, 'r': r_t, 'f1': f1_t, 'tp': tp_t, 'fp': fp_t, 'fn': fn_t}
            if args.debug:
                print('[DEBUG][TYPE] 各类型指标(前5):', list(type_metrics.items())[:5])

        if args.debug and ent_f1 < 0.1:
            # 打印前几个实体调试
            print('[DEBUG][EVAL] 实体级F1过低，调试样例:')
            print('  Gold实体数:', len(gold_ents), ' Pred实体数:', len(pred_ents), ' TP估计:', len(set(gold_ents) & set(pred_ents)))
            print('  Gold前5:', gold_ents[:5])
            print('  Pred前5:', pred_ents[:5])
            # 展示第一条序列标签对比（截断）
            if gold_tags_all:
                print('  序列0 GOLD:', gold_tags_all[0][:80])
                print('  序列0 PRED:', pred_tags_all[0][:80])

        # 记录指标
        with open(metrics_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([epoch, f'{avg_loss:.6f}', f'{ent_p:.6f}', f'{ent_r:.6f}', f'{ent_f1:.6f}', f'{tok_p:.6f}', f'{tok_r:.6f}', f'{tok_f1:.6f}'])
        with open(metrics_jsonl, 'a', encoding='utf-8') as f:
            record = {
                'epoch': epoch,
                'train_loss': avg_loss,
                'dev_entity_precision': ent_p,
                'dev_entity_recall': ent_r,
                'dev_entity_f1': ent_f1,
                'dev_token_precision': tok_p,
                'dev_token_recall': tok_r,
                'dev_token_f1': tok_f1
            }
            if type_metrics is not None:
                record['dev_type_metrics'] = type_metrics
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        history['epoch'].append(epoch)
        history['train_loss'].append(avg_loss)
        history['dev_f1'].append(ent_f1)
        # 简单过拟合监控
        # 学习率调度
        if scheduler is not None:
            if args.plateau:
                scheduler.step(ent_f1)
            else:
                scheduler.step(epoch)
        current_lr = optimizer.param_groups[0]['lr']
        if args.debug:
            print(f'[DEBUG] Epoch {epoch} 当前LR={current_lr:.6g}')

        if ent_f1 > best_dev_f1:
            best_dev_f1 = ent_f1
            patience = 0
            torch.save(model.state_dict(), os.path.join(base, 'best_model.pt'))
        else:
            patience += 1
            if patience >= max_patience:
                print("[早停] 验证集 F1 连续未提升，可能出现过拟合趋势。")
                break

    print(f"训练完成，最佳验证 实体F1={best_dev_f1:.4f}")

    # 绘图
    if not args.no_plot:
        if plt is None:
            print('[提示] 未安装 matplotlib，无法绘制曲线。可执行: pip install matplotlib')
        else:
            plt.figure(figsize=(8,4))
            plt.subplot(1,2,1)
            plt.plot(history['epoch'], history['train_loss'], marker='o')
            plt.title('Train Loss')
            plt.xlabel('Epoch'); plt.ylabel('Loss')
            plt.subplot(1,2,2)
            plt.plot(history['epoch'], history['dev_f1'], marker='o', color='green')
            plt.title('Dev F1')
            plt.xlabel('Epoch'); plt.ylabel('F1')
            plt.tight_layout()
            fig_path = os.path.join(args.save_dir, 'metrics.png')
            plt.savefig(fig_path, dpi=150)
            print(f'[可视化] 指标曲线已保存: {fig_path}')


if __name__ == '__main__':
    main()
