# ============================================================
# install.ps1 —— 部署 PostgreSQL 元数据库（阶段 1.4）
# 部署到 data 命名空间（ClusterIP；验证用 port-forward）
# ============================================================
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

$values    = Join-Path $PSScriptRoot "values.yaml"
$namespace = "data"
$release   = "postgresql"
$chart     = "bitnami/postgresql"

Require-Tool "helm" "请先安装：winget install Helm.Helm"
Require-Tool "kubectl"
Ensure-Context

# ------------------------------------------------------------
# 第 1 步：添加 bitnami 仓库
# ------------------------------------------------------------
Write-Host "[1/5] 添加 bitnami Helm 仓库..." -ForegroundColor Cyan
helm repo add bitnami https://charts.bitnami.com/bitnami 2>$null | Out-Null
helm repo update bitnami

# ------------------------------------------------------------
# 第 2 步：确保镜像就绪
# ------------------------------------------------------------
Write-Host "[2/5] 检查 PostgreSQL 镜像..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "import-images.ps1")
if ($LASTEXITCODE -ne 0) { exit 1 }

# ------------------------------------------------------------
# 第 3 步：创建命名空间并安装
# ------------------------------------------------------------
Write-Host "[3/5] 创建命名空间 $namespace 并安装 PostgreSQL..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
helm upgrade --install $release $chart -f $values -n $namespace --wait --timeout 15m

# ------------------------------------------------------------
# 第 4 步：等待就绪
# ------------------------------------------------------------
Write-Host "[4/5] 等待 PostgreSQL 就绪..." -ForegroundColor Cyan
kubectl rollout status statefulset/$release -n $namespace --timeout=300s

# ------------------------------------------------------------
# 第 5 步：输出结果
# ------------------------------------------------------------
Write-Host "[5/5] 输出结果..." -ForegroundColor Cyan
kubectl get pods -n $namespace
Write-Host ""
Write-Host "[完成] PostgreSQL 部署完成。" -ForegroundColor Green
Write-Host "数据库     ：artifactdb（用户 artifact / artifactpg2026）" -ForegroundColor Green
Write-Host "访问       ：kubectl port-forward -n data svc/postgresql-postgresql 5432:5432 后 psql" -ForegroundColor Cyan
