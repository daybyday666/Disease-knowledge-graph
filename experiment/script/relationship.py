#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""根据 merged.jsonl 中的实体自动补全关系。

支持关系:
  has_symptom            <疾病, has_symptom, 症状>
  has_cause              <疾病, has_cause, 病因>
  needs_diagnosis        <疾病, needs_diagnosis, 诊断方法>
  uses_treatment         <疾病, uses_treatment, 治疗>
  belongs_to_department  <疾病, belongs_to_department, 科室>

默认逻辑: 在同一文档中, 所有 label=疾病 的实体, 分别与其它标签实体组合生成对应关系。
若一个实体跨度完全相同且 label=疾病 与 另一疾病标签重叠不重复, 不进行疾病→疾病 关系。

去重: 基于 (head_text, relation, tail_text)。可选 span 去重模式基于 (head_start,head_end,tail_start,tail_end,relation) (--dedup span)。

输出:
  1) 直接更新文档的 relations 字段 (若存在则追加/去重) 写入新文件
  2) 可选 --triples-only 生成单独三元组文件 (每行 JSON: {head, relation, tail, doc_id})

使用示例:
  python relationship.py --input merged.jsonl --output merged_with_rel.jsonl --dedup text --triples triples.jsonl

"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set

RELATION_MAP = {
	'症状': 'has_symptom',
	'病因': 'has_cause',
	'诊断方法': 'needs_diagnosis',
	'治疗': 'uses_treatment',
	'科室': 'belongs_to_department',
}

DiseaseLabel = '疾病'


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
	data: List[Dict[str, Any]] = []
	with open(path, 'r', encoding='utf-8') as f:
		for line in f:
			line = line.strip()
			if not line:
				continue
			try:
				data.append(json.loads(line))
			except json.JSONDecodeError as e:
				raise ValueError(f'解析失败 {path}: {e}')
	return data


def write_jsonl(path: str | Path, data: List[Dict[str, Any]]):
	with open(path, 'w', encoding='utf-8') as f:
		for obj in data:
			f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def extract_text(doc_text: str, ent: Dict[str, Any]) -> str:
	# 如果实体已有 text 字段优先使用; 否则用 offset 切片
	if 'text' in ent and ent['text'] is not None:
		return ent['text']
	start = ent.get('start_offset')
	end = ent.get('end_offset')
	if isinstance(start, int) and isinstance(end, int):
		return doc_text[start:end]
	return ''


def make_relations_for_doc(doc: Dict[str, Any], dedup: str) -> List[Dict[str, Any]]:
	text = doc.get('text', '')
	entities = doc.get('entities') or []
	diseases = [e for e in entities if e.get('label') == DiseaseLabel]
	others = [e for e in entities if e.get('label') != DiseaseLabel]

	triples: List[Dict[str, Any]] = []
	seen: Set[Tuple[Any, ...]] = set()

	for d in diseases:
		d_text = extract_text(text, d)
		d_span = (d.get('start_offset'), d.get('end_offset'))
		for o in others:
			o_label = o.get('label')
			rel = RELATION_MAP.get(o_label)
			if not rel:
				continue
			o_text = extract_text(text, o)
			o_span = (o.get('start_offset'), o.get('end_offset'))
			if dedup == 'span':
				key = (d_span[0], d_span[1], o_span[0], o_span[1], rel)
			else:  # text
				key = (d_text, rel, o_text)
			if key in seen:
				continue
			seen.add(key)
			triples.append({
				'head': d_text,
				'relation': rel,
				'tail': o_text,
				'head_span': d_span,
				'tail_span': o_span,
			})
	return triples


def merge_relations_field(doc: Dict[str, Any], new_triples: List[Dict[str, Any]], dedup: str):
	existing = doc.get('relations') or []
	out = []
	seen: Set[Tuple[Any, ...]] = set()

	def key_of(t: Dict[str, Any]) -> Tuple[Any, ...]:
		if dedup == 'span':
			return (t.get('head_span', (None, None))[0], t.get('head_span', (None, None))[1],
					t.get('tail_span', (None, None))[0], t.get('tail_span', (None, None))[1], t.get('relation'))
		return (t.get('head'), t.get('relation'), t.get('tail'))

	for t in existing:
		k = key_of(t)
		if k in seen:
			continue
		seen.add(k)
		out.append(t)
	for t in new_triples:
		k = key_of(t)
		if k in seen:
			continue
		seen.add(k)
		out.append(t)
	doc['relations'] = out


def process(
	input_path: str | Path,
	output_path: str | Path,
	dedup: str = 'text',
	triples_only: str | None = None,
	verbose: bool = False,
) -> Dict[str, Any]:
	docs = read_jsonl(input_path)
	total_new = 0
	total_docs_with_new = 0
	all_triples: List[Dict[str, Any]] = []

	for doc in docs:
		triples = make_relations_for_doc(doc, dedup=dedup)
		before = len(doc.get('relations') or [])
		if triples:
			merge_relations_field(doc, triples, dedup=dedup)
		after = len(doc.get('relations') or [])
		added = after - before
		if added > 0:
			total_new += added
			total_docs_with_new += 1
		for t in triples:
			t_out = {
				'doc_id': doc.get('id'),
				'head': t['head'],
				'relation': t['relation'],
				'tail': t['tail'],
			}
			all_triples.append(t_out)
		if verbose and added > 0:
			print(f"doc {doc.get('id')} +{added} relations")

	write_jsonl(output_path, docs)
	if triples_only:
		write_jsonl(triples_only, all_triples)

	stats = {
		'docs': len(docs),
		'docs_with_new_relations': total_docs_with_new,
		'new_relations_added': total_new,
		'total_relations_after': sum(len(d.get('relations') or []) for d in docs),
		'dedup': dedup,
	}
	return stats


def parse_args():
	ap = argparse.ArgumentParser(description='根据实体自动补全疾病相关关系')
	ap.add_argument('--input', required=True, help='输入 merged.jsonl')
	ap.add_argument('--output', required=True, help='输出补全关系后的文件')
	ap.add_argument('--dedup', default='text', choices=['text', 'span'], help='关系去重维度')
	ap.add_argument('--triples', help='可选：另存所有三元组 JSONL')
	ap.add_argument('--verbose', action='store_true', help='打印新增统计')
	return ap.parse_args()


def main():
	args = parse_args()
	stats = process(
		input_path=args.input,
		output_path=args.output,
		dedup=args.dedup,
		triples_only=args.triples,
		verbose=args.verbose,
	)
	print('[RELATION COMPLETION DONE]')
	for k, v in stats.items():
		print(f'{k}: {v}')


if __name__ == '__main__':
	main()

