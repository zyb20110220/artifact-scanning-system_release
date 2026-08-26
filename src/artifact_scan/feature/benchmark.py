# ============================================================
# benchmark.py —— 特征提取基准测试（阶段 2.7）
# 对比各特征（DINOv2/SigLIP/registers/融合/对比）在
#   检索 P@5（period）+ KNN 分类准确率 上的表现。
# 用法：python -m artifact_scan.feature.benchmark
# ============================================================
"""特征基准测试：检索 P@K 与 KNN 分类。"""
import argparse
import json
import logging

import numpy as np

logger = logging.getLogger(__name__)

# 各特征：名称 -> 文件（维度由数据决定）
FEATURES = [
    ("DINOv2_CLS", "data/features/features.npy"),
    ("SigLIP_pooler", "data/features/siglip/features.npy"),
    ("Registers_GeM", "data/features/registers/features.npy"),
    ("Fused_gate", "data/features/fused/fusion.npy"),
    ("Contrastive", "data/features/contrastive/contrastive.npy"),
]
_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"


def load_labels(meta_file=_META, annotated_file=_ANNOTATED):
    """返回 (ids, period 标签 str, codes)。"""
    with open(meta_file, encoding="utf-8") as fh:
        ids = [json.loads(l)["id"] for l in fh if l.strip()]
    pcmap = {}
    with open(annotated_file, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            pcmap[str(r["id"])] = (r.get("labels") or {}).get("period") or r.get("period")
    labels = [(pcmap.get(str(i)) or "unknown") for i in ids]
    classes = sorted(set(labels))
    codes = [classes.index(l) for l in labels]
    return ids, labels, classes, codes


def _l2norm(x):
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (x / n).astype(np.float32)


def search_pk(feat, codes, k=5):
    """检索 P@K：对每个样本 query，返回同 period 的 top-K 命中率。"""
    sim = feat @ feat.T                      # (N, N) cosine（已归一化）
    np.fill_diagonal(sim, -1e9)              # 排除自身
    N = feat.shape[0]
    top = np.argsort(-sim, axis=1)[:, :k]
    p = 0.0
    for i in range(N):
        hits = (codes[top[i]] == codes[i]).sum()
        p += hits / k
    return p / N


def knn_acc(feat, codes, k=5):
    """KNN 分类准确率（各样本留一，用 top-K 投票）。"""
    sim = feat @ feat.T
    np.fill_diagonal(sim, -1e9)
    N = feat.shape[0]
    top = np.argsort(-sim, axis=1)[:, :k]
    preds = np.zeros(N, dtype=int)
    for i in range(N):
        nc = codes[top[i]]
        # 多数投票
        preds[i] = np.bincount(nc).argmax()
    return (preds == codes).mean()


def main(argv=None):
    ap = argparse.ArgumentParser(description="特征基准测试（阶段 2.7）")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    ids, labels, classes, codes = load_labels()
    codes = np.array(codes)
    logger.info("加载 %s 条样本 / %s 类 period", len(ids), len(classes))

    print("=" * 60)
    print("特征基准：检索 P@%d（period）与 KNN 分类" % args.k)
    print("=" * 60)
    rows = []
    for name, path in FEATURES:
        try:
            feat = _l2norm(np.load(path).astype(np.float32))
        except Exception as exc:
            print("  %-18s 缺失：%s" % (name, exc))
            continue
        p = search_pk(feat, codes, args.k)
        acc = knn_acc(feat, codes, args.k)
        rows.append((name, feat.shape[1], p, acc))
        print("  %-18s dim=%-4d  P@%d=%.4f   KNN=%.4f" % (
            name, feat.shape[1], args.k, p, acc))
    print("=" * 60)


if __name__ == "__main__":
    main()
