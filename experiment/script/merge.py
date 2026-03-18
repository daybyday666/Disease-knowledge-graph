#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将已标注 (gold) 的实体与预测实体文件合并。

使用示例:
  python merge.py --original all.jsonl --pred predicted_unlabeled.jsonl --output merged.jsonl 

合并策略 (--mode):
  fill   (默认)  : 只有当原文档实体为空或不存在时才填入预测实体
  append         : 总是把预测实体追加到原实体之后 (可配合 --dedup 去重)
  replace        : 用预测实体完全替换掉原实体 (慎用)
  skip           : 如果原来已有实体则跳过 (与 fill 的区别是 fill 会填充空文档，skip 直接不处理)

去重策略 (--dedup):
  span (默认) : 基于 (start_offset,end_offset,label)
  text       : 基于 (实体文本,label) (预测实体需包含 text 字段)
  none       : 不去重

可选功能:
  --keep-extra   : 保留预测实体里的 text / confidence 字段
  --add-source   : 给实体加 source='gold' 或 'pred'
  --stats stats.json : 额外输出合并统计

输出: 与原 all.jsonl 同一行一个文档, 保留原字段, 更新/新增 entities 列表.
实体 id 规则: 扫描原始文件找到最大 id, 新增预测实体 id 从 max+1 递增。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
	items: List[Dict[str, Any]] = []
	with open(path, 'r', encoding='utf-8') as f:
		for line in f:
			line = line.strip()
			if not line:
				continue
			try:
				items.append(json.loads(line))
			except json.JSONDecodeError as e:
				raise ValueError(f"解析失败 {path}: {e}\n行: {line[:200]}")
	return items


def write_jsonl(path: str | Path, data: List[Dict[str, Any]]):
	with open(path, 'w', encoding='utf-8') as f:
		for obj in data:
			f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def collect_max_entity_id(docs: List[Dict[str, Any]]) -> int:
	max_id = 0
	for d in docs:
		for ent in d.get('entities') or []:
			try:
				max_id = max(max_id, int(ent.get('id', 0)))
			except (TypeError, ValueError):
				continue
	return max_id


