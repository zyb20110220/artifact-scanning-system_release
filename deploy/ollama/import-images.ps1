# ============================================================
# import-images.ps1 —— 将 Ollama 镜像导入 k3d 集群节点（离线化）
# 用法：.\import-images.ps1 [-Force]
# ============================================================
param([switch]$Force)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }
Require-Tool "k3d"
Require-Tool "kubectl"
Ensure-Context

$img = "ollama/ollama:latest"
$nodes = docker ps --format "{{.Names}}" | Where-Object {
    $_ -like "k3d-artifact-scanning-*" -and $_ -notlike "*serverlb*" -and $_ -notlike "*tools*"
}
if (-not $nodes) { Write-Host "[错误] 未找到 k3d 节点容器。" -ForegroundColor Red; exit 1 }

Write-Host "[1/3] 本机 docker pull $img ..." -ForegroundColor Cyan
if (-not $Force) {
    docker image inspect $img 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { docker pull $img }
} else { docker pull $img }

Write-Host "[2/3] docker save 并导入节点..." -ForegroundColor Cyan
$tar = Join-Path $env:TEMP "ollama-imgs\ollama.tar"
New-Item -ItemType Directory -Path (Split-Path $tar) -Force | Out-Null
if (-not (Test-Path $tar)) { docker save -o $tar $img }
foreach ($node in $nodes) {
    $have = docker exec $node ctr -n k8s.io images ls 2>&1
    if (-not $Force -and ($have | Select-String -Pattern ([regex]::Escape($img)))) {
        Write-Host "  [跳过] $node 已有 $img" -ForegroundColor DarkGray
        continue
    }
    Write-Host "  导入 $node ..." -ForegroundColor DarkGray
    docker cp "$tar" "${node}:/tmp/ollama-import.tar"
    docker exec $node ctr -n k8s.io images import /tmp/ollama-import.tar
    docker exec $node rm -f /tmp/ollama-import.tar 2>$null
}

Write-Host "[3/3] 验证节点镜像..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    if (docker exec $node ctr -n k8s.io images ls 2>&1 | Select-String -Pattern ([regex]::Escape($img))) {
        Write-Host "  $node : 有 $img" -ForegroundColor DarkGray
    } else {
        Write-Host "  $node : 缺 $img" -ForegroundColor Red
    }
}
Write-Host "[完成] Ollama 镜像已就绪。" -ForegroundColor Green
