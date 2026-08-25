# 特征提取（阶段 2.1 / 2.2）

> 对标注数据中的文物图片做预训练模型特征提取，输出 L2 归一化向量，
> 为后续向量库（Milvus）、检索与对比学习提供基础。

## 模块结构

```
src/artifact_scan/feature/
├── model.py        # FeatureModel：模型加载 + 缓存 + 特征提取（DINOv2/SigLIP）
├── extract.py      # 批量特征提取：标注数据 → features.npy + meta.ndjson
├── service.py      # gRPC 特征提取服务（模型懒加载缓存）
├── server.py       # gRPC 服务启动入口
├── client.py       # gRPC 测试客户端
├── cli.py          # 批量提取命令行
├── proto/feature.proto  # gRPC 接口定义（feature_pb2 / feature_pb2_grpc）
└── __init__.py
```

## 支持的模型

| 名称 | HF 仓库 | 维度 | 类型 | 特征方式 |
|------|---------|------|------|---------|
| `dinov2-base` | facebook/dinov2-base | 768 | dinov2 | CLS token |
| `dinov2-small` | facebook/dinov2-small | 384 | dinov2 | CLS token |
| `dinov2-registers-base` | facebook/dinov2-with-registers-base | 768 | dinov2 | CLS token |
| `siglip-base` | google/siglip-base-patch16-224 | 768 | siglip | vision pooler |

> 本项目宿主机为 CPU，请安装 CPU 版依赖：
> `pip install -e ".[feature]" --index-url https://download.pytorch.org/whl/cpu`
> （torch 2.13.0+cpu / torchvision 0.28.0+cpu / transformers 5.15.1）

## 批量提取

```powershell
$env:PYTHONPATH = "src"
python -m artifact_scan.feature.cli `
  --annotated data/annotated/records.ndjson `
  --out data/features --model dinov2-base `
  --proxy http://127.0.0.1:7897 [--limit 100]
```

- 读取标注 ndjson，仅处理含 `image_url` 的记录
- 下载图片到 `data/features/images/`（支持代理、UA、重试、缓存命中跳过）
- 提取 CLS / pooler 特征，L2 归一化
- 输出：`data/features/features.npy`（N×768，float32）、`data/features/meta.ndjson`

## gRPC 特征服务

服务端常驻缓存模型（按模型名懒加载），接收图像字节或 URL，返回特征向量。

启动：
```powershell
python -m artifact_scan.feature.server --port 50051 --model dinov2-base [--proxy ...]
```

客户端测试：
```powershell
python -m artifact_scan.feature.client --port 50051 `
  --image data/features/images/cleveland_94979.jpg --model dinov2-base
```

接口（`proto/feature.proto`）：
- `ExtractFeatures`：`image`（字节）/ `image_url`（URL）/ `model` → 特征向量列表
- `GetModelInfo`：模型名 → 维度、设备

## 输出与数据管理

- `features.npy` / `meta.ndjson` 为大数据产物，由 DVC 管理（`data/features/*.dvc`），
  不入 git；`data/features/images/` 为可重建缓存，`data/.gitignore` 忽略
- 模型权重缓存在 `~/.cache/huggingface`（DINOv2 ~346MB / SigLIP ~813MB）

## gRPC 重生成代码

修改 `proto/feature.proto` 后：
```powershell
python -m grpc_tools.protoc -I src/artifact_scan/feature/proto `
  --python_out=src/artifact_scan/feature `
  --grpc_python_out=src/artifact_scan/feature `
  src/artifact_scan/feature/proto/feature.proto
```
> 生成后将 `feature_pb2_grpc.py` 中 `import feature_pb2` 改为 `from . import feature_pb2`（包内导入）。
