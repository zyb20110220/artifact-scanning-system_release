# ============================================================
# client.py —— gRPC 特征服务客户端（阶段 2.1 验证）
# 用法：python -m artifact_scan.feature.client --port 50051 \
#         --image <path> [--url <image_url>] [--model dinov2-base]
# ============================================================
"""gRPC 特征服务测试客户端。"""
import argparse

import grpc

from . import feature_pb2, feature_pb2_grpc


def build_parser():
    parser = argparse.ArgumentParser(description="gRPC 特征客户端（验证）")
    parser.add_argument("--port", type=int, default=50051, help="服务端口")
    parser.add_argument("--host", default="127.0.0.1", help="服务地址")
    parser.add_argument("--image", action="append",
                        default=[], help="图像文件路径（可多次）")
    parser.add_argument("--url", action="append",
                        default=[], help="图像 URL（可多次）")
    parser.add_argument("--model", default="dinov2-base", help="模型名")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    channel = grpc.insecure_channel("%s:%d" % (args.host, args.port))
    stub = feature_pb2_grpc.FeatureServiceStub(channel)

    req = feature_pb2.ExtractRequest(model=args.model)
    for p in args.image:
        with open(p, "rb") as fh:
            req.image.append(fh.read())
    for u in args.url:
        req.image_url.append(u)

    reply = stub.ExtractFeatures(req)
    print("dim =", reply.dim, "n =", len(reply.features))
    for i, f in enumerate(reply.features):
        err = reply.errors[i] if i < len(reply.errors) else ""
        print("  [%d] %s 前5维=%s" % (i, err or "OK", f.vector[:5]))


if __name__ == "__main__":
    main()
