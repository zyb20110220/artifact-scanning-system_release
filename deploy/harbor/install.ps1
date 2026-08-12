# ============================================================
# install.ps1 —— 部署 Harbor 私有镜像仓库到 k3d 集群
# 用法：.\install.ps1
#       部署到 harbor 命名空间，地址 http://localhost:30002
#       幂等：已存在则升级；部署前自动确保离线镜像就绪。
# ============================================================
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$values    = Join-Path $PSScriptRoot "values.yaml"
$namespace = "harbor"
$release   = "harbor"

# 前置检查：helm 与 kubectl，并确保连接 k3d 集群
Require-Tool "helm" "请先安装：winget install Helm.Helm"
Require-Tool "kubectl"
Ensure-Context

# ------------------------------------------------------------
# 第 1 步：添加 Harbor Helm 仓库
# ------------------------------------------------------------
Write-Host "[1/4] 添加 Harbor Helm 仓库..." -ForegroundColor Cyan
helm repo add harbor https://helm.goharbor.io 2>$null | Out-Null
helm repo update harbor

# ------------------------------------------------------------
# 第 2 步：确保 Harbor 离线镜像已就绪（从本目录导入，避免依赖 docker.io）
# ------------------------------------------------------------
Write-Host "[2/4] 检查 Harbor 离线镜像（deploy/harbor/offline/）..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "import-images.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] Harbor 离线镜像就绪失败，中止部署。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 3 步：创建命名空间并安装 Harbor（幂等：已存在则升级）
# --wait 会等待所有组件就绪，镜像已在节点 containerd 中，拉取很快
# ------------------------------------------------------------
Write-Host "[3/4] 创建命名空间 $namespace 并安装 Harbor..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
helm upgrade --install $release harbor/harbor -f $values -n $namespace --wait --timeout 15m

# ------------------------------------------------------------
# 第 4 步：等待各 Deployment 就绪
# ------------------------------------------------------------
Write-Host "[4/4] 等待 Harbor 组件就绪..." -ForegroundColor Cyan
kubectl rollout status deployment -n $namespace --timeout=300s

# ------------------------------------------------------------
# 第 5 步：输出部署结果
# ------------------------------------------------------------
Write-Host "[5/5] 输出部署结果..." -ForegroundColor Cyan
kubectl get pods -n $namespace
Write-Host ""
Write-Host "[完成] Harbor 部署完成。" -ForegroundColor Green
Write-Host "Harbor 地址  ：http://localhost:30002" -ForegroundColor Green
Write-Host "管理员账号  ：admin / Harbor12345（首次登录请修改）" -ForegroundColor Green
Write-Host "重要        ：使用前请确保 Docker Desktop 的 insecure-registries 已加入 localhost:30002" -ForegroundColor Yellow
