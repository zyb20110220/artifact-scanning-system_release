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
KEY_URL = "https://api.data.gov/signup"  # 经 api.data.gov 注册获取 key

MAX_ROWS = 1000  # Smithsonian 单次 rows 上限


class SmithsonianCollector(BaseCollector):
    """Smithsonian 采集器：按关键词搜索并分页拉取。"""

    source = "smithsonian"
    mode = "pages"
    page_size = 100

    def __init__(self, out_dir, query="chinese", **kwargs):
        # 先调 super（避免其 query=None 默认值覆盖），再设关键词
        super().__init__(out_dir, **kwargs)
        self.query = query

    def fetch_page(self, offset):
        if not self.api_key:
            logger.error("Smithsonian API 需要 api_key（申请：%s），可用 --api-key 传入", KEY_URL)
            return []
        start = offset  # Smithsonian start 从 0 开始
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
        freetext = content.get("freetext", {})

        rec["id"] = r.get("id")
        rec["source"] = self.source
        rec["title"] = r.get("title") or dnr.get("title", {}).get("content")
        rec["artist"] = (idx.get("artistDisplayName") or idx.get("artistName") or [None])[0]
        rec["culture"] = (idx.get("culture") or [None])[0]
        rec["date"] = (idx.get("date") or [None])[0]
        rec["medium"] = ", ".join(idx.get("object_type") or [])
        rec["image_url"] = self._first_media(dnr)
        rec["url"] = self._record_url(r, dnr)
        rec["description"] = self._freetext_value(freetext, "physicalDescription")
        rec["object_id"] = r.get("id")
        return rec

    @staticmethod
    def _first_media(dnr):
        """图片：online_media.media[] 第一个 content。"""
        media = dnr.get("online_media", {}).get("media", []) or []
        for m in media:
            content = m.get("content") if isinstance(m, dict) else None
            if content:
                return content
        return None

    @staticmethod
    def _record_url(r, dnr):
        """详情链接：优先 record_link，其次 edanmdm 标识符转官网链接。"""
        rl = dnr.get("record_link")
        if rl:
            return rl
        rid = r.get("url")
        if rid and str(rid).startswith("edanmdm:"):
            return "https://www.si.edu/object/" + str(rid)
        return rid

    @staticmethod
    def _freetext_value(freetext, key):
        """freetext 字段为 [{label, content}]，取第一个 content。"""
        for it in freetext.get(key) or []:
            if isinstance(it, dict) and it.get("content"):
                return it["content"]
        return None
