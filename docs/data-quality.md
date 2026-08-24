# 数据质量 Dashboard（阶段 1.6）

> 基于 Prometheus + Grafana 展示数据质量指标（各源数量 / 字段完整率 / 标注覆盖率）。
> 指标由本机脚本计算，经 **Pushgateway** 送入 Prometheus。

## 架构

```
本机脚本（quality/cli.py --push）
   │  Prometheus 文本指标
   ▼
Pushgateway（monitoring 命名空间, 9091）
   │  Prometheus scrape（additionalScrapeConfigs）
   ▼
Prometheus（:30004）──► Grafana Dashboard（:30003）
```

## 指标

| 指标 | 含义 |
|------|------|
| `artifact_raw_records_total{source}` | 各数据源原始记录数 |
| `artifact_clean_records_total` | 清洗后记录数 |
| `artifact_annotated_records_total` | 标注后记录数 |
| `artifact_dedup_removed_total` | 去重移除数 |
| `artifact_field_completeness{field}` | 字段完整率（0-1） |
| `artifact_label_coverage{label}` | 标注覆盖率（0-1，5 级标签） |

## 使用

```powershell
# 1. 部署 Pushgateway（含镜像导入 + apply）
.\deploy\pushgateway\install.ps1

# 2. 监控栈 values 已配置 scrape（additionalScrapeConfigs），helm upgrade 后生效
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -f deploy/monitoring/values.yaml -n monitoring --wait

# 3. 计算并推送数据质量指标（需 port-forward pushgateway 9091）
kubectl port-forward -n monitoring svc/pushgateway 9091:9091 &
python -m artifact_scan.quality.cli --push

# 4. 查看 Dashboard（数据质量）或导入 JSON
#    浏览器 http://localhost:30003/d/artifact-data-quality/
#    （也可用 docs/data-quality-dashboard.json 手动导入）
```

## Dashboard

- **数据质量 (Artifact Data Quality)**：`docs/data-quality-dashboard.json`
  - 面板：各源记录数 / 清洗·标注·去重统计 / 字段完整率 / 5 级标签覆盖率
  - 数据源：Prometheus（uid `prometheus`）
- 指标默认保留于 Pushgateway（`push` 时覆盖同 job）。

## 模块

```
src/artifact_scan/quality/
├── metrics.py   # 指标计算（raw/clean/annotated → stats + Prometheus 文本）
└── cli.py       # 输出报告 + 推送 Pushgateway
deploy/pushgateway/  # Pushgateway 部署（Deployment + Service + install.ps1）
```

## 说明

- 每次数据更新后运行 `python -m artifact_scan.quality.cli --push` 刷新指标。
- Pushgateway 为一次性指标（无时间序列趋势），适合"当前数据质量快照"。
