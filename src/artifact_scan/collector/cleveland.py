# ============================================================
# cleveland.py —— Cleveland Museum of Art 采集器（阶段 1.1）
# 端点：openaccess-api.clevelandart.org/api/artworks（免 key）
# 模式：pages（分页 /artworks?skip&limit）
# ============================================================
"""Cleveland Museum of Art 采集器（Open Access，无需 key）。"""
import logging

from .base import BaseCollector, COMMON_FIELDS

logger = logging.getLogger(__name__)

API_URL = "https://openaccess-api.clevelandart.org/api/artworks/"


class ClevelandCollector(BaseCollector):
    """Cleveland 采集器：分页拉取开放访问馆藏。"""

    source = "cleveland"
    mode = "pages"
    page_size = 100

    def fetch_page(self, offset):
        params = {"limit": self.page_size, "skip": offset}
        resp = self._request(API_URL, params=params)
        if resp is None:
            return []
        data = resp.json().get("data") or []
        return [self._map(a) for a in data if a.get("id")]

    def _map(self, a):
        rec = {field: None for field in COMMON_FIELDS}
        creators = a.get("creators") or []
        img = (a.get("images") or {}).get("web") or {}
        culture = a.get("culture")
        if isinstance(culture, list):      # 兼容列表，如 ["America"]
            culture = " ".join(culture)
        rec["id"] = a.get("id")
        rec["source"] = self.source
        rec["title"] = a.get("title")
        rec["artist"] = creators[0].get("description") if creators else None
        rec["culture"] = (culture or "").strip("{}")  # 形如 "{America}"
        rec["date"] = a.get("creation_date")
        rec["medium"] = a.get("medium")
        rec["dimensions"] = a.get("measurements")
        rec["image_url"] = img.get("url")
        rec["url"] = a.get("url")
        rec["description"] = a.get("description")
        rec["object_id"] = a.get("id")
        return rec
