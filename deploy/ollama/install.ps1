# ============================================================
# install.ps1 —— 部署 Ollama 到 k3d 集群（阶段 5.1）
# CPU-only 运行（集群无 GPU），PVC 持久化模型。port 11434。
# ============================================================
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

$manifest = Join-Path $PSScriptRoot "deployment.yaml"
$namespace = "llm"
Require-Tool "kubectl"
Ensure-Context

Write-Host "[1/3] 确保 Ollama 镜像就绪..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "import-images.ps1")
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] Ollama 镜像就绪失败" -ForegroundColor Red; exit 1 }

Write-Host "[2/3] 创建命名空间并部署..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
kubectl apply -f $manifest
kubectl rollout status deployment/ollama -n $namespace --timeout=300s

Write-Host "[3/3] 验证..." -ForegroundColor Cyan
kubectl get pods -n $namespace
Write-Host ""
Write-Host "[完成] Ollama 部署完成。" -ForegroundColor Green
Write-Host "访问：kubectl -n $namespace port-forward svc/ollama 11434:11434" -ForegroundColor Green
Write-Host "拉取模型：curl http://127.0.0.1:11434/api/pull -d '{\"model\":\"qwen2.5-vl:3b\"}'" -ForegroundColor Green
