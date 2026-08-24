# ============================================================
# met.py —— MET 大都会艺术博物馆采集器（阶段 1.1）
# 端点：collectionapi.metmuseum.org/public/collection/v1
# 继承 BaseCollector，仅实现 get_ids / fetch_by_id / map_record
# ============================================================
"""MET 大都会艺术博物馆采集器。"""
import logging

from .base import BaseCollector

logger = logging.getLogger(__name__)

API_BASE = "https://collectionapi.metmuseum.org/public/collection/v1"
SEARCH_URL = API_BASE + "/search?q={query}"
OBJECT_URL = API_BASE + "/objects/{object_id}"


class MetCollector(BaseCollector):
    """MET 采集器：按关键词搜索对象 id，再逐条拉取详情。"""

    source = "met"

    def __init__(self, out_dir, query="chinese", **kwargs):
        # 先调 super（避免其 query=None 默认值覆盖），再设关键词
        super().__init__(out_dir, **kwargs)
        self.query = query

    def get_ids(self):
        """按关键词搜索，返回匹配的 objectID 列表。"""
        url = SEARCH_URL.format(query=self.query)
        resp = self._request(url)
        if resp is None:
            return []
        data = resp.json()
        ids = data.get("objectIDs") or []
        logger.info("%s 搜索 '%s' 命中 %s 个对象", self.source, self.query, len(ids))
        return ids

    def fetch_by_id(self, rid):
        url = OBJECT_URL.format(object_id=rid)
        resp = self._request(url)
        if resp is None:
            return None
        return resp.json()

    def map_record(self, rid, raw):
        """把 MET 原始字段映射为统一 schema。"""
        if not raw or not raw.get("objectID"):
            return None
        rec = self._new_record(rid, raw)
        rec["id"] = raw.get("objectID")
        rec["title"] = raw.get("title")
        rec["artist"] = raw.get("artistDisplayName")
        rec["culture"] = raw.get("culture")
        rec["period"] = raw.get("period")
        rec["date"] = raw.get("objectDate")
        rec["medium"] = raw.get("medium")
        rec["dimensions"] = raw.get("dimensions")
        rec["image_url"] = raw.get("primaryImage") or raw.get("primaryImageSmall")
        rec["url"] = raw.get("objectURL")
        rec["description"] = raw.get("description")
        rec["object_id"] = raw.get("objectID")
        return rec
