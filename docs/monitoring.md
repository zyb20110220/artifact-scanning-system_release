# 监控栈（Prometheus + Grafana）

> 阶段 0.4：基于 kube-prometheus-stack 的集群监控栈，部署于 `monitoring` 命名空间。

## 组件

| 组件 | 说明 |
|------|------|
| Prometheus | 指标抓取与存储（数据保留 7 天，local-path 持久化 10Gi） |
| Grafana | 可视化面板（local-path 持久化 5Gi，保存 Dashboard） |
| Alertmanager | 告警（默认规则已内置，含 Watchdog 自检告警） |
| node-exporter | 每节点 1 个，采集节点 CPU / 内存 / 磁盘 / 网络指标 |
| kube-state-metrics | K8s 对象指标（Pod / Deployment / PVC 等状态） |

版本：kube-prometheus-stack 88.5.4 / Prometheus v3.14.0 / Grafana v13.2.0 / Prometheus Operator v0.93.1

## 访问方式（NodePort）

| 服务 | 地址 | 账号 |
|------|------|------|
| Grafana | http://localhost:30003 | admin / prom-operator（首次登录建议修改） |
| Prometheus | http://localhost:30004 | 无认证（开发集群） |

> 端口映射在 `deploy/k3s/k3d/cluster.yaml` 中声明（30003 / 30004），
> 由 k3d serverlb 转发到集群，变更端口需重建集群。

## 部署

```powershell
# 一键部署（含镜像准备 + Helm 安装 + 等待就绪）
.\deploy\monitoring\install.ps1
```

脚本步骤：
1. 添加 prometheus-community Helm 仓库
2. 准备镜像（`import-images.ps1`，见下）
3. 创建 `monitoring` 命名空间并 Helm 安装（幂等，可重复执行升级）
4. 等待组件就绪
5. 输出访问地址

## 镜像准备（import-images.ps1）

监控栈 8 个镜像的来源与导入方式（`deploy/monitoring/import-images.ps1`）：

| 镜像 | 获取方式 |
|------|---------|
| quay.io/prometheus/{prometheus,alertmanager} | 本机 docker pull（代理）→ save → 导入节点 |
| quay.io/prometheus-operator/{prometheus-operator,prometheus-config-reloader} | 同上 |
| quay.io/prometheus/node-exporter、quay.io/kiwigrid/k8s-sidecar | 同上 |
| docker.io/grafana/grafana | 同上 |
| registry.k8s.io/kube-state-metrics | **节点 ctr pull 直拉**（见注意事项） |

## 注意事项

- **registry.k8s.io 镜像走节点直拉**：Docker Desktop 的 `docker save` 对
  registry.k8s.io 镜像存在导出 bug（只导出 manifest 不导出层，ctr import 报
  `content digest not found`）。因此 kube-state-metrics 由节点 containerd 直接
  `ctr pull`（已验证节点可直连 registry.k8s.io）。
- **多镜像合并 tar 导入不可靠**：`docker save` 合并多个镜像到单个 tar 后
  `ctr import` 可能报 `content digest not found`，故脚本逐镜像单独 save + 导入。
- **admission webhook 已禁用**（`prometheusOperator.admissionWebhooks.enabled: false`），
  同时关闭 `prometheusOperator.tls.enabled`，避免 operator 挂载不存在的
  `kube-prometheus-stack-admission` secret。
- 数据（Prometheus TSDB / Grafana 配置）落在 local-path PVC，随集群
  `cluster-data/` 挂载持久化，backup/restore/remap 流程可迁移（见
  [reproducibility.md](reproducibility.md)）。

## 常用查询

- 节点 CPU：`100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`
- 节点内存：`node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100`
- 抓取目标健康：`up`
- 告警中：`ALERTS{alertstate="firing"}`
