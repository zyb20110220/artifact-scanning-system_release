# ============================================================
# install.ps1 —— 部署监控栈（kube-prometheus-stack）到 k3d 集群
# 用法：.\install.ps1
#       部署到 monitoring 命名空间。
#       Grafana    http://localhost:30003（admin / prom-operator）
#       Prometheus http://localhost:30004
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
$namespace = "monitoring"
$release   = "kube-prometheus-stack"
$chart     = "prometheus-community/kube-prometheus-stack"

# 前置检查：helm 与 kubectl，并确保连接 k3d 集群
Require-Tool "helm" "请先安装：winget install Helm.Helm"
Require-Tool "kubectl"
Ensure-Context

# ------------------------------------------------------------
# 第 1 步：添加 prometheus-community Helm 仓库
# ------------------------------------------------------------
Write-Host "[1/4] 添加 prometheus-community Helm 仓库..." -ForegroundColor Cyan
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>$null | Out-Null
helm repo update prometheus-community

# ------------------------------------------------------------
# 第 2 步：确保监控镜像已就绪（经代理拉取并导入节点）
# ------------------------------------------------------------
Write-Host "[2/4] 检查监控镜像（docker pull → 导入节点）..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "import-images.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 监控镜像就绪失败，中止部署。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 3 步：创建命名空间并安装监控栈（幂等：已存在则升级）
# ------------------------------------------------------------
Write-Host "[3/4] 创建命名空间 $namespace 并安装监控栈..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
helm upgrade --install $release $chart -f $values -n $namespace --wait --timeout 15m

# ------------------------------------------------------------
# 第 4 步：等待各 Deployment / StatefulSet 就绪
# ------------------------------------------------------------
Write-Host "[4/4] 等待监控组件就绪..." -ForegroundColor Cyan
kubectl rollout status deployment -n $namespace --timeout=300s
kubectl rollout status statefulset -n $namespace --timeout=300s

# ------------------------------------------------------------
# 第 5 步：输出部署结果
# ------------------------------------------------------------
Write-Host "[5/5] 输出部署结果..." -ForegroundColor Cyan
kubectl get pods -n $namespace
Write-Host ""
Write-Host "[完成] 监控栈部署完成。" -ForegroundColor Green
Write-Host "Grafana     ：http://localhost:30003（admin / prom-operator）" -ForegroundColor Green
Write-Host "Prometheus  ：http://localhost:30004" -ForegroundColor Green
