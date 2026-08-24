# 数据存储层（阶段 1.4）

> 元数据库（PostgreSQL）+ 对象存储（MinIO），部署于 `data` 命名空间（ClusterIP）。

## 组件

| 组件 | 用途 | 版本 | 访问 |
|------|------|------|------|
| PostgreSQL | 元数据（文物结构化信息） | 18.6.0（bitnami） | ClusterIP 5432 |
| MinIO | 对象存储（图片 / 特征 / 模型文件） | RELEASE.2024-12-18 | API 9000 / Console 9001 |

## 部署

```powershell
.\deploy\postgres\install.ps1    # PostgreSQL
.\deploy\minio\install.ps1       # MinIO
```

每个脚本：添加 Helm 仓库 → 导入镜像（经代理逐镜像导入节点）→ 创建 `data`
命名空间 → Helm 安装（幂等）→ 等待就绪 → 输出结果。

## 凭据（开发环境）

| 服务 | 凭据 |
|------|------|
| PostgreSQL | postgres / `artifactpg2026`；用户 `artifact` / 库 `artifactdb` |
| MinIO | `artifactadmin` / `minioart2026` |

> 开发环境固定密码写入 `values.yaml`；生产建议用 `existingSecret`（文档见各 values）。

## 验证

```powershell
# PostgreSQL（pod 内 psql）
kubectl exec -n data postgresql-0 -- env PGPASSWORD=artifactpg2026 psql -U postgres -d artifactdb -c "SELECT 1"

# 或 port-forward + 本机 psql
kubectl port-forward -n data svc/postgresql 5432:5432 &

# MinIO 健康检查（port-forward 9000 后）
curl http://localhost:9000/minio/health/live   # 200

# MinIO 对象操作（boto3 / mc）
python -c "import boto3; s3=boto3.client('s3', endpoint_url='http://127.0.0.1:9000', aws_access_key_id='artifactadmin', aws_secret_access_key='minioart2026', region_name='us-east-1'); print([b['Name'] for b in s3.list_buckets()['Buckets']])"
```

## 数据持久化

- 两者数据均落在 local-path PVC（10Gi），随集群 `cluster-data/` 挂载持久化，
  可经 backup / restore / remap 流程迁移（见 [reproducibility.md](reproducibility.md)）。
- MinIO 已创建 `artifacts` 桶（供 1.5 DVC 使用）。

## 说明

- 均为 ClusterIP：供后续服务（阶段 2+）集群内访问；开发验证用 `port-forward`。
- MinIO chart 默认 `resources.requests.memory: 16Gi`，本集群 8GB/节点需在
  `values.yaml` 调小（512Mi）。
