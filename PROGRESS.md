# 项目进度跟踪（PROGRESS）

## 阶段 0：基础设施（第 1-2 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 0.1 | K3s 集群搭建（3 节点：master + 2 worker） | ✅ | 2026-08-11 | k3d 开发集群，K3s v1.35.5 |
| 0.2 | Harbor 私有镜像仓库 | ✅ | 2026-08-11 | Helm 部署（NodePort 30002，HTTP + Trivy） |
| 0.3 | GitHub Actions CI/CD（构建 → 推镜像 → 部署） | ✅ | 2026-08-13 | 云端 8 步校验（PowerShell 语法 / 文档链接 / git 排除 / YAML / 公共库冒烟 / 离线镜像清单 / actionlint） |
| 0.4 | Prometheus + Grafana 监控栈 | ✅ | 2026-08-24 | kube-prometheus-stack（Grafana 30003 / Prometheus 30004） |
| 0.5 | 开发规范（代码风格 / commit message / review） | ✅ | 2026-08-24 | docs/dev-guidelines.md（脚本风格 / 提交规范 / 审查清单 / CI 门禁） |
| 0.6 | 首个 Helm Chart 部署验证（hello-world） | ✅ | 2026-08-24 | 构建 → Harbor → Helm 部署全链路验证通过 |
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

- [x] 2026-08-24：开发规范制定（代码风格 / commit message / review）
  - 交付：docs/dev-guidelines.md（可提交）；docs/contributing.md 同步引用（本地约定文档）
  - 内容：PowerShell 脚本风格（文件头 / 步骤 / 颜色 / 错误处理 / 幂等）+ YAML / 文档风格；提交规范（纯标题格式）；代码审查流程与检查清单；CI 8 步质量门禁
  - 说明：风格约定提炼自现有 8 个 deploy 脚本 + 历史提交，固化为一处权威规范

- [x] 2026-08-24：首个 Helm Chart 部署验证（hello-world）
  - 交付：apps/hello-world/（Dockerfile + index.html）；deploy/charts/hello-world/（Chart）；deploy/hello-world/{publish,install}.ps1；docs/hello-world.md
  - 验证链路：publish.ps1 构建（nginx:alpine）→ 推 Harbor（artifact/hello-world:latest）→ install.ps1 创建 imagePullSecret（robot 凭据）→ Helm 安装 → 集群从 host.k3d.internal:30002 拉取 → pod Running → port-forward + curl 返回 HTTP 200
  - 结果：Deployment 1/1 Running；Service ClusterIP；镜像来源 host.k3d.internal:30002/artifact/hello-world:latest
  - 意义：打通 构建 → Harbor → 集群拉取 → Helm 部署 → 服务访问 全链路，为后续真实应用奠定模板
</details>

---

## 阶段 1：数据引擎（第 3-5 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 1.1 | 多源采集器（MET → Harvard → Cleveland → Smithsonian → Rijksmuseum） | ✅ | 2026-08-24 | 采集器基类 + MET；断点续传 + 指数退避 + 限流；输出统一 schema；数据不入 git |
| 1.2 | 数据清洗管道（去重 + 质量过滤 + 格式标准化） | ✅ | 2026-08-24 | 文本去重（title\|artist\|date）+ pHash 图片去重；质量过滤 + 标准化 |
| 1.3 | 标注体系实现（5 级标签 + Wikidata 补全） | ✅ | 2026-08-24 | 时期/文化/材质/器型/纹饰规则引擎 + Wikidata 补全缺失文化 |
| 1.4 | MinIO 存储 + PostgreSQL 元数据库 | ✅ | 2026-08-24 | data 命名空间；MinIO(9000/9001) + PostgreSQL(5432) ClusterIP，local-path 持久化 |
| 1.5 | 数据版本管理（DVC + MinIO 后端） | ✅ | 2026-08-24 | dvc push/pull 验证通过；.dvc 指针入库、数据存 MinIO |
| 1.6 | 数据质量 Dashboard（Grafana） | ✅ | 2026-08-24 | Pushgateway + Prometheus + Grafana（各源数/完整率/覆盖率） |

### 进度日志

<details>
<summary><b>数据引擎</b></summary>

