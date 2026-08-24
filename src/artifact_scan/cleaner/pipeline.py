# ============================================================
# pipeline.py —— 清洗管道主流程（阶段 1.2）
# 流程：读取 data/raw/*/records.ndjson
#       → 质量过滤 → 格式标准化 → 文本去重 →（可选）pHash 图片去重
#       → 写入统一 data/clean/records.ndjson
# ============================================================
"""数据清洗管道。"""
import json
import logging
import os

from .quality import is_valid
from .normalize import normalize
from .dedup import dedup_text, phash_dedup

logger = logging.getLogger(__name__)


def load_raw(raw_dir):
    """读取 raw_dir 下各来源的 records.ndjson，返回记录列表。"""
    records = []
    if not os.path.isdir(raw_dir):
        return records
    for src in sorted(os.listdir(raw_dir)):
        path = os.path.join(raw_dir, src, "records.ndjson")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("跳过无效 JSON 行：%s", path)
    return records


def clean(raw_dir, out_file, use_phash=False, phash_threshold=5, proxy=None):
    """执行清洗管道，返回统计。"""
    records = load_raw(raw_dir)
    stats = {"raw": len(records)}

    # 1) 质量过滤
    records = [r for r in records if is_valid(r)]
    stats["after_filter"] = len(records)

    # 2) 格式标准化
    records = [normalize(r) for r in records]

    # 3) 文本去重（跨源合并 title|artist|date 相同）
    records = dedup_text(records)
    stats["after_text_dedup"] = len(records)

    # 4) pHash 图片去重（可选）
    if use_phash:
        records, checked = phash_dedup(records, phash_threshold, proxy)
        stats["phash_checked"] = checked
        stats["after_phash_dedup"] = len(records)

    # 写输出
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats["final"] = len(records)
    logger.info("清洗完成：%s → %s（统计：%s）", raw_dir, out_file, stats)
    return stats
