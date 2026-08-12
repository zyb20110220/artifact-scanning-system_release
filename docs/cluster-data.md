# cluster-data/ —— 集群持久化数据目录

> 存放 k3d 集群各节点的**持久化数据**（PVC 经 local-path 实际落盘的目录），
> 通过 `deploy/k3s/k3d/cluster.yaml` 的 volumes 挂载，实现集群重建不丢数据。

| 目录 | 挂载到节点 | 说明 |
|------|-----------|------|
| `server-0/` | `k3d-artifact-scanning-server-0` | 控制面节点 local-path 数据 |
| `agent-0/` | `k3d-artifact-scanning-agent-0` | 工作节点 local-path 数据 |
| `agent-1/` | `k3d-artifact-scanning-agent-1` | 工作节点 local-path 数据 |

## 作用

- **集群删除重建（down/up）不丢数据**：PVC 数据落在宿主机本目录，而非节点容器临时文件系统
- **迁移**：拷贝本目录到新机器对应路径即可带走数据（需同时保持 cluster.yaml 路径一致）
- 当前承载 Harbor 的数据库、镜像层等数据

## 备份 / 恢复 / 迁移

数据不入库。**完整流程见 [reproducibility.md](reproducibility.md)**（含备份、恢复、
新机器迁移与关键步骤 `remap-data.ps1` 及实验验证）。命令速查亦见该文档，此处不再重复。

> ⚠️ 集群重建并恢复数据后**必须执行 `remap-data.ps1`**，否则数据不会被加载
> （local-path 的 PVC 目录名绑定随机 UUID，需将旧数据复制到新 PVC 目录）。

---

## 相关文档

- [reproducibility.md](reproducibility.md) —— 备份 / 恢复 / 迁移完整流程
