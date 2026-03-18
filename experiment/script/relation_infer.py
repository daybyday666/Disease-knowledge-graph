#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run relation classification inference and merge predictions into documents."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from relation_common import ID_TO_LABEL, LABEL_TO_ID, insert_entity_markers, normalize_span

LABEL_TO_RELATION = {
    "症状": "has_symptom",
    "病因": "has_cause",
    "诊断方法": "needs_diagnosis",
    "治疗": "uses_treatment",
    "科室": "belongs_to_department",
}
DISEASE_LABEL = "疾病"
DEFAULT_THRESHOLD = 0.5


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def write_jsonl(path: Path, data: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for obj in data:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def collect_positive_keys(relations: Sequence[Dict[str, Any]]) -> Tuple[set, set]:
    span_keys = set()
    text_keys = set()
    for rel in relations or []:
        rel_type = rel.get("relation")
        head_span = rel.get("head_span")
        tail_span = rel.get("tail_span")
        head_text = rel.get("head")
        tail_text = rel.get("tail")
        if head_span and tail_span and len(head_span) == 2 and len(tail_span) == 2:
            span_keys.add((head_span[0], head_span[1], tail_span[0], tail_span[1], rel_type))
        if head_text is not None and tail_text is not None:
            text_keys.add((head_text, tail_text, rel_type))
    return span_keys, text_keys


def extract_text(doc_text: str, ent: Dict[str, Any]) -> str:
    if "text" in ent and ent["text"]:
        return ent["text"]
    start = ent.get("start_offset")
    end = ent.get("end_offset")
    if isinstance(start, int) and isinstance(end, int):
        return doc_text[start:end]
    return ""


def build_entities(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = doc.get("text", "")
    entities = []
    for ent in doc.get("entities") or []:
        span = normalize_span(ent.get("span"))
        if span is None:
            span = normalize_span((ent.get("start_offset"), ent.get("end_offset")))
        enriched = dict(ent)
        enriched["text"] = extract_text(text, ent)
        enriched["span"] = span
        entities.append(enriched)
    return entities


@dataclass
class Candidate:
    doc_index: int
    doc_id: Any
    text: str
    expected_relation: str
    head: str
    tail: str
    head_span: Optional[Tuple[int, int]]
    tail_span: Optional[Tuple[int, int]]


def generate_candidates(doc: Dict[str, Any], doc_index: int) -> List[Candidate]:
    text = doc.get("text", "")
    relations = doc.get("relations") or []
    span_pos_keys, text_pos_keys = collect_positive_keys(relations)
    entities = build_entities(doc)
    disease_entities = [e for e in entities if e.get("label") == DISEASE_LABEL]
    other_entities = [e for e in entities if e.get("label") in LABEL_TO_RELATION]

    candidates: List[Candidate] = []
    for head_ent in disease_entities:
        for tail_ent in other_entities:
            rel_type = LABEL_TO_RELATION.get(tail_ent.get("label"))
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
            candidates.append(Candidate(
                doc_index=doc_index,
                doc_id=doc.get("id"),
                text=text,
                expected_relation=rel_type,
                head=head_ent.get("text", ""),
                tail=tail_ent.get("text", ""),
                head_span=head_ent.get("span"),
                tail_span=tail_ent.get("span"),
            ))
    return candidates


class InferenceDataset(Dataset):
    def __init__(self, candidates: Sequence[Candidate], tokenizer: AutoTokenizer, max_length: int):
        self.candidates = list(candidates)
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.encoded_inputs: List[Dict[str, torch.Tensor]] = []
        for cand in self.candidates:
            marked = insert_entity_markers(
                cand.text,
                cand.head_span,
                cand.tail_span,
                cand.head,
                cand.tail,
            )
            enc = tokenizer(
                marked,
                truncation=True,
                max_length=self.max_length,
                padding="max_length",
                return_tensors="pt",
            )
            self.encoded_inputs.append({k: v.squeeze(0) for k, v in enc.items()})

    def __len__(self) -> int:
        return len(self.candidates)

    def __getitem__(self, idx: int):
        return self.encoded_inputs[idx], self.candidates[idx]


def collate_fn(batch):
    input_keys = batch[0][0].keys()
    inputs = {k: torch.stack([item[0][k] for item in batch]) for k in input_keys}
    metas = [item[1] for item in batch]
    return inputs, metas


def add_predictions_to_docs(
    docs: List[Dict[str, Any]],
    positives: List[Tuple[Candidate, float]],
) -> None:
    for cand, score in positives:
        doc = docs[cand.doc_index]
        if "relations" not in doc or doc["relations"] is None:
            doc["relations"] = []
        relation_obj = {
            "head": cand.head,
            "tail": cand.tail,
            "relation": cand.expected_relation,
            "confidence": round(float(score), 6),
        }
        if cand.head_span:
            relation_obj["head_span"] = list(cand.head_span)
        if cand.tail_span:
            relation_obj["tail_span"] = list(cand.tail_span)
        doc["relations"].append(relation_obj)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relation classifier inference")
    parser.add_argument("--model-dir", type=str, required=True, help="Trained model directory (matching relation_train.py output)")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL with documents")
    parser.add_argument("--output", type=str, required=True, help="Output JSONL with merged relations")
    parser.add_argument("--triples-jsonl", type=str, help="Optional JSONL to store predicted triples")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Probability threshold for accepting predictions")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=320)
    parser.add_argument("--device", type=str, default=None, help="Override torch device, e.g., 'cuda:0' or 'cpu'")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = torch.device(args.device) if args.device else torch.device("cuda" if torch.cuda.is_available() else "cpu")

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_dir)
    model.to(device)
    model.eval()

    docs = read_jsonl(Path(args.input))
    all_candidates: List[Candidate] = []
    for idx, doc in enumerate(docs):
        all_candidates.extend(generate_candidates(doc, idx))

    if not all_candidates:
        print("[INFO] No candidate pairs found. Nothing to predict.")
        write_jsonl(Path(args.output), docs)
        return

    dataset = InferenceDataset(all_candidates, tokenizer, max_length=args.max_length)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)

    accepted: List[Tuple[Candidate, float]] = []
    predicted_triples: List[Dict[str, Any]] = []

    softmax = torch.nn.Softmax(dim=-1)
    with torch.no_grad():
        for batch_inputs, metas in dataloader:
            batch_inputs = {k: v.to(device) for k, v in batch_inputs.items()}
            outputs = model(**batch_inputs)
            logits = outputs.logits
            probs = softmax(logits)
            pred_ids = torch.argmax(logits, dim=-1)
            probs_cpu = probs.cpu()
            pred_ids_cpu = pred_ids.cpu()
            for meta, pred_id, prob_vec in zip(metas, pred_ids_cpu, probs_cpu):
                label = ID_TO_LABEL[int(pred_id)]
                if label == "no_relation":
                    continue
                if label != meta.expected_relation:
                    continue
                score = float(prob_vec[pred_id])
                if score < args.threshold:
                    continue
                accepted.append((meta, score))
                predicted_triples.append({
                    "doc_id": meta.doc_id,
                    "head": meta.head,
                    "tail": meta.tail,
                    "relation": label,
                    "confidence": score,
                })

    add_predictions_to_docs(docs, accepted)
    write_jsonl(Path(args.output), docs)
    print(f"[INFO] Saved updated documents to {args.output}. Added {len(accepted)} relations.")

    if args.triples_jsonl:
        write_jsonl(Path(args.triples_jsonl), predicted_triples)
        print(f"[INFO] Saved predicted triples to {args.triples_jsonl}")


if __name__ == "__main__":
    main()
