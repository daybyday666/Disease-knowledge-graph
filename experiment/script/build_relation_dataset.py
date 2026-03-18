#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate relation-classification samples from annotated documents (核心数据处理：关系样本构建).

The script expects an input JSONL where each record contains:
  - "id": document identifier
  - "text": document text
  - "entities": list of entity dicts with at least {label, start_offset, end_offset, text?}
  - "relations": list of relation dicts with at least {head, tail, relation, head_span?, tail_span?}

For every disease-centric entity pair the script produces positive samples from
existing relations and samples negative pairs (labelled as "no_relation") from
entity combinations that do not have an annotated relation.

Outputs can be JSONL and/or CSV containing:
  doc_id, relation, head, tail, head_label, tail_label, text, head_span, tail_span

Usage example:
  python build_relation_dataset.py \
      --input ../data/merged_with_rel_add_disease.jsonl \
      --output-jsonl ../data/relation_dataset.jsonl \
      --output-csv ../data/relation_dataset.csv \
      --neg-ratio 1.0
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Mapping from entity label to relation type when paired with a disease entity.
# 标注到关系类型的映射：当 head 为“疾病”时，tail 标签 -> 关系名
LABEL_TO_RELATION = {
    "症状": "has_symptom",
    "病因": "has_cause",
    "诊断方法": "needs_diagnosis",
    "治疗": "uses_treatment",
    "科室": "belongs_to_department",
}

DISEASE_LABEL = "疾病"
DEFAULT_NEG_RATIO = 1.0


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def extract_text(doc_text: str, ent: Dict[str, Any]) -> str:
    if "text" in ent and ent["text"]:
        return ent["text"]
    start = ent.get("start_offset")
    end = ent.get("end_offset")
    if isinstance(start, int) and isinstance(end, int):
        return doc_text[start:end]
    return ""


