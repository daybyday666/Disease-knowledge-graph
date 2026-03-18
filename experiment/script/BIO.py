import json
import os
import random
from typing import List, Tuple

"""BIO 标注与数据集划分脚本（核心数据处理）

功能 (按“文档(疾病)”而非句子划分训练/验证):
1. 从 all.jsonl 读取文档列表(每条为一个疾病条目)，收集含实体文档与其文本+实体。
2. 以“文档”为划分单位：随机选 40 个文档为训练，10 个文档为验证；若不足 50：按 80% / 20% （验证至少 5）划分。
3. 对每个文档内部再做句子分割并生成句子级 BIO 行；同一文档的所有句子整体进入同一集合(不拆跨 dataset)。
4. 若含实体文档不足 50 条，允许补充无实体文档；仍不足则复制已有文档以凑数量（仅演示用途）。
5. 输出 train.bio / dev.bio （句子之间空行，文档之间额外再空一行，字符<空格>标签）。

假设输入编码为 UTF-8。
"""

SENT_ENDERS = set("。！？!?\n")


def read_jsonl(path: str):
	with open(path, encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line:
				continue
			try:
				yield json.loads(line)
			except json.JSONDecodeError:
				continue


def collect_docs(jsonl_path: str):
	"""读取 JSONL 文档，清洗实体边界，划分为有实体/无实体两组。"""
	annotated = []
	plain = []
	for obj in read_jsonl(jsonl_path):
		text = obj.get("text", "")
		entities = obj.get("entities", []) or []
		cleaned = []
		for e in entities:
			try:
				start = int(e.get("start_offset"))
				end = int(e.get("end_offset"))
				label = str(e.get("label"))
			except Exception:
				continue
			if 0 <= start < end <= len(text):
				cleaned.append((start, end, label))
		record = {"text": text, "entities": cleaned}
		if cleaned:
			annotated.append(record)
		else:
			plain.append(record)
	return annotated, plain


def build_char_labels(text: str, entities: List[Tuple[int, int, str]]):
	"""将实体 span 转为逐字符 BIO 标签。"""
	labels = ["O"] * len(text)
	for start, end, label in entities:
		if start >= end:
			continue
		labels[start] = f"B-{label}"
		for i in range(start + 1, end):
			labels[i] = f"I-{label}"
	return labels


def sentence_segments(text: str) -> List[Tuple[int, int]]:
	"""返回句子 (start, end) 切分 (end 为开区间)."""
	spans = []
	start = 0
	for i, ch in enumerate(text):
		if ch in SENT_ENDERS:
			end = i + 1
			if end - start > 1:  # 非空白句
				spans.append((start, end))
			start = end
	# 末尾残余
	if start < len(text) and len(text) - start > 1:
		spans.append((start, len(text)))
	return spans


def slice_to_sentences(doc):
	"""将文档拆为句子，并切片对应的 BIO 标签。"""
	text = doc["text"]
	ent_spans = doc["entities"]  # list of (s,e,label)
	char_labels = build_char_labels(text, ent_spans)
	sents = []
	for s, e in sentence_segments(text):
		sent_text = text[s:e]
		sent_labels = char_labels[s:e]
		# 去掉纯空白
		if not sent_text.strip():
			continue
		sents.append((sent_text, sent_labels))
	return sents


def ensure_min_docs(docs: List[dict], fallback_plain: List[dict], min_required=50):
	"""当含实体文档不足时，用无实体文档补齐，仍不足则复制（仅演示用途）。"""
	# docs: 仅含实体的文档；fallback_plain: 无实体文档候选
	out = list(docs)
	# 先补无实体
	for p in fallback_plain:
		if len(out) >= min_required:
			break
		out.append(p)
	# 仍不足则复制（演示用途）
	idx = 0
	while len(out) < min_required and out:
		out.append(out[idx % len(out)])
		idx += 1
	return out


def split_docs(docs: List[dict]):
	"""按文档划分训练/验证，满足固定数量或 80/20（验证至少 5）。"""
	n = len(docs)
	if n >= 50:
		train_n, dev_n = 40, 10
	else:
		dev_n = max(5, int(round(n * 0.2)))
		train_n = n - dev_n
	random.shuffle(docs)
	return docs[:train_n], docs[train_n:train_n+dev_n]


def write_bio_docs(path: str, docs_with_sentences):
	"""将句子级 BIO 写入 .bio 文件。句间空行，文档间额外空行。"""
	with open(path, 'w', encoding='utf-8') as f:
		for doc_sents in docs_with_sentences:  # list[(sent_text, labels)] for one doc
			for sent, labels in doc_sents:
				for ch, lab in zip(sent, labels):
					if ch.strip() == "":
						continue
					f.write(f"{ch} {lab}\n")
				f.write("\n")  # 句子间空行
			f.write("\n")      # 文档间再空一行


def main():
	base = os.path.dirname(os.path.abspath(__file__))
	jsonl_path = os.path.join(base, "all.jsonl")
	if not os.path.exists(jsonl_path):
		print("未找到 all.jsonl")
		return
	annotated, plain = collect_docs(jsonl_path)
	# 补足文档数
	final_docs = ensure_min_docs(annotated, plain, 50)
	train_docs, dev_docs = split_docs(final_docs)
	# 展开为句子
	def docs_to_sentlists(docs_list):
		out = []
		for d in docs_list:
			sents = slice_to_sentences(d)
			if not sents:
				# 文档全空白回退
				text = d["text"]
				labels = build_char_labels(text, d["entities"]) if text else []
				if text:
					out.append([(text, labels)])
			else:
				out.append(sents)
		return out
	train_sent_docs = docs_to_sentlists(train_docs)
	dev_sent_docs = docs_to_sentlists(dev_docs)
	write_bio_docs(os.path.join(base, 'train.bio'), train_sent_docs)
	write_bio_docs(os.path.join(base, 'dev.bio'), dev_sent_docs)
	print(f"按文档划分: 训练文档 {len(train_docs)} 验证文档 {len(dev_docs)} (总文档 {len(final_docs)})")


if __name__ == "__main__":
	main()

