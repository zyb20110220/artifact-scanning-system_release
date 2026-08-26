# ============================================================
# orchestrator.py —— 检索编排服务（阶段 3.4）
# 多路召回 → Cross-Encoder 精排 → [图谱增强(可插拔)] → Top-K
# 用法：python -m artifact_scan.feature.orchestrator --query-idx 0 --topk 5
# ============================================================
"""检索编排：多路召回 + 精排 + 可选图谱增强。"""
import argparse
import json
import logging

import numpy as np

from .recall import VIEWS, recall, build, _load_meta
from .rerank import load_reranker

logger = logging.getLogger(__name__)

_FUSED = "data/features/fused/fusion.npy"
_META = "data/features/meta.ndjson"


class RerankHook:
    """图谱增强钩子（3.3 完成后接入；当前为直通/占位）。"""

    def apply(self, candidates, query_id):
        return candidates   # 占位：不修改，后续接入 Neo4j 图谱重排


def search(client, query_views, model, dim, topk=5, cand=20, graph=None):
    """完整检索编排。返回 [(id, final_score, source, title)]。"""
    fused = np.load(_FUSED).astype(np.float32)
    metas = _load_meta()
    id2idx = {str(m["id"]): i for i, m in enumerate(metas)}
    titles = {str(m["id"]): m.get("title", "") for m in metas}
    sources = {str(m["id"]): m.get("source", "") for m in metas}

    # 1) 多路召回（RRF 融合 → 候选 id + rrf 分）
    cand_ids = recall(client, query_views, topk=cand, cand=cand)
    cand_ids = [cid for cid, _ in cand_ids]
    # 2) 图谱增强（可插拔）
    if graph is not None:
        cand_ids = graph.apply(cand_ids)
    # 3) Cross-Encoder 精排（用 fused 特征打分）
    q = np.array([query_views.get(name) for name, _c, _p in VIEWS]).mean(axis=0)
    q = q / (np.linalg.norm(q) if np.linalg.norm(q) else 1.0)
    import torch
    x = torch.from_numpy(fused)
    qt = torch.from_numpy(q.astype(np.float32)).unsqueeze(0)
    scored = []
    if model is not None and cand_ids:
        cand_feats = torch.stack([x[id2idx[c]] for c in cand_ids if c in id2idx])
        cand_ids_valid = [c for c in cand_ids if c in id2idx]
        with torch.no_grad():
            scores = model(qt.expand(len(cand_ids_valid), -1), cand_feats).numpy()
        for c, s in zip(cand_ids_valid, scores):
            scored.append((c, float(s)))
        scored.sort(key=lambda t: -t[1])
    else:
        for c in cand_ids[:topk]:
            scored.append((c, float("-inf")))
    # 4) 输出 Top-K
    out = []
    for c, s in scored[:topk]:
        out.append((c, round(s, 4), sources.get(c, ""), titles.get(c, "")))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="检索编排（阶段 3.4）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=19530)
    ap.add_argument("--query-idx", type=int, default=0)
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--cand", type=int, default=20)
    ap.add_argument("--model-path", default="data/features/rerank_model.pt")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    from pymilvus import MilvusClient
    metas = _load_meta()
    client = MilvusClient(uri="http://%s:%d" % (args.host, args.port))
    if args.build:
        build(client, metas, force=True)

    model, dim = load_reranker(args.model_path)
    logger.info("加载精排模型（dim=%s）", dim)

    # 用本地 query 特征（每路第 N 行）
    qviews = {}
    for name, _c, path in VIEWS:
        q = np.load(path).astype(np.float32)[args.query_idx]
        n = np.linalg.norm(q)
        qviews[name] = q / (n if n else 1.0)

    res = search(client, qviews, model, dim, topk=args.topk, cand=args.cand)
    m = metas[args.query_idx]
    print("query[%s] id=%s %s（source=%s）" % (
        args.query_idx, m["id"], m.get("title", ""), m.get("source", "")))
    for i, (cid, s, src, title) in enumerate(res, 1):
        print("  #%d id=%s score=%.4f [%s] %s" % (i, cid, s, src, title[:40]))


if __name__ == "__main__":
    main()
