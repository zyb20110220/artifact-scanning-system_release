# K3s 集群搭建（阶段 0 · 任务 0.1）

| 方式 | 目录 | 适用场景 |
|------|------|---------|
| **k3d（开发集群）** | `k3d/` | 当前 Windows + Docker 单机环境，容器内模拟 3 节点，开发/验证首选 |
| **K3s 原生（生产集群）** | `k3s-native/`（待阶段 7 生产化时补充） | 3 台物理机/虚拟机，真实多节点生产部署 |

---

## 创建集群

```powershell
cd deploy/k3s/k3d
.\up.ps1
```

脚本行为：
1. 用 `cluster.yaml` 创建集群 `artifact-scanning`
2. 等待所有节点 Ready
3. 打印节点列表

### 端口映射（cluster.yaml）

| 宿主机 | 集群内 | 用途 |
|--------|--------|------|
| `8080` | `80` | HTTP Ingress |
| `8443` | `443` | HTTPS Ingress |

## 验证集群

```powershell
.\verify.ps1
```

## 删除集群

```powershell
.\down.ps1
```

