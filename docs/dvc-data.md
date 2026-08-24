# 数据版本管理（阶段 1.5：DVC + MinIO）

> 用 DVC（Data Version Control）管理 `data/`，远程存储为 MinIO（S3 兼容）。
> 数据文件不入 git（经 DVC 的 `.gitignore` 忽略），`.dvc` 指针文件入库。

## 工作流

```powershell
# 环境：Python 3.10+，需安装 DVC
pip install "dvc[s3]"

# 1. 初始化（已在本仓库执行，生成 .dvc/ + .dvcignore）
dvc init

# 2. 配置 MinIO 远程（S3 兼容；需先 port-forward MinIO 9000）
kubectl port-forward -n data svc/minio 9000:9000 &
dvc remote add -f minio s3://artifacts/dvc
dvc remote modify minio endpointurl http://127.0.0.1:9000
dvc remote modify minio access_key_id artifactadmin
dvc remote modify minio secret_access_key minioart2026

# 3. 跟踪数据（生成 data/raw.dvc 等指针文件）
dvc add data/raw data/clean data/annotated

# 4. 推送 / 拉取
dvc push -r minio       # 上传数据到 MinIO
dvc pull -r minio       # 从 MinIO 恢复（新环境）
dvc status              # 检查本地与远程一致性
```

## 目录与文件

| 路径 | 说明 | 是否入库 |
|------|------|---------|
| `.dvc/` | DVC 配置（remote 定义等） | ✅ |
| `.dvcignore` | DVC 忽略规则 | ✅ |
| `data/{raw,clean,annotated}.dvc` | 数据指针（记录版本 hash） | ✅ |
| `data/.gitignore` | 忽略数据文件（DVC 生成） | ✅ |
| `data/` 下实际数据 | 采集/清洗/标注产物 | ❌（经 .gitignore 忽略，存 MinIO） |

## MinIO 存储

- 远程：`s3://artifacts/dvc`（MinIO `artifacts` 桶，路径 `dvc/`）
- 凭据：`artifactadmin` / `minioart2026`（见 [data-storage.md](data-storage.md)）
- 验证：`dvc push` 15 文件 → 模拟新 clone `dvc pull` 完整恢复 261 条记录

## 说明

- 访问 MinIO 需 `port-forward`（本机 DVC 通过 `127.0.0.1:9000` 连集群内 MinIO）。
- 数据版本通过 git 提交的 `.dvc` 指针追踪；切换 commit 后 `dvc checkout` 还原对应版本。
- 新增数据后：`dvc add` → `git add <*.dvc>` → commit → `dvc push`。
