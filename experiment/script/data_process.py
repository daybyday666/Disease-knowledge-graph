"""数据处理（核心预处理脚本）

涵盖两类核心处理：
1) merge_csvs_to_txt: 将 5 个抓取得到的 CSV（简介/病因/症状/诊断/治疗）按疾病名合并成一行文本，便于下游标注/训练；
2) csv_to_jsonl/batch_process: 将单个 CSV 转为 Doccano 兼容 JSONL（text + meta），支持术语归一化。

约定：脚本与数据位于同一目录（script/），输入编码默认 UTF-8 或 UTF-8-SIG。
"""

import csv
import json
import os

def merge_csvs_to_txt():
	"""将五个 CSV 文件整合为一个 TXT，每行一个疾病的整合段落。

	输出格式类似：
	疾病名称：<name>。简介：...。病因：...。症状：...。诊断：...。治疗：...。
	- 以 disease_kg.csv 的疾病名为主集合，保证行覆盖；
	- 对缺失的字段仅跳过，不报错；
	- 字段内换行与多空格会被清洗为单空格。
	"""
	import collections
	base_dir = os.path.dirname(os.path.abspath(__file__))
	files = [
		("disease_dxy_intro.csv", "简介"),
		("disease_dxy_cause.csv", "病因"),
		("disease_dxy_symptom.csv", "症状"),
		("disease_dxy_diagnosis.csv", "诊断"),
		("disease_dxy_treatment.csv", "治疗"),
	]
	# 以 disease_kg.csv 为主，保证所有疾病都输出
	kg_path = os.path.join(base_dir, "disease_kg.csv")
	kg_names = []
	with open(kg_path, encoding="utf-8-sig") as f:
		for row in csv.reader(f):
			if row and row[0]:
				kg_names.append(row[0].strip())

	# 读取所有 CSV 内容，构建 {疾病名: {字段: 文本}}
	disease_info = {name: {} for name in kg_names}
	csv_disease_sets = {}  # {csv_file: set(疾病名)}
	for csv_file, field in files:
		csv_path = os.path.join(base_dir, csv_file)
		disease_set = set()
		if not os.path.exists(csv_path):
			print(f"跳过 {csv_file}，文件不存在")
			csv_disease_sets[csv_file] = disease_set
			continue
		with open(csv_path, encoding="utf-8-sig") as f:
			reader = csv.DictReader(f)
			for row in reader:
				name = row.get("疾病名称", "").strip()
				value = row.get(field, "").strip()
				if name in disease_info:
					disease_info[name][field] = value
					disease_set.add(name)
		csv_disease_sets[csv_file] = disease_set

	# 检查每个疾病在哪些 CSV 缺失，打印提示以便补抓或人工核对
	for disease in kg_names:
		missing = []
		for csv_file, (_, field) in zip(csv_disease_sets.keys(), files):
			if disease not in csv_disease_sets[csv_file]:
				missing.append(f"{csv_file}({field})")
		if missing:
			print(f"[缺失] 疾病：{disease} 在以下文件缺失：{', '.join(missing)}")
	# 写入合并后的 TXT，一行一个疾病
	txt_path = os.path.join(base_dir, "disease_merged.txt")
	def clean_text(text):
		# 去除属性内容中的所有回车和换行，替换为一个空格
		return text.replace('\r', ' ').replace('\n', ' ').replace('  ', ' ').strip() if text else ''

	with open(txt_path, "w", encoding="utf-8") as fout:
		for name in kg_names:
			info = disease_info.get(name, {})
			line = f"疾病名称：{name}。"
			for field in ["简介", "病因", "症状", "诊断", "治疗"]:
				val = info.get(field, '')
				if val:
					line += f"{field}：{clean_text(val)}。"
			fout.write(line + "\n")
	print(f"已生成整合文本：{txt_path}")
if __name__ == "__main__":
	# batch_process()  # 如需批量处理jsonl可取消注释
	merge_csvs_to_txt()
# -*- coding: utf-8 -*-


# 1. 术语映射表，可根据实际需求扩展
TERM_MAP = {
	"心梗": "心肌梗死",
	"高血压病": "高血压",
}

def replace_terms(text, term_map):
	"""批量替换文本中的非标准术语为标准术语（简单 string 替换）。"""
	for k, v in term_map.items():
		text = text.replace(k, v)
	return text

def normalize_text(text):
	"""将字段内的换行替换为 \n，去除首尾空白，便于 JSON 序列化与标注工具展示。"""
	if text is None:
		return ""
	return text.strip().replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n')

def csv_to_jsonl(csv_path, text_col, meta_cols, term_map, jsonl_path):
	"""将 CSV 文件转换为 Doccano 支持的 JSONL 格式。

	参数：
	- csv_path: 输入 CSV 路径；
	- text_col: 作为正文的列名（例如“简介”）；
	- meta_cols: 作为 meta 的列名列表（例如 ["疾病名称"]）；
	- term_map: 术语归一化映射表；
	- jsonl_path: 输出 JSONL 路径。
	"""
	with open(csv_path, encoding="utf-8-sig") as f:
		try:
			reader = csv.DictReader(f)
			with open(jsonl_path, "w", encoding="utf-8") as fout:
				for idx, row in enumerate(reader, 1):
					try:
						text = row.get(text_col, "")
						text = replace_terms(text, term_map)
						text = normalize_text(text)
						meta = {k: normalize_text(row.get(k, "")) for k in meta_cols}
						obj = {"text": text, "meta": meta}
						fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
					except Exception as e:
						print(f"[WARN] 第{idx}行处理异常，已跳过：{e}")
		except Exception as e:
			print(f"[ERROR] 读取csv文件时发生异常：{e}")

def batch_process():
	"""批量处理 5 个 CSV，分别生成 JSONL，便于导入 Doccano 进行标注。"""
	base_dir = os.path.dirname(os.path.abspath(__file__))
	files = [
		("disease_dxy_intro.csv", "简介", ["疾病名称"], "disease_dxy_intro.jsonl"),
		("disease_dxy_cause.csv", "病因", ["疾病名称"], "disease_dxy_cause.jsonl"),
		("disease_dxy_symptom.csv", "症状", ["疾病名称"], "disease_dxy_symptom.jsonl"),
		("disease_dxy_diagnosis.csv", "诊断", ["疾病名称"], "disease_dxy_diagnosis.jsonl"),
		("disease_dxy_treatment.csv", "治疗", ["疾病名称"], "disease_dxy_treatment.jsonl"),
	]
	for csv_file, text_col, meta_cols, jsonl_file in files:
		csv_path = os.path.join(base_dir, csv_file)
		jsonl_path = os.path.join(base_dir, jsonl_file)
		if os.path.exists(csv_path):
			print(f"处理 {csv_file} ...")
			csv_to_jsonl(csv_path, text_col, meta_cols, TERM_MAP, jsonl_path)
		else:
			print(f"跳过 {csv_file}，文件不存在")