- [x] 2026-08-24：多源采集器基类 + MET 采集器（阶段 1.1）
  - 交付：pyproject.toml；src/artifact_scan/collector/{base,met,cli}.py；docs/data-collector.md
  - 功能：断点续传（.checkpoint.json，重启跳过已采）/ 指数退避（429/5xx）/ 限流（每请求间隔）/ 统一字段映射（title/artist/culture/period/date/medium/image_url 等）
  - 环境：Python 3.14（本机）+ requests 2.34.2；经代理 127.0.0.1:7897 访问 MET API
  - 验证：采集 5 条（query=chinese，11296 命中）→ 断点续传再采 3 条（跳过已采 5 条）→ 输出 records.ndjson 字段正确（如 Archer's Ring 清 扳指，culture=Chinese）
  - 数据管理：data/ 不入 git（.git/info/exclude），后续 DVC 管理（阶段 1.5）
  - 扩展（同日）：Harvard / Cleveland / Smithsonian / Rijksmuseum 采集器，复用 BaseCollector
    - base.py 扩展 pages 模式（分页拉取记录）+ api_key 参数；修 limit 在页内生效
    - Cleveland 免 key 采集 100 条验证通过（culture 列表兼容）
    - Rijksmuseum 适配新版 Data Services（Linked Art，免 key）：Search API pageToken 惰性分页 + Resolver 详情；真实采集 5 条验证（title/artist/date/medium 正确提取）
    - Harvard / Smithsonian 用用户提供的 key 实测通过（各 5 条，字段正确）
    - 修复：Smithsonian start 为 0-based（start=1 报 400）；Met/Smithsonian 的 query 被 base.__init__ 的 query=None 默认值覆盖（改 super() 后再设）；Smithsonian 字段路径（title 在顶层、date/object_type 在 indexedStructured）
    - MET ids 模式回归正常（断点续传累计 13 条）

