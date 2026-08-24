# 多源数据采集器（阶段 1.1）

> 从多个博物馆 API 采集文物数据，统一为通用 schema，支持断点续传 / 限流 / 指数退避。

## 模块结构

```
src/artifact_scan/collector/
├── base.py     # 采集器基类：限流 / 指数退避 / 断点续传 / 分页 / 统一字段映射
├── met.py      # MET 大都会博物馆采集器（ids 模式）
├── harvard.py      # Harvard Art Museums 采集器（pages 模式，需 key）
├── cleveland.py    # Cleveland Museum of Art 采集器（pages 模式，免 key）
├── smithsonian.py  # Smithsonian Open Access 采集器（pages 模式，需 key）
├── rijksmuseum.py  # Rijksmuseum 采集器（pages 模式，需 key）
├── cli.py      # 命令行入口
└── __init__.py
pyproject.toml  # 依赖（requests），Python >= 3.10
```

## 支持的数据源

| 数据源 | 采集器 | 模式 | API key | 状态 |
|--------|--------|------|---------|------|
| MET（大都会） | `met.py` | ids（搜索→逐条详情） | 否 | ✅ |
| Cleveland | `cleveland.py` | pages（skip/limit） | 否 | ✅ |
| Harvard | `harvard.py` | pages（page/size） | 需申请 | ✅ |
| Smithsonian | `smithsonian.py` | pages（start/rows） | 需申请 | ✅ |
| Rijksmuseum | `rijksmuseum.py` | pages（pageToken + Linked Art Resolver） | 否（新版免 key） | ✅ |

> 需要 API key 的来源：`harvard` / `smithsonian`，用 `--api-key` 传入
> 或设环境变量 `ARTIFACT_API_KEY`。无 key 时采集器会提示申请地址并跳过（不报错）。
> Rijksmuseum 新版 Data Services（Linked Art）无需 key，已验证真实采集。

## API key 申请指南

| 来源 | 申请入口 | 说明 |
|------|---------|------|
| Harvard | https://www.harvardartmuseums.org/collections/api | 填表申请，免费 |
| Smithsonian | https://api.data.gov/signup | 经 api.data.gov 注册，免费 |

> 申请后可用 `--api-key <KEY>` 或 `$env:ARTIFACT_API_KEY` 传入进行真实采集。
> key 为敏感信息，不写入仓库。

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
| `--source` | 数据源（met / harvard / cleveland / smithsonian / rijksmuseum） |
| `--query` | 关键词搜索（MET / Smithsonian 用） |
| `--out` | 输出目录（默认 `data/raw`，各来源子目录） |
| `--limit` | 最多采集条数（None=全部） |
| `--proxy` | HTTP 代理（如 `http://127.0.0.1:7897`） |
| `--api-key` | API key（harvard/smithsonian/rijksmuseum 需要；缺省读 `ARTIFACT_API_KEY`） |
| `--no-resume` | 禁用断点续传（默认启用） |
| `--verbose` | 调试日志 |

> API key 为敏感信息，不写入仓库；用 `--api-key` 或环境变量 `ARTIFACT_API_KEY` 传入。

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
