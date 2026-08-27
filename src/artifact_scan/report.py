# ============================================================
# report.py —— 证据链引擎 + 结构化报告（阶段 5.3 / 5.4）
# 整合：多特征检索（Milvus）+ 知识图谱（Neo4j）+ 标注，
# 构建文物断代证据链，并生成结构化 JSON 报告。
# 用法：python -m artifact_scan.report --id <artifact_id>
# ============================================================
"""证据链引擎 + 结构化断代报告。"""
import argparse
import json
import logging

logger = logging.getLogger(__name__)

_ANNOTATED = "data/annotated/records.ndjson"
_META = "data/features/meta.ndjson"
_URI = "bolt://127.0.0.1:7687"
_AUTH = ("neo4j", "graph2026")
_MILVUS_URI = "http://127.0.0.1:19530"


def _load_annotated():
    with open(_ANNOTATED, encoding="utf-8") as fh:
        return {str(r["id"]): r for r in [json.loads(l) for l in fh if l.strip()]}


def _load_meta():
    with open(_META, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def build_evidence(artifact_id, topk=5, graph_driver=None, milvus=None):
    """构建证据链：标注 + 图谱 + 相似文物检索。"""
    ann = _load_annotated()
    r = ann.get(str(artifact_id))
    if not r:
        return None
    lab = r.get("labels") or {}
    evidence = {
        "artifact": {
            "id": str(r["id"]), "title": r.get("title"), "source": r.get("source"),
            "culture": lab.get("culture"), "period": lab.get("period"),
            "materials": lab.get("materials"), "forms": lab.get("forms"),
            "decorations": lab.get("decorations"), "date": r.get("date"),
            "medium": r.get("medium"),
        },
        "similar_artifacts": [],
        "graph_evidence": {},
    }

    # 相似文物（Milvus 融合特征检索）
    if milvus is not None:
        import numpy as np
        fused = np.load("data/features/fused/fusion.npy").astype(np.float32)
        metas = _load_meta()
        idx = next((i for i, m in enumerate(metas) if str(
            m["id"]) == str(artifact_id)), None)
        if idx is not None:
            res = milvus.search("artifact_fusion", data=fused[idx:idx + 1],
                                limit=topk, output_fields=["title", "source"])
            for h in res[0]:
                evidence["similar_artifacts"].append({
                    "id": h["id"], "title": h.get("title", ""),
                    "source": h.get("source", ""), "score": round(h["distance"], 4),
                })

    # 图谱证据
    if graph_driver is not None:
        from .graph import culture_trace, period_infer
        ct = culture_trace(graph_driver, artifact_id)
        if ct:
            d = dict(ct)
            evidence["graph_evidence"]["culture_trace"] = {
                "cultures": d.get("cultures"), "periods": d.get("periods"),
                "materials": d.get("materials"),
            }
            culture = (evidence["graph_evidence"]
                       ["culture_trace"]["cultures"] or [None])[0]
            if culture:
                evidence["graph_evidence"]["period_infer"] = period_infer(
                    graph_driver, culture)
    return evidence


def build_report(evidence):
    """从证据链生成结构化 JSON 断代报告。"""
    a = evidence["artifact"]
    # 置信度：基于文化/时期证据与相似文物数
    score = 0.5
    if a["period"]:
        score += 0.15
    if a["culture"]:
        score += 0.15
    score += min(0.2, len(evidence["similar_artifacts"]) * 0.05)
    report = {
        "artifact": {"id": a["id"], "title": a["title"], "source": a["source"]},
        "conclusion": {
            "period": a["period"], "culture": a["culture"],
            "materials": a["materials"], "forms": a["forms"],
            "date": a["date"], "confidence": round(min(score, 1.0), 3),
        },
        "evidence_chain": evidence,
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据链 + 结构化报告（阶段 5.3/5.4）")
    ap.add_argument("--id", required=True, help="文物 id")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--graph", action="store_true", help="启用图谱证据")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    graph_driver = None
    if args.graph:
        from neo4j import GraphDatabase
        graph_driver = GraphDatabase.driver(_URI, auth=_AUTH)
        graph_driver.verify_connectivity()

    milvus = None
    from pymilvus import MilvusClient
    try:
        milvus = MilvusClient(uri=_MILVUS_URI)
    except Exception as exc:
        logger.warning("Milvus 连接失败：%s（跳过相似检索）", exc)

    ev = build_evidence(args.id, args.topk, graph_driver, milvus)
    if not ev:
        print("未找到文物 %s" % args.id)
        return
    report = build_report(ev)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if graph_driver:
        graph_driver.close()


if __name__ == "__main__":
    main()
