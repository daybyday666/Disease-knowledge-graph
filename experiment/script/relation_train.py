#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Train a BERT-based relation classification model (disease centric).

Steps performed:
 1. Load relation samples generated via build_relation_dataset.py (JSONL).
 2. Split data by document id into train/dev sets.
 3. Fine-tune a pretrained Chinese BERT encoder with a softmax classifier.
 4. Track per-class and macro precision/recall/F1, trigger early stopping on
    macro F1 improvements, and persist the best checkpoint.

Example usage:
  python relation_train.py \
      --input ../data/relation_dataset.jsonl \
      --output-dir ../model/relation_cls \
      --epochs 10 --batch-size 16
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import csv

import torch
from accelerate import Accelerator
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)
from contextlib import nullcontext

from relation_common import (
    ID_TO_LABEL,
    LABEL_LIST,
    LABEL_TO_ID,
    insert_entity_markers,
    normalize_span,
)

try:
    from tqdm.auto import tqdm
except ImportError:
    tqdm = None

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

DEFAULT_MAX_LENGTH = 320


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            samples.append(json.loads(line))
    return samples


def group_by_doc(samples: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        doc_id = sample.get("doc_id")
        grouped[str(doc_id)].append(sample)
    return grouped


def train_dev_split(
    samples: Sequence[Dict[str, Any]],
    dev_ratio: float,
    seed: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    grouped = group_by_doc(samples)
    doc_ids = list(grouped.keys())
    rng = random.Random(seed)
    rng.shuffle(doc_ids)
    dev_size = int(round(len(doc_ids) * dev_ratio))
    dev_ids = set(doc_ids[:dev_size])
    train, dev = [], []
    for doc_id, doc_samples in grouped.items():
        if doc_id in dev_ids:
            dev.extend(doc_samples)
        else:
            train.extend(doc_samples)
    return train, dev


def train_dev_test_split(
    samples: Sequence[Dict[str, Any]],
    dev_ratio: float,
    test_ratio: float,
    seed: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split samples by document into train/dev/test to avoid leakage.

    The split is document-level: all samples from a document go into the same split.
    Ratios don't need to sum exactly to 1.0; train receives the remainder.
    """
    if dev_ratio < 0 or test_ratio < 0:
        raise ValueError("dev_ratio and test_ratio must be >= 0")

    grouped = group_by_doc(samples)
    doc_ids = list(grouped.keys())
    rng = random.Random(seed)
    rng.shuffle(doc_ids)

    n_docs = len(doc_ids)
    # Use floor to ensure we don't exceed total, assign remainder to train
    dev_count = int(n_docs * dev_ratio)
    test_count = int(n_docs * test_ratio)
    if dev_count + test_count >= n_docs:
        # Ensure at least one train doc
        if n_docs >= 3:
            # back off test_count first
            test_count = max(1, min(test_count, n_docs - 2))
            dev_count = max(1, min(dev_count, n_docs - 1 - test_count))
        else:
            raise ValueError("Not enough documents to perform train/dev/test split.")

    dev_ids = set(doc_ids[:dev_count])
    test_ids = set(doc_ids[dev_count:dev_count + test_count])

    train, dev, test = [], [], []
    for doc_id, doc_samples in grouped.items():
        if doc_id in dev_ids:
            dev.extend(doc_samples)
        elif doc_id in test_ids:
            test.extend(doc_samples)
        else:
            train.extend(doc_samples)

    if not train or not dev or not test:
        raise ValueError("Empty split encountered. Try adjusting dev_ratio/test_ratio or check data.")
    return train, dev, test


@dataclass
class RelationExample:
    text: str
    head: str
    tail: str
    head_span: Optional[Tuple[int, int]]
    tail_span: Optional[Tuple[int, int]]
    label_id: int


class RelationDataset(Dataset):
    def __init__(
        self,
        samples: Sequence[Dict[str, Any]],
        tokenizer: AutoTokenizer,
        max_length: int = DEFAULT_MAX_LENGTH,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.examples: List[RelationExample] = []
        for sample in samples:
            label = sample.get("relation")
            if label not in LABEL_TO_ID:
                continue
            text = sample.get("text", "")
            head_span = normalize_span(sample.get("head_span"))
            tail_span = normalize_span(sample.get("tail_span"))
            example = RelationExample(
                text=text,
                head=sample.get("head", ""),
                tail=sample.get("tail", ""),
                head_span=head_span,
                tail_span=tail_span,
                label_id=LABEL_TO_ID[label],
            )
            self.examples.append(example)

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        ex = self.examples[idx]
        marked = insert_entity_markers(
            ex.text,
            ex.head_span,
            ex.tail_span,
            ex.head,
            ex.tail
        )
        encoded = self.tokenizer(
            marked,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )
        item = {k: v.squeeze(0) for k, v in encoded.items()}
        item["labels"] = torch.tensor(ex.label_id, dtype=torch.long)
        return item


def create_dataloaders(
    train_samples: Sequence[Dict[str, Any]],
    dev_samples: Sequence[Dict[str, Any]],
    tokenizer: AutoTokenizer,
    batch_size: int,
    max_length: int,
) -> Tuple[DataLoader, DataLoader]:
    train_dataset = RelationDataset(train_samples, tokenizer, max_length=max_length)
    dev_dataset = RelationDataset(dev_samples, tokenizer, max_length=max_length)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    dev_loader = DataLoader(dev_dataset, batch_size=batch_size, shuffle=False)
    return train_loader, dev_loader


def create_dataloaders3(
    train_samples: Sequence[Dict[str, Any]],
    dev_samples: Sequence[Dict[str, Any]],
    test_samples: Sequence[Dict[str, Any]],
    tokenizer: AutoTokenizer,
    batch_size: int,
    max_length: int,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    train_dataset = RelationDataset(train_samples, tokenizer, max_length=max_length)
    dev_dataset = RelationDataset(dev_samples, tokenizer, max_length=max_length)
    test_dataset = RelationDataset(test_samples, tokenizer, max_length=max_length)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    dev_loader = DataLoader(dev_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    return train_loader, dev_loader, test_loader


def count_parameters(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def compute_metrics(preds: torch.Tensor, labels: torch.Tensor) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    eps = 1e-8
    macros: List[float] = []
    total_tp = total_fp = total_fn = 0

    for label_id, label_name in ID_TO_LABEL.items():
        tp = int(((preds == label_id) & (labels == label_id)).sum().item())
        fp = int(((preds == label_id) & (labels != label_id)).sum().item())
        fn = int(((preds != label_id) & (labels == label_id)).sum().item())
        precision = tp / (tp + fp + eps)
        recall = tp / (tp + fn + eps)
        f1 = 2 * precision * recall / (precision + recall + eps)
        metrics[f"precision_{label_name}"] = precision
        metrics[f"recall_{label_name}"] = recall
        metrics[f"f1_{label_name}"] = f1
        macros.append(f1)
        total_tp += tp
        total_fp += fp
        total_fn += fn

    metrics["macro_f1"] = sum(macros) / len(macros) if macros else 0.0
    metrics["micro_precision"] = total_tp / (total_tp + total_fp + eps)
    metrics["micro_recall"] = total_tp / (total_tp + total_fn + eps)
    metrics["micro_f1"] = 2 * metrics["micro_precision"] * metrics["micro_recall"] / (
        metrics["micro_precision"] + metrics["micro_recall"] + eps
    )
    return metrics


def save_metrics_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train relation classifier")
    parser.add_argument("--input", type=str, required=True, help="Relation samples JSONL")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to store checkpoints & metrics")
    parser.add_argument("--model-name", type=str, default="bert-base-chinese")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.06)
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    parser.add_argument("--dev-ratio", type=float, default=0.10, help="Validation split ratio (e.g., 0.1 for 10%)")
    parser.add_argument("--test-ratio", type=float, default=0.20, help="Test split ratio (e.g., 0.2 for 20%)")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--patience", type=int, default=3, help="Early stopping patience based on macro F1")
    parser.add_argument("--grad-accum", type=int, default=1, help="Gradient accumulation steps")
    parser.add_argument("--no-plot", action="store_true", help="禁用训练曲线可视化输出")
    return parser.parse_args()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def main() -> None:
    args = parse_args()
    accelerator = Accelerator(log_with=None)
    seed_everything(args.seed)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    samples = read_jsonl(input_path)
    # 7:1:2 默认：dev_ratio=0.1, test_ratio=0.2
    train_samples, dev_samples, test_samples = train_dev_test_split(samples, args.dev_ratio, args.test_ratio, args.seed)

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    if tokenizer.pad_token is None:
        tokenizer.add_special_tokens({"pad_token": "[PAD]"})

    train_loader, dev_loader, test_loader = create_dataloaders3(
        train_samples,
        dev_samples,
        test_samples,
        tokenizer,
        batch_size=args.batch_size,
        max_length=args.max_length,
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(LABEL_LIST),
    )
    if tokenizer.pad_token_id is not None and model.config.pad_token_id is None:
        model.config.pad_token_id = tokenizer.pad_token_id

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    total_steps = args.epochs * math.ceil(len(train_loader) / args.grad_accum)
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)

    model, optimizer, train_loader, dev_loader, test_loader, scheduler = accelerator.prepare(
        model,
        optimizer,
        train_loader,
        dev_loader,
        test_loader,
        scheduler,
    )

    best_macro_f1 = -1.0
    best_epoch = -1
    patience_counter = 0
    history_rows: List[Dict[str, Any]] = []
    metrics_jsonl = output_dir / "relation_metrics.jsonl"
    metrics_csv = output_dir / "relation_metrics.csv"

    print(f"[INFO] Train samples: {len(train_samples)}  Dev samples: {len(dev_samples)}  Test samples: {len(test_samples)}")
    print(f"[INFO] Trainable parameters: {count_parameters(model):,}")

    if accelerator.state.mixed_precision != "no":
        autocast_ctx = accelerator.autocast
    else:
        autocast_ctx = nullcontext

    best_checkpoint_path = output_dir / "best_model"

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        step = 0
        optimizer.zero_grad()
        train_iter = train_loader
        if tqdm is not None:
            train_iter = tqdm(
                train_loader,
                desc=f"Epoch {epoch}/{args.epochs} - train",
                leave=False,
                disable=not accelerator.is_local_main_process,
            )
        for batch_idx, batch in enumerate(train_iter, start=1):
            with autocast_ctx():
                outputs = model(**batch)
                loss = outputs.loss / args.grad_accum
            accelerator.backward(loss)
            total_loss += loss.item()
            if batch_idx % args.grad_accum == 0:
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
            step += 1
            if tqdm is not None and accelerator.is_local_main_process:
                train_iter.set_postfix(loss=f"{loss.item():.4f}")
        avg_loss = total_loss / max(1, step)

        if tqdm is not None:
            train_iter.close()

        metrics = evaluate(model, dev_loader, accelerator)
        metrics["epoch"] = epoch
        metrics["train_loss"] = avg_loss
        history_rows.append(metrics.copy())

        print(f"[Epoch {epoch:02d}] loss={avg_loss:.4f} macro_f1={metrics['macro_f1']:.4f}")

        if accelerator.is_local_main_process:
            with metrics_jsonl.open("a", encoding="utf-8") as jf:
                jf.write(json.dumps(metrics, ensure_ascii=False) + "\n")

        # Early stopping based on macro F1
        if metrics["macro_f1"] > best_macro_f1 + 1e-5:
            best_macro_f1 = metrics["macro_f1"]
            best_epoch = epoch
            patience_counter = 0
            accelerator.wait_for_everyone()
            unwrapped = accelerator.unwrap_model(model)
            ensure_dir(best_checkpoint_path)
            unwrapped.save_pretrained(best_checkpoint_path, save_function=accelerator.save)
            tokenizer.save_pretrained(best_checkpoint_path)
            print(f"[INFO] Saved new best checkpoint to {best_checkpoint_path}")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                print(f"[EARLY STOP] No macro F1 improvement for {args.patience} epochs.")
                break

    # Evaluate best checkpoint on test split
    if accelerator.is_local_main_process:
        print("[INFO] Loading best checkpoint for test evaluation…")
    best_model = AutoModelForSequenceClassification.from_pretrained(best_checkpoint_path)
    best_model = accelerator.prepare(best_model)
    test_metrics = evaluate(best_model, test_loader, accelerator)
    test_metrics["split"] = "test"
    if accelerator.is_local_main_process:
        # Save test metrics
        test_json = output_dir / "test_metrics.json"
        test_csv = output_dir / "test_metrics.csv"
        with test_json.open("w", encoding="utf-8") as jf:
            jf.write(json.dumps(test_metrics, ensure_ascii=False, indent=2))
        save_metrics_csv(test_csv, [test_metrics])
        print(f"[TEST] macro_f1={test_metrics.get('macro_f1', 0.0):.4f}  micro_f1={test_metrics.get('micro_f1', 0.0):.4f}")
        # Save train/dev history and plot with test overlay
        save_metrics_csv(metrics_csv, history_rows)
        if not args.no_plot:
            plot_training_curves(history_rows, output_dir, test_macro_f1=test_metrics.get("macro_f1"), best_epoch=best_epoch)
    accelerator.wait_for_everyone()
    print(f"[DONE] Best macro F1={best_macro_f1:.4f} at epoch {best_epoch}")


def evaluate(
    model: torch.nn.Module,
    dataloader: DataLoader,
    accelerator: Accelerator,
) -> Dict[str, Any]:
    model.eval()
    all_preds: List[torch.Tensor] = []
    all_labels: List[torch.Tensor] = []
    data_iter = dataloader
    if tqdm is not None:
        data_iter = tqdm(
            dataloader,
            desc="Evaluation",
            leave=False,
            disable=not accelerator.is_local_main_process,
        )
    with torch.no_grad():
        for batch in data_iter:
            labels = batch["labels"]
            outputs = model(**batch)
            logits = outputs.logits
            preds = torch.argmax(logits, dim=-1)
            preds = accelerator.gather(preds)
            labels = accelerator.gather(labels)
            all_preds.append(preds.cpu())
            all_labels.append(labels.cpu())
    if tqdm is not None:
        data_iter.close()
    preds_tensor = torch.cat(all_preds, dim=0)
    labels_tensor = torch.cat(all_labels, dim=0)
    metrics = compute_metrics(preds_tensor, labels_tensor)
    return metrics


def plot_training_curves(
    history_rows: List[Dict[str, Any]],
    output_dir: Path,
    test_macro_f1: Optional[float] = None,
    best_epoch: Optional[int] = None,
) -> None:
    if not history_rows:
        return
    if plt is None:
        print("[提示] 未安装 matplotlib，无法绘制训练曲线。")
        return
    epochs = [row.get("epoch") for row in history_rows]
    losses = [row.get("train_loss") for row in history_rows]
    macro_f1 = [row.get("macro_f1") for row in history_rows]
    plt.figure(figsize=(8, 4))
    plt.subplot(1, 2, 1)
    plt.plot(epochs, losses, marker="o")
    plt.title("Train Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.grid(True, alpha=0.3)
    plt.subplot(1, 2, 2)
    plt.plot(epochs, macro_f1, marker="o", color="green")
    plt.title("Dev Macro F1")
    plt.xlabel("Epoch")
    plt.ylabel("F1")
    plt.ylim(0, 1.0)
    # Optional: add test macro F1 as a horizontal line and a marker at best epoch
    if test_macro_f1 is not None:
        plt.axhline(y=test_macro_f1, color="red", linestyle="--", linewidth=1.2, label=f"Test Macro F1={test_macro_f1:.4f}")
        if best_epoch is not None and len(epochs) > 0:
            plt.scatter([best_epoch], [test_macro_f1], color="red", marker="*", s=90, label="Test @ best epoch")
        plt.legend(loc="lower right")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    fig_path = output_dir / "relation_training_curves.png"
    plt.savefig(fig_path, dpi=150)
    plt.close()
    print(f"[INFO] 训练曲线已保存到 {fig_path}")


if __name__ == "__main__":
    main()
