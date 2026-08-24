# ============================================================
# import-images.ps1 —— 将 MinIO 镜像导入 k3d 节点
# 幂等：节点已具备则跳过（-Force 强制）；逐镜像导入
# ============================================================
param(
    [switch]$Force
)
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

Require-Tool "k3d"
Require-Tool "kubectl"
Ensure-Context

# MinIO 镜像（与 values.yaml 对齐）
$images = @(
    "quay.io/minio/minio:RELEASE.2024-12-18T13-15-44Z",
    "quay.io/minio/mc:RELEASE.2024-11-21T17-21-54Z"
)

$nodes = docker ps --format "{{.Names}}" | Where-Object {
    $_ -like "k3d-artifact-scanning-*" -and $_ -notlike "*serverlb*" -and $_ -notlike "*tools*"
}
if (-not $nodes) {
    Write-Host "[错误] 未找到 k3d 节点容器，请先运行 up.ps1。" -ForegroundColor Red
    exit 1
}
Write-Host "节点：$($nodes -join ', ')" -ForegroundColor Cyan

# ------------------------------------------------------------
# 第 1 步：本机 docker pull（幂等）
# ------------------------------------------------------------
Write-Host "[1/3] 本机 docker pull（共 $($images.Count) 个）..." -ForegroundColor Cyan
foreach ($img in $images) {
    $haveLocal = $false
    if (-not $Force) {
        docker image inspect $img 2>$null | Out-Null
        $haveLocal = ($LASTEXITCODE -eq 0)
    }
    if ($haveLocal) {
        Write-Host "  [已有] $img" -ForegroundColor DarkGray
    } else {
        Write-Host "  [拉取] $img ..." -ForegroundColor DarkGray
        docker pull $img
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] docker pull 失败：$img" -ForegroundColor Red
            exit 1
        }
    }
}

# ------------------------------------------------------------
# 第 2 步：逐镜像 save
# ------------------------------------------------------------
Write-Host "[2/3] 逐镜像 docker save ..." -ForegroundColor Cyan
$imgDir = Join-Path $env:TEMP "minio-imgs"
New-Item -ItemType Directory -Path $imgDir -Force | Out-Null
$tarMap = @{}
foreach ($img in $images) {
    $name = ($img -replace '[^A-Za-z0-9._-]', '_')
    $tar  = Join-Path $imgDir "$name.tar"
    if (-not (Test-Path $tar)) {
        docker save -o $tar $img
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] docker save 失败：$img" -ForegroundColor Red
            exit 1
        }
    }
    $tarMap[$img] = $tar
}

# ------------------------------------------------------------
# 第 3 步：逐节点逐镜像导入
# ------------------------------------------------------------
Write-Host "[3/3] 导入集群节点..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    $have = docker exec $node ctr -n k8s.io images ls 2>&1
    foreach ($img in $images) {
        if (-not $Force -and ($have | Where-Object { $_ -match [regex]::Escape($img) })) {
            Write-Host "  [跳过] $node 已有 $img" -ForegroundColor DarkGray
            continue
        }
        Write-Host "  导入 $node <- $img ..." -ForegroundColor DarkGray
        docker cp "$($tarMap[$img])" "${node}:/tmp/minio-import.tar"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] docker cp 失败：$node" -ForegroundColor Red
            exit 1
        }
        docker exec $node ctr -n k8s.io images import /tmp/minio-import.tar
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] ctr import 失败：$node" -ForegroundColor Red
            exit 1
        }
        docker exec $node rm -f /tmp/minio-import.tar 2>$null
    }
}

Write-Host ""
Write-Host "[完成] MinIO 镜像已就绪。可运行 .\minio\install.ps1 部署。" -ForegroundColor Green
