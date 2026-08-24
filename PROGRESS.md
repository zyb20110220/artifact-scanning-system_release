# 项目进度跟踪（PROGRESS）

## 阶段 0：基础设施（第 1-2 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 0.1 | K3s 集群搭建（3 节点：master + 2 worker） | ✅ | 2026-08-11 | k3d 开发集群，K3s v1.35.5 |
| 0.2 | Harbor 私有镜像仓库 | ✅ | 2026-08-11 | Helm 部署（NodePort 30002，HTTP + Trivy） |
| 0.3 | GitHub Actions CI/CD（构建 → 推镜像 → 部署） | ✅ | 2026-08-13 | 云端 8 步校验（PowerShell 语法 / 文档链接 / git 排除 / YAML / 公共库冒烟 / 离线镜像清单 / actionlint） |
| 0.4 | Prometheus + Grafana 监控栈 | ✅ | 2026-08-24 | kube-prometheus-stack（Grafana 30003 / Prometheus 30004） |
| 0.5 | 开发规范（代码风格 / commit message / review） | ⬜ | | |
| 0.6 | 首个 Helm Chart 部署验证（hello-world） | ⬜ | | |

### 进度日志

<details>
<summary><b>基础设施</b></summary>

- [x] 2026-08-11：K3s 集群搭建（k3d 3 节点：1 server + 2 agents）
  - 交付：deploy/k3s/k3d/cluster.yaml + up/down/verify.ps1
  - 遇到的问题：winget 安装 k3d 后 PATH 未刷新（脚本 Get-Command 找不到）；k3d v5 配置 schema 校验失败（servers/agents 应为整数而非数组）
  - 解决方案：脚本增加 Find-K3d 自动定位（搜索 winget Links/Packages 目录并加入会话 PATH）；修正 cluster.yaml 为 servers: 1 / agents: 2
  - 健壮性：up.ps1 幂等（集群已存在跳过创建）+ 自动合并 kubeconfig
  - 结果：集群 artifact-scanning 创建成功，3 节点 Ready；Traefik Ingress 就绪；local-path StorageClass（default）可用；metrics-server 正常
  - 环境：k3d 5.9.0 + kubectl 1.36.1 + Docker Desktop 29.6.2（纯 CPU）
  - 端口映射：宿主机 8080→集群 80（HTTP Ingress），8443→443（HTTPS Ingress）

- [x] 2026-08-11：Harbor 私有镜像仓库部署
  - 交付：deploy/harbor/values.yaml + install/verify/init.ps1
  - 环境：helm 4.2.3（winget 安装，脚本自动定位 PATH）
  - 遇到的问题：k3d 默认不暴露 NodePort（仅 80/443），需在 cluster.yaml 显式映射；映射整个 30000-32767 范围导致 serverlb/traefik 配置爆炸无法启动（bufio.Scanner: token too long）→ 改为只映射 30002；kubectl 默认指向 docker-desktop(kind) 集群 → 脚本自动 use-context k3d-artifact-scanning
  - 结果：Harbor 2.15.2 部署成功，8 组件 Running（core/database/jobservice/nginx/portal/redis/registry/trivy）；门户 http://localhost:30002 可达（HTTP 200）；docker admin 与机器人账号登录/推送/拉回闭环验证通过；项目 artifact(public) + 机器人 robot$artifact+cicd 创建（凭据存 .harbor-credentials.json，敏感勿提交）
  - 说明：127.0.0.0/8 默认被 Docker 视为 insecure，本机访问无需改 daemon.json
  - 集成验证：imagePullSecret（机器人账号）+ 测试 Deployment（镜像 host.k3d.internal:30002/artifact/busybox:test）成功 Running，集群可从 Harbor 正常拉取并运行镜像（验证用脚本/清单已移除，registries.yaml 保留为基础设施配置）
  - 踩坑：k3d 节点无法访问 ClusterIP（kube-proxy 不 DNAT 节点本机发起的 Service 流量，containerd 拉镜像报 EOF）→ registries.yaml 与镜像地址改用 host.k3d.internal:30002（经 serverlb 转发到 Harbor）

- [x] 2026-08-24：Prometheus + Grafana 监控栈部署（kube-prometheus-stack 88.5.4）
  - 交付：deploy/monitoring/{values,install,import-images}.ps1 + docs/monitoring.md；cluster.yaml 新增 30003/30004 端口
  - 组件：Prometheus v3.14.0 + Grafana v13.2.0 + Alertmanager + node-exporter（每节点）+ kube-state-metrics
  - 访问：Grafana http://localhost:30003（admin/prom-operator）；Prometheus http://localhost:30004
  - 验证：21 个 target 全部 up（node-exporter/kubelet/apiserver/coredns/alertmanager/grafana/kube-state-metrics/operator）；Prometheus 查询 up 返回 21 系列全 1
  - 数据持久化：Prometheus TSDB（10Gi local-path，保留 7 天）+ Grafana（5Gi），随 cluster-data 挂载
  - 镜像准备：7 个镜像经代理 docker pull → 逐镜像 save → 导入 3 节点；kube-state-metrics 走节点 ctr pull 直拉
  - 遇到的问题：
    - k3d 重建集群后 kubeconfig 指向 host.docker.internal 无法访问 → 手动改 127.0.0.1:<新API端口>
    - Docker Desktop 的 docker save 对 registry.k8s.io 镜像导出 bug（缺层，ctr import 报 content digest not found）→ 该镜像改节点 ctr pull 直拉（节点可直连 registry.k8s.io）
    - 多镜像合并 tar 的 ctr import 报 content digest not found → 改逐镜像单独 save + 导入
    - operator 挂载 kube-prometheus-stack-admission secret 失败 → 禁用 admissionWebhooks 同时关闭 prometheusOperator.tls.enabled
  - 数据安全：重建集群前已 backup（cluster-data-backup-20260824-162941.tar.gz），Harbor admin/Zyb262502 登录与项目/镜像完整恢复验证通过
