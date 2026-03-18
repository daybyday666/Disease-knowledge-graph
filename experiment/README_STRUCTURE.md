# 项目目录结构说明

为了保持项目整洁，文件已被重新组织到以下目录中：

## 📁 data/
存放所有数据文件。
- **raw/**: 包含爬虫获取的原始 CSV 数据 (原 `crawler/*.csv`)。
- **processed/**: 存放处理后的数据 (原 `data/` 下的文件保持不变)。

## 📁 crawler/
存放数据爬虫相关的 Python 脚本。
- `data_get.py`, `dxy_crawler.py`

## 📁 script/
存放主要的项目源代码，包括模型训练、数据处理和推理脚本。
*(文件位置保持不变以确保代码运行正常)*

## 📁 results/
存放所有运行结果、指标和图表。
- **metrics/**: 存放模型评估指标 (CSV, JSONL)。
    - `old_20251011/`: 归档的原根目录下的旧指标文件。
- **plots/**: 存放生成的图表 (PNG)。
- **reports/**: 存放导出报告 (如 `neo4j_export_report.txt`)。
- **final_output/**: 存放最终输出文件 (如 `enriched_final.jsonl`)。
- **relation_cls/**: 关系分类相关的指标和结果。

## 根目录文件
- `README.md`
- `requirements.txt`
