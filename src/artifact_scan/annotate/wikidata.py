# ============================================================
# wikidata.py —— Wikidata 补全（阶段 1.3，可选增强）
# 对缺失文化标签的记录，用 title/artist 搜索 Wikidata，
# 尝试从实体描述中识别文化。
# ============================================================
"""Wikidata 补全（可选）。"""
import logging

import requests

from .labels import map_culture

logger = logging.getLogger(__name__)

API = "https://www.wikidata.org/w/api.php"
# Wikidata 要求自定义 User-Agent（否则 403）
HEADERS = {
    "User-Agent": "artifact-scanning-system/0.1 (archaeology data collector)"}


def wb_search(term, proxy=None, limit=3):
    """wbsearchentities 搜索，返回实体列表 [{id, label, description}]。"""
    params = {
        "action": "wbsearchentities", "search": term,
        "language": "en", "format": "json", "limit": limit,
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = requests.get(API, params=params, timeout=15,
                            proxies=proxies, headers=HEADERS)
        if resp.status_code == 200:
            return resp.json().get("search", [])
    except Exception as exc:
        logger.debug("Wikidata 搜索 %s 失败：%s", term, exc)
    return []


def enrich(record, proxy=None):
    """Wikidata 补全：为缺失 culture 标签的记录尝试补全。

    返回 (记录, 是否补全成功)。
    """
    out = dict(record)
    labels = dict(out.get("labels") or {})
    out["labels"] = labels
    if labels.get("culture"):
        return out, False
    term = out.get("artist") or out.get("title")
    if not term:
        return out, False
    for res in wb_search(term, proxy):
        desc = res.get("description") or ""
        culture = map_culture(desc)
        if culture:
            labels["culture"] = culture
            return out, True
    return out, False


def enrich_all(records, proxy=None):
    """批量补全，返回 (记录列表, 补全数量)。"""
    out = []
    enriched = 0
    for rec in records:
        rec, ok = enrich(rec, proxy)
        if ok:
            enriched += 1
        out.append(rec)
    return out, enriched
