# ============================================================
# fusion.py —— 特征融合模块（阶段 2.4：可学习注意力门控）
# 输入 K 路特征（如 DINOv2 CLS / SigLIP pooler / registers GeM），
# 用可学习注意力门控（per-sample 权重）融合为统一特征。
# 通过弱监督（标注 culture）训练门控与分类头。
# ============================================================
"""特征融合：可学习注意力门控。"""
import argparse
import json
import logging
import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# 默认三路特征（顺序：dinov2 / siglip / registers），对应 meta 顺序
DEFAULT_VIEWS = [
    ("dinov2", "data/features/features.npy"),
    ("siglip", "data/features/siglip/features.npy"),
    ("registers", "data/features/registers/features.npy"),
]
_META = "data/features/meta.ndjson"
_ANNOTATED = "data/annotated/records.ndjson"


class FusionGating(nn.Module):
    """可学习注意力门控融合。

    输入 K 路特征列表（每路 N×dim），对所有视图拼接后经 MLP 预测
    每样本的门控权重（softmax），再对视图逐元素加权求和。
    """

    def __init__(self, views, dim, hidden=256):
        super().__init__()
        self.views = views
        self.dim = dim
        self.gate = nn.Sequential(
            nn.Linear(views * dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, views),
        )

    def forward(self, views):
        """views: list[(N, dim)] → (融合特征 (N,dim), 门控权重 (N,views))"""
        cat = torch.cat(views, dim=1)             # (N, views*dim)
        w = F.softmax(self.gate(cat), dim=1)      # (N, views)
        out = torch.zeros_like(views[0])
        for i, v in enumerate(views):
            out = out + w[:, i:i + 1] * v
        return out, w


class _Classifier(nn.Module):
    """融合特征分类头（弱监督辅助任务）。"""

    def __init__(self, dim, num_classes):
        super().__init__()
        self.head = nn.Linear(dim, num_classes)

    def forward(self, x):
        return self.head(x)


# ------------------------------------------------------------
# 数据加载
# ------------------------------------------------------------
def _load_meta(meta_file):
    """读取 meta.ndjson → (ids, sources) 列表。"""
    with open(meta_file, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    ids = [r["id"] for r in rows]
    sources = [r.get("source") for r in rows]
    return ids, sources


def _label_map(annotated_file, field="period"):
    """从标注数据构建 id -> 标签映射（field 为 period/culture）。"""
    mapping = {}
    with open(annotated_file, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            lab = r.get("labels") or {}
            value = lab.get(field) or r.get(field)
            if value:
                mapping[str(r["id"])] = value
    return mapping


def load_dataset(view_files, annotated_file, meta_file, label_field="period"):
    """加载三路特征（对齐）+ 标签。

    返回 (X 列表, labels, ids, classes)。
    """
    feats = [np.load(p).astype(np.float32) for p in view_files]
    ids, _ = _load_meta(meta_file)
    cmap = _label_map(annotated_file, label_field)
    labels, classes = [], ["unknown"]
    for rid in ids:
        lab = cmap.get(str(rid), "unknown")
        if lab not in classes:
            classes.append(lab)
        labels.append(classes.index(lab))
    return feats, np.array(labels, dtype=np.int64), ids, classes


# ------------------------------------------------------------
# 训练 / 融合
# ------------------------------------------------------------
def train(feats, labels, epochs=80, lr=1e-3, batch=64, seed=0, ent_w=0.05):
    """训练 FusionGating（弱监督分类）+ 分类头。

    ent_w 控制门控熵正则权重：鼓励门控权重分散，避免塌缩到单一视图。
    返回 (gate, classifier, history)。
    """
    torch.manual_seed(seed)
    n, dim = feats[0].shape
    num_classes = int(labels.max()) + 1
    gate = FusionGating(len(feats), dim)
    clf = _Classifier(dim, num_classes)
    opt = torch.optim.Adam(list(gate.parameters()) +
                           list(clf.parameters()), lr=lr)
    criterion = nn.CrossEntropyLoss()

    X = [torch.from_numpy(f) for f in feats]
    y = torch.from_numpy(labels)
    idx = np.arange(n)
    history = []
    for ep in range(epochs):
        np.random.shuffle(idx)
        gate.train()
        total = 0.0
        for i in range(0, n, batch):
            b = idx[i:i + batch]
            xs = [x[b] for x in X]
            fused, w = gate(xs)
            logits = clf(fused)
            loss = criterion(logits, y[b])
            # 门控熵正则：最大化 -sum(w log w)，使权重分布更分散
            eps = 1e-8
            ent = -(w * torch.log(w + eps)).sum(dim=1).mean()
            loss = loss - ent_w * ent
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        acc = _accuracy(gate, clf, X, y, batch)
        history.append(total / n)
        if (ep + 1) % 20 == 0:
            logger.info("epoch %s/%s loss %.4f acc %.3f", ep + 1, epochs,
                        total / n, acc)
    gate.eval()
    return gate, clf, history


def _accuracy(gate, clf, X, y, batch=128):
    gate.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(y), batch):
            xs = [x[i:i + batch] for x in X]
            fused, _ = gate(xs)
            preds.append(clf(fused).argmax(dim=1))
    return (torch.cat(preds) == y).float().mean().item()


def fuse(gate, feats):
    """用训练好的门控融合特征，返回 (融合特征 (N,dim), 门控权重 (N,views))。

    融合特征做 L2 归一化，保证单位球尺度，便于 cosine/向量检索。
    """
    gate.eval()
    X = [torch.from_numpy(f) for f in feats]
    with torch.no_grad():
        fused, w = gate(X)
    fused = fused.numpy()
    norm = np.linalg.norm(fused, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return (fused / norm).astype(np.float32), w.numpy()


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="特征融合（阶段 2.4：可学习注意力门控）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--views", nargs="+", default=None,
                   help="特征文件列表（缺省用 3 路默认）")
    p.add_argument("--annotated", default=_ANNOTATED,
                   help="标注数据（取 culture 标签）")
    p.add_argument("--meta", default=_META, help="特征 meta（记录顺序）")
    p.add_argument("--epochs", type=int, default=80, help="训练轮数")
    p.add_argument("--lr", type=float, default=1e-3, help="学习率")
    p.add_argument("--out", default="data/features/fused/fusion.npy",
                   help="融合特征输出文件")
    p.add_argument("--weights-out", default="data/features/fused/gate_weights.npy",
                   help="门控权重输出文件")
    p.add_argument("--verbose", action="store_true", help="调试日志")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    view_files = args.views or [v[1] for v in DEFAULT_VIEWS]
    feats, labels, ids, classes = load_dataset(
        view_files, args.annotated, args.meta)
    logger.info("加载特征 %s 路，%s 样本，%s 个 culture 类别", len(feats),
                feats[0].shape[0], len(classes) - 1)

    gate, clf, hist = train(feats, labels, epochs=args.epochs, lr=args.lr)
    fused, w = fuse(gate, feats)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.save(args.out, fused)
    np.save(args.weights_out, w)
    torch.save({"gate": gate.state_dict(), "classes": classes},
               os.path.join(os.path.dirname(args.out), "gate.pt"))
    logger.info("融合特征已保存：%s（%s），门控权重：%s",
                args.out, fused.shape, args.weights_out)


if __name__ == "__main__":
    main()
