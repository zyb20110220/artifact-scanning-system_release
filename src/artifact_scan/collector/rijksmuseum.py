# ============================================================
# rijksmuseum.py —— Rijksmuseum 采集器（阶段 1.1）
# 端点：www.rijksmuseum.nl/api/en/collection（需 API key）
# 模式：pages（分页 /collection?p&ps）
# ============================================================
"""Rijksmuseum 采集器（需 API key）。"""
import logging

from .base import BaseCollector, COMMON_FIELDS

logger = logging.getLogger(__name__)

API_URL = "https://www.rijksmuseum.nl/api/en/collection"
KEY_URL = "https://data.rijksmuseum.nl/object-metadata/api/"


class RijksmuseumCollector(BaseCollector):
    """Rijksmuseum 采集器：分页拉取馆藏。"""

    source = "rijksmuseum"
    mode = "pages"
    page_size = 100

    def fetch_page(self, offset):
        if not self.api_key:
            logger.error("Rijksmuseum API 需要 api_key（申请：%s），可用 --api-key 传入", KEY_URL)
            return []
        page = offset // self.page_size + 1  # p 从 1 开始
        params = {"key": self.api_key, "p": page, "ps": self.page_size}
        resp = self._request(API_URL, params=params)
        if resp is None:
            return []
        art = resp.json().get("artObjects") or []
        return [self._map(a) for a in art if a.get("objectNumber")]

    def _map(self, a):
        rec = {field: None for field in COMMON_FIELDS}
        rec["id"] = a.get("objectNumber")
        rec["source"] = self.source
        rec["title"] = a.get("title")
        rec["artist"] = a.get("principalOrFirstMaker")
        # longTitle 形如 "De Nachtwacht, Rembrandt van Rijn, 1642" —— 提取年代
        long_title = a.get("longTitle") or ""
        rec["date"] = self._extract_date(long_title)
        rec["medium"] = ", ".join(a.get("objectTypes") or [])
        rec["image_url"] = (a.get("webImage") or {}).get("url")
        rec["url"] = (a.get("links") or {}).get("web")
        rec["object_id"] = a.get("objectNumber")
        return rec

    @staticmethod
    def _extract_date(long_title):
        """从 longTitle 末尾提取 4 位年代（尽力而为）。"""
        import re
        match = re.search(r"(\d{3,4})\s*$", long_title.strip())
        return match.group(1) if match else None
