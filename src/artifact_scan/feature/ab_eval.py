# ============================================================
# ab_eval.py —— 检索 A/B 评估框架（阶段 3.5）
# 对比不同检索策略（单路各特征 / 多路 RRF / 多路+精排）在
#   P@K / Recall@K / MRR 上的表现（period 与 culture 两套标签）。
# 用法：python -m artifact_scan.feature.ab_eval --topk 5
# ============================================================
"""检索 A/B 评估框架：多策略对比。"""
import argparse
import json
import logging

import numpy as np

from .rerank import load_reranker

logger = logging.getLogger(__name__)

VIEWS = [
    ("DINOv2", "data/features/features.npy"),
    ("SigLIP", "data/features/siglip/features.npy"),
    ("Registers", "data/features/registers/features.npy"),
    ("Fused", "data/features/fused/fusion.npy"),
]
_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"
_RRF_K = 60


def _load_codes(field):
    metas = [json.loads(l) for l in open(_META, encoding="utf-8") if l.strip()]
    pcmap = {}
    for l in open(_ANNOTATED, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        pcmap[str(r["id"])] = (r.get("labels") or {}).get(field) or r.get(field)
    classes, code = ["unknown"], []
    for m in metas:
        lab = pcmap.get(str(m["id"]), "unknown")
        if lab not in classes:
            classes.append(lab)
        code.append(classes.index(lab))
    return metas, np.array(code)


def _sim(feat):
    s = feat @ feat.T
    np.fill_diagonal(s, -1e9)
    return s


def strategy_single(feat, topk):
    return np.argsort(-_sim(feat), axis=1)[:, :topk]


def strategy_multi_rrf(feats, topk=5, cand=20):
    """多路 RRF（本地实现，与 Milvus recall 一致）。"""
    n = feats[0].shape[0]
    import collections
    all_c = []
    for feat in feats:
        s = _sim(feat)
        all_c.append(np.argsort(-s, axis=1)[:, :cand])
    res = np.zeros((n, topk), dtype=int)
    for i in range(n):
        scores = collections.defaultdict(float)
        for c in all_c:
            for rank, j in enumerate(c[i], start=1):
                scores[int(j)] += 1.0 / (_RRF_K + rank)
        order = sorted(scores, key=lambda k: -scores[k])[:topk]
        res[i] = order
    return res


def strategy_multi_rerank(feats, model, cand=20, topk=5):
    """多路 RRF 候选 → Cross-Encoder 精排。"""
    import torch
    fuse = feats[-1]  # 用最后一路（Fused）做精排打分
    cand_idx = strategy_multi_rrf(feats, topk=cand, cand=cand)
    x = torch.from_numpy(fuse)
    res = np.zeros((len(feats[0]), topk), dtype=int)
    for i in range(len(feats[0])):
        cur = cand_idx[i]
        with torch.no_grad():
            scores = model(x[i:i + 1].expand(len(cur), -1), x[cur]).numpy()
        order = np.argsort(-scores)[:topk]
        res[i] = cur[order]
    return res


def _metrics(topk_mat, codes, topk):
    n = len(codes)
    p = r = mrr = 0.0
    for i in range(n):
        rel = np.where(codes == codes[i])[0]
        rel = rel[rel != i]
        if len(rel) == 0:
            continue
        hits = topk_mat[i]
        hit_set = set(hits.tolist())
        inter = len(hit_set & set(rel.tolist()))
        p += inter / topk
        r += inter / len(rel)
        # MRR
        rank = None
        for rk, j in enumerate(hits, start=1):
            if j in rel:
                rank = rk
                break
        mrr += 1.0 / (rank or (topk + 1))
    return p / n, r / n, mrr / n


def main(argv=None):
    ap = argparse.ArgumentParser(description="检索 A/B 评估（阶段 3.5）")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--cand", type=int, default=20)
    ap.add_argument("--model-path", default="data/features/rerank_model.pt")
    ap.add_argument("--label", default="culture", choices=["period", "culture"])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    feats = [np.load(p).astype(np.float32) for _, p in VIEWS]
    metas, codes = _load_codes(args.label)
    logger.info("加载 %s 路特征，%s 样本，%s 类 %s",
                len(feats), len(codes), len(np.unique(codes)), args.label)

    strategies = [
        ("DINOv2 单路", lambda: strategy_single(feats[0], args.topk)),
        ("SigLIP 单路", lambda: strategy_single(feats[1], args.topk)),
        ("Registers 单路", lambda: strategy_single(feats[2], args.topk)),
        ("Fused 单路", lambda: strategy_single(feats[3], args.topk)),
        ("多路 RRF", lambda: strategy_multi_rrf(feats, args.topk, args.cand)),
    ]
    model, dim = load_reranker(args.model_path)
    strategies.append(("多路 RRF+精排",
                       lambda: strategy_multi_rerank(feats, model, args.cand, args.topk)))

    print("=" * 66)
    print("检索 A/B 评估（label=%s, topk=%d）：" % (args.label, args.topk))
    print("=" * 66)
    print("  %-18s %-9s %-9s %-7s" % ("策略", "P@%d" % args.topk,
                                     "R@%d" % args.topk, "MRR"))
    for name, fn in strategies:
        mat = fn()
        p, r, m = _metrics(mat, codes, args.topk)
        print("  %-18s %-9.4f %-9.4f %-7.4f" % (name, p, r, m))
    print("=" * 66)


if __name__ == "__main__":
    main()
