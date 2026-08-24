# ============================================================
# cli.py —— 清洗管道命令行入口（阶段 1.2）
# 用法：python -m artifact_scan.cleaner.cli \
#         --input data/raw --output data/clean/records.ndjson [--phash]
# ============================================================
"""数据清洗管道命令行入口。"""
import argparse
import logging

from .pipeline import clean


def build_parser():
    parser = argparse.ArgumentParser(
        description="数据清洗管道（阶段 1.2：去重 / 质量过滤 / 标准化）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", default="data/raw",
                        help="原始数据目录（各来源子目录）")
    parser.add_argument("--output", default="data/clean/records.ndjson",
                        help="清洗后输出文件")
    parser.add_argument("--phash", action="store_true",
                        help="启用 pHash 图片去重（需下载图片）")
    parser.add_argument("--phash-threshold", type=int, default=5,
                        help="pHash Hamming 距离阈值（≤ 视为重复）")
    parser.add_argument("--proxy", default=None,
                        help="HTTP 代理（pHash 下载图片用），如 http://127.0.0.1:7897")
    parser.add_argument("--verbose", action="store_true", help="调试日志")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    stats = clean(
        args.input, args.output,
        use_phash=args.phash,
        phash_threshold=args.phash_threshold,
        proxy=args.proxy,
    )
    print("清洗统计：")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
