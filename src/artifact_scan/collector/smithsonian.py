# ============================================================
# smithsonian.py —— Smithsonian Open Access 采集器（阶段 1.1）
# 端点：api.si.edu/openaccess/api/v1.0/search（需 API key）
# 模式：pages（分页 /search?start&rows）
# ============================================================
"""Smithsonian Open Access 采集器（需 API key）。"""
import logging

from .base import BaseCollector, COMMON_FIELDS

logger = logging.getLogger(__name__)

API_URL = "https://api.si.edu/openaccess/api/v1.0/search"
KEY_URL = "https://library.si.edu/register"

MAX_ROWS = 1000  # Smithsonian 单次 rows 上限


class SmithsonianCollector(BaseCollector):
    """Smithsonian 采集器：按关键词搜索并分页拉取。"""

    source = "smithsonian"
    mode = "pages"
    page_size = 100

    def __init__(self, out_dir, query="chinese", **kwargs):
        self.query = query
        super().__init__(out_dir, **kwargs)

    def fetch_page(self, offset):
        if not self.api_key:
            logger.error("Smithsonian API 需要 api_key（申请：%s），可用 --api-key 传入", KEY_URL)
            return []
        start = offset + 1  # start 从 1 开始
        params = {
            "q": self.query,
            "api_key": self.api_key,
            "start": start,
            "rows": self.page_size,
        }
        resp = self._request(API_URL, params=params)
        if resp is None:
            return []
        rows = resp.json().get("response", {}).get("rows") or []
        return [self._map(r) for r in rows if r.get("id")]

    def _map(self, r):
        rec = {field: None for field in COMMON_FIELDS}
        content = r.get("content", {})
        dnr = content.get("descriptiveNonRepeating", {})
        idx = content.get("indexedStructured", {})

        # 图片：media 列表取第一个
        media = dnr.get("online_media", {}).get("media", []) or []
        rec["id"] = r.get("id")
        rec["source"] = self.source
        rec["title"] = dnr.get("title", {}).get("text")
        rec["artist"] = (idx.get("artistName") or [None])[0]
        rec["culture"] = (idx.get("culture") or [None])[0]
        rec["date"] = dnr.get("date", {}).get("text")
        rec["medium"] = dnr.get("medium", {}).get("text")
        rec["image_url"] = media[0].get("content") if media else None
        rec["url"] = dnr.get("record_link")
        rec["description"] = dnr.get("physical_description", {}).get("text")
        rec["object_id"] = r.get("id")
        return rec
