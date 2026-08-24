# 多源数据采集器（阶段 1.1）

> 从多个博物馆 API 采集文物数据，统一为通用 schema，支持断点续传 / 限流 / 指数退避。

## 模块结构

```
src/artifact_scan/collector/
├── base.py     # 采集器基类：限流 / 指数退避 / 断点续传 / 统一字段映射
├── met.py      # MET 大都会博物馆采集器
├── cli.py      # 命令行入口
└── __init__.py
pyproject.toml  # 依赖（requests），Python >= 3.10
```

## 支持的数据源

| 数据源 | 采集器 | 状态 |
|--------|--------|------|
| MET（大都会） | `met.py` | ✅ 已实现 |
| Harvard | — | ⬜ 待实现 |
| Cleveland | — | ⬜ 待实现 |
| Smithsonian | — | ⬜ 待实现 |
| Rijksmuseum | — | ⬜ 待实现 |

## 运行

```powershell
# 设置模块路径
$env:PYTHONPATH = "src"

# MET 按关键词采集（默认 chinese，限 5 条，经代理）
python -m artifact_scan.collector.cli --source met --query chinese `
  --limit 5 --proxy http://127.0.0.1:7897 --out data/raw

# 全量采集（启用断点续传）
python -m artifact_scan.collector.cli --source met --query chinese `
  --proxy http://127.0.0.1:7897 --out data/raw
```

## 通用参数

| 参数 | 说明 |
|------|------|
| `--source` | 数据源（met / harvard / ...） |
| `--query` | 关键词搜索（MET 用） |
| `--out` | 输出目录（默认 `data/raw`，各来源子目录） |
| `--limit` | 最多采集条数（None=全部） |
| `--proxy` | HTTP 代理（如 `http://127.0.0.1:7897`） |
| `--no-resume` | 禁用断点续传（默认启用） |
| `--verbose` | 调试日志 |

## 输出与断点续传

- **数据**：`<out>/<source>/records.ndjson`（每行一条 JSON，统一 schema）
- **断点**：`<out>/<source>/.checkpoint.json`（记录已采对象 id，重启自动跳过）
- **限流/退避**：每请求间隔 `rate_limit`（默认 1s）；429/5xx 指数退避重试

## 统一字段 schema

| 字段 | 说明 |
|------|------|
| `id` / `object_id` | 对象标识 |
| `source` | 数据源（如 met） |
| `title` / `artist` | 标题 / 艺术家 |
| `culture` / `period` | 文化 / 时期 |
| `date` / `medium` / `dimensions` | 年代 / 材质 / 尺寸 |
| `image_url` / `url` | 图片 / 详情链接 |
| `description` | 描述 |

## 数据管理

- 采集的原始数据（`data/`）为**运行时/原始数据**，不入 git（经 `.git/info/exclude`
  排除），后续由 DVC 版本管理（阶段 1.5）。
- 采集器代码入 git。
