# ============================================================
# harvard.py —— Harvard Art Museums 采集器（阶段 1.1）
# 端点：api.harvardartmuseums.org/object（需 API key）
# 模式：pages（分页 /object?page&size）
# ============================================================
"""Harvard Art Museums 采集器（需 API key）。"""
import logging

from .base import BaseCollector, COMMON_FIELDS

logger = logging.getLogger(__name__)

API_URL = "https://api.harvardartmuseums.org/object"
KEY_URL = "https://harvardartmuseums.org/collections/api"


class HarvardCollector(BaseCollector):
    """Harvard 采集器：分页拉取对象记录。"""

    source = "harvard"
    mode = "pages"
    page_size = 100

    def fetch_page(self, offset):
        if not self.api_key:
            logger.error(
                "Harvard API 需要 api_key（申请：%s），可用 --api-key 传入", KEY_URL)
            return []
        page = offset // self.page_size + 1  # Harvard 页号从 1 开始
        params = {"apikey": self.api_key, "page": page, "size": self.page_size}
        resp = self._request(API_URL, params=params)
        if resp is None:
            return []
        records = resp.json().get("records") or []
        return [self._map(r) for r in records if r.get("id")]

    def _map(self, r):
        rec = {field: None for field in COMMON_FIELDS}
        people = r.get("people") or []
        images = r.get("images") or []
        rec["id"] = r.get("id")
        rec["source"] = self.source
        rec["title"] = r.get("title")
        rec["artist"] = people[0].get("name") if people else None
        rec["culture"] = r.get("culture")
        rec["period"] = r.get("period")
        rec["date"] = r.get("dated")
        rec["medium"] = r.get("medium")
        rec["dimensions"] = r.get("dimensions")
        rec["image_url"] = images[0].get("baseimageurl") if images else None
        rec["url"] = r.get("url")
        rec["description"] = r.get("description")
        rec["object_id"] = r.get("id")
        return rec
