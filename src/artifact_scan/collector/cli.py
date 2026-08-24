# ============================================================
# cli.py —— 采集器命令行入口（阶段 1.1）
# 用法：python -m artifact_scan.collector.cli --source met \
#         --query chinese --limit 10 --proxy http://127.0.0.1:7897
#       需要 key 的源（harvard/smithsonian/rijksmuseum）：
#         --api-key <KEY>（或设环境变量 ARTIFACT_API_KEY）
# ============================================================
"""采集器命令行入口。"""
import argparse
import logging
import os

from .met import MetCollector
from .harvard import HarvardCollector
from .cleveland import ClevelandCollector
from .smithsonian import SmithsonianCollector
from .rijksmuseum import RijksmuseumCollector

# 注册采集器：来源名 -> 采集器类
COLLECTORS = {
    "met": MetCollector,
    "harvard": HarvardCollector,
    "cleveland": ClevelandCollector,
    "smithsonian": SmithsonianCollector,
    "rijksmuseum": RijksmuseumCollector,
}


def build_parser():
    parser = argparse.ArgumentParser(
        description="多源文物数据采集器（阶段 1.1）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", required=True, choices=sorted(COLLECTORS),
                        help="数据源（%s）" % ", ".join(sorted(COLLECTORS)))
    parser.add_argument("--query", default="chinese",
                        help="关键词搜索（MET / Smithsonian 使用）")
    parser.add_argument("--out", default="data/raw",
                        help="输出目录（各来源子目录）")
    parser.add_argument("--limit", type=int, default=None,
                        help="最多采集条数（None=全部）")
    parser.add_argument("--proxy", default=None,
                        help="HTTP 代理，如 http://127.0.0.1:7897")
    parser.add_argument("--api-key", default=None,
                        help="API key（harvard/smithsonian/rijksmuseum 需要；"
                             "缺省读环境变量 ARTIFACT_API_KEY）")
    parser.add_argument("--no-resume", action="store_true",
                        help="禁用断点续传（默认启用）")
    parser.add_argument("--verbose", action="store_true", help="调试日志")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    api_key = args.api_key or os.environ.get("ARTIFACT_API_KEY")

    coll_cls = COLLECTORS[args.source]
    coll = coll_cls(
        out_dir=args.out,
        query=args.query,
        proxy=args.proxy,
        limit=args.limit,
        resume=not args.no_resume,
        api_key=api_key,
    )
    coll.collect()
    logging.info("完成：来源 %s，输出 %s/%s/records.ndjson",
                 args.source, args.out, args.source)


if __name__ == "__main__":
    main()
