# ============================================================
# rerank.py —— Cross-Encoder 精排（阶段 3.2）
# 对 (query 特征, candidate 特征) 拼接，用 MLP 预测相关性分数，
# 对召回候选重排，提升检索精度（culture P@5）。
# 用法：python -m artifact_scan.feature.rerank --epochs 80
# ============================================================
"""Cross-Encoder 精排：拼接特征 MLP 打分重排。"""
import argparse
import json
import logging
import random

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

_FEATS = "data/features/fused/fusion.npy"
_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"


class Reranker(nn.Module):
    """Cross-Encoder：输入 (query, cand) 拼接，输出相关性分数。"""

    def __init__(self, dim, hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim * 2, hidden), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(hidden, 1),
        )

    def forward(self, q, c):
        x = torch.cat([q, c], dim=1)
        return self.net(x).squeeze(1)


def _load_ids_labels():
    metas = [json.loads(l) for l in open(_META, encoding="utf-8") if l.strip()]
    pcmap, cmap = {}, {}
    for l in open(_ANNOTATED, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        lab = r.get("labels") or {}
        pcmap[str(r["id"])] = lab.get("period") or r.get("period")
        cmap[str(r["id"])] = lab.get("culture") or r.get("culture")
    pcodes, ccodes = ["unknown"], ["unknown"]
    pid, cid = {}, {}
    for m in metas:
        p = pcmap.get(str(m["id"]), "unknown")
        c = cmap.get(str(m["id"]), "unknown")
        if p not in pcodes:
            pcodes.append(p)
        if c not in ccodes:
            ccodes.append(c)
        pid[str(m["id"])] = pcodes.index(p)
        cid[str(m["id"])] = ccodes.index(c)
    return metas, pid, cid


def make_pairs(codes, n=493, pos=2, neg=4, seed=0):
    """构造 (query_idx, cand_idx, label) 训练对。
    正：同 period；负：异 period（难负例从召回相似但异类中采）。
    """
    random.seed(seed)
    rng = np.random.default_rng(seed)
    pairs = []
    for i in range(n):
        same = np.where(codes == codes[i])[0]
        same = same[same != i]
        negs = np.where(codes != codes[i])[0]
        for _ in range(pos):
            if len(same):
                j = int(rng.choice(same))
                pairs.append((i, j, 1))
        for _ in range(neg):
            if len(negs):
                j = int(rng.choice(negs))
                pairs.append((i, j, 0))
    return pairs


def train(feats, pairs, epochs=80, lr=1e-3, batch=256, seed=0):
    torch.manual_seed(seed)
    n, dim = feats.shape
    model = Reranker(dim)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    x = torch.from_numpy(feats)
    arr = np.array(pairs, dtype=np.int64)
    idx = np.arange(len(arr))
    for ep in range(epochs):
        np.random.shuffle(idx)
        model.train()
        total = 0.0
        for i in range(0, len(arr), batch):
            b = idx[i:i + batch]
            qi = arr[b, 0]
            ci = arr[b, 1]
            y = torch.from_numpy(arr[b, 2]).float()
            logits = model(x[qi], x[ci])
            loss = F.binary_cross_entropy_with_logits(logits, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        if (ep + 1) % 20 == 0:
            logger.info("epoch %s/%s loss %.4f", ep +
                        1, epochs, total / len(arr))
    model.eval()
    return model


def rerank_candidates(model, feats, topk=5, cand=20):
    """对每个 query，cosine 初排取 cand，再用 MLP 精排取 topk。
    返回 (cosine P@5, rerank P@5)（按 culture 标签）。"""
    metas, pid, cid = _load_ids_labels()
    ccodes = np.array([cid[str(m["id"])] for m in metas])
    n, dim = feats.shape
    sim = feats @ feats.T
    np.fill_diagonal(sim, -1e9)
    x = torch.from_numpy(feats)
    cos_total = rerank_total = 0.0
    for i in range(n):
        cands = np.argsort(-sim[i])[:cand]
        # cosine 初排
        order_cos = np.argsort(-sim[i, cands])[:topk]
        pick = cands[order_cos]
        cos_total += (ccodes[pick] == ccodes[i]).sum() / topk
        # Cross-Encoder 精排
        order = order_cos
        if model is not None:
            with torch.no_grad():
                scores = model(
                    x[i:i + 1].expand(len(cands), -1), x[cands]).numpy()
            order = np.argsort(-scores)[:topk]
        pick = cands[order]
        rerank_total += (ccodes[pick] == ccodes[i]).sum() / topk
    return cos_total / n, rerank_total / n


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cross-Encoder 精排（阶段 3.2）")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--cand", type=int, default=20)
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--pos", type=int, default=2)
    ap.add_argument("--neg", type=int, default=4)
    ap.add_argument("--save", default="data/features/rerank_model.pt",
                    help="训练后保存精排模型")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    feats = np.load(_FEATS).astype(np.float32)
    metas, pid, cid = _load_ids_labels()
    pcodes = np.array([pid[str(m["id"])] for m in metas])
    logger.info("加载融合特征 %s，%s 样本", _FEATS, len(metas))

    # 用 period 构造训练对（正对充足）
    pairs = make_pairs(pcodes, n=len(feats), pos=args.pos, neg=args.neg)
    logger.info("构造训练对 %s 个（期类）", len(pairs))
    model = train(feats, pairs, epochs=args.epochs)

    # 保存精排模型（供 3.4 编排服务加载）
    import os
    os.makedirs(os.path.dirname(args.save), exist_ok=True)
    torch.save({"state": model.state_dict(), "dim": feats.shape[1]}, args.save)
    logger.info("精排模型已保存：%s", args.save)

    # 评估 cosine vs rerank（culture P@5）
    p, pr = rerank_candidates(model, feats, topk=args.topk, cand=args.cand)
    print("culture P@%d：cosine 初排 = %.4f   Cross-Encoder 精排 = %.4f"
          % (args.topk, p, pr))


def load_reranker(path="data/features/rerank_model.pt"):
    """加载训练好的精排模型，返回 (Reranker, dim)。"""
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    dim = ckpt["dim"]
    model = Reranker(dim)
    model.load_state_dict(ckpt["state"])
    model.eval()
    return model, dim


if __name__ == "__main__":
    main()
