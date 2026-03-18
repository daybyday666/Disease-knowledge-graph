import re
import json
from pathlib import Path
from typing import List, Dict, Any

SOURCE = Path('merged_with_rel.jsonl')  # 先用 enriched 版本，避免丢失已有 relations
OUTPUT = Path('merged_with_rel_add_disease.jsonl')
REPORT = Path('added_disease_report.txt')

# 正则匹配：疾病名称：XXX。 允许全角冒号/半角冒号，结尾句号可选，停在第一个换行或句号。
PATTERNS = [
    re.compile(r'疾病名称[：:]\s*([^。\n；;，,]{1,40})'),  # 抓取疾病名主体（避免太长）
]

# 去除可能的尾部装饰字符
TRIM_CHARS = ' 。，,；;:：'


def read_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            yield json.loads(line)


def find_disease(text: str) -> List[str]:
    names = []
    for pat in PATTERNS:
        for m in pat.finditer(text):
            name = m.group(1).strip(TRIM_CHARS)
            # 排除明显非疾病词的简单启发：长度>=2，且不含空格/冒号
            if len(name) >= 2 and (' ' not in name):
                names.append(name)
    # 去重，保持顺序
    uniq = []
    seen = set()
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def entity_span_all(text: str, target: str):
    # 返回所有精确匹配 target 的起止下标（首次需求通常只用第一个即可）
    start = 0
    while True:
        idx = text.find(target, start)
        if idx == -1:
            break
        yield (idx, idx + len(target))
        start = idx + len(target)


def main():
    if not SOURCE.exists():
        print('Source file not found:', SOURCE)
        return

    added_docs = 0
    added_entities = 0
    updated = []

    for doc in read_jsonl(SOURCE):
        entities: List[Dict[str, Any]] = doc.get('entities') or []
        # 如果已经有疾病实体则跳过
        if any(e.get('label') == '疾病' for e in entities):
            updated.append(doc)
            continue

        text = doc.get('text', '')
        disease_names = find_disease(text)
        if not disease_names:
            updated.append(doc)
            continue

        # 给每个匹配疾病名创建实体（取第一个出现位置）
        modified = False
        for dn in disease_names:
            # 选择第一个 span
            spans = list(entity_span_all(text, dn))
            if not spans:
                continue
            start, end = spans[0]
            # 生成新的 id：避免冲突，取当前最大 id + 1（若没有则 1）
            existing_ids = [e.get('id', 0) for e in entities if isinstance(e.get('id'), int)]
            next_id = (max(existing_ids) + 1) if existing_ids else 1
            entities.append({
                'id': next_id,
                'label': '疾病',
                'start_offset': start,
                'end_offset': end
            })
            added_entities += 1
            modified = True
        if modified:
            added_docs += 1
        doc['entities'] = entities
        updated.append(doc)

    with OUTPUT.open('w', encoding='utf-8') as f:
        for d in updated:
            f.write(json.dumps(d, ensure_ascii=False) + '\n')

    with REPORT.open('w', encoding='utf-8') as f:
        f.write(f'新增疾病实体文档数: {added_docs}\n')
        f.write(f'新增疾病实体总数: {added_entities}\n')

    print('完成:')
    print('  新增疾病实体文档数:', added_docs)
    print('  新增疾病实体总数:', added_entities)
    print('输出文件:', OUTPUT)
    print('报告文件:', REPORT)


if __name__ == '__main__':
    main()
