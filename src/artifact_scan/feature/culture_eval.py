# ============================================================
# culture_eval.py —— culture 检索优化评估（阶段 3.6）
# 对比：SigLIP 单路 cosine vs SigLIP + culture 匹配增强（不同权重）
# 评估 culture P@5。culture 匹配 = 候选与 query 共享 culture 加分。
# 用法：python -m artifact_scan.feature.culture_eval --topk 5
# ============================================================
"""culture 检索优化评估（P@5）。"""
import argparse
import json
import logging

import numpy as np

logger = logging.getLogger(__name__)

_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"
_SIGLIP = "data/features/siglip/features.npy"


def _load(field="culture"):
    metas = [json.loads(l) for l in open(_META, encoding="utf-8") if l.strip()]
    pcmap = {}
    for l in open(_ANNOTATED, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        pcmap[str(r["id"])] = (r.get("labels") or {}).get(
            field) or r.get(field)
    codes, id2v = [], {}
    for m in metas:
        v = pcmap.get(str(m["id"]))
        codes.append(v)
        id2v[str(m["id"])] = v
    return metas, codes, id2v


def main(argv=None):
    ap = argparse.ArgumentParser(description="culture 检索优化评估（3.6）")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--cand", type=int, default=20)
    ap.add_argument("--weights", type=float, nargs="+",
                    default=[0.0, 0.5, 1.0, 2.0])
    ap.add_argument("--infer", action="store_true",
                    help="用候选多数 culture 推断（无 oracle），否则用真实 culture（oracle 上界）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    feat = np.load(_SIGLIP).astype(np.float32)
    metas, codes, id2v = _load("culture")
    n = len(codes)
    sim = feat @ feat.T
    np.fill_diagonal(sim, -1e9)
    logger.info("SigLIP %s×%s，%s 样本，unknown=%s",
                n, feat.shape[1], n, sum(1 for c in codes if c is None))

    print("=" * 56)
    print("culture P@%d 评估（SigLIP + culture 匹配增强）：" % args.topk)
    print("=" * 56)
    for w in args.weights:
        total = 0.0
        for i in range(n):
            cand = np.argsort(-sim[i])[:args.cand]
            qc = codes[i]
            score = sim[i, cand].copy()
            if w > 0:
                # 推断 query 的 culture（oracle=用真实；否则候选多数投票）
                if args.infer:
                    from collections import Counter
                    voted = Counter([codes[j]
                                    for j in cand if codes[j]]).most_common(1)
                    qc = voted[0][0] if voted else None
                for k, j in enumerate(cand):
                    if codes[j] == qc and codes[j] is not None:
                        score[k] += w
            order = np.argsort(-score)[:args.topk]
            pick = cand[order]
            hits = sum(
                1 for j in pick if codes[j] == qc and codes[j] is not None)
            total += hits / args.topk
        p = total / n
        print("  w=%-4s  P@%d = %.4f" % (w, args.topk, p))
    print("=" * 56)


if __name__ == "__main__":
    main()