</details>

---

## 阶段 1：数据引擎（第 3-5 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 1.1 | 多源采集器（MET → Harvard → Cleveland → Smithsonian → Rijksmuseum） | ⬜ | | 断点续传 + 指数退避 + 限流控制 |
| 1.2 | 数据清洗管道（去重 + 质量过滤 + 格式标准化） | ⬜ | | pHash + 特征相似度去重 |
| 1.3 | 标注体系实现（5 级标签 + Wikidata 补全） | ⬜ | | 时期/文化/材质/器型/纹饰 |
| 1.4 | MinIO 存储 + PostgreSQL 元数据库 | ⬜ | | |
| 1.5 | 数据版本管理（DVC + MinIO 后端） | ⬜ | | |
| 1.6 | 数据质量 Dashboard（Grafana） | ⬜ | | |

### 进度日志

<details>
<summary><b>数据引擎</b></summary>

- [ ] 待开始
</details>

---

## 阶段 2：特征工程（第 6-8 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 2.1 | DINOv2 特征提取服务（gRPC + 模型缓存） | ⬜ | | |
| 2.2 | SigLIP 特征提取服务 | ⬜ | | |
| 2.3 | DINOv2-registers 局部特征提取 | ⬜ | | patch tokens + GeM 池化 |
| 2.4 | 特征融合模块（可学习注意力门控） | ⬜ | | |
| 2.5 | 对比学习训练（SimCLR + Center Loss） | ⬜ | | 解决数据稀疏问题 |
| 2.6 | Milvus 向量库部署与索引构建 | ⬜ | | |
| 2.7 | 特征提取基准测试 | ⬜ | | |

### 进度日志

<details>
<summary><b>特征工程</b></summary>

- [ ] 待开始
</details>

---

## 阶段 3：检索引擎（第 9-11 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 3.1 | 多路召回实现（DINOv2 + SigLIP + 局部特征） | ⬜ | | |
| 3.2 | Cross-Encoder 精排模型训练 | ⬜ | | |
| 3.3 | 图谱增强重排 | ⬜ | | |
| 3.4 | 检索编排服务（多路 → 精排 → 图谱 → Top-K） | ⬜ | | |
| 3.5 | 检索 A/B 评估框架 | ⬜ | | |
| 3.6 | 检索精度达到 culture P@5 ≥ 0.60 | ⬜ | | 里程碑 |

### 进度日志

<details>
<summary><b>检索引擎</b></summary>

- [ ] 待开始
</details>

---

## 阶段 4：知识图谱（第 12-14 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 4.1 | Wikidata JSON Dump 本地索引 | ⬜ | | 离线批量匹配，避免线上 SPARQL |
| 4.2 | Neo4j 集群部署（StatefulSet） | ⬜ | | |
| 4.3 | 全量图谱导入（Artifact + Culture + Period + Material + ...） | ⬜ | | |
| 4.4 | 图查询优化（索引 + 查询缓存） | ⬜ | | |
| 4.5 | Cypher 查询库（文物关联 / 时期推断 / 文化溯源） | ⬜ | | |
| 4.6 | 图谱完整性验证 | ⬜ | | |

### 进度日志

<details>
<summary><b>知识图谱</b></summary>

- [ ] 待开始
</details>

---

## 阶段 5：LLM 集成（第 15-17 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 5.1 | Ollama 本地部署 + Qwen2.5-VL 量化 | ⬜ | | 离线可用 |
| 5.2 | 考古 Prompt 模板库（10+ 场景） | ⬜ | | |
| 5.3 | 证据链构建引擎 | ⬜ | | |
| 5.4 | 结构化报告生成 | ⬜ | | JSON 输出便于前端渲染 |
| 5.5 | LoRA 微调数据准备（2000+ 条） | ⬜ | | |
| 5.6 | LoRA 微调训练 → 部署 | ⬜ | | |
| 5.7 | LLM 输出质量评估（考古专家盲评） | ⬜ | | |

### 进度日志

<details>
<summary><b>LLM 集成</b></summary>

- [ ] 待开始
</details>

---

## 阶段 6：前端与应用（第 18-20 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 6.1 | Next.js 前端框架搭建 | ⬜ | | |
| 6.2 | 图片上传 + 实时检索体验 | ⬜ | | |
| 6.3 | 检索结果画廊 + 详情面板 | ⬜ | | |
| 6.4 | D3.js 证据链交互式网络图 | ⬜ | | |
| 6.5 | 断代报告渲染（结构化 JSON → 可视化） | ⬜ | | |
| 6.6 | 时间轴 / 地图可视化 | ⬜ | | |
| 6.7 | 移动端适配 | ⬜ | | |

### 进度日志

<details>
<summary><b>前端与应用</b></summary>

- [ ] 待开始
</details>

---

## 阶段 7：评估与优化（第 21-24 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 7.1 | 全链路延迟优化（端到端 < 5s） | ⬜ | | |
| 7.2 | 检索精度 final push（culture P@5 ≥ 0.70） | ⬜ | | |
| 7.3 | 压力测试（100 QPS 并发） | ⬜ | | |
| 7.4 | 考古专家用户测试（10+ 专家） | ⬜ | | |
| 7.5 | 论文 / 技术报告撰写 | ⬜ | | |
| 7.6 | 开源发布 + 文档完善 | ⬜ | | |

### 进度日志

<details>
<summary><b>评估与优化</b></summary>

- [ ] 待开始
</details>
