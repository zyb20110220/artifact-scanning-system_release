# ============================================================
# model.py —— 特征模型加载器（阶段 2.1 / 2.2）
# 封装 DINOv2 / SigLIP 模型与图像处理器，带模型缓存与设备管理。
# 统一输入：PIL.Image 或图像路径；输出：L2 归一化特征向量。
# ============================================================
"""特征模型加载器：按名称加载预训练模型，输出归一化特征。"""
import logging
import os

from PIL import Image
from transformers import AutoImageProcessor, AutoModel

logger = logging.getLogger(__name__)

# 模型注册表：名称 -> (HF 仓库, 维度, 类型)
# 类型用于选择特征提取方式：dinov2 用 CLS token；siglip 用 vision pooler
_MODEL_REGISTRY = {
    "dinov2-base": ("facebook/dinov2-base", 768, "dinov2"),             # ViT-B/14
    "dinov2-small": ("facebook/dinov2-small", 384, "dinov2"),           # ViT-S/14
    "dinov2-registers-base": ("facebook/dinov2-with-registers-base", 768, "dinov2"),
    "siglip-base": ("google/siglip-base-patch16-224", 768, "siglip"),
}
_DEFAULT_NAME = "dinov2-base"


def _hf_cache_dir():
    """HF 模型缓存目录（可用环境变量覆盖）。"""
    return os.environ.get("HF_HOME", os.path.join(os.path.expanduser("~"), ".cache", "huggingface"))


class FeatureModel:
    """封装一个预训练视觉特征模型。

    - 懒加载：首次实例化下载并缓存权重（之后走本地缓存）。
    - ``extract`` / ``extract_one``：输入 PIL 图或路径，返回 L2 归一化向量。
    - 设备：默认 CPU（本项目无 GPU）；可传 ``device`` 覆盖。
    """

    def __init__(self, name=_DEFAULT_NAME, device="cpu", cache_dir=None):
        if name not in _MODEL_REGISTRY:
            raise ValueError("未知模型 %r，可选：%s" % (name, ", ".join(_MODEL_REGISTRY)))
        self.name = name
        self.repo, self.dim, self.kind = _MODEL_REGISTRY[name]
        self.device = device
        if cache_dir is None:
            cache_dir = _hf_cache_dir()
        self.cache_dir = cache_dir
        logger.info("加载特征模型 %s（%s, %d 维）到 %s",
                    name, self.repo, self.dim, self.device)
        self.processor = AutoImageProcessor.from_pretrained(
            self.repo, cache_dir=cache_dir)
        self.model = AutoModel.from_pretrained(self.repo, cache_dir=cache_dir)
        self.model.eval().to(device)
        logger.info("模型就绪：%s", name)

    # ------------------------------------------------------------
    # 特征提取
    # ------------------------------------------------------------
    def extract(self, images):
        """对一批图（PIL.Image / 路径）提取特征，返回 (N, dim) ndarray。"""
        import torch
        if not images:
            return None
        pil = [_load_img(i) for i in images]
        inputs = self.processor(images=pil, return_tensors="pt").to(self.device)
        with torch.no_grad():
            if self.kind == "siglip":
                # SigLIP 用 vision 编码器的 CLS 池化向量
                feats = self.model.vision_model(**inputs).pooler_output
            else:
                # DINOv2 用 last_hidden_state 的 CLS token
                outputs = self.model(**inputs)
                feats = outputs.last_hidden_state[:, 0, :]
        return _l2_normalize(feats.cpu().numpy())

    def extract_one(self, image):
        """提取单张图特征，返回 1-D ndarray。"""
        out = self.extract([image])
        return out[0] if out is not None else None

    def extract_pooled(self, images):
        """平均池化所有 patch token（含局部信息），常用于基线对比。"""
        import torch
        if not images:
            return None
        pil = [_load_img(i) for i in images]
        inputs = self.processor(images=pil, return_tensors="pt").to(self.device)
        with torch.no_grad():
            if self.kind == "siglip":
                h = self.model.vision_model(**inputs).last_hidden_state
            else:
                h = self.model(**inputs).last_hidden_state
        feats = h[:, 1:, :].mean(dim=1)  # 去掉 CLS，平均 patch token
        return _l2_normalize(feats.cpu().numpy())


def _load_img(src):
    """把路径 / PIL 图像统一为 RGB PIL.Image。"""
    if isinstance(src, str):
        return Image.open(src).convert("RGB")
    return src.convert("RGB")


def _l2_normalize(arr):
    """按行做 L2 归一化（避免除零）。"""
    import numpy as np
    arr = np.asarray(arr, dtype=np.float32)
    norm = np.linalg.norm(arr, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return (arr / norm).astype(np.float32)
