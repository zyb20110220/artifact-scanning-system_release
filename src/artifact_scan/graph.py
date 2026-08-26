# ============================================================
# graph.py —— 知识图谱导入与查询（阶段 4.3 / 4.5 / 3.3）
# 导入文物 → 文化/时期/材料/器型/纹饰 图谱；
# 提供图谱增强重排（候选与 query 共享文化/时期加分）。
# 用法：python -m artifact_scan.graph [--import]
# ============================================================
"""知识图谱：导入文物标签图谱 + 图谱增强重排。"""
import argparse
import json
import logging

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

_ANNOTATED = "data/annotated/records.ndjson"
_URI = "bolt://127.0.0.1:7687"
_AUTH = ("neo4j", "graph2026")


def _load_records(path=_ANNOTATED):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def import_graph(driver, records):
    """批量导入文物 + 标签节点与关系（MERGE 幂等）。"""
    rows = []
    for r in records:
        lab = r.get("labels") or {}
        rows.append({
            "id": str(r["id"]), "title": r.get("title") or "",
            "source": r.get("source") or "",
            "cultures": [c for c in [lab.get("culture")] if c],
            "periods": [p for p in [lab.get("period")] if p],
            "materials": lab.get("materials") or [],
            "forms": lab.get("forms") or [],
            "decorations": lab.get("decorations") or [],
        })
    cypher = """
    UNWIND $rows AS row
    MERGE (a:Artifact {id: row.id})
    SET a.title = row.title, a.source = row.source
    FOREACH (c IN row.cultures | MERGE (n:Culture {name: c})
             MERGE (a)-[:HAS_CULTURE]->(n))
    FOREACH (p IN row.periods | MERGE (n:Period {name: p})
             MERGE (a)-[:HAS_PERIOD]->(n))
    FOREACH (m IN row.materials | MERGE (n:Material {name: m})
             MERGE (a)-[:HAS_MATERIAL]->(n))
    FOREACH (f IN row.forms | MERGE (n:Form {name: f})
             MERGE (a)-[:HAS_FORM]->(n))
    FOREACH (d IN row.decorations | MERGE (n:Decoration {name: d})
             MERGE (a)-[:HAS_DECORATION]->(n))
    """
    with driver.session() as s:
        s.run(cypher, rows=rows)
    logger.info("导入 %s 条文物到图谱", len(rows))


def graph_stats(driver):
    with driver.session() as s:
        counts = {}
        for label in ["Artifact", "Culture", "Period", "Material", "Form", "Decoration"]:
            r = s.run("MATCH (n:%s) RETURN count(n) AS c" % label)
            counts[label] = r.single()["c"]
    return counts


# ------------------------------------------------------------
# Cypher 查询库（阶段 4.5）
# ------------------------------------------------------------
def culture_trace(driver, artifact_id):
    """文化溯源：某文物的文化/时期/材料。"""
    with driver.session() as s:
        r = s.run(
            "MATCH (a:Artifact {id:$id}) "
            "OPTIONAL MATCH (a)-[:HAS_CULTURE]->(c) "
            "OPTIONAL MATCH (a)-[:HAS_PERIOD]->(p) "
            "OPTIONAL MATCH (a)-[:HAS_MATERIAL]->(m) "
            "RETURN a.title AS title, collect(DISTINCT c.name) AS cultures, "
            "collect(DISTINCT p.name) AS periods, collect(DISTINCT m.name) AS materials",
            id=str(artifact_id))
        return r.single()


def period_infer(driver, culture):
    """时期推断：某文化的文物主要时期分布。"""
    with driver.session() as s:
        r = s.run(
            "MATCH (c:Culture {name:$culture})<-[:HAS_CULTURE]-(a:Artifact)"
            "-[:HAS_PERIOD]->(p) RETURN p.name AS period, count(a) AS n "
            "ORDER BY n DESC LIMIT 10", culture=culture)
        return [{"period": x["period"], "count": x["n"]} for x in r]


def similar_artifacts(driver, culture, limit=10):
    """文物关联：同文化的文物列表。"""
    with driver.session() as s:
        r = s.run(
            "MATCH (c:Culture {name:$culture})<-[:HAS_CULTURE]-(a:Artifact) "
            "RETURN a.id AS id, a.title AS title LIMIT $limit",
            culture=culture, limit=limit)
        return [x.data() for x in r]


def graph_boost(driver, query_record, candidate_ids, topk=20):
    """图谱增强：给候选打分（与 query 共享文化/时期/材料数）。
    返回 {candidate_id: boost_score}。
    """
    ql = query_record.get("labels") or {}
    qc = {ql.get("culture"), ql.get("period")}
    qc.discard(None)
    boost = {}
    with driver.session() as s:
        for cid in candidate_ids:
            r = s.run(
                "MATCH (a:Artifact {id: $id}) "
                "OPTIONAL MATCH (a)-[:HAS_CULTURE|HAS_PERIOD]->(n) "
                "RETURN collect(n.name) AS names", id=str(cid))
            names = set(r.single()["names"])
            boost[str(cid)] = len(qc & names)
    return boost


def main(argv=None):
    ap = argparse.ArgumentParser(description="知识图谱（阶段 4）")
    ap.add_argument("--uri", default=_URI)
    ap.add_argument("--password", default=_AUTH[1])
    ap.add_argument("--import", dest="do_import", action="store_true", help="导入图谱")
    ap.add_argument("--stats", action="store_true", help="统计")
    ap.add_argument("--query", action="store_true", help="执行 Cypher 查询库演示(4.5)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    driver = GraphDatabase.driver(args.uri, auth=("neo4j", args.password))
    driver.verify_connectivity()
    logger.info("已连接 Neo4j %s", args.uri)

    if args.do_import:
        records = _load_records()
        import_graph(driver, records)
        print(json.dumps(graph_stats(driver), ensure_ascii=False, indent=2))
    elif args.stats:
        print(json.dumps(graph_stats(driver), ensure_ascii=False, indent=2))
    elif args.query:
        # 4.5 Cypher 查询库演示
        demo = _load_records()[0]
        rid = str(demo["id"])
        print("== 文化溯源 (artifact %s) ==" % rid)
        print(json.dumps(culture_trace(driver, rid).data(), ensure_ascii=False))
        culture = (demo.get("labels") or {}).get("culture")
        if culture:
            print("== 时期推断 (culture=%s) ==" % culture)
            print(json.dumps(period_infer(driver, culture), ensure_ascii=False))
            print("== 文物关联 (culture=%s) ==" % culture)
            print(json.dumps(similar_artifacts(driver, culture, 5), ensure_ascii=False))
    driver.close()


if __name__ == "__main__":
    main()