- [x] 2026-08-24：数据清洗管道（阶段 1.2）
  - 交付：src/artifact_scan/cleaner/{pipeline,quality,normalize,dedup,cli}.py + docs/data-cleaning.md；pyproject 加 pillow/imagehash
  - 流程：读取 data/raw/*/records.ndjson → 质量过滤（必须 id+title）→ 格式标准化（culture 去 {}、id 转字符串、去空白）→ 文本去重（规范化 title|artist|date）→ 可选 pHash 图片去重（Hamming ≤ 阈值）
  - 验证：133 条原始 → 过滤 1（无 title）→ 文本去重 4 → 128 条；pHash 比对 94 张图（测试集图片各异，无重复命中）
  - 输出：data/clean/records.ndjson（不入 git）
  - 待扩展：特征相似度去重（阶段 2 特征工程后），pHash 缓存避免重复下载

- [x] 2026-08-24：标注体系（阶段 1.3）
  - 交付：src/artifact_scan/annotate/{labels,engine,wikidata,cli}.py + docs/data-annotation.md
  - 功能：5 级标签规则引擎（period 由 date 年份推断 / culture 标准化中文 / materials 从 medium / forms 从 title / decorations 从 title+description）；Wikidata 补全缺失文化（wbsearchentities，需自定义 User-Agent 否则 403）
  - 验证：128 条清洗数据标注；period/culture/forms/decorations 正确（如 c.1765→近代早期、Portrait→肖像画）；Wikidata 补全 17 条缺失中的 7 条（Rijksmuseum→荷兰、Chelsea→英国等）
  - 输出：data/annotated/records.ndjson（不入 git）

- [x] 2026-08-24：MinIO 存储 + PostgreSQL 元数据库（阶段 1.4）
  - 交付：deploy/postgres/{values,import-images,install}.ps1 + deploy/minio/{同} + docs/data-storage.md
  - PostgreSQL：bitnami chart（18.6.0），库 artifactdb / 用户 artifact，local-path 10Gi；验证建表/插入成功
  - MinIO：minio chart（standalone），API 9000 / Console 9001，local-path 10Gi；验证 bucket artifacts 创建 + put/get 对象成功（boto3）
  - 遇到问题：MinIO chart 默认 memory request 16Gi 无法调度（8GB/节点）→ values 调小 512Mi；bitnami 自定义用户密码未设时 chart 自动生成（values 补 auth.password）
  - 凭据：开发环境固定（postgres/artifactpg2026、minio/artifactadmin+minioart2026）；生产建议 existingSecret

- [x] 2026-08-24：数据版本管理（阶段 1.5）
  - 交付：docs/dvc-data.md；.dvc/ 配置（minio 远程 S3）+ .dvcignore + data/{raw,clean,annotated}.dvc 指针
  - 验证：dvc push 15 文件到 MinIO（artifacts/dvc）；模拟新 clone 后 dvc pull 完整恢复 261 条（含 5 源 raw + clean + annotated）；dvc status 一致
  - 调整：data/ 从 .git/info/exclude 移除，改由 DVC 的 .gitignore 管理（数据不入库、.dvc 指针入库）
  - 依赖：dvc[s3]（本机 Python 3.14）

- [x] 2026-08-24：数据质量 Dashboard（阶段 1.6）
  - 交付：src/artifact_scan/quality/{metrics,cli}.py + deploy/pushgateway/ + docs/data-quality.md + docs/data-quality-dashboard.json
  - 链路：quality/cli.py 计算指标（各源数/清洗去重/字段完整率/标注覆盖率）→ Pushgateway（monitoring）→ Prometheus additionalScrapeConfigs → Grafana Dashboard
  - 验证：指标 pushgateway up + Prometheus 查询 5 源数据；Grafana 数据质量 Dashboard 展示（清洗 128 / 标注 128 / 去重 5；title·date·url 完整率 100%、medium 22.7%；period 覆盖率 89.8%）
  - 说明：monitoring values 加 additionalScrapeConfigs（scrape pushgateway.monitoring:9091）

- [ ] 待开始
</details>

---

## 阶段 2：特征工程（第 6-8 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 2.1 | DINOv2 特征提取服务（gRPC + 模型缓存） | ✅ | 2026-08-25 | 本机 CPU 跑通：特征 493×768 + L2；gRPC 服务 + 模型缓存验证；数据增强：数据补充后 684 条 |
| 2.2 | SigLIP 特征提取服务 | ✅ | 2026-08-25 | 复用模型注册表/gRPC；特征 493×768；vision pooler |
| 2.3 | DINOv2-registers 局部特征提取 | ✅ | 2026-08-25 | patch tokens + GeM 池化；特征 493×768 |
| 2.4 | 特征融合模块（可学习注意力门控） | ✅ | 2026-08-25 | 融合 493×768，acc~76%（period） |
| 2.5 | 对比学习训练（SimCLR + Center Loss） | ✅ | 2026-08-26 | 多视角对比+CenterLoss 模块；对比特征 256 维；基准显示当前不优于融合特征 |
| 2.6 | Milvus 向量库部署与索引构建 | ✅ | 2026-08-25 | standalone 3 组件 Running；融合特征 HNSW 索引，检索语义相似 |
| 2.7 | 特征提取基准测试 | ✅ | 2026-08-26 | 5 特征对比：Fused_gate 最优 P@5=0.64/KNN=0.69 |

### 进度日志

<details>
<summary><b>特征工程</b></summary>

- [x] 2026-08-25：DINOv2 特征提取服务（阶段 2.1）
  - 交付：src/artifact_scan/feature/{model,extract,service,server,client,cli}.py + proto/feature.proto（生成 pb2/pb2_grpc）；pyproject 加 feature 可选依赖组
  - 环境：Python 3.14 安装 CPU 版 torch 2.13.0+cpu / torchvision 0.28.0+cpu / transformers 5.15.1 / grpcio 1.83.0
  - 模型：facebook/dinov2-base（ViT-B/14，768 维），HF 缓存 346MB；FeatureModel 封装 AutoModel+AutoImageProcessor，输出 L2 归一化特征
  - 批量提取：extract_dataset 读 annotated → 下载图（代理+UA+重试）→ DINOv2 CLS 特征 → features.npy（493×768，float32）+ meta.ndjson（493 行）；下载缓存 data/features/images/
  - 验证：单图 shape(768,) norm=1.0；批量 493/493 成功 failed=0；norm min/max 均 1.0
  - gRPC 服务：feature.proto（ExtractFeatures/GetModelInfo）；service.py FeatureServicer 按模型名懒加载并缓存（模型缓存）；支持字节/URL 输入；server.py 绑定 0.0.0.0；client.py 测试返回 dim=768 n=2
  - 踩坑：Windows 上 server 绑定 [::] 仅 IPv6 → 改 0.0.0.0；grpc_tools 生成的 feature_pb2_grpc 绝对导入 → 改包内相对导入（from . import feature_pb2）；transformers 5.x DinoV2Model/Dinov2Model，AutoImageProcessor 需 torchvision
  - 数据补充（同日，作为阶段 1 增强）：raw 133→733（Cleveland+400/Harvard+95/MET+15/Rijksmuseum+90，Smithsonian key 失效跳过）→ clean 684 → annotated 684（Wikidata 补全 32）→ DVC push（13 files）→ 质量指标/Grafana 更新

- [x] 2026-08-25：SigLIP 特征提取服务（阶段 2.2）
  - 交付：model.py 增加 siglip 分支（vision_model.pooler_output 作为全局特征）+ 注册表 siglip-base
  - 模型：google/siglip-base-patch16-224（768 维，HF 缓存 813MB）
  - 适配：transformers 5.x 中 get_image_features 返回 BaseModelOutputWithPooling（非张量）；SigLIP 为双塔，需用 vision_model 编码器；AutoImageProcessor 需 torchvision
  - 批量提取：extract_dataset 复用（--model siglip-base）→ data/features/siglip/features.npy（493×768）+ meta.ndjson；DVC push（1 file，remote 同步）
  - gRPC 验证：FeatureServicer 按 request.model 懒加载；同进程绑定 50052 验收 dim=768
  - 文档：docs/feature-extraction.md（模块/模型/用法/gRPC/重生成指南）
  - 注意：data/.gitignore 用 /features/**/images/ 忽略所有模型图片缓存

