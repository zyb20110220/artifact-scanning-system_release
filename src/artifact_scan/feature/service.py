# ============================================================
# service.py —— gRPC 特征提取服务实现（阶段 2.1）
# 模型缓存：按模型名懒加载并常驻，避免每次请求重新加载权重。
# 接收：图像字节 / URL；返回：L2 归一化特征向量。
# ============================================================
"""gRPC 特征提取服务：FeatureService 实现。"""
import io
import logging

import grpc
import requests
from PIL import Image

from . import feature_pb2, feature_pb2_grpc
from .model import FeatureModel

logger = logging.getLogger(__name__)

_UA = "artifact-scanning-system/0.1 (feature gRPC)"


def _download_bytes(url, proxy=None, timeout=30):
    """下载图像为 bytes，失败抛异常。"""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.get(url, timeout=timeout, proxies=proxies,
                        headers={"User-Agent": _UA}, stream=True)
    resp.raise_for_status()
    return resp.content


class FeatureServicer(feature_pb2_grpc.FeatureServiceServicer):
    """实现 FeatureService。服务启动时按需加载模型并缓存。"""

    def __init__(self, default_model="dinov2-base", proxy=None):
        self._models = {}      # 模型名 -> FeatureModel（缓存）
        self._default = default_model
        self._proxy = proxy

    def _get_model(self, name):
        """按名懒加载模型（模型缓存）。"""
        name = name or self._default
        if name not in self._models:
            logger.info("加载模型 %s 并缓存", name)
            self._models[name] = FeatureModel(name, device="cpu")
        return self._models[name]

    # ------------------------------------------------------------
    # ExtractFeatures
    # ------------------------------------------------------------
    def ExtractFeatures(self, request, context):
        model = self._get_model(request.model)
        images, errors = [], []

        # 字节图像
        for b in request.image:
            try:
                images.append(Image.open(io.BytesIO(b)).convert("RGB"))
                errors.append("")
            except Exception as exc:
                errors.append("图像解码失败: %s" % exc)
        # URL 图像
        for url in request.image_url:
            try:
                data = _download_bytes(url, proxy=self._proxy)
                images.append(Image.open(io.BytesIO(data)).convert("RGB"))
                errors.append("")
            except Exception as exc:
                errors.append("URL 下载失败: %s" % exc)

        reply = feature_pb2.ExtractReply(dim=model.dim)
        if images:
            feats = model.extract(images)
        else:
            feats = []
        for i, f in enumerate(feats):
            reply.features.add(vector=f.tolist())
        # 补齐错误（无图项为空向量，errors 对齐请求数）
        for e in errors:
            reply.errors.append(e)
        logger.info("ExtractFeatures: %s 张图（模型 %s, %d 维）",
                    len(images), model.name, model.dim)
        return reply

    # ------------------------------------------------------------
    # GetModelInfo
    # ------------------------------------------------------------
    def GetModelInfo(self, request, context):
        model = self._get_model(request.model)
        return feature_pb2.ModelInfoReply(
            model=model.name, dim=model.dim, device=model.device)
