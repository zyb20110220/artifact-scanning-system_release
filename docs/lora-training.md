# LoRA 微调与本地部署指南（阶段 5.6）

本文档打通「云端 GPU 训练 → 本地 Ollama 部署」全链路。

## 0. 全局约定

- 数据集：`data/lora/train.jsonl`（2263 条，LLaVA/Qwen2-VL 兼容格式，由 `lora_data.py` 生成）
- 基座模型：**Qwen2.5-VL-3B**（与本机 Ollama 的 `qwen2.5-vl:3b` 一致，保证落地可行）
- 训练：需 **NVIDIA GPU**（本机无 → 用 Colab/云端）
- 本地部署：本机 Ollama 已可用（CPU 推理，已实测 3B 一张图 ~150s）

---

## 1. 打包数据集（Colab 就绪）

训练机（Colab）无法访问本机 `data/features/images/`，需先打包图片与 jsonl：

```powershell
# 项目根目录，设置 PYTHONPATH
$env:PYTHONPATH="src"
python -m artifact_scan.lora_package --src data/lora/train.jsonl --out data/lora/colab_bundle
```

产物：
- `data/lora/colab_bundle/train.jsonl`（`image` 路径已改写为 `images/<文件名>`）
- `data/lora/colab_bundle/images/*`（复制的全部图片）
- `data/lora/colab_bundle.zip`（可直接上传 Colab）

---

## 2. Colab 训练

将 `colab_bundle.zip` 上传到 Colab 并解压，另上传 `src/artifact_scan/lora_train.py`，然后：

```python
# !pip install -q "transformers>=4.49" "peft" "accelerate" "bitsandbytes" "datasets" "pillow"
import os, zipfile
if not os.path.exists("/content/colab_bundle"):
    with zipfile.ZipFile("/content/colab_bundle.zip") as z:
        z.extractall("/content")

os.environ["PYTHONPATH"] = "/content"
!python -m artifact_scan.lora_train \
    --data /content/colab_bundle/train.jsonl \
    --base Qwen/Qwen2.5-VL-3B-Instruct \
    --out /content/lora_out --epochs 3 --lr 2e-4
```

产物：`/content/lora_out/adapter`（PEFT adapter + processor）。

---

## 3. 导出 GGUF LoRA adapter（供本地 Ollama）

Ollama 的 `ADAPTER` 需要 **GGUF 格式的 LoRA**。在 Colab 用 **unsloth** 追加导出（推荐）：

```python
# !pip install -q unsloth
from unsloth import FastVisionModel  # 受支持时
# 重新加载 4bit 基座 + 你训练的 PEFT adapter
model, tokenizer = FastVisionModel.from_pretrained(
    "Qwen/Qwen2.5-VL-3B-Instruct", load_in_4bit=True)
model.load_adapter("/content/lora_out/adapter")
model.save_pretrained_gguf("/content/gguf_out", quant_method="q4_k_m", save_gguf_dir="/content/gguf_out")
```

> 也可用 llama.cpp 的 `convert_lora_to_gguf.py`，把 PEFT adapter 转成 `*.gguf` LoRA。

下载 `/content/gguf_out` 里的 GGUF LoRA（通常是 `*lora*.gguf` 或 base+mmproj 组合）。

---

## 4. 本地 Ollama 部署

1. 把 GGUF LoRA 拷到本机，例如 `ollama-models/lora_model.gguf`
   （该目录已 bind 挂载进 ollama 容器 `/root/.ollama`）
2. 在本机 Ollama 已有基座 `qwen2.5-vl:3b` 的前提下，创建微调模型：

```powershell
docker exec -e OLLAMA_HOST=127.0.0.1:11434 ollama-local \
  ollama create qwen2.5-vl-lora -f /root/.ollama/../... 
```

> 更稳妥：把 `deploy/ollama/qwen2.5-vl-lora.Modelfile` 拷进 `ollama-models/`，并确保其中 `ADAPTER` 路径可见，再在容器内 `ollama create`。

（若无法用 `ADAPTER`，也可在 Colab 把 LoRA **merge** 进基座并导出完整 GGUF（含 mmproj），按 5.1 中「双 FROM」的方式 `ollama create`。）

---

## 5. 本地验证

```powershell
# 传图断代（复用 5.1 的 API 方式）
$b64=[Convert]::ToBase64String([IO.File]::ReadAllBytes("test-image-1024.jpg"))
$body=@{ model="qwen2.5-vl-lora"; prompt="请对这幅文物图片进行断代鉴定..."; images=@($b64); stream=$false; options=@{num_ctx=4096;num_predict=200} } | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri "http://127.0.0.1:11435/api/generate" -Method Post -Body $body -ContentType "application/json"
```

---

## 6. 文档索引
- 数据生成：`src/artifact_scan/lora_data.py`（5.5）
- 打包：`src/artifact_scan/lora_package.py`
- 训练：`src/artifact_scan/lora_train.py`
- 本地模板：`deploy/ollama/qwen2.5-vl-lora.Modelfile`
- 相关：本机 Ollama 部署见 `deploy/ollama/`（5.1）