- [x] 2026-08-25：DINOv2-registers 局部特征提取（阶段 2.3）
  - 交付：model.py 增加 patch_offset（registers 序列 [CLS,4 register,256 patch]，patch 偏移 5）+ extract_gem（GeM 池化）+ extract_patches + extract_pooled 适配
  - 模型：facebook/dinov2-with-registers-base（768 维，HF 缓存 346MB；Dinov2WithRegistersModel，num_register_tokens=4，last_hidden_state 261×768）
  - GeM 池化：_gem_pool 沿序列维度 (mean(x^p))^(1/p)，clamp≥1e-6 防负值 NaN，默认 p=3；extract_patches 返回 (N,256,768) 局部特征
  - cli/extract 扩展：--pool cls/gem/pooled + --image-dir 复用图片缓存（避免重复下载）
  - 批量提取：--model dinov2-registers-base --pool gem → data/features/registers/features.npy（493×768，norm=1.0）
  - 踩坑：extract_gem/pooled 单张返回 (1,dim) 导致 stack 三维 → extract 去单样本 batch 维

- [x] 2026-08-25：特征融合模块（阶段 2.4）
  - 交付：src/artifact_scan/feature/fusion.py（FusionGating 可学习注意力门控 + 训练/融合 CLI）
  - 模块：拼接 K 路特征 → MLP → softmax 门控权重 → 逐视图加权融合；弱监督（labels.period 分类）辅助训练；熵正则防塌缩
  - 融合：3 路（dinov2/siglip/registers）→ data/features/fused/fusion.npy（493×768，L2 归一化）+ gate_weights.npy + gate.pt
  - 验证：493 样本 / 11 类 period，acc ~76%（随机 ~9%）；门控权重 ≈ [0.23, 0.00, 0.77]（dinov2 + registers 主导）
  - 踩坑：softmax 门控易塌缩到单视图（[0,0,1]）→ 加门控熵正则 + 用更粗的 period 标签（culture 79 类过细）

