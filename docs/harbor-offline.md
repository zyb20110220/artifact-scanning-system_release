# Harbor 离线镜像库（offline/）

> `deploy/harbor/offline/` 目录存放 Harbor 的离线镜像 tar 包，用于**从本目录直接导入集群节点**，
> 不依赖 docker.io 网络拉取，避免后续版本不兼容 / 外网不可达问题。

## 当前文件

- `harbor-images-v2.15.2.tar`（约 556 MB）：Harbor v2.15.2 全部 9 个组件镜像

## 使用方式

```powershell
# 1. 导入镜像到集群所有节点（幂等：已有则跳过；-Force 强制重导）
.\deploy\harbor\import-images.ps1

# 2. 部署 Harbor（install.ps1 会自动先调用 import-images.ps1 检查镜像就绪）
.\deploy\harbor\install.ps1
```

## 生成 / 更新此离线包

在有 docker.io 网络（或代理）的机器上，用 docker 命令生成：

```powershell
docker pull docker.io/goharbor/harbor-core:v2.15.2   # 其余 8 个镜像同理
docker save -o harbor-images-v2.15.2.tar goharbor/*:v2.15.2
# 将生成的 tar 移动到本目录：move .\harbor-images-v2.15.2.tar .\deploy\harbor\offline\
```

> ⚠️ `offline/` 体积大（约 556 MB），已通过 `.git/info/exclude` 排除，不入版本库。
> 集群重建后仅需重新运行 import-images.ps1，无需再次访问 docker.io。

---

## 相关文档

- [reproducibility.md](reproducibility.md) —— 部署 / 迁移完整流程
