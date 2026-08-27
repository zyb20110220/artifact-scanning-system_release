# ============================================================
# lora_train.py —— 阶段 5.6 LoRA 微调训练（面向 Colab / GPU）
# 基于 Qwen2.5-VL，使用 PEFT LoRA（默认 QLoRA 4bit）微调。
# 数据集：lora_data.py 生成的 LLaVA/Qwen2-VL 格式 train.jsonl。
# 输出：PEFT adapter；可合并导出。
# 用法（Colab）：
#   pip install -q "transformers>=4.49" "peft" "accelerate" "bitsandbytes" "datasets" "pillow"
#   PYTHONPATH=/content python -m artifact_scan.lora_train --data /content/colab_bundle/train.jsonl \
#       --base Qwen/Qwen2.5-VL-3B-Instruct --out /content/lora_out
# ============================================================
"""Qwen2.5-VL LoRA 微调训练（QLoRA）。"""

import argparse
import json
import logging
import os

import torch
from PIL import Image

logger = logging.getLogger(__name__)


def _load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def make_processor(base):
    from transformers import AutoProcessor
    return AutoProcessor.from_pretrained(base, trust_remote_code=True)


def make_model(base, qlora=True):
    from transformers import AutoModelForVision2Seq
    kwargs = {"trust_remote_code": True}
    if qlora:
        try:
            import bitsandbytes  # noqa: F401
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        except Exception as exc:  # no bitsandbytes -> fallback to bf16
            logger.warning("bitsandbytes 不可用，回退到 bf16：%s", exc)
    else:
        kwargs["torch_dtype"] = torch.bfloat16
    model = AutoModelForVision2Seq.from_pretrained(base, **kwargs)
    return model


def add_lora(model, r=16, alpha=16, dropout=0.0, qlora=True):
    from peft import LoraConfig, get_peft_model
    target = ["q_proj", "k_proj", "v_proj", "o_proj",
              "gate_proj", "up_proj", "down_proj"]
    config = LoraConfig(
        r=r, lora_alpha=alpha, lora_dropout=dropout,
        target_modules=target, bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    return model


class TrainDataset(torch.utils.data.Dataset):
    """将 LLaVA/Qwen2-VL conversations 处理为处理器可用的输入。"""

    def __init__(self, samples, processor, max_len=2048):
        self.samples = samples
        self.processor = processor
        self.max_len = max_len

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        s = self.samples[i]
        img = Image.open(s["image"]).convert("RGB")
        user = s["conversations"][0]["value"].replace("<image>", "").strip()
        ans = s["conversations"][1]["value"]

        messages = [
            {"role": "user", "content": [{"type": "image", "image": img},
                                         {"type": "text", "text": user}]},
            {"role": "assistant", "content": [{"type": "text", "text": ans}]},
        ]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False)
        inputs = self.processor(text=[text], images=[img], return_tensors="pt",
                                padding=True, max_length=self.max_len)

        # 仅监督 assistant 部分：用 user-only 文本长度做 mask
        user_messages = [{"role": "user",
                          "content": [{"type": "text", "text": user}]}]
        user_text = self.processor.apply_chat_template(
            user_messages, tokenize=False, add_generation_prompt=False)
        user_len = len(self.processor.tokenizer(
            user_text, add_special_tokens=False)["input_ids"])

        input_ids = inputs["input_ids"][0]
        labels = input_ids.clone()
        labels[:user_len] = -100

        return {
            "input_ids": input_ids,
            "attention_mask": inputs["attention_mask"][0],
            "labels": labels,
            "pixel_values": inputs["pixel_values"][0],
            "image_grid_thw": inputs["image_grid_thw"][0],
        }


def collate_fn(batch, pad_token_id):
    from torch.nn.utils.rnn import pad_sequence

    def pad(seq, pad_id):
        return pad_sequence(seq, batch_first=True, padding_value=pad_id)

    input_ids = pad([b["input_ids"] for b in batch], pad_token_id)
    attention_mask = pad([b["attention_mask"] for b in batch], 0)
    labels = pad([b["labels"] for b in batch], -100)
    max_imgs = max(b["pixel_values"].shape[0] for b in batch)
    max_patches = max(b["pixel_values"].shape[1] for b in batch)
    pixel_values = torch.stack([
        torch.nn.functional.pad(b["pixel_values"],
                                (0, 0, 0, max_patches -
                                 b["pixel_values"].shape[1]),
                                value=0)
        for b in batch])
    image_grid_thw = torch.cat([b["image_grid_thw"] for b in batch], dim=0)
    return {"input_ids": input_ids, "attention_mask": attention_mask,
            "labels": labels, "pixel_values": pixel_values,
            "image_grid_thw": image_grid_thw}


def train(samples, processor, model, out, epochs=3, lr=2e-4, batch=1, accum=8,
          max_len=2048):
    from transformers import Trainer, TrainingArguments
    ds = TrainDataset(samples, processor, max_len=max_len)
    args = TrainingArguments(
        output_dir=out, num_train_epochs=epochs, learning_rate=lr,
        per_device_train_batch_size=batch, gradient_accumulation_steps=accum,
        logging_steps=10, save_strategy="epoch", report_to="none",
        fp16=(torch.cuda.is_available() and not torch.cuda.is_bf16_supported()),
        bf16=torch.cuda.is_bf16_supported(),
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model, args=args, train_dataset=ds,
        data_collator=lambda b: collate_fn(
            b, processor.tokenizer.pad_token_id),
    )
    trainer.train()
    model.save_pretrained(os.path.join(out, "adapter"))
    processor.save_pretrained(os.path.join(out, "adapter"))
    logger.info("adapter 已保存到 %s", os.path.join(out, "adapter"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Qwen2.5-VL LoRA 微调训练")
    ap.add_argument("--data", required=True, help="train.jsonl 路径")
    ap.add_argument("--base", default="Qwen/Qwen2.5-VL-3B-Instruct",
                    help="基座模型（需与本地部署一致）")
    ap.add_argument("--out", default="lora_out")
    ap.add_argument("--no-qlora", action="store_true", help="不使用 4bit QLoRA")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    samples = _load_jsonl(args.data)
    logger.info("载入 %d 条训练样本", len(samples))
    processor = make_processor(args.base)
    model = make_model(args.base, qlora=not args.no_qlora)
    model = add_lora(model, r=args.r, alpha=args.alpha,
                     qlora=not args.no_qlora)
    model.config.use_cache = False
    train(samples, processor, model, args.out, epochs=args.epochs, lr=args.lr,
          batch=args.batch, accum=args.accum, max_len=args.max_len)
    print("训练完成，adapter 输出：%s/adapter" % args.out)


if __name__ == "__main__":
    main()
