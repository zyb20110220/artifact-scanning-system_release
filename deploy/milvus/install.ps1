# ============================================================
# install.ps1 —— 部署 Milvus 向量库（standalone）到 k3d 集群
# 用法：.\install.ps1
#       官方 milvus/milvus 4.0.31 (app 2.2.13) standalone 模式
#       依赖：etcd + minio（standalone 必需；pulsar/attu 禁用）
#       访问：kubectl -n milvus port-forward svc/milvus 19530:19530（gRPC）
#       幂等：已存在则升级；部署前自动确保节点镜像就绪。
# ============================================================
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

# Helm 拉取 chart 仓库走代理（外网）
$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

$values    = Join-Path $PSScriptRoot "values.yaml"
$namespace = "milvus"
$release   = "milvus"
$chart     = "milvus/milvus"

# 前置检查：helm 与 kubectl，并确保连接 k3d 集群
Require-Tool "helm" "请先安装：winget install Helm.Helm"
Require-Tool "kubectl"
Ensure-Context

# ------------------------------------------------------------
# 第 1 步：添加 milvus Helm 仓库
# ------------------------------------------------------------
Write-Host "[1/4] 添加 milvus Helm 仓库..." -ForegroundColor Cyan
helm repo add milvus https://milvus-io.github.io/milvus-helm/ 2>$null | Out-Null
helm repo update milvus

# ------------------------------------------------------------
# 第 2 步：确保 Milvus 镜像已就绪（经代理拉取并导入节点）
# ------------------------------------------------------------
Write-Host "[2/4] 检查 Milvus 镜像（docker pull → 导入节点）..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "import-images.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] Milvus 镜像就绪失败，中止部署。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 3 步：创建命名空间并安装 Milvus（幂等：已存在则升级）
# ------------------------------------------------------------
Write-Host "[3/4] 创建命名空间 $namespace 并安装 Milvus..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
helm upgrade --install $release $chart -f $values -n $namespace --wait --timeout 20m

# ------------------------------------------------------------
# 第 4 步：等待核心组件就绪 / 输出结果
# ------------------------------------------------------------
Write-Host "[4/4] 等待 Milvus 组件就绪..." -ForegroundColor Cyan
kubectl rollout status statefulset -n $namespace --timeout=300s
kubectl get pods -n $namespace

Write-Host ""
Write-Host "[完成] Milvus 向量库部署完成。" -ForegroundColor Green
Write-Host "访问（gRPC 19530）  ：kubectl -n $namespace port-forward svc/$release 19530:19530" -ForegroundColor Green
Write-Host "访问（REST 9091）   ：kubectl -n $namespace port-forward svc/$release 9091:9091" -ForegroundColor Green
