# ============================================================
# lora_data.py —— 阶段 5.5 LoRA 微调数据准备
# 从标注数据 + 本地图片生成 Qwen2.5-VL LoRA 微调指令-答案对（JSONL）。
# 输出格式：LLaVA / Qwen2-VL 兼容 conversations 格式（含 <image> 占位）。
# 用法：python -m artifact_scan.lora_data --out data/lora/train.jsonl
# ============================================================
"""LoRA 微调数据准备：标注 + 图片 -> (instruction, answer) 对。"""

import argparse
import json
import logging
import os
import random

logger = logging.getLogger(__name__)

_DATA = "data/annotated/records.ndjson"
_META = "data/features/meta.ndjson"
_IMAGES = "data/features/images"


def _load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def load_meta():
    """加载特征元数据 {id: {id, source, title, image_url, uid}}。"""
    return {str(m["id"]): m for m in _load_jsonl(_META)}


def load_annotated():
    """加载标注数据 {id: record}。"""
    return {str(r["id"]): r for r in _load_jsonl(_DATA)}


def image_path(uid):
    """由 uid（如 cleveland_94979）定位本地图片。"""
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = os.path.join(_IMAGES, f"{uid}.{ext}")
        if os.path.exists(p):
            return p.replace("\\", "/")
    return None


def _lst(v):
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if v is None:
        return []
    return [str(v)]


def _confidence(record):
    """启发式置信度：根据已知字段丰富度。"""
    lb = record.get("labels") or {}
    score = 0.5
    if lb.get("period"):
        score += 0.15
    if lb.get("culture"):
        score += 0.15
    if lb.get("materials"):
        score += 0.05
    if lb.get("forms"):
        score += 0.05
    if record.get("date"):
        score += 0.1
    return round(min(score, 0.95), 2)


# ------------------------------------------------------------------
# 各场景：instruction 模板 + answer 构建
# ------------------------------------------------------------------
_SCENARIOS = {
    "dating": {
        "instruction": "请根据这幅文物图片进行断代分析，推断其大致年代、所属时期，并说明判断依据与置信度。",
        "label_keys": ["period"],
    },
    "culture": {
        "instruction": "请根据这幅文物图片，判断其文化归属与可能的地域来源，并说明推理依据。",
        "label_keys": ["culture"],
    },
    "material": {
        "instruction": "请根据这幅文物图片，分析其材质构成与可能的制作工艺，并说明依据。",
        "label_keys": ["materials"],
    },
    "form": {
        "instruction": "请根据这幅文物图片，分析其器型类别与可能的用途，并结合描述说明。",
        "label_keys": ["forms"],
    },
    "decoration": {
        "instruction": "请根据这幅文物图片，解读其纹饰主题与象征意涵，并说明依据。",
        "label_keys": ["decorations"],
    },
    "overview": {
        "instruction": "请对这幅文物图片进行综合考古鉴定，从年代、文化归属、材质工艺、器型、纹饰等方面给出分析。",
        "label_keys": [],
    },
    "report": {
        "instruction": "请根据这幅文物图片，输出一份结构化的断代鉴定报告（JSON），包含结论与依据。",
        "label_keys": [],
    },
}


def _basis(record, keys, default="图像细节有限，需进一步实物检验"):
    """从记录提取用于作答的依据描述。"""
    lb = record.get("labels") or {}
    parts = []
    if "period" in keys and lb.get("period"):
        parts.append(f"年代判断为{lb['period']}")
    if "culture" in keys and lb.get("culture"):
        parts.append(f"文化归属为{lb['culture']}")
    if "materials" in keys and lb.get("materials"):
        parts.append(f"材质为{'、'.join(_lst(lb['materials']))}")
    if "forms" in keys and lb.get("forms"):
        parts.append(f"器型为{'、'.join(_lst(lb['forms']))}")
    if "decorations" in keys and lb.get("decorations"):
        parts.append(f"纹饰主题包括{'、'.join(_lst(lb['decorations']))}")
    return "；".join(parts) if parts else default


