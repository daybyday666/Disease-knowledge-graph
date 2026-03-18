import csv
import json
from pathlib import Path
from typing import Dict, Any, Tuple

# 输入与输出路径
INPUT = Path('enriched_final.jsonl')
NODES_CSV = Path('nodes.csv')
RELS_CSV = Path('relations.csv')
REPORT = Path('neo4j_export_report.txt')

# 标签映射：实体 label -> 节点标签
NODE_LABEL_MAP = {
    '疾病': 'Disease',
    '症状': 'Symptom',
    '病因': 'Cause',
    '诊断方法': 'Diagnosis',
    '治疗': 'Treatment',
    '科室': 'Department'
}

# 关系 relation 字段已是英文语义，可直接作为 Neo4j 类型（大写）
# 若需转换可在此定义映射
REL_TYPE_MAP = {
    'has_symptom': 'HAS_SYMPTOM',
    'has_cause': 'HAS_CAUSE',
    'needs_diagnosis': 'NEEDS_DIAGNOSIS',
    'uses_treatment': 'USES_TREATMENT',
    'belongs_to_department': 'BELONGS_TO_DEPARTMENT'
}

# 去除可能的首尾空白
def norm_text(t: str) -> str:
    return (t or '').strip()

# 生成节点唯一 key：使用 (标签, 文本) 组合哈希；同时保持一个自增 ID 分配
class NodeIndexer:
    def __init__(self):
        self.index: Dict[Tuple[str, str], int] = {}
        self.next_id = 1

    def get_or_add(self, label: str, name: str) -> int:
        key = (label, name)
        if key in self.index:
            return self.index[key]
        nid = self.next_id
        self.next_id += 1
        self.index[key] = nid
        return nid


def export():
    if not INPUT.exists():
        raise FileNotFoundError(f'Input not found: {INPUT}')

    node_indexer = NodeIndexer()
    node_rows = []  # (id, name, label)
    rel_rows = []   # (start_id, end_id, type, doc_id)

    # 统计
    stats = { 'relations_total': 0 }
    rel_type_counter: Dict[str, int] = {}
    node_label_counter: Dict[str, int] = {}

    with INPUT.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            doc = json.loads(line)
            doc_id = doc.get('id')
            entities = doc.get('entities') or []
            # 建立一个span->(label,text) 辅助索引
            spans = {}
            text = doc.get('text','')
            for ent in entities:
                label = ent.get('label')
                if label not in NODE_LABEL_MAP:
                    continue
                start = ent.get('start_offset'); end = ent.get('end_offset')
                ent_text = norm_text(text[start:end]) if (isinstance(start,int) and isinstance(end,int)) else ''
                spans[(start,end,label,ent_text)] = (label, ent_text)
            # 关系
            for rel in doc.get('relations') or []:
                rtype_raw = rel.get('relation')
                rtype = REL_TYPE_MAP.get(rtype_raw)
                if not rtype:
                    continue
                head = norm_text(rel.get('head'))
                tail = norm_text(rel.get('tail'))
                # 推断 head/tail label: 需要通过 spans 或回退策略（遍历实体匹配文本）
                head_label = None
                tail_label = None
                # 先用 head_span / tail_span 精确定位
                h_span = rel.get('head_span'); t_span = rel.get('tail_span')
                if isinstance(h_span, list) and len(h_span)==2:
                    hs,he = h_span
                    # 扫描实体匹配这个 span
                    for ent in entities:
                        if ent.get('start_offset')==hs and ent.get('end_offset')==he:
                            lbl = ent.get('label');
                            if lbl in NODE_LABEL_MAP:
                                head_label = lbl; break
                if isinstance(t_span, list) and len(t_span)==2:
                    ts,te = t_span
                    for ent in entities:
                        if ent.get('start_offset')==ts and ent.get('end_offset')==te:
                            lbl = ent.get('label');
                            if lbl in NODE_LABEL_MAP:
                                tail_label = lbl; break
                # 如果仍未匹配，用文本匹配（首次命中即可）
                if head_label is None:
                    for ent in entities:
                        lbl = ent.get('label');
                        if lbl in NODE_LABEL_MAP:
                            start = ent.get('start_offset'); end = ent.get('end_offset')
                            etxt = norm_text(text[start:end]) if isinstance(start,int) and isinstance(end,int) else ''
                            if etxt == head:
                                head_label = lbl; break
                if tail_label is None:
                    for ent in entities:
                        lbl = ent.get('label');
                        if lbl in NODE_LABEL_MAP:
                            start = ent.get('start_offset'); end = ent.get('end_offset')
                            etxt = norm_text(text[start:end]) if isinstance(start,int) and isinstance(end,int) else ''
                            if etxt == tail:
                                tail_label = lbl; break
                # 若仍未知则跳过（保证类型完整性）
                if not head_label or not tail_label:
                    continue
                head_id = node_indexer.get_or_add(head_label, head)
                tail_id = node_indexer.get_or_add(tail_label, tail)
                rel_rows.append((head_id, tail_id, rtype, doc_id))
                stats['relations_total'] += 1
                rel_type_counter[rtype] = rel_type_counter.get(rtype,0)+1

    # 整理节点行
    for (label, name), nid in [((k[0], k[1]), v) for k,v in node_indexer.index.items()]:
        node_rows.append((nid, name, label))
        node_label_counter[label] = node_label_counter.get(label,0)+1

    # 写 CSV (Neo4j bulk import friendly headers)
    # nodes: id:ID,name,:LABEL
    with NODES_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['id:ID','name',':LABEL'])
        for nid, name, label in node_rows:
            w.writerow([nid, name, label])

    # relationships: :START_ID,:END_ID,:TYPE,doc_id:int
    with RELS_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([':START_ID',':END_ID',':TYPE','doc_id:INT'])
        for s,e,t,did in rel_rows:
            w.writerow([s,e,t,did])

    # 报告
    with REPORT.open('w', encoding='utf-8') as f:
        f.write('Neo4j Export Report\n')
        f.write(f'Nodes: {len(node_rows)}\n')
        f.write(f'Relations: {stats["relations_total"]}\n')
        f.write('\nNode label counts:\n')
        for k,v in sorted(node_label_counter.items()):
            f.write(f'  {k}: {v}\n')
        f.write('\nRelation type counts:\n')
        for k,v in sorted(rel_type_counter.items()):
            f.write(f'  {k}: {v}\n')
    print('导出完成')
    print('节点数:', len(node_rows))
    print('关系数:', stats['relations_total'])

if __name__ == '__main__':
    export()
