# ============================================================
# metrics.py —— 数据质量指标计算（阶段 1.6）
# 读取 data/raw + data/clean + data/annotated，计算：
#   各源记录数 / 清洗去重数 / 字段完整率 / 标注覆盖率
# 输出：report.json（可读）+ Prometheus 文本指标（供 Pushgateway）
# ============================================================
"""数据质量指标计算。"""
import json
import logging
import os

logger = logging.getLogger(__name__)

# 统计的字段（完整率）
FIELDS = ["title", "artist", "culture", "date", "medium", "image_url", "url"]
# 统计的标签（覆盖率）
LABELS = ["period", "culture", "materials", "forms", "decorations"]


def _load_records(path):
    """读取 ndjson 文件返回记录列表。"""
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _field_completeness(records, field):
    if not records:
        return 0.0
    filled = sum(1 for r in records if r.get(field))
    return round(filled / len(records), 4)


def _label_coverage(records, label):
    if not records:
        return 0.0
    filled = sum(1 for r in records if (r.get("labels") or {}).get(label))
    return round(filled / len(records), 4)


def compute(raw_dir, clean_file, annotated_file):
    """计算数据质量指标，返回统计 dict。"""
    # 各源 raw 记录数
    sources = {}
    raw_total = 0
    if os.path.isdir(raw_dir):
        for src in sorted(os.listdir(raw_dir)):
            path = os.path.join(raw_dir, src, "records.ndjson")
            if not os.path.isfile(path):
                continue
            n = len(_load_records(path))
            if n:
                sources[src] = n
                raw_total += n

    clean = _load_records(clean_file)
    annotated = _load_records(annotated_file)

    return {
        "sources": sources,
        "raw_total": raw_total,
        "clean_total": len(clean),
        "annotated_total": len(annotated),
        "dedup_removed": raw_total - len(clean),
        "field_completeness": {f: _field_completeness(clean, f) for f in FIELDS},
        "label_coverage": {l: _label_coverage(annotated, l) for l in LABELS},
    }


def to_prom_text(stats):
    """生成 Prometheus 文本格式指标。"""
    lines = [
        "# HELP artifact_raw_records_total 各数据源原始记录数",
        "# TYPE artifact_raw_records_total gauge",
    ]
    for src, n in stats["sources"].items():
        lines.append(f'artifact_raw_records_total{{source="{src}"}} {n}')

    lines += [
        "# HELP artifact_clean_records_total 清洗后记录数",
        "# TYPE artifact_clean_records_total gauge",
        f"artifact_clean_records_total {stats['clean_total']}",
        "# HELP artifact_annotated_records_total 标注后记录数",
        "# TYPE artifact_annotated_records_total gauge",
        f"artifact_annotated_records_total {stats['annotated_total']}",
        "# HELP artifact_dedup_removed_total 去重移除数",
        "# TYPE artifact_dedup_removed_total gauge",
        f"artifact_dedup_removed_total {stats['dedup_removed']}",
        "# HELP artifact_field_completeness 字段完整率 (0-1)",
        "# TYPE artifact_field_completeness gauge",
    ]
    for field, v in stats["field_completeness"].items():
        lines.append(f'artifact_field_completeness{{field="{field}"}} {v}')

    lines += [
        "# HELP artifact_label_coverage 标签覆盖率 (0-1)",
        "# TYPE artifact_label_coverage gauge",
    ]
    for label, v in stats["label_coverage"].items():
        lines.append(f'artifact_label_coverage{{label="{label}"}} {v}')

    return "\n".join(lines) + "\n"


def to_report(stats):
    """生成人类可读统计 dict（含完整字段信息）。"""
    return stats
