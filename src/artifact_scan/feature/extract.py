# ============================================================
# extract.py —— 批量特征提取（阶段 2.1）
# 读取标注数据（data/annotated/records.ndjson），对带 image_url 的
# 文物图片：下载到本地缓存 → DINOv2 提取 CLS 特征 → L2 归一化，
# 输出 features.npy（N×dim）+ meta.ndjson（每条记录的 id/source 等）。
# 支持断点：图片缓存命中则跳过下载；结果可追加（按 id 去重）。
# ============================================================
"""批量特征提取：标注数据 → DINOv2 特征（L2 归一化）。"""
import json
import logging
import os

import requests
from PIL import Image

from .model import FeatureModel

logger = logging.getLogger(__name__)

_UA = "artifact-scanning-system/0.1 (feature extraction)"


def _load_records(path):
    """读取 ndjson 标注数据。"""
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _download(url, dest, proxy=None, retries=3, timeout=30):
    """下载图片到 dest，成功返回 True。"""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout, proxies=proxies,
                                headers={"User-Agent": _UA}, stream=True)
            if resp.status_code == 200:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8192):
                        fh.write(chunk)
                return True
            logger.warning("下载 %s 返回 %s", url, resp.status_code)
        except requests.RequestException as exc:
            logger.warning("下载 %s 失败：%s（第 %s 次）", url, exc, attempt + 1)
    return False


def extract_dataset(annotated_file, out_dir, model_name="dinov2-base",
                    proxy=None, limit=None, image_dir=None, batch=16,
                    pool="cls"):
    """对标注数据中带图的记录批量提取特征。

    返回：写入 features.npy / meta.ndjson / 类计数字典。
    """
    import numpy as np

    records = _load_records(annotated_file)
    # 只保留有 image_url 的
    records = [r for r in records if r.get("image_url")]
    if limit:
        records = records[:limit]
    logger.info("待提取记录 %s 条（含图）", len(records))

    if image_dir is None:
        image_dir = os.path.join(out_dir, "images")
    os.makedirs(image_dir, exist_ok=True)

    model = FeatureModel(model_name)

    feats, metas = [], []
    skipped, failed = 0, 0
    for i, r in enumerate(records):
        rid = r.get("id")
        uid = "%s_%s" % (r.get("source"), rid)  # 源+id 作缓存键，避免跨源 id 冲突
        img_path = os.path.join(image_dir, "%s.jpg" % uid)
        if not _download(r["image_url"], img_path, proxy=proxy):
            failed += 1
            logger.warning("[%s/%s] 跳过 %s（下载失败）", i + 1, len(records), uid)
            continue
        try:
            if pool == "gem":
                f = model.extract_gem(img_path)
            elif pool == "pooled":
                f = model.extract_pooled(img_path)
            else:  # cls
                f = model.extract_one(img_path)
        except Exception as exc:  # 图损坏等
            logger.warning("[%s/%s] 跳过 %s（提取失败：%s）", i + 1, len(records), uid, exc)
            failed += 1
            continue
        if f is None:
            failed += 1
            continue
        f = np.asarray(f, dtype=np.float32)
        if f.ndim == 2 and f.shape[0] == 1:
            f = f[0]  # 去掉单样本 batch 维（extract_gem/pooled 单张返回 (1, dim)）
        feats.append(f)
        metas.append({"id": rid, "source": r.get("source"),
                      "title": r.get("title"), "image_url": r["image_url"],
                      "uid": uid})
        if (i + 1) % 50 == 0:
            logger.info("已提取 %s/%s 条", i + 1, len(records))

    if not feats:
        logger.warning("无有效特征输出")
        return {"records": len(records), "extracted": 0, "failed": failed}

    arr = np.stack(feats)  # (N, dim)
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "features.npy"), arr)
    with open(os.path.join(out_dir, "meta.ndjson"), "w", encoding="utf-8") as fh:
        for m in metas:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    logger.info("特征已保存：%s/features.npy（%s×%s）",
                out_dir, arr.shape[0], arr.shape[1])
    return {"records": len(records), "extracted": len(feats), "failed": failed}
