# ============================================================
# normalize.py —— 格式标准化（阶段 1.2）
# 统一字段：去除多余空白、清理 culture 的 {}、id 转字符串
# ============================================================
"""格式标准化：清洗字段格式，统一 schema。"""
import re

TEXT_FIELDS = [
    "title", "artist", "culture", "period", "date",
    "medium", "dimensions", "url", "description",
]


def clean_text(value):
    """去除首尾空白、压缩内部空白、去换行；空串返回 None。"""
    if value is None:
        return None
    s = str(value).replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def clean_culture(value):
    """culture 特殊清洗：去除形如 '{America}' 的大括号。"""
    s = clean_text(value)
    if s is None:
        return None
    return s.strip("{}").strip() or None


def normalize(record):
    """返回标准化后的记录（浅拷贝）。"""
    rec = dict(record)
    for field in TEXT_FIELDS:
        if field == "culture":
            rec[field] = clean_culture(rec.get(field))
        else:
            rec[field] = clean_text(rec.get(field))
    if rec.get("id") is not None:
        rec["id"] = str(rec["id"])
    return rec
