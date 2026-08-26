# ============================================================
# install.ps1 —— 部署 Neo4j standalone 到 k3d 集群（阶段 4.2）
# 用法：.\install.ps1
#       手动 Deployment + Service + PVC（local-path，5Gi）
#       访问：kubectl -n neo4j port-forward svc/neo4j 7687:7687（bolt）
#       幂等：已存在则 apply 更新；部署前自动确保节点镜像就绪。
# ============================================================
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

$manifest = Join-Path $PSScriptRoot "deployment.yaml"
$namespace = "neo4j"

Require-Tool "kubectl"
Ensure-Context

Write-Host "[1/3] 确保 Neo4j 镜像就绪（pull → 导入节点）..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "import-images.ps1")
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] Neo4j 镜像就绪失败" -ForegroundColor Red; exit 1 }

Write-Host "[2/3] 创建命名空间并部署..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
kubectl apply -f $manifest
kubectl rollout status deployment/neo4j -n $namespace --timeout=300s

Write-Host "[3/3] 验证..." -ForegroundColor Cyan
kubectl get pods -n $namespace
Write-Host ""
Write-Host "[完成] Neo4j standalone 部署完成。" -ForegroundColor Green
Write-Host "访问（bolt 7687）：kubectl -n $namespace port-forward svc/neo4j 7687:7687" -ForegroundColor Green
Write-Host "访问（http 7474）：kubectl -n $namespace port-forward svc/neo4j 7474:7474" -ForegroundColor Green
