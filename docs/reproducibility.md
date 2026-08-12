# 可复现性指南（新机器启动 / 迁移）

> 在新机器上完整复现本项目运行环境（K3s 集群 + Harbor 私有仓库及其中数据）的**唯一权威流程**。
> 已经过模拟实验验证：删除集群 + 清空数据后，按本流程可在新环境完整还原用户密码、项目与镜像。

## 数据策略（核心原则）

| 内容 | 是否入库 | 迁移方式 |
|------|---------|---------|
| 代码 / 脚本 / 配置 / 文档 | ✅ 提交 git | `git clone` |
| 环境定义（cluster.yaml、values.yaml） | ✅ 提交 git | `git clone` |
| 运行时数据（`cluster-data/`） | ❌ **不提交**（GB 级，超 git 限制） | **备份文件**（backup/ + `backup.ps1`） |
| 敏感凭据（`.harbor-credentials.json` 等） | ❌ **不提交** | 各机器独立生成 |

> 一句话：**代码走 git，数据走备份**。拷贝"仓库 + 备份文件"即可完整迁移。

## 数据存放与关键机制

- 集群节点持久化数据挂载到工作区 `cluster-data/`（见 `deploy/k3s/k3d/cluster.yaml` 的 volumes）
- **关键机制（remap）**：local-path 的 PVC 目录名绑定**随机 UUID**
  （`pvc-<uid>_<release>_<pvc>`）。集群重建后重新部署 Harbor 会生成新 UID 目录，
  备份恢复的旧数据不会被自动加载。`deploy/remap-data.ps1` 负责把旧数据
  复制到新 PVC 目录并重启组件，从而还原数据。

## 备份

```powershell
cd deploy
.\backup.ps1                  # 打包 cluster-data/ → backup\cluster-data-backup-<时间戳>.tar.gz
.\backup.ps1 -StopCluster     # 推荐：备份前停止集群，保证数据一致
```

> ⚠️ 备份前建议清理 `cluster-data/` 中不在用 PVC 的冗余目录（避免备份膨胀），
> 可用 `kubectl get pvc -n harbor` 对比在用 PVC 的 UID。

## 新机器迁移（完整流程）

### 第 1 步：前置安装（一次性）

- Docker Desktop（并启动）
- k3d：`winget install k3d`
- Helm：`winget install Helm.Helm`
- kubectl（Docker Desktop 自带或单独安装）
- gh（可选，拉取仓库）

### 第 2 步：拷贝代码与备份

```powershell
git clone https://github.com/zyb20110220/artifact-scanning-system_release.git
cd artifact-scanning-system_release
# 将源机器的 backup\cluster-data-backup-*.tar.gz 放入 backup/ 目录
```

### 第 3 步：重建集群（数据卷挂载生效）

```powershell
cd deploy/k3s/k3d
.\up.ps1
```

### 第 4 步：恢复数据（解包备份）

```powershell
cd deploy
.\restore.ps1 -BackupFile "backup\cluster-data-backup-<时间戳>.tar.gz"
```

### 第 5 步：部署 Harbor（生成新的 PVC 目录）

```powershell
cd deploy/harbor
.\install.ps1
```

### 第 6 步：数据重映射（关键）

```powershell
cd deploy
.\remap-data.ps1
```

> ⚠️ 不做此步则数据"丢失"（Harbor 被初始化为全新状态）。

### 第 7 步：验证数据完整

用自定义 admin 密码登录（如 Zyb262502），确认项目/镜像复现：

```powershell
$cred = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("admin:Zyb262502"))
$h = @{ Authorization = "Basic $cred" }
Invoke-RestMethod -Uri "http://localhost:30002/api/v2.0/projects" -Headers $h | Select-Object name
Invoke-RestMethod -Uri "http://localhost:30002/api/v2.0/projects/artifact/repositories" -Headers $h | Select-Object name
```

## 当前可复现范围

- 阶段 0：K3s 集群（3 节点）+ Harbor 私有镜像仓库（含用户密码/项目/镜像） ✅ 已验证
- 后续阶段（数据引擎、检索引擎等）数据，均通过 `cluster-data` 挂载 + 备份/重映射机制覆盖。

---

## 相关文档

- [cluster-data.md](cluster-data.md) —— cluster-data 目录说明
- [harbor-offline.md](harbor-offline.md) —— Harbor 离线镜像库