# ============================================================
# import-images.ps1 —— 将 Harbor 离线镜像导入 k3d 集群节点
# 用法：.\import-images.ps1 [-TarFile 离线tar] [-Force]
#       默认 tar：deploy\harbor\offline\harbor-images-v2.15.2.tar
#       幂等：节点已具备全部镜像时自动跳过（-Force 强制重导）。
#       前置：集群已启动（up.ps1）。
# ============================================================
param(
    [string]$TarFile = "",
    [switch]$Force
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

# 默认离线镜像路径（项目内固定位置，版本与 values.yaml 对齐）
if (-not $TarFile) {
    $TarFile = Join-Path $RepoRoot "deploy\harbor\offline\harbor-images-v2.15.2.tar"
}
if (-not [System.IO.Path]::IsPathRooted($TarFile)) {
    $TarFile = Join-Path $RepoRoot $TarFile
}
if (-not (Test-Path $TarFile)) {
    Write-Host "[错误] 未找到离线镜像：$TarFile" -ForegroundColor Red
    exit 1
}

# 前置检查
Require-Tool "k3d"
Require-Tool "kubectl"
Ensure-Context

# Harbor 需就绪的镜像清单（v2.15.2，与 offline tar 内容一致）
$needTags = @(
    "harbor-core:v2.15.2", "harbor-db:v2.15.2", "harbor-jobservice:v2.15.2",
    "harbor-portal:v2.15.2", "harbor-registryctl:v2.15.2", "nginx-photon:v2.15.2",
    "registry-photon:v2.15.2", "trivy-adapter-photon:v2.15.2", "valkey-photon:v2.15.2"
)

# 节点容器名（排除 serverlb / tools 辅助节点，它们只做转发或辅助，无需镜像）
$nodes = docker ps --format "{{.Names}}" | Where-Object {
    $_ -like "k3d-artifact-scanning-*" -and $_ -notlike "*serverlb*" -and $_ -notlike "*tools*"
}
if (-not $nodes) {
    Write-Host "[错误] 未找到 k3d 节点容器，请先运行 up.ps1 启动集群。" -ForegroundColor Red
    exit 1
}
Write-Host "节点：$($nodes -join ', ')" -ForegroundColor Cyan

# ------------------------------------------------------------
# 第 1 步：docker load 到本机（校验 tar 有效性，镜像可复用）
# ------------------------------------------------------------
Write-Host "[1/3] docker load 校验离线 tar..." -ForegroundColor Cyan
docker load -i $TarFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] docker load 失败，tar 可能损坏。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 2 步：逐节点导入（docker cp + ctr，规避 k3d image import 的 Windows 路径 bug）
# ------------------------------------------------------------
Write-Host "[2/3] 导入集群节点..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    # 幂等：该节点已含全部镜像则跳过
    $have = docker exec $node ctr -n k8s.io images ls 2>&1
    $missing = @($needTags | Where-Object {
        $tag = $_
        -not ($have | Where-Object { $_ -match "goharbor/$([regex]::Escape($tag))" })
    })
    if (-not $Force -and $missing.Count -eq 0) {
        Write-Host "  [跳过] $node 已具备全部 Harbor 镜像" -ForegroundColor DarkGray
        continue
    }
    Write-Host "  导入 $node ..." -ForegroundColor DarkGray
    docker cp "$TarFile" "${node}:/tmp/harbor-images.tar"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [错误] docker cp 失败：$node" -ForegroundColor Red
        exit 1
    }
    docker exec $node ctr -n k8s.io images import /tmp/harbor-images.tar
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [错误] ctr import 失败：$node" -ForegroundColor Red
        exit 1
    }
    docker exec $node rm -f /tmp/harbor-images.tar 2>$null
}

# ------------------------------------------------------------
# 第 3 步：验证各节点镜像
# ------------------------------------------------------------
Write-Host "[3/3] 验证节点镜像..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    $cnt = (docker exec $node ctr -n k8s.io images ls 2>&1 | Select-String "goharbor").Count
    Write-Host "  $node : $cnt 个 goharbor 镜像" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[完成] Harbor 离线镜像已就绪。" -ForegroundColor Green
Write-Host "       现在可运行 .\harbor\install.ps1 部署 Harbor。" -ForegroundColor Cyan