def _clip(s, maxlen=110):
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    if len(s) <= maxlen:
        return s
    cut = s[:maxlen]
    # 尽量在句子边界截断，避免单词/汉字被硬切
    for sep in ("。", "；", ". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > 40:
            return cut[:idx + len(sep)]
    return cut + "……"


def build_answer(record, scenario, conf):
    """按场景构建作答文本。"""
    lb = record.get("labels") or {}
    date = record.get("date") or "年代不详"
    period = lb.get("period") or "年代暂难以仅凭图片判定"
    culture = lb.get("culture") or "文化归属暂难以仅凭图片判定"
    materials = "、".join(_lst(lb.get("materials"))) or "材质暂难以从图片准确判定"
    forms = "、".join(_lst(lb.get("forms"))) or "器型暂难以从图片准确判定"
    decorations = "、".join(_lst(lb.get("decorations"))) or "纹饰主题暂难以仅凭图片准确解读"
    desc = _clip((record.get("description") or "").strip())

    if scenario == "dating":
        return (f"根据图片中展现的器型、纹饰与整体风格判断，这件文物大致属于【{period}】时期"
                f"（{date}）。其造型与装饰特征符合该时期的典型工艺面貌。"
                f"综合判断，年代判断置信度为【{conf}】，建议结合胎釉/锈蚀等微观特征进一步确认。")
    if scenario == "culture":
        return (f"从器物造型、装饰风格与工艺特征推断，该文物文化归属为【{culture}】。"
                f"其造型语言与纹饰系统具有该文化的典型特征，"
                f"故初步判定文化归属置信度为【{conf}】。")
    if scenario == "material":
        return (f"依据图片呈现的质感、色泽与纹饰表现，该文物主要材质为【{materials}】。"
                f"工艺上体现出相应的制作方式，材质判断置信度为【{conf}】。")
    if scenario == "form":
        body = f"该文物器型为【{forms}】。"
        if desc:
            body += f"结合相关描述：{desc}"
        body += f"据此推测其用途与使用场景，器型判断置信度【{conf}】。"
        return body
    if scenario == "decoration":
        return (f"该文物纹饰主题主要包含【{decorations}】。"
                f"这些纹饰通常承载相应的象征意涵与等级信息，"
                f"纹饰解读置信度为【{conf}】。")
    if scenario == "overview":
        body = (f"这是一件【{culture}】文物，年代约【{period}】（{date}）。"
                f"材质以【{materials}】为主，器型为【{forms}】，"
                f"纹饰主题包括【{decorations}】。")
        if desc:
            body += f"画面相关描述：{desc}"
        body += f"综合鉴定置信度为【{conf}】。"
        return body
    if scenario == "report":
        return json.dumps({
            "artifact": {"id": str(record.get("object_id") or record["id"]),
                         "title": record.get("title"),
                         "source": record.get("source")},
            "conclusion": {
                "period": period, "culture": culture,
                "materials": _lst(lb.get("materials")),
                "forms": _lst(lb.get("forms")),
                "date": date, "confidence": conf,
            },
            "basis": _basis(record, ["period", "culture", "materials", "forms", "decorations"]),
        }, ensure_ascii=False)
    return ""


def build_dataset(per_artifact=None, limit=None, seed=42, selected=None):
    """构建 (instruction, answer, image_path) 数据集。"""
    random.seed(seed)
    meta = load_meta()
    annotated = load_annotated()
    records = []
    for rid, m in meta.items():
        if rid not in annotated:
            continue
        p = image_path(m["uid"])
        if not p:
            continue
        rec = annotated[rid]
        conf = _confidence(rec)
        records.append((rid, rec, p, conf))

    samples = []
    for rid, rec, p, conf in records:
        lb = rec.get("labels") or {}
        for sc, cfg in _SCENARIOS.items():
            keys = cfg["label_keys"]
            if keys and not any(lb.get(k) for k in keys):
                continue
            instruction = cfg["instruction"]
            answer = build_answer(rec, sc, conf)
            if not answer:
                continue
            samples.append({
                "id": f"{rid}_{sc}",
                "image": p,
                "conversations": [
                    {"from": "human", "value": "<image>\n" + instruction},
                    {"from": "gpt", "value": answer},
                ],
                "metadata": {"artifact_id": rid, "scenario": sc,
                             "title": rec.get("title"), "source": rec.get("source")},
            })

    # 可选：按每件文物样本数控制
    if per_artifact:
        filtered = []
        from collections import defaultdict
        by_id = defaultdict(list)
        for s in samples:
            by_id[s["metadata"]["artifact_id"]].append(s)
        for rid, ss in by_id.items():
            if per_artifact > 0:
                filtered.extend(ss[:per_artifact])
            else:
                filtered.extend(ss)
        samples = filtered

    if selected:
        samples = [s for s in samples if s["metadata"]
                   ["artifact_id"] in selected]

    if limit:
        samples = samples[:limit]

    random.shuffle(samples)
    return samples


def write_jsonl(samples, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    logger.info("已写入 %d 条 -> %s", len(samples), out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="LoRA 微调数据准备（阶段 5.5）")
    ap.add_argument("--out", default="data/lora/train.jsonl",
                    help="输出 JSONL 路径")
    ap.add_argument("--per-artifact", type=int,
                    default=0, help="每件文物保留样本数（0=全部）")
    ap.add_argument("--limit", type=int, default=0, help="仅生成前 N 条（调试用）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    samples = build_dataset(per_artifact=args.per_artifact,
                            limit=args.limit, seed=args.seed)
    write_jsonl(samples, args.out)

    # 统计
    by_sc = {}
    for s in samples:
        by_sc[s["metadata"]["scenario"]] = by_sc.get(
            s["metadata"]["scenario"], 0) + 1
    logger.info("场景分布：%s", by_sc)
    print("总样本数: %d" % len(samples))


if __name__ == "__main__":
    main()
