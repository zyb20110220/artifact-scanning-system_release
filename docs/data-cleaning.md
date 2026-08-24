# 数据清洗管道（阶段 1.2）

> 对采集的原始数据（`data/raw/`）执行去重、质量过滤与格式标准化，输出统一
> 清洗后数据（`data/clean/records.ndjson`）。

## 模块结构

```
src/artifact_scan/cleaner/
├── pipeline.py   # 清洗主流程：读取 → 过滤 → 标准化 → 去重 → 输出
├── quality.py    # 质量过滤（必须有 id + title）
├── normalize.py  # 格式标准化（去空白、culture 清 {}、id 转字符串）
├── dedup.py      # 去重（文本 title|artist|date + pHash 图片）
└── cli.py        # 命令行入口
```

## 清洗流程

1. **读取**：`data/raw/<source>/records.ndjson`（各来源）
2. **质量过滤**：去除无 `id` 或无 `title` 的低质量记录
3. **格式标准化**：
   - 文本字段去首尾/内部空白、去换行
   - `culture` 去除形如 `{America}` 的大括号
   - `id` 统一转字符串
4. **文本去重**：基于规范化 `title|artist|date`（小写、去标点）跨源合并重复，保留第一条
5. **pHash 图片去重**（可选）：下载 `image_url` 计算感知哈希，Hamming 距离 ≤ 阈值视为重复，丢弃后出现的

## 运行

```powershell
# 基础清洗（文本去重）
python -m artifact_scan.cleaner.cli --input data/raw --output data/clean/records.ndjson

# 启用 pHash 图片去重（需下载图片，建议加代理）
python -m artifact_scan.cleaner.cli --input data/raw --output data/clean/records.ndjson `
  --phash --proxy http://127.0.0.1:7897
```

## 参数

| 参数 | 说明 |
|------|------|
| `--input` | 原始数据目录（默认 `data/raw`） |
| `--output` | 清洗后输出文件（默认 `data/clean/records.ndjson`） |
| `--phash` | 启用 pHash 图片去重 |
| `--phash-threshold` | pHash Hamming 阈值（默认 5） |
| `--proxy` | 图片下载代理 |

## 依赖

- `pillow` / `imagehash`：pHash 图片去重（`pyproject.toml` 已声明）

## 说明

- `data/`（含 raw / clean）为运行时数据，不入 git（经 `.git/info/exclude` 排除）。
- 清洗结果供后续阶段使用（1.3 标注、1.4 存储）。
