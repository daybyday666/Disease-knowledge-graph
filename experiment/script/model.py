import torch
import torch.nn as nn


class CRF(nn.Module):
    """简单 CRF 实现 (PAD=0)。

    参数:
        enforce_bio: 旧方式(黑名单禁用若干非法转移)。
        strict_bio:  白名单方式，只允许合法 BIO 转移 (推荐)；自动跳过 <PAD> 标签。
        id2tag:      id->标签字符串映射，用于构造合法转移集合。
    """

    def __init__(self, num_tags: int, pad_idx: int = 0, enforce_bio: bool = False, id2tag=None, strict_bio: bool = False):
        super().__init__()
        self.num_tags = num_tags
        self.start_tag = num_tags          # 伪起始
        self.end_tag = num_tags + 1        # 伪结束
        self.pad_idx = pad_idx
        self.enforce_bio = enforce_bio
        self.strict_bio = strict_bio
        self.id2tag = id2tag

        # 转移矩阵 (含 start / end)
        self.transitions = nn.Parameter(torch.randn(num_tags + 2, num_tags + 2))

        neg_inf = -1e4
        # 任何标签 -> START 禁止; END -> 任何标签 禁止
        self.transitions.data[:, self.start_tag] = neg_inf
        self.transitions.data[self.end_tag, :] = neg_inf

        if self.strict_bio and id2tag is not None:
            # 白名单：全部初始化为 -inf，再按规则放开
            self.transitions.data[:, :] = neg_inf
            # START 只允许到 O 或 B-*
            for j in range(num_tags):
                if j == self.pad_idx:
                    continue
                tj = id2tag[j]
                if tj == 'O' or tj.startswith('B-'):
                    self.transitions.data[self.start_tag, j] = 0
            # 标签内部转移
            for i in range(num_tags):
                if i == self.pad_idx:
                    continue
                ti = id2tag[i]
                if ti == 'O':
                    for j in range(num_tags):
                        if j == self.pad_idx:
                            continue
                        tj = id2tag[j]
                        # O -> O 或 B-*
                        if tj == 'O' or tj.startswith('B-'):
                            self.transitions.data[i, j] = 0
                    continue
                # 解析前缀与类型
                if '-' in ti:
                    pi, type_i = ti.split('-', 1)
                else:
                    pi, type_i = ti, None
                for j in range(num_tags):
                    if j == self.pad_idx:
                        continue
                    tj = id2tag[j]
                    if tj == 'O':
                        # B/I -> O 允许结束实体
                        self.transitions.data[i, j] = 0
                        continue
                    if '-' in tj:
                        pj, type_j = tj.split('-', 1)
                    else:
                        pj, type_j = tj, None
                    allow = False
                    if pi == 'B':
                        # B-X -> I-X 或 B-* (新实体) 或 O(已在上面) 已处理 O
                        if (pj == 'I' and type_j == type_i) or pj == 'B':
                            allow = True
                    elif pi == 'I':
                        # I-X -> I-X / B-* (紧跟新实体) / O(已处理)
                        if (pj == 'I' and type_j == type_i) or pj == 'B':
                            allow = True
                    if allow:
                        self.transitions.data[i, j] = 0
            # 合法标签 -> END
            for i in range(num_tags):
                if i == self.pad_idx:
                    continue
                self.transitions.data[i, self.end_tag] = 0
        elif self.enforce_bio and id2tag is not None:
            # 黑名单：仅屏蔽明显非法 (保留兼容，建议使用 strict_bio)
            for i in range(num_tags):
                if i == self.pad_idx:
                    continue
                tag_i = id2tag[i]
                prefix_i = tag_i.split('-', 1)[0] if '-' in tag_i else tag_i
                type_i = tag_i.split('-', 1)[1] if '-' in tag_i else None
                for j in range(num_tags):
                    if j == self.pad_idx:
                        continue
                    tag_j = id2tag[j]
                    prefix_j = tag_j.split('-', 1)[0] if '-' in tag_j else tag_j
                    type_j = tag_j.split('-', 1)[1] if '-' in tag_j else None
                    if prefix_i == 'O' and prefix_j == 'I':
                        self.transitions.data[i, j] = neg_inf
                    if prefix_i == 'I' and prefix_j == 'I' and type_i != type_j:
                        self.transitions.data[i, j] = neg_inf
                    if prefix_i == 'B' and prefix_j == 'I' and type_i != type_j:
                        self.transitions.data[i, j] = neg_inf
            for j in range(num_tags):
                if j == self.pad_idx:
                    continue
                tag_j = id2tag[j]
                if tag_j.startswith('I-'):
                    self.transitions.data[self.start_tag, j] = neg_inf

    def forward(self, emissions, tags, mask):
        # emissions: (B, L, num_tags)
        # 前向：计算序列的条件对数似然 = log Z(x) - score(x, y)
        log_den = self._compute_log_partition(emissions, mask)
        log_num = self._compute_gold_score(emissions, tags, mask)
        return torch.mean(log_den - log_num)

    def _compute_log_partition(self, emissions, mask):
        B, L, C = emissions.size()
        emissions_ext = torch.cat([emissions, emissions.new_zeros(B, L, 2)], dim=-1)
        alpha = emissions.new_full((B, C + 2), -1e4)
        alpha[:, self.start_tag] = 0
        for t in range(L):
            emit_t = emissions_ext[:, t]
            mask_t = mask[:, t].unsqueeze(1)
            score_t = alpha.unsqueeze(2) + self.transitions.unsqueeze(0) + emit_t.unsqueeze(1)
            score_t = torch.logsumexp(score_t, dim=1)
            alpha = torch.where(mask_t.bool(), score_t, alpha)
        end_scores = alpha + self.transitions[:, self.end_tag].unsqueeze(0)
        return torch.logsumexp(end_scores, dim=1)

    def _compute_gold_score(self, emissions, tags, mask):
        B, L, C = emissions.size()
        emissions_ext = torch.cat([emissions, emissions.new_zeros(B, L, 2)], dim=-1)
        score = emissions.new_zeros(B)
        prev = torch.full((B,), self.start_tag, dtype=torch.long, device=emissions.device)
        for t in range(L):
            mask_t = mask[:, t]
            current = tags[:, t]
            emit_t = emissions_ext[torch.arange(B), t, current]
            trans_t = self.transitions[prev, current]
            score += (emit_t + trans_t) * mask_t
            prev = torch.where(mask_t.bool(), current, prev)
        score += self.transitions[prev, self.end_tag]
        return score

    def decode(self, emissions, mask):
        """Viterbi 解码：在 CRF 图上找到分数最高的标签路径。

        返回：list[list[int]]，每个样本的最佳标签id序列（按有效长度截断）。
        """
        B, L, C = emissions.size()
        emissions_ext = torch.cat([emissions, emissions.new_zeros(B, L, 2)], dim=-1)
        # dp: 动态规划表，初始 START 为 0，其他为 -inf
        dp = emissions.new_full((B, C + 2), -1e4)
        dp[:, self.start_tag] = 0
        backptr = []
        for t in range(L):
            emit_t = emissions_ext[:, t]  # (B, C+2)
            # 对每个“上一状态”取转移后加当前发射得分的最大值
            scores = dp.unsqueeze(2) + self.transitions.unsqueeze(0)  # (B, C+2, C+2)
            best_scores, best_tags = scores.max(1)  # (B, C+2)
            dp = best_scores + emit_t
            backptr.append(best_tags)
        # 结束
        end_scores = dp + self.transitions[:, self.end_tag].unsqueeze(0)
        best_last_scores, best_last_tags = end_scores.max(1)
        paths = []
        for b in range(B):
            seq_len = int(mask[b].sum().item())
            tag = best_last_tags[b].item()
            path = []
            for t in range(seq_len - 1, -1, -1):
                bp = backptr[t][b, tag].item()
                if tag < self.num_tags:
                    path.append(tag)
                tag = bp
            path = list(reversed(path))
            paths.append(path[:seq_len])
        return paths


