# ============================================================
# llm_eval.py —— 阶段 5.7 LLM 输出质量评估
# 对一组测试文物图片调用 Ollama 模型（默认 qwen2.5-vl:3b），
# 提取其断代/文化结论，与标注真值比对，输出质量指标 + JSON 报告。
# 用法：
#   python -m artifact_scan.llm_eval --n 10 --model qwen2.5-vl:3b \
#       --out data/eval/base_qlora.json
# ============================================================
"""LLM 输出质量评估：Ollama 视觉断代 vs 标注真值。"""

import argparse
import base64
import json
import logging
import os
import random

import requests

logger = logging.getLogger(__name__)

_ANNOTATED = "data/annotated/records.ndjson"
_META = "data/features/meta.ndjson"
_IMAGES = "data/features/images"
_OLLAMA = "http://127.0.0.1:11435"


def _load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _load_annotated():
    return {str(r["id"]): r for r in _load_jsonl(_ANNOTATED)}


def _load_meta():
    return {str(m["id"]): m for m in _load_jsonl(_META)}


def _image_path(meta):
    uid = meta.get("uid")
    if not uid:
        return None
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = os.path.join(_IMAGES, f"{uid}.{ext}")
        if os.path.exists(p):
            return p
    return None


def _base64(path):
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


PROMPT = (
    "请根据这幅文物图片进行断代与文化归属鉴定。"
    "请只输出一个紧凑 JSON，格式："
    '{"period":"<年代>","culture":"<文化>","confidence":<0-1>}。'
    "不要输出任何其他内容。"
)


def _extract_json(text):
    """从模型输出中抽取第一个 JSON 对象。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _norm(s):
    return (s or "").strip().lower()


def _match(gt, pred):
    """返回 (exact, contains)。"""
    gt, pred = _norm(gt), _norm(pred)
    if not gt and not pred:
        return True, True  # 双方都缺失视为一致
    if not gt or not pred:
        return False, False
    return gt == pred, (gt in pred or pred in gt)


def call_ollama(model, image_path, uri=_OLLAMA, timeout=600):
    body = {
        "model": model,
        "prompt": PROMPT,
        "images": [_base64(image_path)],
        "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 128, "temperature": 0.2},
    }
    r = requests.post(f"{uri}/api/generate", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", "")


def evaluate(model, n=10, seed=42, ids=None, uri=_OLLAMA, timeout=600):
    ann = _load_annotated()
    meta = _load_meta()

    # 可选：固定测试集；否则从带图文物中采样
    if ids:
        pool = [str(i) for i in ids if str(i) in ann and str(i) in meta]
    else:
        pool = [rid for rid in ann if rid in meta and _image_path(meta[rid])]
        random.seed(seed)
        pool = random.sample(pool, min(n, len(pool)))

    results = []
    for rid in pool:
        rec = ann[rid]
        img = _image_path(meta[rid])
        if not img:
            continue
        gt = rec.get("labels") or {}
        try:
            raw = call_ollama(model, img, uri=uri, timeout=timeout)
            parsed = _extract_json(raw) or {}
            pred_period = parsed.get("period", "")
            pred_culture = parsed.get("culture", "")
            conf = parsed.get("confidence")
        except Exception as exc:
            logger.warning("id=%s 调用失败：%s", rid, exc)
            raw, pred_period, pred_culture, conf = "", "", "", None

        results.append({
            "id": rid, "title": rec.get("title"), "source": rec.get("source"),
            "gt": {"period": gt.get("period"), "culture": gt.get("culture")},
            "pred": {"period": pred_period, "culture": pred_culture,
                     "confidence": conf},
            "raw": raw[:300],
        })

    # 汇总指标（仅对有 ground-truth 的条目计算，避免缺失真值被误判为错误）
    n_items = len(results)
    c_den = p_den = 0
    c_exact = c_cont = p_exact = p_cont = 0
    for r in results:
        if r["gt"]["culture"]:
            c_den += 1
            ce, cc = _match(r["gt"]["culture"], r["pred"]["culture"])
            c_exact += ce
            c_cont += cc
        if r["gt"]["period"]:
            p_den += 1
            pe, pc = _match(r["gt"]["period"], r["pred"]["period"])
            p_exact += pe
            p_cont += pc

    metrics = {
        "n": n_items,
        "culture_exact_acc": round(c_exact / c_den, 4) if c_den else None,
        "culture_contains_acc": round(c_cont / c_den, 4) if c_den else None,
        "period_exact_acc": round(p_exact / p_den, 4) if p_den else None,
        "period_contains_acc": round(p_cont / p_den, 4) if p_den else None,
    }
    return {"model": model, "metrics": metrics, "items": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description="LLM 输出质量评估（阶段 5.7）")
    ap.add_argument("--model", default="qwen2.5-vl:3b")
    ap.add_argument("--n", type=int, default=10, help="采样测试文物数")
    ap.add_argument("--ids", nargs="+", help="固定测试集（文物 id 列表）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--uri", default=_OLLAMA)
    ap.add_argument("--out", default="data/eval/llm_eval.json")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    report = evaluate(args.model, n=args.n, seed=args.seed, ids=args.ids,
                      uri=args.uri)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print("模型：%s" % args.model)
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print("报告已写入：%s" % args.out)


if __name__ == "__main__":
    main()
