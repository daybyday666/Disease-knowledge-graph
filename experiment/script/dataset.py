import os
from typing import List, Dict, Tuple
import torch
from torch.utils.data import Dataset


def read_bio(path: str) -> List[Tuple[List[str], List[str]]]:
    """读取BIO文件 -> [(chars, tags), ...]"""
    samples = []
    chars, tags = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                if chars:
                    samples.append((chars, tags))
                    chars, tags = [], []
                continue
            if ' ' not in line:
                # 容错: 没有标签
                ch = line
                lab = 'O'
            else:
                ch, lab = line.split(' ', 1)
            chars.append(ch)
            tags.append(lab)
    if chars:
        samples.append((chars, tags))
    return samples


def build_vocab(samples: List[Tuple[List[str], List[str]]]):
    char2id = {"<PAD>": 0, "<UNK>": 1}
    tag2id = {"<PAD>": 0}
    for chars, tags in samples:
        for ch in chars:
            if ch not in char2id:
                char2id[ch] = len(char2id)
        for t in tags:
            if t not in tag2id:
                tag2id[t] = len(tag2id)
    return char2id, tag2id


class NERDataset(Dataset):
    def __init__(self, samples, char2id, tag2id):
        self.samples = samples
        self.char2id = char2id
        self.tag2id = tag2id

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        chars, tags = self.samples[idx]
        x = [self.char2id.get(c, self.char2id["<UNK>"]) for c in chars]
        y = [self.tag2id[t] for t in tags]
        return torch.tensor(x, dtype=torch.long), torch.tensor(y, dtype=torch.long)


def pad_batch(batch, pad_idx=0):
    xs, ys = zip(*batch)
    max_len = max(len(x) for x in xs)
    mask = []
    padded_x, padded_y = [], []
    for x, y in zip(xs, ys):
        pad_len = max_len - len(x)
        padded_x.append(torch.cat([x, torch.full((pad_len,), pad_idx)]))
        padded_y.append(torch.cat([y, torch.full((pad_len,), pad_idx)]))
        mask.append(torch.tensor([1]*len(x) + [0]*pad_len, dtype=torch.uint8))
    return torch.stack(padded_x), torch.stack(padded_y), torch.stack(mask)


def save_vocab(path: str, mapping: Dict[str, int]):
    with open(path, 'w', encoding='utf-8') as f:
        for k, v in mapping.items():
            f.write(f"{k}\t{v}\n")


def load_vocab(path: str) -> Dict[str, int]:
    d = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            k, v = line.split('\t')
            d[k] = int(v)
    return d
