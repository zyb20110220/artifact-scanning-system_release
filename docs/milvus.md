# Milvus 向量库（阶段 2.6）

> 为文物特征提供向量检索能力：用融合特征（阶段 2.4 输出）构建 HNSW 索引，
> 支持语义相似检索（图像 → 相似文物）。

## 部署（官方 milvus/milvus standalone）

| 项 | 值 |
|---|---|
| Chart | `milvus/milvus` 4.0.31（app 2.2.13） |
| 模式 | standalone（`cluster.enabled=false` + `standalone.enabled=true`） |
| 命名空间 | `milvus` |
| 依赖 | `milvusdb/etcd`（1 副本，2Gi）+ minio（单节点，5Gi） |
| 组件 | `milvus-standalone` / `milvus-etcd-0` / `milvus-minio`（各 1 副本） |
| 访问 | gRPC `19530` / REST `9091`（kubectl port-forward） |

部署：
```powershell
.\deploy\milvus\install.ps1
# 访问（本机）：
kubectl -n milvus port-forward svc/milvus 19530:19530 --address 127.0.0.1
```

## 镜像离线化（`deploy/milvus/offline/`）

- 镜像来源：`milvusdb/milvus:v2.2.13`、`milvusdb/etcd:3.5.5-r2`、
  `minio/minio:RELEASE.2023-09-04T19-57-37Z`、`milvusdb/milvus-config-tool:v0.1.1`
- 已 `docker save` 到 `deploy/milvus/offline/*.tar`（与 Harbor 离线镜像同理，离线可复用）
- `import-images.ps1` 优先从 offline 目录加载，缺则经代理 pull；逐镜像导入节点
- 说明：`docker.io/bitnami/*` 与 `quay.io/bitnami/*` 上的标签不可用（Bitnami 已迁移），
  官方 chart 用官方 Milvus 镜像；minio 默认 tag `RELEASE.2023-03-20` 已不存在，覆盖为
  `RELEASE.2023-09-04T19-57-37Z`

## 索引构建与检索（`src/artifact_scan/feature/milvus_index.py`）

```powershell
$env:PYTHONPATH = "src"
python -m artifact_scan.feature.milvus_index `
  --host 127.0.0.1 --port 19530 `
  --features data/features/fused/fusion.npy
```

- 集合：`artifact_fusion`，字段 `id`(VARCHAR 主键) / `vector`(768) / `source` / `title`
- 度量：**IP**（特征已 L2 归一化，内积 = cosine）；索引 HNSW（M=16, efConstruction=200）
- 验证：Top-1 均为自身（score 1.0），后续召回语义相似作品（人像→人像、场景→场景）

> 注意：Milvus 2.2 该版本 index 仅支持 `L2`/`IP`（不支持 COSINE），且 VARCHAR 字段需 `max_length`。
> 检索用 IP 需保证向量已归一化（本模块特征均 L2 归一化）。

## 数据管理与坑点

- 开发集群 8GB/节点，`values.yaml` 已收紧资源（etcd/minio/standalone 均小预算）
- bitnami/milvus（cluster-only）与官方 `mode: standalone` 均非正确 standalone 开关；
  官方正确写法是顶层 `cluster.enabled=false` + `standalone.enabled=true`
- etcd 多副本残留数据会导致 `invalid downgrade`（3.6 数据 vs 3.5.5）崩溃：
  需删除并回收 Milvus 命名空间 PVC/PV 后重装
