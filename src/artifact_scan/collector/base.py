# ============================================================
# base.py —— 采集器基类（阶段 1.1 多源采集器）
# 封装通用逻辑：限流 / 指数退避 / 断点续传 / 分页 / 统一字段映射
# 子类只需实现：source、get_ids、fetch_by_id、map_record
# ============================================================
"""采集器基类：限流、指数退避、断点续传、分页、统一字段映射。"""
import json
import os
import time
import logging

import requests

logger = logging.getLogger(__name__)

# 统一字段 schema（供 1.2 清洗 / 1.3 标注使用；缺省为 None）
COMMON_FIELDS = [
    "id", "source", "title", "artist", "culture", "period",
    "date", "medium", "dimensions", "image_url", "url",
    "description", "object_id",
]


class BaseCollector:
    """所有采集器的公共逻辑。

    子类需实现：
      - ``source``       : 来源名（如 ``"met"``）
      - ``get_ids()``    : 返回待采集对象 id 列表（去重）
      - ``fetch_by_id``  : 按 id 拉取单个对象的原始字典
      - ``map_record``   : 将原始字典映射为统一 schema 字典
    """

    source = "base"
    rate_limit = 1.0      # 每请求最小间隔（秒），用于限流
    max_retries = 5       # 指数退避最大重试次数
    timeout = 30          # HTTP 超时（秒）
    checkpoints_every = 50  # 每采 N 条保存一次断点
    mode = "ids"          # 采集模式："ids"（先取 id 再逐条详情）/"pages"（分页直接取记录）

    def __init__(self, out_dir, proxy=None, limit=None, resume=True, api_key=None, query=None):
        self.out_dir = out_dir
        self.proxy = proxy
        self.limit = limit            # 最多采集多少条（None=全部）
        self.resume = resume          # 是否启用断点续传
        self.api_key = api_key        # 部分 API 需要 key
        self.query = query            # 关键词（部分来源使用）
        self.done_ids = set()
        self.records_file = os.path.join(
            out_dir, self.source, "records.ndjson")
        self.checkpoint_file = os.path.join(
            out_dir, self.source, ".checkpoint.json")

        # requests 会话（复用连接；可选代理）
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        if resume:
            self._load_checkpoint()

    # ------------------------------------------------------------
    # 请求：限流 + 指数退避重试
    # ------------------------------------------------------------
    def _request(self, url, **kwargs):
        """带限流与指数退避的 GET 请求；429 / 5xx 自动退避重试。"""
        for attempt in range(self.max_retries + 1):
            self._rate_limit()
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429 or resp.status_code >= 500:
                    # 退避：2 的 attempt 次幂 + 随机抖动，上限 60s
                    wait = min(2 ** attempt, 60) + (attempt and 0.5 or 0)
                    logger.warning("%s 返回 %s，%s 秒后重试（第 %s 次）",
                                   url, resp.status_code, round(wait, 1), attempt + 1)
                    time.sleep(wait)
                    continue
                # 其他错误：记录并返回空
                logger.error("%s 返回 %s", url, resp.status_code)
                resp.raise_for_status()
            except requests.RequestException as exc:
                wait = min(2 ** attempt, 60)
                logger.warning("请求 %s 异常：%s，%s 秒后重试", url, exc, wait)
                time.sleep(wait)
        return None

    def _rate_limit(self):
        """限流：每请求最小间隔（供子类覆盖或调整）。"""
        time.sleep(self.rate_limit)

    # ------------------------------------------------------------
    # 断点续传
    # ------------------------------------------------------------
    def _load_checkpoint(self):
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, "r", encoding="utf-8") as fh:
                self.done_ids = set(json.load(fh).get("done_ids", []))
            logger.info("%s 断点续传：已采 %s 条", self.source, len(self.done_ids))

    def _save_checkpoint(self):
        os.makedirs(os.path.dirname(self.checkpoint_file), exist_ok=True)
        with open(self.checkpoint_file, "w", encoding="utf-8") as fh:
            json.dump({"source": self.source, "done_ids": sorted(self.done_ids)},
                      fh, ensure_ascii=False)
        logger.info("%s 断点已保存：共 %s 条", self.source, len(self.done_ids))

    # ------------------------------------------------------------
    # 主采集流程（按 mode 分发：ids / pages）
    # ------------------------------------------------------------
    def collect(self):
        """获取记录 → 落盘 ndjson + 断点。"""
        os.makedirs(os.path.dirname(self.records_file), exist_ok=True)
        written = 0
        with open(self.records_file, "a", encoding="utf-8") as fh:
            if self.mode == "pages":
                written = self._collect_pages(fh)
            else:
                written = self._collect_ids(fh)
        self._save_checkpoint()
        logger.info("%s 采集完成：本次新增 %s 条（累计 %s 条）。",
                    self.source, written, len(self.done_ids))

    def _collect_ids(self, fh):
        """模式 A（ids）：先取 id 列表，再逐条拉详情。"""
        ids = self.get_ids()
        if self.limit:
            ids = ids[: self.limit]
        written = 0
        for rid in ids:
            if rid in self.done_ids:
                continue
            raw = self.fetch_by_id(rid)
            if raw is None:
                continue
            record = self.map_record(rid, raw)
            if record is None:
                continue
            written += self._emit(record, fh)
            if written % self.checkpoints_every == 0:
                fh.flush()
                self._save_checkpoint()
        return written

    def _collect_pages(self, fh):
        """模式 B（pages）：分页拉取已映射记录，offset 递增。"""
        offset = 0
        written = 0
        while True:
            page = self.fetch_page(offset)
            if not page:
                break
            for record in page:
                if self.limit and written >= self.limit:
                    break
                rid = record.get("id")
                if rid in self.done_ids:
                    continue
                written += self._emit(record, fh)
                if written % self.checkpoints_every == 0:
                    fh.flush()
                    self._save_checkpoint()
            offset += len(page)
            if self.limit and written >= self.limit:
                break
        return written

    def _emit(self, record, fh):
        """写一条记录并标记 done，返回本次新增数（0/1）。"""
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.done_ids.add(record["id"])
        return 1

    # ------------------------------------------------------------
    # 子类需实现
    # ------------------------------------------------------------
    def get_ids(self):
        """[ids 模式] 返回待采集对象 id 列表。"""
        raise NotImplementedError

    def fetch_by_id(self, rid):
        """[ids 模式] 按 id 拉取单个对象原始字典，失败返回 None。"""
        raise NotImplementedError

    def map_record(self, rid, raw):
        """[ids 模式] 将原始字典映射为统一 schema 字典，跳过无效记录返回 None。"""
        raise NotImplementedError

    def fetch_page(self, offset):
        """[pages 模式] 返回一页已映射记录列表；无更多返回空列表。"""
        raise NotImplementedError

    def _new_record(self, rid, raw):
        """构造统一 schema 字典（子类在 map_record 中填充字段）。"""
        return {field: None for field in COMMON_FIELDS} | {"id": rid, "source": self.source}
