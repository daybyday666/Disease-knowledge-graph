import csv
import sys
from pathlib import Path
from typing import Dict, Any, List
from neo4j import GraphDatabase, basic_auth

# ============= 用户需确认的配置 =============
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"
# 目标数据库名称（Neo4j Enterprise 多库才支持自定义；Community 版只有 neo4j 一个库，指定其它会被忽略或报错）
DATABASE_NAME = "neo4j"  # 修改为你期望的库名；若是社区版仍只能写入 neo4j 默认库

NODES_CSV = Path(r"data/nodes.csv")
RELS_CSV = Path(r"data/relations.csv")

CLEAR_BEFORE_IMPORT = False

# 读取 nodes.csv -> [{id, name, label}]
def load_nodes(path: Path):
    nodes = []
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        required = { 'id:ID', 'name', ':LABEL' }
        if not required.issubset(reader.fieldnames):
            raise ValueError(f"Nodes CSV 缺少必要列: {required}")
        for row in reader:
            try:
                nid = int(row['id:ID'])
            except ValueError:
                continue
            nodes.append({
                'id': nid,
                'name': row['name'].strip(),
                'label': row[':LABEL'].strip()
            })
    return nodes

# 读取 relations.csv -> [{start_id,end_id,type,doc_id}]
def load_rels(path: Path):
    rels = []
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        required = { ':START_ID', ':END_ID', ':TYPE', 'doc_id:INT' }
        if not required.issubset(reader.fieldnames):
            raise ValueError(f"Relations CSV 缺少必要列: {required}")
        for row in reader:
            try:
                s = int(row[':START_ID']); e = int(row[':END_ID'])
            except ValueError:
                continue
            doc_id_val = row.get('doc_id:INT', '')
            try:
                doc_id = int(doc_id_val) if doc_id_val != '' else None
            except ValueError:
                doc_id = None
            rels.append({
                's': s,
                'e': e,
                'type': row[':TYPE'].strip(),
                'doc_id': doc_id
            })
    return rels


