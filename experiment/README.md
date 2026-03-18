## NER (BiLSTM-CRF) 训练流程

步骤:
1. 生成 BIO 数据
	- 运行 `python BIO.py` 读取 `all.jsonl` -> 按文档(疾病条目) 随机划分 40 个文档为训练、10 个文档为验证；每个文档内部再句子切分写入 BIO；不足 50 文档会用无实体或复制补齐（仅演示用途）。
2. 训练模型
	- 运行 `python train.py` 进行 30 epoch 训练 (含早停, 监控验证 F1)。

文件说明:
| 文件 | 说明 |
|------|------|
| BIO.py | 标注转换脚本，输出 train.bio / dev.bio |
| dataset.py | 读取 BIO 数据、构建词表、数据集、批处理填充 |
| model.py | BiLSTM-CRF 模型与 CRF 实现 |
| train.py | 训练 & 验证 & 指标与早停 |
| bert_crf_model.py | BERT + CRF 模型，支持冻结 embedding / 前 N 层 |
| bert_train.py | BERT-CRF 训练脚本 (实体级/Token级指标, 早停, 可视化) |
| infer_unlabeled.py | 使用已训练 BERT-CRF 对 all.jsonl 中未人工标注文档自动标注并输出 |

依赖 (CPU 可运行):
```
pip install torch>=2.0 transformers accelerate
```

运行示例 (Windows PowerShell):
```
python .\BIO.py
python .\train.py
```
BERT-CRF 训练示例:
```
python .\bert_train.py --epochs 8 --batch-size 8 --lr 2e-5 --strict-bio --freeze-emb --freeze-layers 2 --patience 3
```

输出:
```
train.bio / dev.bio        # 数据集
char_vocab.txt / tag_vocab.txt
best_model.pt              # BiLSTM-CRF 最优参数
best_bert_crf.pt           # BERT-CRF 最优参数
bert_metrics.csv / bert_metrics.jsonl / bert_metrics.png
```

指标: 采用实体级 (BIO 片段) 微平均 Precision / Recall / F1；同时记录 token 级指标。

过拟合监控: BERT 版本使用实体 F1 触发早停 (默认 patience=3)。

---
### 推理: 自动标注未标注文档
脚本: `infer_unlabeled.py`

功能:
* 读取 `all.jsonl`，跳过已有 `entities` 的文档，对其余文档进行预测。
* 输出文件包含新增字段 `predicted_entities`，每个实体含: `label, start_offset, end_offset, text, confidence(None)`。
* 支持跨文档全局去重 (`--global-dedup` 按 (label,text) 去重) 与单文档内部去重 (默认按 (label,start,end,text))。

使用前提:
* 已有 `train.bio` / `dev.bio`（用于重建标签表）
* 已训练好的 `best_bert_crf.pt` 模型参数

示例:
```
python .\infer_unlabeled.py --model best_bert_crf.pt --pretrained bert-base-chinese \
    --input all.jsonl --output predicted_unlabeled.jsonl --max-len 256 --strict-bio --global-dedup
```
参数说明:
* `--model`: 训练保存的 BERT-CRF state_dict (默认 best_bert_crf.pt)
* `--pretrained`: 与训练一致的预训练模型名 / 路径
* `--max-len`: 单批最大序列长度 (含 [CLS] [SEP])
* `--strict-bio` / `--enforce-bio`: 与训练一致的 CRF 约束方式 (建议只开 `--strict-bio`)
* `--global-dedup`: 额外进行跨文档 (label,text) 去重

置信度: 当前未计算 Viterbi 路径概率，保留 `confidence: None` 占位；后续可在 CRF decode 后加路径得分归一化或 token 概率聚合。

---
### 后续可改进
* CRF decode 置信度/路径得分输出。
* 子词层面对非首子词标签的 mask 处理 (忽略 loss)。
* 学习率 warmup + 余弦退火。
* 梯度累积与混合精度 (AMP)。
* 数据自动增广（同义词替换 / 实体 dropout）。
* per-type F1 在 BERT 训练阶段统计输出。