def canonical_span(ent: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    start = ent.get("start_offset")
    end = ent.get("end_offset")
    if isinstance(start, int) and isinstance(end, int):
        return (start, end)
    return None


def build_entity_views(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """为实体补充文本与标准化 span，便于后续采样。"""
    text = doc.get("text", "")
    entities = doc.get("entities") or []
    enriched = []
    for ent in entities:
        view = dict(ent)
        view.setdefault("text", extract_text(text, ent))
        view["span"] = canonical_span(ent)
        enriched.append(view)
    return enriched


def collect_positive_keys(relations: Sequence[Dict[str, Any]]) -> Tuple[set, set]:
    """从已标注关系中构造去重键（span 级与文本级）。"""
    span_keys = set()
    text_keys = set()
    for rel in relations:
        rel_type = rel.get("relation")
        if rel_type not in LABEL_TO_RELATION.values():
            continue
        head_span = rel.get("head_span")
        tail_span = rel.get("tail_span")
        head_text = rel.get("head")
        tail_text = rel.get("tail")
        if head_span and tail_span and len(head_span) == 2 and len(tail_span) == 2:
            span_keys.add((head_span[0], head_span[1], tail_span[0], tail_span[1], rel_type))
        if head_text is not None and tail_text is not None:
            text_keys.add((head_text, tail_text, rel_type))
    return span_keys, text_keys


def relation_for_pair(head_label: str, tail_label: str) -> Optional[str]:
    """若 head 是“疾病”，返回 tail 的映射关系；否则 None。"""
    if head_label != DISEASE_LABEL:
        return None
    return LABEL_TO_RELATION.get(tail_label)


def generate_samples(
    doc: Dict[str, Any],
    neg_ratio: float,
    rng: random.Random,
) -> List[Dict[str, Any]]:
    """从单篇文档生成关系分类样本（正样本 + 负采样）。

    正样本：直接来自标注的 relations；
    负样本：从 (疾病, 其它目标实体) 组合中剔除已存在关系的对，按 neg_ratio 抽取并标注为 no_relation。
    """
    text = doc.get("text", "")
    doc_id = doc.get("id")
    entities = build_entity_views(doc)
    relations = doc.get("relations") or []

    span_pos_keys, text_pos_keys = collect_positive_keys(relations)
    positives: List[Dict[str, Any]] = []
    for rel in relations:
        rel_type = rel.get("relation")
        if rel_type not in LABEL_TO_RELATION.values():
            continue
        head_text = rel.get("head")
        tail_text = rel.get("tail")
        if not head_text or not tail_text:
            continue
        positives.append({
            "doc_id": doc_id,
            "text": text,
            "relation": rel_type,
            "head": head_text,
            "tail": tail_text,
            "head_label": DISEASE_LABEL,
            "tail_label": _infer_tail_label(rel_type),
            "head_span": tuple(rel.get("head_span") or []),
            "tail_span": tuple(rel.get("tail_span") or []),
        })

    # Candidate generation for negatives（候选负样本）
    disease_entities = [e for e in entities if e.get("label") == DISEASE_LABEL]
    other_entities = [e for e in entities if e.get("label") in LABEL_TO_RELATION]

    candidate_negatives: List[Dict[str, Any]] = []
    for head_ent in disease_entities:
        for tail_ent in other_entities:
            rel_type = relation_for_pair(head_ent.get("label"), tail_ent.get("label"))
            if not rel_type:
                continue
            span_key = None
            if head_ent.get("span") and tail_ent.get("span"):
                span_key = (
                    head_ent["span"][0],
                    head_ent["span"][1],
                    tail_ent["span"][0],
                    tail_ent["span"][1],
                    rel_type,
                )
            text_key = (head_ent.get("text"), tail_ent.get("text"), rel_type)
            if span_key and span_key in span_pos_keys:
                continue
            if text_key in text_pos_keys:
                continue
            candidate_negatives.append({
                "doc_id": doc_id,
                "text": text,
                "relation": "no_relation",
                "head": head_ent.get("text", ""),
                "tail": tail_ent.get("text", ""),
                "head_label": head_ent.get("label"),
                "tail_label": tail_ent.get("label"),
                "head_span": head_ent.get("span"),
                "tail_span": tail_ent.get("span"),
            })

    # Sample negatives（按比例采样负例）
    num_pos = len(positives)
    if num_pos == 0:
        max_negs = int(round(len(candidate_negatives) if neg_ratio < 0 else neg_ratio))
    else:
        max_negs = int(round(num_pos * neg_ratio)) if neg_ratio >= 0 else len(candidate_negatives)
    if neg_ratio == 0 or max_negs == 0:
        selected_negatives: List[Dict[str, Any]] = []
    else:
        if max_negs >= len(candidate_negatives):
            selected_negatives = candidate_negatives
        else:
            selected_negatives = rng.sample(candidate_negatives, max_negs)

    return positives + selected_negatives


def _infer_tail_label(relation: str) -> str:
    for label, rel in LABEL_TO_RELATION.items():
        if rel == relation:
            return label
    return ""


def write_jsonl(path: Path, samples: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for sample in samples:
            fh.write(json.dumps(sample, ensure_ascii=False) + "\n")


def write_csv(path: Path, samples: Iterable[Dict[str, Any]]) -> None:
    fields = [
        "doc_id",
        "relation",
        "head",
        "tail",
        "head_label",
        "tail_label",
        "head_span",
        "tail_span",
        "text",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            row = {key: sample.get(key) for key in fields}
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build relation classification dataset")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL with entities and relations")
    parser.add_argument("--output-jsonl", type=str, help="Output JSONL path")
    parser.add_argument("--output-csv", type=str, help="Output CSV path")
    parser.add_argument("--neg-ratio", type=float, default=DEFAULT_NEG_RATIO,
                        help="Negative sampling ratio relative to positives (use -1 for all)")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    input_path = Path(args.input)
    docs = read_jsonl(input_path)
    all_samples: List[Dict[str, Any]] = []

    for doc in docs:
        doc_samples = generate_samples(doc, neg_ratio=args.neg_ratio, rng=rng)
        all_samples.extend(doc_samples)

    if args.output_jsonl:
        write_jsonl(Path(args.output_jsonl), all_samples)
        print(f"[OK] JSONL saved to {args.output_jsonl}, total samples: {len(all_samples)}")
    if args.output_csv:
        write_csv(Path(args.output_csv), all_samples)
        print(f"[OK] CSV saved to {args.output_csv}, total samples: {len(all_samples)}")
    if not args.output_jsonl and not args.output_csv:
        print("[WARN] No output path specified. Nothing written.")


if __name__ == "__main__":
    main()
