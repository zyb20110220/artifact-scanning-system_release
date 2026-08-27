# ============================================================
# recall.py —— 多路召回（阶段 3.1）
# DINOv2 + SigLIP + registers + 融合 4 路特征分别建 Milvus 索引，
# 对给定 query（本地特征或图像路径）做多路检索并用 RRF 融合为候选集。
# 用法：python -m artifact_scan.feature.recall --build
#       python -m artifact_scan.feature.recall --query-idx 0 --topk 5
# ============================================================
"""多路召回：多特征 Milvus 索引 + RRF 融合。"""
import argparse
import json
import logging
import os

import numpy as np
from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema

logger = logging.getLogger(__name__)

_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"

# 多路特征：名称 -> (集合名, 特征文件)
VIEWS = [
    ("dinov2", "artifact_dinov2", "data/features/features.npy"),
    ("siglip", "artifact_siglip", "data/features/siglip/features.npy"),
    ("registers", "artifact_registers", "data/features/registers/features.npy"),
    ("fused", "artifact_fusion", "data/features/fused/fusion.npy"),
]
_RRF_K = 60  # RRF 常数


def _load_meta(path=_META):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _load_codes(metas, field="period"):
    """id -> 类别编码（field: period / culture）。"""
    pcmap = {}
    with open(_ANNOTATED, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            pcmap[str(r["id"])] = (r.get("labels") or {}).get(
                field) or r.get(field)
    classes, code = ["unknown"], {}
    for m in metas:
        lab = pcmap.get(str(m["id"]), "unknown")
        if lab not in classes:
            classes.append(lab)
        code[str(m["id"])] = classes.index(lab)
    return code


def evaluate(client, topk=5, cand=20, limit=None, field="period"):
    """对全部样本做多路召回，计算 P@K。"""
    metas = _load_meta()
    codes = _load_codes(metas, field)
    N = len(metas)
    limit = limit or N
    total = 0.0
    for i in range(limit):
        qviews = {}
        for name, _coll, path in VIEWS:
            q = np.load(path).astype(np.float32)[i]
            n = np.linalg.norm(q)
            qviews[name] = q / (n if n else 1.0)
        res = recall(client, qviews, topk=topk, cand=cand)
        hits = sum(1 for r in res if codes.get(
            r[0]) == codes.get(str(metas[i]["id"])))
        total += hits / topk
    return total / limit


def _schema(dim):
    return CollectionSchema([
        FieldSchema("id", DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema("vector", DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema("source", DataType.VARCHAR, max_length=64),
        FieldSchema("title", DataType.VARCHAR, max_length=512),
    ])


def build(client, metas, force=True):
    """为 4 路特征各建集合（drop+create+insert+index+load）。"""
    for name, coll, path in VIEWS:
        feats = np.load(path).astype(np.float32)
        n, dim = feats.shape
        if client.has_collection(coll):
            if not force:
                logger.info("集合 %s 已存在，跳过", coll)
                continue
            client.drop_collection(coll)
        client.create_collection(coll, schema=_schema(dim))
        rows = [{
            "id": str(m["id"]), "vector": feats[i].tolist(),
            "source": m.get("source", ""), "title": m.get("title", ""),
        } for i, m in enumerate(metas)]
        client.insert(coll, rows)
        idx = client.prepare_index_params()
        idx.add_index("vector", index_type="HNSW", metric_type="IP",
                      params={"M": 16, "efConstruction": 200})
        client.create_index(coll, index_params=idx)
        client.load_collection(coll)
        logger.info("集合 %s 就绪：%s×%s（%s）", coll, n, dim, name)


def recall(client, query_views, topk=5, cand=20):
    """多路召回 + RRF 融合。

    query_views: {name: 归一化 query 向量 (dim,)}
    返回 [(id, rrf_score, top1_title)] 按 rrf 降序。
    """
    import collections
    scores = collections.defaultdict(float)
    for name, coll, _path in VIEWS:
        if name not in query_views:
            continue
        q = query_views[name]
        res = client.search(coll, data=q.reshape(1, -1), limit=cand,
                            output_fields=["title", "source"])
        for rank, h in enumerate(res[0], start=1):
            scores[h["id"]] += 1.0 / (_RRF_K + rank)
    results = sorted(scores.items(), key=lambda x: -x[1])[:topk]
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="多路召回（阶段 3.1）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=19530)
    ap.add_argument("--build", action="store_true", help="先建 4 路索引")
    ap.add_argument("--query-idx", type=int, default=0, help="用第 N 个样本作 query")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--cand", type=int, default=20)
    ap.add_argument("--eval", action="store_true", help="多路召回 P@K 评估")
    ap.add_argument("--limit", type=int, default=None, help="--eval 的样本数上限")
    ap.add_argument("--label", default="period", choices=["period", "culture"],
                    help="--eval 的标签字段")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    metas = _load_meta()
    client = MilvusClient(uri="http://%s:%d" % (args.host, args.port))
    logger.info("已连接 Milvus")

    if args.build:
        build(client, metas, force=True)

    if args.eval:
        p = evaluate(client, topk=args.topk, cand=args.cand,
                     limit=args.limit, field=args.label)
        print("多路召回 P@%d（%s，%s 样本）= %.4f" % (
            args.topk, args.label, args.limit or len(metas), p))
        return

    # 用本地第 N 个样本的各路特征作为 query
    qviews = {}
    for name, coll, path in VIEWS:
        feats = np.load(path).astype(np.float32)
        q = feats[args.query_idx]
        n = np.linalg.norm(q)
        q = q / (n if n else 1.0)
        qviews[name] = q

    res = recall(client, qviews, topk=args.topk, cand=args.cand)
    m = metas[args.query_idx]
    print("query[%s] id=%s %s（source=%s）" % (
        args.query_idx, m["id"], m.get("title", ""), m.get("source", "")))
    title_map = {str(x["id"]): x.get("title", "") for x in metas}
    for i, (rid, sc) in enumerate(res, 1):
        print("  #%d id=%s rrf=%.4f %s" %
              (i, rid, sc, title_map.get(str(rid), "")))


if __name__ == "__main__":
    main()