class BiLSTMCRF(nn.Module):
    def __init__(self, vocab_size, tag_size, emb_dim=128, hidden_dim=256, pad_idx=0, dropout=0.0, enforce_bio=False, id2tag=None, strict_bio=False):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, emb_dim, padding_idx=pad_idx)
        self.lstm = nn.LSTM(emb_dim, hidden_dim // 2, num_layers=1, bidirectional=True, batch_first=True)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        self.fc = nn.Linear(hidden_dim, tag_size)
        self.id2tag = id2tag
        self.crf = CRF(tag_size, pad_idx=pad_idx, enforce_bio=enforce_bio, id2tag=id2tag, strict_bio=strict_bio)

    def forward(self, x, tags=None, mask=None):
        emb = self.embedding(x)
        emb = self.dropout(emb)
        out, _ = self.lstm(emb)
        out = self.dropout(out)
        emissions = self.fc(out)
        if tags is not None:
            return self.crf(emissions, tags, mask)
        paths = self.crf.decode(emissions, mask)
        # 纠正非法 I-* 开头或 I 不连续片段: 简单规则 I->B
        if self.id2tag is not None:
            for p in paths:
                prev_type = None
                for idx, tid in enumerate(p):
                    tag_str = self.id2tag.get(tid, 'O')
                    if tag_str.startswith('I-'):
                        cur_type = tag_str[2:]
                        if idx == 0 or prev_type != cur_type:
                            # 转换为对应 B- 标签 id
                            # 查找 B-cur_type
                            for k,v in self.id2tag.items():
                                if v == f'B-{cur_type}':
                                    p[idx] = k
                                    break
                            prev_type = cur_type
                        else:
                            prev_type = cur_type
                    elif tag_str.startswith('B-'):
                        prev_type = tag_str[2:]
                    else:
                        prev_type = None
        return paths
