# ============================================================
# cli.py —— 特征提取命令行入口（阶段 2.1）
# 用法：python -m artifact_scan.feature.cli \
#         --annotated data/annotated/records.ndjson \
#         --out data/features --model dinov2-base \
#         --proxy http://127.0.0.1:7897 [--limit 100]
# ============================================================
"""特征提取命令行入口。"""
import argparse
import logging

from .extract import extract_dataset


def build_parser():
    parser = argparse.ArgumentParser(
        description="特征提取（阶段 2.1：DINOv2 批量提取 + L2 归一化）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--annotated", default="data/annotated/records.ndjson",
                        help="标注数据输入文件")
    parser.add_argument("--out", default="data/features", help="输出目录")
    parser.add_argument("--model", default="dinov2-base",
                        choices=["dinov2-base", "dinov2-small",
                                 "dinov2-registers-base", "siglip-base"],
                        help="特征模型")
    parser.add_argument("--proxy", default=None, help="HTTP 代理（下载图片）")
    parser.add_argument("--limit", type=int, default=None, help="最多处理记录条数")
    parser.add_argument("--batch", type=int, default=16, help="推理批大小")
    parser.add_argument("--pool", default="cls", choices=["cls", "gem", "pooled"],
                        help="特征聚合方式：cls(pooler)/gem(GeM)/pooled(平均)")
    parser.add_argument("--image-dir", default=None,
                        help="图片缓存目录（缺省为 <out>/images，可复用已有缓存）")
    parser.add_argument("--verbose", action="store_true", help="调试日志")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    stats = extract_dataset(
        args.annotated, args.out,
        model_name=args.model,
        proxy=args.proxy,
        limit=args.limit,
        batch=args.batch,
        pool=args.pool,
        image_dir=args.image_dir,
    )
    print("特征提取统计：")
    for k, v in stats.items():
        print("  %s: %s" % (k, v))


if __name__ == "__main__":
    main()
