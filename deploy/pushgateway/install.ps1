# ============================================================
# install.ps1 —— 部署 Pushgateway（阶段 1.6）
# 导入镜像 + apply 清单；需 monitoring values 配置 scrape（见 monitoring/values.yaml）
# ============================================================
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

$manifest = Join-Path $PSScriptRoot "deployment.yaml"
$namespace = "monitoring"
$image = "docker.io/prom/pushgateway:v1.11.0"

Require-Tool "k3d"
Require-Tool "kubectl"
Ensure-Context

# ------------------------------------------------------------
# 第 1 步：本机拉取并导入节点
# ------------------------------------------------------------
Write-Host "[1/3] 拉取并导入 Pushgateway 镜像..." -ForegroundColor Cyan
docker pull $image
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] docker pull 失败" -ForegroundColor Red; exit 1 }
$tar = Join-Path $env:TEMP "pushgateway.tar"
Remove-Item $tar -ErrorAction SilentlyContinue
docker save -o $tar $image

$nodes = docker ps --format "{{.Names}}" | Where-Object {
    $_ -like "k3d-artifact-scanning-*" -and $_ -notlike "*serverlb*" -and $_ -notlike "*tools*"
}
foreach ($node in $nodes) {
    $have = docker exec $node ctr -n k8s.io images ls 2>&1
    if ($have | Where-Object { $_ -match "pushgateway" }) {
        Write-Host "  [跳过] $node 已有 pushgateway 镜像" -ForegroundColor DarkGray
        continue
    }
    Write-Host "  导入 $node ..." -ForegroundColor DarkGray
    docker cp "$tar" "${node}:/tmp/pg.tar"
    docker exec $node ctr -n k8s.io images import /tmp/pg.tar
    docker exec $node rm -f /tmp/pg.tar 2>$null
}

# ------------------------------------------------------------
# 第 2 步：apply 清单
# ------------------------------------------------------------
Write-Host "[2/3] 部署 Pushgateway..." -ForegroundColor Cyan
kubectl apply -f $manifest

# ------------------------------------------------------------
# 第 3 步：等待就绪
# ------------------------------------------------------------
Write-Host "[3/3] 等待就绪..." -ForegroundColor Cyan
kubectl rollout status deployment/pushgateway -n $namespace --timeout=120s
kubectl get pods -n $namespace -l app=pushgateway

Write-Host ""
Write-Host "[完成] Pushgateway 已部署。" -ForegroundColor Green
Write-Host "集群内    ：http://pushgateway.monitoring:9091" -ForegroundColor Cyan
Write-Host "访问验证  ：kubectl port-forward -n monitoring svc/pushgateway 9091:9091" -ForegroundColor Cyan
