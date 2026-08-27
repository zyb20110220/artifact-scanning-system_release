# ============================================================
# lora_package.py —— 阶段 5.6 数据集打包（Colab 就绪）
# 读取 data/lora/train.jsonl，把图片复制为扁平布局 images/<文件名>,
# 并改写 jsonl 中的 image 路径，生成一个可直接上传到 Colab/云端训练机的目录。
# 用法：python -m artifact_scan.lora_package --src data/lora/train.jsonl --out data/lora/colab_bundle
# ============================================================
"""LoRA 数据集打包：复制图片 + 改写路径 -> Colab 可上传的目录。"""

import argparse
import json
import logging
import os
import shutil

logger = logging.getLogger(__name__)


def _load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _save_jsonl(samples, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")


def package(src, out, zip_out=True, rewrite=True):
    """把 train.jsonl 打包为 Colab 目录：out/images/* + out/train.jsonl（路径改写）。"""
    samples = _load_jsonl(src)
    img_dir = os.path.join(out, "images")
    os.makedirs(img_dir, exist_ok=True)

    copied = 0
    missing = 0
    new_samples = []
    for s in samples:
        img = s.get("image")
        if not img or not os.path.exists(img):
            missing += 1
            continue
        base = os.path.basename(img)
        dst = os.path.join(img_dir, base)
        if not os.path.exists(dst):
            shutil.copy2(img, dst)
            copied += 1
        if rewrite:
            ns = dict(s)
            ns["image"] = f"images/{base}"
            new_samples.append(ns)
        else:
            new_samples.append(s)

    if rewrite:
        _save_jsonl(new_samples, os.path.join(out, "train.jsonl"))
    else:
        shutil.copy2(src, os.path.join(out, "train.jsonl"))

    logger.info("复制图片 %d 张，缺失 %d 条", copied, missing)
    logger.info("输出目录：%s", out)

    if zip_out:
        zkind = "/" if os.name != "nt" else "\\"
        zip_path = shutil.make_archive(out, "zip", root_dir=os.path.dirname(out),
                                       base_dir=os.path.basename(out))
        logger.info("已压缩：%s", zip_path)
        return zip_path
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="LoRA 数据集打包（阶段 5.6）")
    ap.add_argument("--src", default="data/lora/train.jsonl")
    ap.add_argument("--out", default="data/lora/colab_bundle")
    ap.add_argument("--no-zip", action="store_true", help="不打包 zip")
    ap.add_argument("--no-rewrite", action="store_true", help="不改写图片路径")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    res = package(args.src, args.out, zip_out=not args.no_zip,
                  rewrite=not args.no_rewrite)
    print("打包结果：%s" % res)


if __name__ == "__main__":
    main()
