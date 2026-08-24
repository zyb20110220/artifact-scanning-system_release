# ============================================================
# dedup.py —— 去重（阶段 1.2）
# 1) 文本去重：基于规范化 title|artist|date（跨源合并重复）
# 2) pHash 图片去重：下载 image_url 计算感知哈希，Hamming ≤ 阈值视为重复
# ============================================================
"""去重：文本相似 + 感知哈希（pHash）图片相似。"""
import io
import logging
import re

import requests

logger = logging.getLogger(__name__)

DEDUP_FIELDS = ("title", "artist", "date")


def _norm(value):
    """规范化：小写、去标点/空白（用于去重 key）。"""
    if not value:
        return ""
    return re.sub(r"[\W_]+", "", str(value).lower())


def text_key(record):
    """基于 title|artist|date 的去重 key。"""
    return "|".join(_norm(record.get(f)) for f in DEDUP_FIELDS)


def dedup_text(records):
    """文本去重：title|artist|date 规范化后相同视为重复，保留第一个。"""
    seen = set()
    out = []
    for rec in records:
        key = text_key(rec)
        if not key:
            out.append(rec)   # 无有效 key（如缺 title）保留
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def phash_dedup(records, threshold=5, proxy=None):
    """pHash 图片去重。

    - 对每条有 image_url 的记录下载图片并计算感知哈希；
    - 与已保留记录的哈希比较，Hamming 距离 ≤ threshold 视为重复丢弃；
    - 无图 / 下载或解析失败：保留记录（不做 hash 去重）。
    返回 (去重后记录, 参与 hash 比对的图片数)。
    """
    from PIL import Image
    import imagehash

    out = []
    seen_hashes = []   # [(phash, record_id)]
    checked = 0
    proxies = {"http": proxy, "https": proxy} if proxy else None

    for rec in records:
        url = rec.get("image_url")
        if not url:
            out.append(rec)
            continue
        try:
            resp = requests.get(url, timeout=15, proxies=proxies)
            if resp.status_code != 200:
                out.append(rec)
                continue
            img = Image.open(io.BytesIO(resp.content))
            h = imagehash.phash(img)
            checked += 1
            if any((h - other) <= threshold for other, _ in seen_hashes):
                logger.info("pHash 命中重复：%s（丢弃）", rec.get("id"))
                continue
            seen_hashes.append((h, rec.get("id")))
            out.append(rec)
        except Exception as exc:
            logger.debug("pHash 处理 %s 失败：%s", rec.get("id"), exc)
            out.append(rec)
    return out, checked
