# ============================================================
# milvus_index.py —— Milvus 向量库索引构建与检索（阶段 2.6）
# 用融合特征（data/features/fused/fusion.npy）建 HNSW 索引并做检索验证。
# 用法：python -m artifact_scan.feature.milvus_index \
#         [--host 127.0.0.1 --port 19530 --features data/features/fused/fusion.npy]
# ============================================================
"""Milvus 索引构建与检索验证。"""
import argparse
import json
import logging

import numpy as np
from pymilvus import (
    MilvusClient, DataType, CollectionSchema, FieldSchema,
)

logger = logging.getLogger(__name__)

_META = "data/features/meta.ndjson"  # 特征 meta（各模型共享，含 id/source/title）


def build_parser():
    p = argparse.ArgumentParser(
        description="Milvus 索引构建与检索（阶段 2.6）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--host", default="127.0.0.1", help="Milvus 地址")
    p.add_argument("--port", type=int, default=19530, help="Milvus gRPC 端口")
    p.add_argument("--collection", default="artifact_fusion", help="集合名")
    p.add_argument("--features", default="data/features/fused/fusion.npy",
                   help="融合特征文件")
    p.add_argument("--meta", default=_META, help="特征 meta（id/source/title）")
    p.add_argument("--nlist", type=int, default=64, help="HNSW 候选数")
    p.add_argument("--topk", type=int, default=5, help="检索 Top-K")
    p.add_argument("--verbose", action="store_true", help="调试日志")
    return p


def load(meta_file):
    """读取 meta，返回 id/source/title 列表。"""
    with open(meta_file, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    feats = np.load(args.features).astype(np.float32)
    metas = load(args.meta)
    n, dim = feats.shape
    logger.info("加载融合特征 %s（%s×%s）+ %s 条 meta", args.features, n, dim, len(metas))

    # 连接（统一用新 MilvusClient）
    client = MilvusClient(uri="http://%s:%d" % (args.host, args.port))
    logger.info("已连接 Milvus %s:%d", args.host, args.port)

    # 集合存在则删除（幂等重建）
    if client.has_collection(args.collection):
        client.drop_collection(args.collection)
        logger.info("删除已存在集合 %s", args.collection)

    # 建集合（schema：VARCHAR 主键 + 向量 + 标量）
    schema = CollectionSchema([
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
    ])
    client.create_collection(collection_name=args.collection, schema=schema)
    logger.info("已创建集合 %s（dim=%d, COSINE）", args.collection, dim)

    # 插入数据（id + vector + source + title）
    rows = []
    for i, m in enumerate(metas):
        rows.append({
            "id": str(m["id"]),
            "vector": feats[i].tolist(),
            "source": m.get("source", ""),
            "title": m.get("title", ""),
        })
    client.insert(collection_name=args.collection, data=rows)
    logger.info("已插入 %s 条向量", len(rows))

    # 建 HNSW 索引（特征已 L2 归一化，IP 内积 = cosine）
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="HNSW",
        metric_type="IP",
        params={"M": 16, "efConstruction": 200},
    )
    client.create_index(collection_name=args.collection, index_params=index_params)
    logger.info("HNSW 索引已创建（IP）")

    # 加载集合并做检索验证
    client.load_collection(collection_name=args.collection)
    q = feats[: args.topk]
    res = client.search(
        collection_name=args.collection,
        data=q,
        limit=args.topk,
        output_fields=["source", "title"],
    )
    print("检索验证（前 %s 条查询的 Top-%s）：" % (args.topk, args.topk))
    for qi, hits in enumerate(res):
        print("  query[%s] (id=%s, %s):" % (
            qi, metas[qi]["id"], metas[qi].get("title", "")))
        for h in hits:
            print("    -> id=%s source=%s score=%.4f %s" % (
                h["id"], h.get("source", ""), h["distance"],
                h.get("title", "")[:30]))
    client.close()


if __name__ == "__main__":
    main()
