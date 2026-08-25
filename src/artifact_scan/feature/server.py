# ============================================================
# server.py —— gRPC 特征服务启动入口（阶段 2.1）
# 用法：python -m artifact_scan.feature.server \
#         --port 50051 --model dinov2-base [--proxy ...]
# ============================================================
"""gRPC 特征服务启动入口。"""
import argparse
import logging
from concurrent import futures

import grpc

from . import feature_pb2_grpc
from .service import FeatureServicer


def build_parser():
    parser = argparse.ArgumentParser(
        description="gRPC 特征提取服务（阶段 2.1）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=50051, help="gRPC 端口")
    parser.add_argument("--model", default="dinov2-base", help="默认特征模型")
    parser.add_argument("--proxy", default=None, help="HTTP 代理（下载 URL 图像）")
    parser.add_argument("--verbose", action="store_true", help="调试日志")
    return parser


def serve(port=50051, model="dinov2-base", proxy=None, max_workers=4):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    feature_pb2_grpc.add_FeatureServiceServicer_to_server(
        FeatureServicer(default_model=model, proxy=proxy), server)
    # 绑定 0.0.0.0 以同时接受 IPv4/IPv6（Windows 上 [::] 仅监听 IPv6）
    server.add_insecure_port("0.0.0.0:%d" % port)
    logging.info("gRPC 特征服务启动，端口 %d，默认模型 %s，代理 %s",
                 port, model, proxy or "(无)")
    server.start()
    return server


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    serve(port=args.port, model=args.model, proxy=args.proxy)
    server = None
    try:
        import time
        while True:
            time.sleep(60 * 60)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
