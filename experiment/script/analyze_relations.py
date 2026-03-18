import json
from collections import Counter, defaultdict
from pathlib import Path

INPUT = Path('merged.jsonl')  # 原始输入文件（未加关系）
ENRICHED = Path('merged_with_rel.jsonl')  # 已加关系文件

# 需要的标签映射，与 relationship.py 保持一致
REL_MAP = {
    '症状': 'has_symptom',
    '病因': 'has_cause',
    '诊断方法': 'needs_diagnosis',
    '治疗': 'uses_treatment',
    '科室': 'belongs_to_department'
}


def read_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    if not ENRICHED.exists():
        print(f"File not found: {ENRICHED}")
        return

    stats_counter = Counter()
    doc_reasons = defaultdict(list)

    total_docs = 0
    no_relation_docs = []

    for doc in read_jsonl(ENRICHED):
        total_docs += 1
        relations = doc.get('relations') or []
        entities = doc.get('entities') or []
        labels = [e.get('label') for e in entities]
        has_disease = any(l == '疾病' for l in labels)
        has_other = any(l in REL_MAP for l in labels if l != '疾病')

        if relations:
            continue  # 已有关系，无需分析缺失

        no_relation_docs.append(doc.get('id'))
        if not has_disease and not has_other:
            stats_counter['无疾病且无其它相关标签'] += 1
            doc_reasons['无疾病且无其它相关标签'].append(doc.get('id'))
        elif not has_disease and has_other:
            stats_counter['有其它标签但无疾病'] += 1
            doc_reasons['有其它标签但无疾病'].append(doc.get('id'))
        elif has_disease and not has_other:
            stats_counter['只有疾病无可配对标签'] += 1
            doc_reasons['只有疾病无可配对标签'].append(doc.get('id'))
        else:
            # 理论上不会发生，如果发生表示逻辑或数据异常
            stats_counter['未知原因'] += 1
            doc_reasons['未知原因'].append(doc.get('id'))

    print('=== 缺少关系文档诊断报告 ===')
    print(f'总文档数: {total_docs}')
    print(f'无任何关系的文档数: {len(no_relation_docs)}')
    if no_relation_docs:
        print('分类统计:')
        for k, v in stats_counter.items():
            print(f'  {k}: {v}')

        # 展示每类前若干示例
        print('\n示例文档ID (每类至多前10个):')
        for k, ids in doc_reasons.items():
            print(f'  {k}: {ids[:10]}')
    else:
        print('所有文档均已生成至少一条关系。')

    # 进一步提示
    print('\n可能的后续改进方向:')
    print('- 检查无疾病实体的文档是否应标注疾病（标注遗漏）。')
    print('- 对只有疾病的文档，可考虑是否遗漏症状/病因等实体标注。')
    print('- 如果确实只有一种实体类型，则规则生成无法构建关系，可考虑跨文档或外部知识补全。')


if __name__ == '__main__':
    main()
