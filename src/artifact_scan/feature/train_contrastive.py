# ============================================================
# train_contrastive.py —— 对比学习训练（阶段 2.5）
# 多视角对比学习（SimCLR 风格）+ Center Loss，缓解数据稀疏。
# 输入：同一文物的多路特征（DINOv2/SigLIP/registers，作为 3 个视角）
#       正对 = 同一样本的不同视角；负对 = 不同样本（所有视角）
# 输出：投影后的对比特征（用于后续检索/基准）。
# 用法：python -m artifact_scan.feature.train_contrastive --epochs 60
# ============================================================
"""对比学习：多视角 SimCLR + Center Loss。"""
import argparse
import json
import logging
import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

VIEWS = [
    ("dinov2", "data/features/features.npy"),
    ("siglip", "data/features/siglip/features.npy"),
    ("registers", "data/features/registers/features.npy"),
]
_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"


class Projector(nn.Module):
    """投影头：768 -> 256 -> proj（对比空间）。"""

    def __init__(self, dim, proj=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, 256), nn.BatchNorm1d(256), nn.ReLU(),
            nn.Linear(256, proj),
        )

    def forward(self, x):
        return self.net(x)


def info_nce(z, sample_ids, temperature=0.07):
    """对称 InfoNCE。z: (N*views, proj) 已归一化；sample_ids: 同长度，同 id 为正对。"""
    # 对每个 anchor，正对 = 同 sample_id 的其他视角；负对 = 不同 sample_id
    sim = z @ z.t() / temperature            # (M, M)
    M = z.shape[0]
    mask = sample_ids[:, None] == sample_ids[None, :]  # (M, M) 正样本掩码
    # 去掉自身（对角线）
    eye = torch.eye(M, device=z.device, dtype=torch.bool)
    pos_mask = mask & (~eye)
    neg_mask = ~mask
    exp = torch.exp(sim) * (~neg_mask).float()  # 屏蔽负对（非 inplace，保留梯度）
    denom = exp.sum(dim=1) + 1e-8
    pos = torch.where(pos_mask, exp, torch.zeros_like(exp))
    l = -torch.log(pos.sum(dim=1) / denom)
    return l.mean()


def center_loss(z, labels, centers):
    """Center Loss：使样本投影靠近其类别中心。centers: (num_classes, proj)。"""
    c = centers[labels]
    return ((z - c) ** 2).sum(dim=1).mean()


def load_data(annotated_file=_ANNOTATED, meta_file=_META):
    """加载多路特征 + period 标签 + 样本 id 分组。"""
    with open(meta_file, encoding="utf-8") as fh:
        metas = [json.loads(line) for line in fh if line.strip()]
    ids = [m["id"] for m in metas]
    # period 标签
    with open(annotated_file, encoding="utf-8") as fh:
        for line in fh:
            pass
    pcmap = {}
    with open(annotated_file, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            lab = (r.get("labels") or {}).get("period") or r.get("period")
            pcmap[str(r["id"])] = lab
    classes = ["unknown"]
    labels = []
    for rid in ids:
        lab = pcmap.get(str(rid), "unknown")
        if lab not in classes:
            classes.append(lab)
        labels.append(classes.index(lab))
    feats = [np.load(p).astype(np.float32) for p in [v[1] for v in VIEWS]]
    return feats, np.array(labels, dtype=np.int64), ids, classes


def train(feats, labels, epochs=60, proj=128, temp=0.07, lr=1e-3,
          center_w=0.1, batch=64, seed=0):
    torch.manual_seed(seed)
    n, dim = feats[0].shape
    views = len(feats)
    num_classes = int(labels.max()) + 1

    projector = Projector(dim, proj)
    centers = nn.Parameter(torch.zeros(num_classes, proj, dtype=torch.float32))
    opt = torch.optim.Adam(list(projector.parameters()) + [centers], lr=lr)

    X = [torch.from_numpy(f) for f in feats]
    y = torch.from_numpy(labels)
    sample_ids = torch.arange(n)
    idx = np.arange(n)
    history = []
    for ep in range(epochs):
        np.random.shuffle(idx)
        projector.train()
        total = 0.0
        for i in range(0, n, batch):
            b = torch.from_numpy(idx[i:i + batch])
            # 组装 (batch*views, dim)
            xb = torch.cat([x[b] for x in X], dim=0)
            zb = projector(xb)
            zb_norm = F.normalize(zb, dim=1)
            sid = torch.repeat_interleave(b, views)  # 每 batch 每样本 views 个 id
            # InfoNCE
            loss_ce = info_nce(zb_norm, sid, temp)
            # Center Loss（在投影上，用样本标签，每视角一份）
            # 取每个样本第一个 view 的投影用于 center loss 简化
            first_view = zb[::views]
            loss_ct = center_loss(first_view, y[b], centers)
            loss = loss_ce + center_w * loss_ct
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        history.append(total / n)
        if (ep + 1) % 15 == 0:
            logger.info("epoch %s/%s infoNCE+center %.4f", ep + 1, epochs,
                        total / n)
    projector.eval()
    return projector, centers, history


def main(argv=None):
    ap = argparse.ArgumentParser(description="对比学习（阶段 2.5）")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--proj", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--center-w", type=float, default=0.1)
    ap.add_argument("--out", default="data/features/contrastive/")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    feats, labels, ids, classes = load_data()
    n, dim = feats[0].shape
    logger.info("加载 %s 路特征 %s×%s，%s 类 period",
                len(feats), n, dim, len(classes) - 1)

    projector, centers, hist = train(feats, labels, epochs=args.epochs,
                                     proj=args.proj, lr=args.lr,
                                     center_w=args.center_w)
    # 投影全部样本到对比空间
    X = [torch.from_numpy(f) for f in feats]
    with torch.no_grad():
        # 用第 1 视角作为代表，投影得到对比特征（或 3 视角平均）
        z = Projector(768, args.proj)
        z.load_state_dict(projector.state_dict())
        z.eval()
        contrastive = z(X[0]).numpy()   # (n, proj)
        # 归一化
        norm = np.linalg.norm(contrastive, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        contrastive = (contrastive / norm).astype(np.float32)

    os.makedirs(args.out, exist_ok=True)
    np.save(os.path.join(args.out, "contrastive.npy"), contrastive)
    torch.save({"projector": projector.state_dict(),
                "centers": centers.detach().cpu().numpy(),
                "classes": classes},
               os.path.join(args.out, "contrastive_model.pt"))
    logger.info("对比特征已保存：%s/contrastive.npy（%s），模型：%s",
                args.out, contrastive.shape, args.out)


if __name__ == "__main__":
    main()
