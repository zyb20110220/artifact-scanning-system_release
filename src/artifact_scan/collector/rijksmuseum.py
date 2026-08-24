# ============================================================
# rijksmuseum.py —— Rijksmuseum 采集器（阶段 1.1）
# 新版 Data Services（Linked Art，无需 API key）：
#   Search API    https://data.rijksmuseum.nl/search/collection
#   Resolver      https://id.rijksmuseum.nl/{id}（Accept: application/json）
# 模式：pages（pageToken 分页 → 逐 id Resolver 详情）
# ============================================================
"""Rijksmuseum 采集器（新版 Data Services，无 key，Linked Art）。"""
import logging
from urllib.parse import urlparse, parse_qs

from .base import BaseCollector, COMMON_FIELDS

logger = logging.getLogger(__name__)

SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"
# Linked Art 中标题的 AAT 类型（titles）
AAT_TITLES = "http://vocab.getty.edu/aat/300404670"


class RijksmuseumCollector(BaseCollector):
    """Rijksmuseum 采集器：按类型搜索 → 分页 id → Resolver 解析 Linked Art 详情。"""

    source = "rijksmuseum"
    mode = "pages"
    page_size = 100

    def __init__(self, out_dir, query="painting", **kwargs):
        # query 用作 Linked Art 的 type 搜索条件（如 painting）
        super().__init__(out_dir, query=query, **kwargs)
        self._id_queue = []      # 待解析的 id 队列（惰性分页）
        self._next_token = None  # Search API 下一页 token

    # ------------------------------------------------------------
    # 分页：每次返回 1 条（惰性 id 队列 + pageToken 搜索分页），
    # 使 --limit 精确生效（不会一次拉整页详情）
    # ------------------------------------------------------------
    def fetch_page(self, offset):
        while True:
            if not self._id_queue and not self._load_next_page():
                return []
            lid = self._id_queue.pop(0)
            rec = self._fetch_detail(lid)
            if rec:
                return [rec]
            # 该 id 解析失败则继续下一个，不中断采集

    def _load_next_page(self):
        """搜索一页 id 填充队列；返回是否有数据。"""
        if self._next_token:
            params = {"pageToken": self._next_token}
        else:
            params = {"type": self.query or "painting"}
        resp = self._request(SEARCH_URL, params=params)
        if resp is None:
            return False
        data = resp.json()
        self._next_token = self._extract_token(data.get("next"))
        ids = [it.get("id") for it in (data.get("orderedItems") or []) if it.get("id")]
        self._id_queue.extend(ids)
        return bool(ids)

    @staticmethod
    def _extract_token(node):
        if not node:
            return None
        nid = node.get("id")
        if not nid:
            return None
        q = parse_qs(urlparse(nid).query)
        return q.get("pageToken", [None])[0]

    # ------------------------------------------------------------
    # Resolver：拉取单个对象的 Linked Art 详情（异常防御）
    # ------------------------------------------------------------
    def _fetch_detail(self, lid):
        try:
            resp = self._request(lid, headers={"Accept": "application/json"})
            if resp is None:
                return None
            return self._map_linked_art(lid, resp.json())
        except Exception as exc:
            logger.warning("解析 %s 失败：%s", lid, exc)
            return None

    def _map_linked_art(self, lid, data):
        """从 Linked Art HumanMadeObject 提取统一 schema 字段。"""
        rec = {field: None for field in COMMON_FIELDS}
        rec["id"] = lid.rsplit("/", 1)[-1] if lid else None
        rec["source"] = self.source
        rec["title"] = self._title(data)
        rec["artist"] = self._artist(data)
        rec["date"] = self._date(data)
        rec["medium"] = self._technique(data)
        rec["image_url"] = self._image(data)
        rec["url"] = lid.replace("id.rijksmuseum.nl", "www.rijksmuseum.nl/nl/collectie") \
            if lid else None
        rec["object_id"] = lid.rsplit("/", 1)[-1] if lid else None
        return rec

    # ---------- Linked Art 字段解析（健壮处理空值）----------
    def _identified_names(self, node, aat=None):
        """返回 node.identified_by 中 Name 的 content 列表（可选按 AAT 过滤）。"""
        out = []
        if not isinstance(node, dict):
            return out
        for name in node.get("identified_by") or []:
            if not isinstance(name, dict) or name.get("type") != "Name":
                continue
            if aat:
                classes = [c.get("id") for c in name.get("classified_as") or []]
                if aat not in classes:
                    continue
            if name.get("content"):
                out.append(name["content"])
        return out

    def _notation(self, node):
        """返回 node.notation 的 @value 列表（如 "paint"）。"""
        out = []
        if not isinstance(node, dict):
            return out
        for n in node.get("notation") or []:
            if isinstance(n, dict) and n.get("@value"):
                out.append(n["@value"])
        return out

    def _name_value(self, node):
        """取任意 Name 的第一个 content（兜底）。"""
        names = self._identified_names(node)
        return names[0] if names else None

    def _title(self, data):
        titles = self._identified_names(data, aat=AAT_TITLES)
        if titles:
            return titles[0]
        return self._name_value(data)

    def _date(self, data):
        ts = ((data.get("produced_by") or {}).get("timespan")) or {}
        names = self._identified_names(ts)
        return names[0] if names else None

    def _artist(self, data):
        """艺术家：part[].carried_out_by 或 produced_by.carried_out_by →
        兜底 produced_by.referred_to_by（AAT 300435416 = attribution）。"""
        produced = data.get("produced_by") or {}
        containers = [produced] + (data.get("part") or [])
        for container in containers:
            if not isinstance(container, dict):
                continue
            carried = container.get("carried_out_by") or []
            if not carried:
                continue
            actor = carried[0]
            notation = actor.get("notation") or []
            if notation and notation[0].get("@value"):
                return notation[0]["@value"]
            names = self._identified_names(actor)
            if names:
                return names[0]
        for ref in produced.get("referred_to_by") or []:
            if not isinstance(ref, dict):
                continue
            classes = [c.get("id") for c in ref.get("classified_as") or []]
            if "http://vocab.getty.edu/aat/300435416" in classes and ref.get("content"):
                return ref["content"]
        return None

    def _technique(self, data):
        """材质/技法：produced_by.technique + made_of 的 notation。"""
        produced = data.get("produced_by") or {}
        values = []
        for t in produced.get("technique") or []:
            values.extend(self._notation(t))
        for m in data.get("made_of") or []:
            values.extend(self._notation(m))
        return ", ".join(dict.fromkeys(values)) if values else None

    def _image(self, data):
        # 图片通常在 representation -> digitally_shown_by -> content_url
        rep = data.get("representation") or {}
        shown = rep.get("digitally_shown_by") or []
        for img in shown:
            url = img.get("content_url")
            if url:
                return url
        return None

