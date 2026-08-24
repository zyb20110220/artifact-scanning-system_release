# docs/ —— 项目文档索引

> 本项目所有 Markdown 文档统一存放于此目录，避免散落。README.md / PROGRESS.md
> 为项目入口与进度跟踪，保留在仓库根目录（GitHub 首页展示需要）。

## 文档列表

| 文档 | 内容 |
|------|------|
| [README.md](../README.md) | 项目总览、系统架构、技术栈、路线图（仓库根） |
| [PROGRESS.md](../PROGRESS.md) | 分阶段进度跟踪与日志（仓库根） |
| [reproducibility.md](reproducibility.md) | 可复现性指南：备份 / 恢复 / 新机器迁移 |
| [cluster-data.md](cluster-data.md) | cluster-data 目录说明（集群持久化数据挂载） |
| [harbor-offline.md](harbor-offline.md) | Harbor 离线镜像库（offline/）说明 |
| [monitoring.md](monitoring.md) | 监控栈（Prometheus + Grafana）部署与使用说明 |
| [dev-guidelines.md](dev-guidelines.md) | 开发规范：代码风格 / 提交规范 / 代码审查 / 质量门禁 |
| [hello-world.md](hello-world.md) | hello-world 验证应用（构建 → Harbor → Helm 部署） |
| [data-collector.md](data-collector.md) | 多源数据采集器（阶段 1.1：断点续传 / 限流 / 退避） |
| [data-cleaning.md](data-cleaning.md) | 数据清洗管道（阶段 1.2：去重 / 质量过滤 / 标准化 / pHash） |

## 约定

- 各目录下不再放置 Markdown 说明文件，统一链接回 docs/。
- 内容避免重复：命令速查 / 完整流程等只保留在单一文档中。
