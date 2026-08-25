# ============================================================
# cli.py —— 数据质量指标命令行（阶段 1.6）
# 用法：python -m artifact_scan.quality.cli \
#         [--raw data/raw] [--clean data/clean/records.ndjson] \
#         [--annotated data/annotated/records.ndjson] \
#         [--report data/quality/report.json] \
#         [--pushgateway http://127.0.0.1:9091] [--push]
# ============================================================
"""数据质量指标命令行入口。"""
import argparse
import json
import logging
import os

import requests

from .metrics import compute, to_prom_text

logger = logging.getLogger(__name__)


def build_parser():
    parser = argparse.ArgumentParser(
        description="数据质量指标（阶段 1.6）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--raw", default="data/raw", help="原始数据目录")
    parser.add_argument(
        "--clean", default="data/clean/records.ndjson", help="清洗数据文件")
    parser.add_argument(
        "--annotated", default="data/annotated/records.ndjson", help="标注数据文件")
    parser.add_argument(
        "--report", default="data/quality/report.json", help="报告输出文件")
    parser.add_argument("--pushgateway", default="http://127.0.0.1:9091",
                        help="Pushgateway 地址（--push 时使用）")
    parser.add_argument("--push", action="store_true",
                        help="推送到 Pushgateway（需 --pushgateway）")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    stats = compute(args.raw, args.clean, args.annotated)

    # 输出报告
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    logger.info("报告已写入 %s", args.report)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    # 推送到 Pushgateway
    if args.push:
        prom = to_prom_text(stats)
        url = args.pushgateway.rstrip("/") + "/metrics/job/artifact_data"
        resp = requests.put(url, data=prom, timeout=15)
        resp.raise_for_status()
        logger.info("指标已推送到 %s（HTTP %s）", url, resp.status_code)


if __name__ == "__main__":
    main()
