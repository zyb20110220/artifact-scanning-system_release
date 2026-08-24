# ============================================================
# engine.py —— 标注引擎（阶段 1.3）
# 对清洗后记录生成 5 级标签：period / culture / materials / forms / decorations
# ============================================================
"""标注引擎：为记录附加 5 级标签。"""
from .labels import (
    date_to_period,
    map_culture,
    map_materials,
    map_forms,
    map_decorations,
)


def annotate(record):
    """为单条记录生成 5 级标签，附加到 ``labels`` 字段（返回新字典）。"""
    out = dict(record)
    out["labels"] = {
        "period": date_to_period(out.get("date")),
        "culture": map_culture(out.get("culture")),
        "materials": map_materials(out.get("medium")),
        "forms": map_forms(out.get("title")),
        "decorations": map_decorations(out.get("title"), out.get("description")),
    }
    return out


def annotate_all(records):
    """批量标注。"""
    return [annotate(r) for r in records]