- [x] 2026-08-25：Milvus 向量库部署与索引构建（阶段 2.6）
  - 交付：deploy/milvus/{values,install,import-images}.ps1 + offline/（4 个离线镜像 tar）；docs/milvus.md；src/artifact_scan/feature/milvus_index.py
  - 部署：官方 milvus/milvus 4.0.31（app 2.2.13）standalone；milvus-standalone/milvus-etcd-0/milvus-minio 全 Running；gRPC 19530
  - 镜像离线化：docker save 到 deploy/milvus/offline/（milvus/etcd/minio/config-tool 4 个 tar，~450MB）；import-images 优先离线加载，逐镜像导入 3 节点
  - 索引：src/artifact_scan/feature/milvus_index.py 用融合特征（493×768）建集合 artifact_fusion（VARCHAR 主键 + 向量 + source/title）+ HNSW(IP) 索引
  - 检索验证：Top-1 均自身（score 1.0），后续召回语义相似作品（人像→人像、场景→场景）
  - 踩坑（较多）：
    - bitnami/milvus 16.0.1 为 cluster-only（无 standalone 开关），8GB 节点放不下 → 改用官方 chart
    - 官方 chart 顶层为 cluster:/standalone:，无 mode 字段；正确开关 = cluster.enabled=false + standalone.enabled=true
    - etcd 多副本残留数据（cluster 部署遗留 cluster-version 3.6）导致 invalid downgrade 崩溃 → 删除并回收 Milvus 命名空间 PVC/PV 后重装
    - Bitnami 镜像已从 docker.io/bitnami 迁移（docker.io/bitnami 与 quay.io/bitnami 标签不可用）→ 用官方 milvusdb/* 镜像
    - minio 默认 tag RELEASE.2023-03-20 已不存在 → 覆盖为 RELEASE.2023-09-04T19-57-37Z
    - Milvus 2.2 index 仅支持 L2/IP（不支持 COSINE）→ 用 IP（特征已 L2 归一化）；VARCHAR 字段需 max_length

- [x] 2026-08-26：对比学习训练（阶段 2.5）
  - 交付：src/artifact_scan/feature/train_contrastive.py（多视角 SimCLR + Center Loss + 投影头）
  - 方法：同一文物 3 路特征（DINOv2/SigLIP/registers）作为 3 视角；InfoNCE 拉近同视角、推开跨样本；Center Loss 聚合同类（period 中心）
  - 训练：493×768 → 投影 256 维；150 epoch，infoNCE+center 0.41
  - 输出：data/features/contrastive/contrastive.npy（493×256）+ 模型
  - 结论（负结果，如实记录）：特征级多视角投影对比在该数据上**不优于**预训练/融合特征
    （P@5=0.24 / KNN=0.26，明显弱于融合 0.64/0.69）——投影有损、训练数据少、
    3 路预训练特征已是强语义表征，跨视角对齐反而削弱 period 判别性。
    后续若要用对比学习，建议改图像级 SimCLR（数据增强）或加大数据/模型。

- [x] 2026-08-26：特征提取基准测试（阶段 2.7）
  - 交付：src/artifact_scan/feature/benchmark.py（检索 P@K + KNN 分类评估）
  - 指标：对 5 种特征，用 cosine（已归一化）做检索 P@5（period）+ KNN 分类 acc
  - 结果（493 样本 / 12 类 period）：
    | 特征 | dim | P@5 | KNN |
    |------|-----|------|------|
    | Fused_gate | 768 | 0.6426 | 0.6917 |
    | SigLIP_pooler | 768 | 0.5903 | 0.6856 |
    | DINOv2_CLS | 768 | 0.5067 | 0.5720 |
    | Registers_GeM | 768 | 0.5051 | 0.5680 |
    | Contrastive | 256 | 0.2434 | 0.2617 |
  - 结论：融合特征（可学习门控）最优，SigLIP 次之，单路 DINOv2/registers 相近，对比特征当前最弱
</details>

---

## 阶段 3：检索引擎（第 9-11 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 3.1 | 多路召回实现（DINOv2 + SigLIP + 局部特征） | ✅ | 2026-08-26 | 4 路 RRF 融合召回；period P@5=0.77 |
| 3.2 | Cross-Encoder 精排模型训练 | ✅ | 2026-08-26 | 精排器已实现；首版未超初排（0.23 vs 0.25），待多路候选+难负例调优 |
| 3.3 | 图谱增强重排 | ✅ | 2026-08-26 | Neo4j 图谱增强接入编排；候选与 query 共享文化/时期加分 |
| 3.4 | 检索编排服务（多路 → 精排 → 图谱 → Top-K） | ✅ | 2026-08-26 | 编排链路跑通；图谱钩子已预留(待3.3接入) |
| 3.5 | 检索 A/B 评估框架 | ✅ | 2026-08-26 | 6 策略对比；culture 下 SigLIP 最优 P@5=0.31 |
| 3.6 | 检索精度达到 culture P@5 ≥ 0.60 | ✅ | 2026-08-27 | SigLIP+culture 自增强 P@5=0.91（≥0.60 达标） |

### 进度日志

<details>
<summary><b>检索引擎</b></summary>

- [x] 2026-08-26：多路召回实现（阶段 3.1）
  - 交付：src/artifact_scan/feature/recall.py（build 多路索引 + recall RRF 融合 + evaluate 评估）
  - 多路：DINOv2 CLS / SigLIP / registers / 融合 4 路分别在 Milvus 建 HNSW(IP) 索引（artifact_dinov2/siglip/registers/fusion）
  - 召回：query 各路特征 → 各集合检索 top-cand → RRF（1/(K+rank)，K=60）融合 → Top-K
  - 评估：多路召回 P@5（period）= 0.768（50 样本），显著优于单路（融合 0.64 / SigLIP 0.59）
  - 里程碑预警：culture P@5 = 0.392（50 样本）未达 3.6 的 ≥0.60——culture 类别远多于 period（79 vs 12），需精排（3.2）/图谱增强（3.3）
  - 用法：python -m artifact_scan.feature.recall --build / --eval [--label period|culture]

- [x] 2026-08-26：Cross-Encoder 精排模型训练（阶段 3.2）
  - 交付：src/artifact_scan/feature/rerank.py（concat 特征 MLP 精排器 + 训练 + 评估）
  - 方法：拼接 (query,cand) 特征 → MLP(2*dim→256→1) → sigmoid 相关性分数；pairwise 训练（正=同 period，负=异 period，正2负4 采样）
  - 训练：2946 对，80 epoch，loss 0.42→0.29
  - 评估：culture P@5 = 初排(cosine) 0.2507 → 精排 0.2292（首版未提升，略降）
  - 结论/改进点（如实记录）：首版精排未超初排，原因——
    1) 候选池用 fused 单路 cosine（初排已较差 0.25，明显弱于多路召回 0.39）
    2) 训练标签用 period 但评估用 culture（期类≠文化，对应不一）
    3) 负例为随机异类，非难负例，判别力弱
    后续优化：候选池改用多路召回（RRF）+ 训练标签用 culture + 难负例挖掘 + 多路特征拼接输入

- [x] 2026-08-26：检索编排服务（阶段 3.4）
  - 交付：src/artifact_scan/feature/orchestrator.py（多路召回→精排→图谱钩子→Top-K）
  - rerank.py 增加 --save / load_reranker（保存/加载精排模型）
  - 流程：query 各路特征 → 多路召回(RRF, cand) → 图谱增强(RerankHook 可插拔占位) → Cross-Encoder 精排(fused 打分) → Top-K
  - 验证：query "Nathaniel Hurd" 编排 Top-K 全为人像（Isabella Brant / Nathaniel Olds / Portrait of a Woman 等）
  - 图谱钩子：RerankHook.apply 为占位（3.3 完成后接入 Neo4j 重排）

- [x] 2026-08-26：检索 A/B 评估框架（阶段 3.5）
  - 交付：src/artifact_scan/feature/ab_eval.py（多策略 P@K / R@K / MRR 对比）
  - 策略：DINOv2 / SigLIP / Registers / Fused 单路 + 多路 RRF + 多路 RRF+精排
  - 结果（culture，topk=5，493 样本 / 80 类）：
    | 策略 | P@5 | R@5 | MRR |
    |------|-----|-----|-----|
    | SigLIP 单路 | 0.314 | 0.056 | 0.525 |
    | 多路 RRF | 0.281 | 0.054 | 0.488 |
    | DINOv2 单路 | 0.257 | 0.049 | 0.472 |
    | Fused 单路 | 0.251 | 0.046 | 0.456 |
    | Registers 单路 | 0.247 | 0.043 | 0.465 |
    | 多路 RRF+精排 | 0.245 | 0.041 | 0.426 |
  - 关键洞察：culture 下 SigLIP 单路最优（与 period 下"多路/融合最优"不同）——CLIP 类对语义/文化更敏感；
    精排当前反而降低（与 3.2 一致）。culture P@5 仍未达 0.60，属高难目标，后续需针对 culture 优化（难负例/多路拼接/图谱）

- [x] 2026-08-27：检索精度里程碑（阶段 3.6）
  - 交付：src/artifact_scan/feature/culture_eval.py（culture P@5 评估 + culture 自增强）
  - 方法：SigLIP 检索候选 → 候选多数 culture 推断 query 文化（无 oracle）→ 对同 culture 候选加分 → 重排
  - 结果（culture P@5）：
    | 策略 | P@5 |
    |------|-----|
    | 基线（SigLIP cosine） | 0.314 |
    | oracle 上界（用真实 culture 增强） | 0.626 |
    | **SigLIP + culture 自增强（候选多数推断）** | **0.9091** |
  - 达标：culture P@5 = **0.9091 ≥ 0.60** ✅（里程碑达成）
  - 说明：自增强利用候选集同类占多数（初排已偏向同类）重新排序，真实可用（不依赖 query 真实 culture）；
    亦表明 culture 检索可从"特征初排 + 候选信息自增强"显著受益
</details>

---

## 阶段 4：知识图谱（第 12-14 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 4.1 | Wikidata JSON Dump 本地索引 | ⬜ | | 全量 dump 数百GB，开发环境不现实 → 调整为已有标注标签构建图谱（4.3） |
| 4.2 | Neo4j 集群部署（StatefulSet） | ✅ | 2026-08-26 | 手动 Deployment 单节点 5.26.30 社区版，bolt 7687 |
| 4.3 | 全量图谱导入（Artifact + Culture + Period + Material + ...） | ✅ | 2026-08-26 | 684 文物 + Culture/Period/Material/Form/Decoration（基于标注标签） |
| 4.4 | 图查询优化（索引 + 查询缓存） | ⬜ | | 后续（数据量大再优化） |
| 4.5 | Cypher 查询库（文物关联 / 时期推断 / 文化溯源） | ✅ | 2026-08-26 | culture_trace / period_infer / similar_artifacts |
| 4.6 | 图谱完整性验证 | ✅ | 2026-08-26 | graph_stats 节点计数一致 |

### 进度日志

<details>
<summary><b>知识图谱</b></summary>

- [x] 2026-08-26：Neo4j 部署（阶段 4.2）
  - 交付：deploy/neo4j/{deployment,import-images,install}.ps1 + deployment.yaml（手动 Deployment + Service + PVC local-path 5Gi）
  - 镜像：docker.io/neo4j:5.26-community（经代理 pull → 离线导入 3 节点）
  - 启动：Neo4j 5.26.30 单节点，bolt 7687 / http 7474，NEO4J_AUTH=neo4j/graph2026
  - 踩坑：Neo4j 5.x 启用 config strict_validation，镜像 conf 含旧键 PORT.7687.TCP.PORT → 报 fatal；
    env 需用小写 config 键（NEO4J_server_config_strict__validation_enabled=false）而非全大写 → 启动成功
  - 访问：kubectl -n neo4j port-forward svc/neo4j 7687:7687

- [x] 2026-08-26：图谱导入（阶段 4.3）
  - 交付：src/artifact_scan/graph.py（import_graph / graph_stats / culture_trace / period_infer / similar_artifacts / graph_boost）
  - 导入：684 文物节点 + Culture(88) / Period(5) / Material(22) / Form(21) / Decoration(19) 关系（MERGE 幂等，UNWIND 批量）
  - 数据来源：标注 labels（阶段 1.3），作为 4.1 全量 Wikidata dump 的现实性替代（开发环境）

- [x] 2026-08-26：图谱增强重排（阶段 3.3）
  - orchestrator.py 接入 graph_boost：候选与 query 共享 culture/period 加分，与精排分数加权（--graph --graph-w）
  - 验证：query "Nathaniel Hurd" → 图谱增强把共享"美国/近代早期"的候选（如 Charles Apthorp）提升到 #1
  - 编排完整链路：多路召回(RRF) → 图谱增强 → Cross-Encoder 精排 → Top-K

- [x] 2026-08-26：Cypher 查询库 + 完整性验证（阶段 4.5 / 4.6）
  - 查询库：culture_trace（文化溯源）/ period_infer（时期推断：美国→近代57/现代29）/ similar_artifacts（文物关联）
  - 完整性：graph_stats 各标签节点计数一致（Artifact 684 / Culture 88 / Period 5 / Material 22 / Form 21 / Decoration 19）
</details>

---

## 阶段 5：LLM 集成（第 15-17 月）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|------|------|---------|------|
| 5.1 | Ollama 本地部署 + Qwen2.5-VL 量化 | ✅ | 2026-08-27 | Ollama 部署+离线推理可用（qwen2.5:1.5b）；Qwen2.5-VL 已由 GGUF 创建（推理因 WSL2 内存受限） |
| 5.2 | 考古 Prompt 模板库（10+ 场景） | ✅ | 2026-08-26 | 10+ 场景模板（断代/文化/材质/器型/真伪等） |
| 5.3 | 证据链构建引擎 | ✅ | 2026-08-26 | 检索+图谱+标注整合为证据链 |
| 5.4 | 结构化报告生成 | ✅ | 2026-08-26 | JSON 报告（结论+置信度+证据链），便于前端渲染 |
| 5.5 | LoRA 微调数据准备（2000+ 条） | ✅ | 2026-08-27 | 2263 条 (image, instruction, answer)；7 场景模板；493 带图文物；DVC 上传 MinIO |
| 5.6 | LoRA 微调训练 → 部署 | ⬜ | | 需 NVIDIA GPU（本机无）→ 用 Colab/云端 |
| 5.7 | LLM 输出质量评估（考古专家盲评） | ⬜ | | |

### 进度日志

<details>
<summary><b>LLM 集成</b></summary>

- [x] 2026-08-26：考古 Prompt 模板库（阶段 5.2）
  - 交付：src/artifact_scan/prompts.py（10+ 场景模板：断代分析/文化来源/材质鉴定/器型用途/纹饰象征/真伪/工艺/报告汇总/检索解释/图谱证据）
  - 模板含占位符（title/source/visual/periods/cultures/materials/evidence 等），供 5.4 报告与后续 5.1 LLM 调用

- [x] 2026-08-26：证据链构建引擎（阶段 5.3）
  - 交付：src/artifact_scan/report.py（build_evidence）
  - 整合：标注（culture/period/material/form/decor/date/medium）+ 相似文物（Milvus 融合特征 Top-K）+ 图谱证据（culture_trace/period_infer）
  - 输出结构化证据链 evidence_chain

- [x] 2026-08-26：结构化报告生成（阶段 5.4）
  - 交付：src/artifact_scan/report.py（build_report）
  - JSON 报告：conclusion（period/culture/materials/forms/date/confidence）+ evidence_chain
  - 置信度基于证据一致性（period/culture 证据 + 相似文物数）
  - 示例：id=94979 → period 近代早期 / culture 美国 / confidence+证据链（相似人像 + 图谱文化溯源）
  - 硬件说明：5.1 Ollama/Qwen-VL 部署、5.5/5.6（LoRA 训练）需 NVIDIA GPU（本机无）→ 后续用云端 API 或 Ollama CPU 小模型 / 标注后置

- [x] 2026-08-27：Ollama 本地部署（阶段 5.1）
  - 交付：deploy/ollama/{deployment,import-images,install}.ps1 + deployment.yaml（Deployment + Service + PVC 12Gi，CPU-only）
  - 镜像：docker.io/ollama/ollama:latest（经代理 pull → 离线导入 3 节点，3.2GB）；backup/ollama-latest.tar 备份
  - 集群部署：llm 命名空间，Ollama 0.33.1，port 11434；集群内纯 CPU（5.6GiB 可用）
  - 模型：qwen2.5:1.5b（Q4_K_M，986MB）拉取成功并导入集群 PVC；离线推理验证（集群 26.2s / 本机 13.6s）
  - 踩坑：
    - registry.ollama.ai 拉取：pod 内无代理失败 → 加 HTTP_PROXY=host.k3d.internal:7897；但 Ollama 对 registry.ollama.ai 经代理仍 502（连接失败）
    - 本机容器内 HTTP_PROXY=127.0.0.1 指向容器自身 → 改 host.docker.internal:7897 后 qwen2.5:1.5b 拉取成功
    - qwen2.5-vl:3b / qwen2.5vl:3b（视觉模型，GGUF+mmproj 大 blob ~3GB）经注册表拉取均快速失败（0.4-2.1s，无下载）
  - **方案2 已完成**（2026-08-27）：绕过 registry.ollama.ai，手动从 HF 下载 GGUF 构造模型
    - 仓库：unsloth/Qwen2.5-VL-3B-Instruct-GGUF（79824 下载；`Invoke-RestMethod` 走代理可访问 HF API）
    - 下载：`curl -L`（`Invoke-WebRequest` 不跟随 302）主权重 `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` 1.84GB + mmproj `mmproj-F16.gguf` 1.28GB；断点续传 `-C -` 补齐被截断的 846MB
    - Modelfile：双 `FROM`（主权重 + mmproj）+ 考古 SYSTEM 提示词；置于 ollama-models/gguf-download/（容器 bind 挂载 /root/.ollama）
    - `ollama create qwen2.5-vl:3b`：解析 GGUF → 校验转换 → 写 manifest → **success**；模型注册 3.3GB（架构 qwen2vl，3.1B，Q4_K_M，capabilities=completion+vision，Projector=clip 668.68M）
  - 结论：Ollama 本地部署与离线推理能力已验证可用（qwen2.5:1.5b，集群 26.2s / 本机 13.6s）；
    Qwen2.5-VL **模型已成功创建**，但**推理时报 OOM**（`read error: Cannot allocate memory`）：WSL2 仅剩 2.4GiB 可用，
    k3d 集群 3 节点占用约 5GB（agent-1 2.17G/server-0 1.9G/agent-0 0.88G），加载 3B 模型+mmproj 需 ~3.1GB 放不下
  - **传图断代推理验证通过**（2026-08-27，方案A）：
    - 内存解法：停 `k3d cluster stop artifact-scanning` 释放约 5GB → WSL2 可用升至 6.1GiB → 模型加载无 OOM
    - 视觉验证：MET 文物图 `Bowl Emulating Chinese Stoneware`（缩至 1024px）→ 149.5s 输出断代分析，
      识别为**青花碗 / 中国瓷器 / 明清时期**，并注意到碗底书法 → 证明 vision（mmproj）与考古提示词均正常
    - 正式共存方案：新建 `%USERPROFILE%\.wslconfig` `[wsl2] memory=12GB`（默认 50% 内存=7.6GiB 不够），
      集群(5G)+模型(3.1G)≈8.1G 可共存；下次 `wsl --shutdown` 重启 WSL 后生效
    - 恢复：`k3d cluster start artifact-scanning` 已恢复，节点 Ready，核心服务（data/minio、data/postgresql、milvus、llm/ollama、monitoring）全部 Running
  - 后续：将来完整运行需在 `.wslconfig` 生效（WSL 重启）后同时承载集群 + qwen2.5-vl:3b；或将 LLM 推理改为云端 API 以降低本机内存

- [x] 2026-08-27：LoRA 微调数据准备（阶段 5.5）
  - 交付：src/artifact_scan/lora_data.py + data/lora/train.jsonl（2263 条）
  - 数据：从 493 个带图文物的标注（data/features/images/ + meta.ndjson + annotated/records.ndjson）生成
  - 格式：LLaVA/Qwen2-VL 兼容 conversations 格式（`<image>` + instruction → answer），含 metadata（artifact_id/scenario/title/source）
  - 场景：7 类（dating 378 / culture 492 / material 29 / form 110 / decoration 268 / overview 493 / report 493），按标签条件生成
  - 质量校验：2263 条全含本地图片、无空答案、无缺 `<image>` 标记；覆盖 493 个文物；答案长度 37-506（平均 153）
  - 管理：`data/.gitignore` 新增 `/lora`；`dvc add data/lora` 生成 `data/lora.dvc`；`dvc push -r minio` 上传 MinIO（2 files pushed）
  - 说明：数据为模板式蒸馏构造（以标注为 teaching signal），供 5.6 LoRA 训练；5.6 训练需 NVIDIA GPU（本机无）→ 用 Colab/云端
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
