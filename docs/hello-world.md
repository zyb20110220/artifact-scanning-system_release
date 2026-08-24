# hello-world（阶段 0.6 部署验证）

> 首个 Helm Chart 部署验证应用。验证完整链路：**镜像构建 → Harbor 推送 →
> 集群从 Harbor 拉取 → Helm Chart 部署 → 服务访问**。

## 目录结构

```
apps/hello-world/                  # 应用源码（Dockerfile + index.html）
deploy/charts/hello-world/         # Helm Chart（Deployment + Service）
deploy/hello-world/                # 操作脚本
```

## 完整链路

```powershell
# 1. 构建镜像并推送到 Harbor（localhost:30002/artifact/hello-world:latest）
.\deploy\hello-world\publish.ps1

# 2. 部署（创建命名空间 + imagePullSecret + Helm 安装 + 验证）
.\deploy\hello-world\install.ps1
```

`install.ps1` 步骤：
1. 创建 `hello-world` 命名空间
2. 创建 `imagePullSecret` `harbor-registry`（Harbor robot 凭据，指向
   `host.k3d.internal:30002`）
3. `helm upgrade --install`（镜像从 Harbor 拉取）
4. 等待 Deployment 就绪
5. `port-forward` + `curl` 验证 HTTP 200

## 访问

```powershell
kubectl port-forward -n hello-world svc/hello-world 38080:80
# 浏览器打开 http://localhost:38080，应显示 "Hello from artifact-scanning-system!"
```

## 镜像

- 仓库：`artifact/hello-world`（Harbor）
- 基础镜像：`nginx:alpine`（`apps/hello-world/Dockerfile`）
- 集群内地址：`host.k3d.internal:30002/artifact/hello-world:latest`
- 拉取认证：`imagePullSecret`（robot 账号 `robot$artifact+cicd`，凭据存于
  `deploy/harbor/.harbor-credentials.json`）

## 说明

- 集群节点经 `deploy/k3s/registries.yaml` 将 `host.k3d.internal:30002` 配置为
  HTTP 私有仓库，配合 `imagePullSecret` 完成认证拉取。
- 作为验证应用，使用 ClusterIP 服务；后续真实应用可按需改为 NodePort / Ingress。
