# ============================================================
# import-images.ps1 —— 将 Milvus 向量库镜像导入 k3d 集群节点（离线化）
# 用法：.\import-images.ps1 [-Force]
#       镜像来源：经代理 docker pull（milvus 官方 chart standalone 依赖）
#       幂等：节点已具备全部镜像时自动跳过（-Force 强制重导）。
#       前置：集群已启动（up.ps1）；本机 docker 可用且能访问外网（代理 127.0.0.1:7897）。
# ============================================================
param(
    [switch]$Force
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

# 本机代理（docker pull / 外网访问用）
$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

# 前置检查
Require-Tool "k3d"
Require-Tool "kubectl"
Ensure-Context

# 镜像清单（chart 引用名；minio tag 需与 values.yaml 一致）
$targets = @(
    "milvusdb/milvus:v2.2.13",
    "milvusdb/etcd:3.5.5-r2",
    "minio/minio:RELEASE.2023-09-04T19-57-37Z",
    "milvusdb/milvus-config-tool:v0.1.1"
)

# 节点容器名（排除 serverlb / tools 辅助节点）
$nodes = docker ps --format "{{.Names}}" | Where-Object {
    $_ -like "k3d-artifact-scanning-*" -and $_ -notlike "*serverlb*" -and $_ -notlike "*tools*"
}
if (-not $nodes) {
    Write-Host "[错误] 未找到 k3d 节点容器，请先运行 up.ps1 启动集群。" -ForegroundColor Red
    exit 1
}
Write-Host "节点：$($nodes -join ', ')" -ForegroundColor Cyan

# ------------------------------------------------------------
# ------------------------------------------------------------
# 第 1 步：确保本机具备镜像（离线 tar 优先，否则 docker pull）
# ------------------------------------------------------------
Write-Host "[1/4] 准备本机 Milvus 镜像（离线 tar / 拉取，共 $($targets.Count) 个）..." -ForegroundColor Cyan
$OfflineDir = Join-Path $PSScriptRoot "offline"
foreach ($img in $targets) {
    if (-not $Force) {
        docker image inspect $img 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [已有] $img" -ForegroundColor DarkGray
            continue
        }
    }
    $tar = Join-Path $OfflineDir (($img -replace '[/:]', '_') + ".tar")
    if (Test-Path $tar) {
        Write-Host "  [离线加载] $img <- $tar" -ForegroundColor DarkGray
        docker load -i $tar
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
# 第 2 步：准备导入用 tar（优先复用 offline 目录，其余 save 到临时目录）
# ------------------------------------------------------------
Write-Host "[2/4] 准备导入 tar（离线优先）..." -ForegroundColor Cyan
$imgDir = Join-Path $env:TEMP "milvus-imgs"
New-Item -ItemType Directory -Path $imgDir -Force | Out-Null
$tarMap = @{}
foreach ($img in $targets) {
    $offTar = Join-Path $OfflineDir (($img -replace '[/:]', '_') + ".tar")
    if (Test-Path $offTar) {
        $tarMap[$img] = $offTar
        continue
    }
    $name = ($img -replace '[^A-Za-z0-9._-]', '_')
    $tar  = Join-Path $imgDir "$name.tar"
    if (-not (Test-Path $tar)) {
        Write-Host "  save $img ..." -ForegroundColor DarkGray
        docker save -o $tar $img
    }
    $tarMap[$img] = $tar
}
Write-Host "  已准备 $($tarMap.Count) 个单镜像 tar" -ForegroundColor DarkGray

# ------------------------------------------------------------
# 第 3 步：逐节点逐镜像导入（docker cp + ctr，幂等）
# ------------------------------------------------------------
Write-Host "[3/4] 导入集群节点..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    $have = docker exec $node ctr -n k8s.io images ls 2>&1
    foreach ($img in $targets) {
        if (-not $Force -and ($have | Where-Object { $_ -match [regex]::Escape($img) })) {
            Write-Host "  [跳过] $node 已有 $img" -ForegroundColor DarkGray
            continue
        }
        Write-Host "  导入 $node <- $img ..." -ForegroundColor DarkGray
        $tar = $tarMap[$img]
        docker cp "$tar" "${node}:/tmp/milvus-import.tar"
        docker exec $node ctr -n k8s.io images import /tmp/milvus-import.tar
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] ctr import 失败：$node <- $img" -ForegroundColor Red
            exit 1
        }
        docker exec $node rm -f /tmp/milvus-import.tar 2>$null
    }
}

# ------------------------------------------------------------
# 第 4 步：验证各节点镜像
# ------------------------------------------------------------
Write-Host "[4/4] 验证节点镜像..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    $cnt = 0
    foreach ($img in $targets) {
        if (docker exec $node ctr -n k8s.io images ls 2>&1 | Select-String -Pattern ([regex]::Escape($img))) { $cnt++ }
    }
    Write-Host "  $node : $cnt / $($targets.Count) 个 Milvus 镜像" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[完成] Milvus 镜像已就绪。" -ForegroundColor Green
Write-Host "       现在可运行 .\milvus\install.ps1 部署。" -ForegroundColor Cyan
