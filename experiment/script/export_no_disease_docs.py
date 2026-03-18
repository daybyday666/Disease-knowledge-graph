import json
from pathlib import Path

ENRICHED = Path('merged_with_rel.jsonl')
OUT_IDS = Path('no_disease_ids.txt')
OUT_JSONL = Path('no_disease_docs.jsonl')

REL_MAP_LABELS = {'症状','病因','诊断方法','治疗','科室'}

def read_jsonl(p: Path):
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)

def main():
    if not ENRICHED.exists():
        print('missing file', ENRICHED)
        return
    ids = []
    docs = []
    for doc in read_jsonl(ENRICHED):
        relations = doc.get('relations') or []
        if relations:  # 只挑完全没有关系的文档
            continue
        entities = doc.get('entities') or []
        labels = [e.get('label') for e in entities]
        has_disease = any(l == '疾病' for l in labels)
        has_other = any(l in REL_MAP_LABELS for l in labels if l != '疾病')
        if (not has_disease) and has_other:
            ids.append(doc.get('id'))
            docs.append(doc)
    # 排序保证稳定
    ids_sorted = sorted(ids)
    with OUT_IDS.open('w', encoding='utf-8') as f:
        for i in ids_sorted:
            f.write(str(i)+'\n')
    with OUT_JSONL.open('w', encoding='utf-8') as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False)+'\n')
    print(f'导出文档数: {len(docs)} -> {OUT_JSONL}')
    print(f'ID 列表写入: {OUT_IDS}')
    print('前10个ID:', ids_sorted[:10])

if __name__ == '__main__':
    main()