def main():
    if not NODES_CSV.exists() or not RELS_CSV.exists():
        print("❌ 找不到 nodes.csv 或 relations.csv，请确认路径。")
        sys.exit(1)

    print("📥 读取 CSV ...")
    nodes = load_nodes(NODES_CSV)
    rels = load_rels(RELS_CSV)
    print(f"  节点记录: {len(nodes)} 条")
    print(f"  关系记录: {len(rels)} 条")

    # 连接 Neo4j
    print("🔌 连接 Neo4j ...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

    # 如果使用 Enterprise 并且当前不在默认库，可以尝试检测库是否存在；社区版会抛错（忽略即可）
    def get_edition() -> str:
        try:
            with driver.session(database="system") as sys_sess:
                rec = sys_sess.run("CALL dbms.components() YIELD edition RETURN edition LIMIT 1").single()
                return rec[0] if rec else "unknown"
        except Exception:
            return "unknown"

    def list_databases() -> List[str]:
        try:
            with driver.session(database="system") as sys_sess:
                return [r[0] for r in sys_sess.run("SHOW DATABASES YIELD name RETURN name").records()]
        except Exception:
            return []

    def database_exists(dbname: str) -> bool:
        try:
            with driver.session(database="system") as sys_sess:
                res = sys_sess.run("SHOW DATABASES YIELD name WHERE name = $n RETURN name", n=dbname)
                return res.single() is not None
        except Exception:
            return False  # 社区版或旧版本不支持 SHOW DATABASES

    edition = get_edition()
    existing_dbs = list_databases()
    if edition != "unknown":
        print(f"ℹ️ 检测到 Neo4j Edition: {edition}; 可用数据库: {existing_dbs or '未能获取'}")
    else:
        print("ℹ️ 未能检测到版本/Edition (可能是较旧版本或无 system DB 访问权限)")

    import time
    if DATABASE_NAME not in ("neo4j", "system") and not database_exists(DATABASE_NAME):
        try:
            with driver.session(database="system") as sys_sess:
                sys_sess.run(f"CREATE DATABASE `{DATABASE_NAME}` IF NOT EXISTS")
                print(f"🆕 已尝试创建数据库: {DATABASE_NAME}")
            # 轮询等待数据库 ONLINE
            for attempt in range(10):
                time.sleep(0.5)
                if database_exists(DATABASE_NAME):
                    break
            if not database_exists(DATABASE_NAME):
                print(f"⚠️ 数据库 {DATABASE_NAME} 在等待后仍不可见，回退 neo4j")
                DATABASE_IN_USE = "neo4j"
            else:
                DATABASE_IN_USE = DATABASE_NAME
        except Exception as e:
            print(f"⚠️ 创建数据库 {DATABASE_NAME} 失败/不支持：{e}")
            print("➡️ 回退使用默认库 neo4j")
            DATABASE_IN_USE = "neo4j"
    else:
        DATABASE_IN_USE = DATABASE_NAME if DATABASE_NAME != "system" else "neo4j"
        if DATABASE_NAME == "neo4j":
            print("ℹ️ 使用默认数据库 neo4j")
        else:
            print(f"✔️ 将使用已存在数据库: {DATABASE_NAME}")

    # 使用 session 操作数据库
    try:
        try:
            session = driver.session(database=DATABASE_IN_USE)
        except Exception as e:
            print(f"⚠️ 打开数据库 {DATABASE_IN_USE} 会话失败: {e}; 回退 neo4j")
            DATABASE_IN_USE = "neo4j"
            session = driver.session(database=DATABASE_IN_USE)
        with session as session:
            if CLEAR_BEFORE_IMPORT:
                confirm = input('⚠️ 确认删除当前数据库所有节点与关系? 输入 y 继续: ')
                if confirm.lower() == 'y':
                    session.run('MATCH (n) DETACH DELETE n')
                    print('  已清空原有图数据')
                else:
                    print('  跳过清空')

            # 约束: 每个标签单独对 name 建唯一约束 (可选)。这里只做一次尝试忽略错误
            labels = sorted(set(n['label'] for n in nodes))
            for lbl in labels:
                cypher_constraint = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:`{lbl}`) REQUIRE n.name IS UNIQUE"  # Neo4j 4.x+/5.x 语法
                session.run(cypher_constraint)

            # 导入节点（分批）
            BATCH = 1000
            print("🚀 导入节点 ...")
            for i in range(0, len(nodes), BATCH):
                batch = nodes[i:i+BATCH]
                # 对应标签不同 -> 使用 apoc 动态创建或拆分 by label。这里拆分：按 label 分组后写入
                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for n in batch:
                    grouped.setdefault(n['label'], []).append(n)
                for lbl, rows in grouped.items():
                    session.run(
                        f"UNWIND $rows AS row MERGE (n:`{lbl}` {{name: row.name}}) SET n.internalId=row.id",
                        rows=rows
                    )
            print("  节点导入完成")

            # 为 internalId 建索引（需指定标签，否则语法错误）。
            # 这里给所有出现过的标签建立一个索引，或使用通用标签方案。Neo4j 5 语法: CREATE INDEX name IF NOT EXISTS FOR (n:Label) ON (n.prop)
            for lbl in labels:
                index_name = f"idx_{lbl}_internalId".replace('-', '_')
                session.run(f"CREATE INDEX {index_name} IF NOT EXISTS FOR (n:`{lbl}`) ON (n.internalId)")

            # 构建 id->label 映射以加速匹配（在 Python 侧）
            id_to_label = { n['id']: n['label'] for n in nodes }

            # 导入关系（分批）
            print("🔗 导入关系 ...")
            rel_batch = []
            BATCH_REL = 2000
            def flush_rel(batch_rows):
                if not batch_rows:
                    return
                # 由于 start / end 标签不一定相同，这里使用内部 id 匹配；按关系类型拆分批量 MERGE
                # 因为类型不同，需要按类型拆分
                types_group: Dict[str, List[Dict[str, Any]]] = {}
                for r in batch_rows:
                    types_group.setdefault(r['type'], []).append(r)
                for ttype, rows in types_group.items():
                    session.run(
                        "UNWIND $rels AS r MATCH (s {internalId: r.s}) MATCH (t {internalId: r.e}) "
                        f"MERGE (s)-[rel:`{ttype}`]->(t) SET rel.doc_id = r.doc_id",
                        rels=rows
                    )
            for r in rels:
                rel_batch.append(r)
                if len(rel_batch) >= BATCH_REL:
                    flush_rel(rel_batch)
                    rel_batch.clear()
            flush_rel(rel_batch)
            print("  关系导入完成")

            # 基础统计
            stats_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()['c']
            stats_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()['c']
            print(f"✅ 导入结束: 节点 {stats_nodes} 个, 关系 {stats_rels} 条")

    finally:
        driver.close()
        print("🔌 已关闭连接")

if __name__ == '__main__':
    main()
