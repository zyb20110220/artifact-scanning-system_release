# ============================================================
# cli.py —— 标注命令行入口（阶段 1.3）
# 用法：python -m artifact_scan.annotate.cli \
#         --input data/clean/records.ndjson --output data/annotated/records.ndjson \
#         [--wikidata --proxy ...]
# ============================================================
"""标注体系命令行入口。"""
import argparse
import json
import logging
import os

from .engine import annotate_all
from .wikidata import enrich_all


def build_parser():
    parser = argparse.ArgumentParser(
        description="标注体系（阶段 1.3：5 级标签 + Wikidata 补全）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", default="data/clean/records.ndjson",
                        help="清洗后输入文件")
    parser.add_argument("--output", default="data/annotated/records.ndjson",
                        help="标注后输出文件")
    parser.add_argument("--wikidata", action="store_true",
                        help="启用 Wikidata 补全缺失文化标签")
    parser.add_argument("--proxy", default=None,
                        help="HTTP 代理（Wikidata 查询用）")
    parser.add_argument("--verbose", action="store_true", help="调试日志")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    with open(args.input, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]

    records = annotate_all(records)
    enriched = 0
    if args.wikidata:
        records, enriched = enrich_all(records, args.proxy)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    logging.info("标注完成：%s 条 → %s（Wikidata 补全 %s 条）",
                 len(records), args.output, enriched)


if __name__ == "__main__":
    main()