def index_docs(docs: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
	idx: Dict[Any, Dict[str, Any]] = {}
	for d in docs:
		doc_id = d.get('id')
		if doc_id in idx:
			raise ValueError(f"重复文档 id: {doc_id}")
		idx[doc_id] = d
	return idx


def make_dedup_key(e: Dict[str, Any], mode: str) -> Tuple[Any, ...]:
	if mode == 'span':
		return (e.get('start_offset'), e.get('end_offset'), e.get('label'))
	if mode == 'text':
		txt = e.get('text')
		if txt is None:
			return (e.get('start_offset'), e.get('end_offset'), e.get('label'))
		return (txt, e.get('label'))
	return (id(e),)


def dedup_merge(base: List[Dict[str, Any]], extra: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
	if mode == 'none':
		return base + extra
	seen: Set[Tuple[Any, ...]] = set()
	out: List[Dict[str, Any]] = []
	for e in base:
		k = make_dedup_key(e, mode)
		seen.add(k)
		out.append(e)
	for e in extra:
		k = make_dedup_key(e, mode)
		if k in seen:
			continue
		seen.add(k)
		out.append(e)
	return out


def convert_pred(raw: Dict[str, Any], new_id: int, keep_extra: bool, add_source: bool) -> Dict[str, Any]:
	ent = {
		'id': new_id,
		'label': raw['label'],
		'start_offset': raw['start_offset'],
		'end_offset': raw['end_offset'],
	}
	if keep_extra:
		if 'text' in raw:
			ent['text'] = raw['text']
		if 'confidence' in raw:
			ent['confidence'] = raw['confidence']
	if add_source:
		ent['source'] = 'pred'
	return ent


def mark_gold(docs: List[Dict[str, Any]]):
	for d in docs:
		for e in d.get('entities') or []:
			e.setdefault('source', 'gold')


def merge(
	original: str | Path,
	pred: str | Path,
	output: str | Path,
	mode: str = 'fill',
	dedup: str = 'span',
	keep_extra: bool = False,
	add_source: bool = False,
) -> Dict[str, Any]:
	gold_docs = read_jsonl(original)
	pred_docs = read_jsonl(pred)
	idx = index_docs(gold_docs)
	max_id = collect_max_entity_id(gold_docs)
	if add_source:
		mark_gold(gold_docs)

	stats = {
		'total_gold_docs': len(gold_docs),
		'pred_docs': len(pred_docs),
		'new_docs_added': 0,
		'docs_modified': 0,
		'new_entities_assigned': 0,
		'mode': mode,
		'dedup': dedup,
	}

	for pd in pred_docs:
		doc_id = pd.get('id')
		pred_entities_raw = pd.get('predicted_entities') or []
		if not pred_entities_raw:
			continue
		if doc_id not in idx:
			# 全新文档
			new_list = []
			for raw in pred_entities_raw:
				max_id += 1
				new_list.append(convert_pred(raw, max_id, keep_extra, add_source))
			stats['new_entities_assigned'] += len(new_list)
			gold_docs.append({
				'id': doc_id,
				'text': pd.get('text', ''),
				'entities': new_list
			})
			idx[doc_id] = gold_docs[-1]
			stats['new_docs_added'] += 1
			stats['docs_modified'] += 1
			continue

		doc = idx[doc_id]
		orig_entities = doc.get('entities') or []
		has_gold = len(orig_entities) > 0

		if mode in ('fill', 'skip') and has_gold:
			# fill/skip: 原有实体不动; fill 若空则继续添加逻辑
			if mode == 'skip':
				continue
			if mode == 'fill':
				# has_gold==True -> 跳过
				continue

		if mode == 'replace':
			orig_entities = []

		converted: List[Dict[str, Any]] = []
		for raw in pred_entities_raw:
			max_id += 1
			converted.append(convert_pred(raw, max_id, keep_extra, add_source))
		stats['new_entities_assigned'] += len(converted)

		if mode == 'replace':
			merged = converted
		else:  # append / fill (when empty)
			merged = dedup_merge(orig_entities, converted, dedup)

		before = len(doc.get('entities') or [])
		after = len(merged)
		if after != before:
			doc['entities'] = merged
			stats['docs_modified'] += 1

	stats['final_max_entity_id'] = max_id
	write_jsonl(output, gold_docs)
	return stats


def parse_args():
	ap = argparse.ArgumentParser(description='合并 gold 实体与预测实体 JSONL 文件。')
	ap.add_argument('--original', required=True, help='原始带实体标注的 all.jsonl')
	ap.add_argument('--pred', required=True, help='预测结果 predicted_unlabeled.jsonl')
	ap.add_argument('--output', required=True, help='输出文件')
	ap.add_argument('--mode', default='fill', choices=['fill', 'append', 'replace', 'skip'], help='合并策略')
	ap.add_argument('--dedup', default='span', choices=['span', 'text', 'none'], help='去重策略 (追加/填充时)')
	ap.add_argument('--keep-extra', action='store_true', help='保留预测实体 text/confidence 字段')
	ap.add_argument('--add-source', action='store_true', help='给实体增加 source 字段')
	ap.add_argument('--stats', help='可选: 统计信息输出 JSON')
	return ap.parse_args()


def main():
	args = parse_args()
	stats = merge(
		original=args.original,
		pred=args.pred,
		output=args.output,
		mode=args.mode,
		dedup=args.dedup,
		keep_extra=args.keep_extra,
		add_source=args.add_source,
	)
	print('[MERGE DONE]')
	for k, v in stats.items():
		print(f'{k}: {v}')
	if args.stats:
		with open(args.stats, 'w', encoding='utf-8') as f:
			json.dump(stats, f, ensure_ascii=False, indent=2)
		print(f'Stats saved -> {args.stats}')


if __name__ == '__main__':
	main()


