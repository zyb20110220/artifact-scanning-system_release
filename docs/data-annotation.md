# 标注体系（阶段 1.3）

> 对清洗后数据生成 5 级标签（时期 / 文化 / 材质 / 器型 / 纹饰），并可用 Wikidata
> 补全缺失的文化标签。输出 `data/annotated/records.ndjson`。

## 5 级标签

| 标签 | 字段来源 | 说明 |
|------|---------|------|
| `period` 时期 | `date`（年份 → 时期分类） | 古代 / 中世纪 / 中世纪末期 / 近代早期 / 近代 / 现代 |
| `culture` 文化 | `culture`（标准化为中文） | 如 Chinese → 中国、America → 美国 |
| `materials` 材质 | `medium`（关键词映射） | 如 porcelain → 瓷、bronze → 青铜、ivory → 象牙 |
| `forms` 器型 | `title`（关键词映射） | 如 Bowl → 碗、Vase → 瓶、Portrait → 肖像画 |
| `decorations` 纹饰 | `title` + `description` | 如 dragon → 龙纹、lotus → 莲纹、landscape → 山水 |

标签附加在记录的 `labels` 字段（JSON 对象），保留原始字段。

## 模块结构

```
src/artifact_scan/annotate/
├── labels.py    # 5 级标签规则表 + 推断辅助函数
├── engine.py    # 标注引擎（annotate / annotate_all）
├── wikidata.py  # Wikidata 补全（wb_search / enrich）
└── cli.py       # 命令行入口
```

## 运行

```powershell
# 基础标注（本地规则，无网络）
python -m artifact_scan.annotate.cli \
  --input data/clean/records.ndjson --output data/annotated/records.ndjson

# 启用 Wikidata 补全缺失文化（需网络，建议代理）
python -m artifact_scan.annotate.cli \
  --input data/clean/records.ndjson --output data/annotated/records.ndjson \
  --wikidata --proxy http://127.0.0.1:7897
```

## Wikidata 补全

- 对 `labels.culture` 缺失的记录，用 `artist`（或 `title`）搜索 Wikidata
  `wbsearchentities`，从实体描述中识别文化并补全。
- 需要自定义 User-Agent（Wikidata 要求，否则 403）。
- 补全效果取决于搜索命中质量（本项目测试：17 条缺失中补全 7 条，多来自
  Rijksmuseum / 瓷器厂等，大部分合理）。

## 依赖与数据

- 无新增第三方依赖（仅 requests）。
- `data/annotated/` 为运行时数据，不入 git（经 `.git/info/exclude` 排除）。
- 标注结果供阶段 4 知识图谱 / 阶段 3 图谱增强重排使用。
