# ============================================================
# import-images.ps1 —— 将监控栈镜像导入 k3d 集群节点（离线化）
# 用法：.\import-images.ps1 [-Force]
#       镜像来源：经代理 docker pull（quay.io / registry.k8s.io / docker.io / ghcr.io）
#       幂等：节点已具备全部镜像时自动跳过（-Force 强制重导）。
#       前置：集群已启动（up.ps1）；本机 docker 可用且能访问外网（代理 127.0.0.1:7897）。
# ============================================================
param(
    [switch]$Force
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

# 本机代理（docker pull / 外网访问用；Docker Desktop 需已配置或在环境变量中）
$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

# 前置检查
Require-Tool "k3d"
Require-Tool "kubectl"
Ensure-Context

# 监控栈镜像清单（与 kube-prometheus-stack 88.5.4 / Prometheus Operator v0.93.1 对齐）
$images = @(
    "quay.io/prometheus/prometheus:v3.14.0-distroless",
    "quay.io/prometheus/alertmanager:v0.34.0",
    "quay.io/prometheus-operator/prometheus-operator:v0.93.1",
    "quay.io/prometheus-operator/prometheus-config-reloader:v0.93.1",
    "quay.io/prometheus/node-exporter:v1.12.1-distroless",
    "registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.20.0",
    "docker.io/grafana/grafana:13.2.0",
    "quay.io/kiwigrid/k8s-sidecar:2.10.1"
)

# registry.k8s.io 镜像改为节点直拉：
# Docker Desktop 的 docker save 对 registry.k8s.io 镜像存在导出 bug
# （只导出 manifest 不导出 Config/层 blob，ctr import 报 content digest not found），
# 但节点 containerd 可直接访问 registry.k8s.io（已验证可直连），故走 ctr pull。
$pullDirect = @(
    "registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.20.0"
)
$saveImports = @($images | Where-Object { $_ -notin $pullDirect })

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
# 第 1 步：本机 docker 拉取缺失镜像（幂等）
# ------------------------------------------------------------
Write-Host "[1/4] 本机 docker pull 监控镜像（共 $($images.Count) 个）..." -ForegroundColor Cyan
foreach ($img in $images) {
    # 幂等：本机已有该镜像则跳过拉取
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
            Write-Host "  [错误] docker pull 失败：$img（请检查代理 127.0.0.1:7897）" -ForegroundColor Red
            exit 1
        }
    }
}

# ------------------------------------------------------------
# 第 2 步：逐镜像单独 docker save 到临时目录
# （不用合并 tar：多镜像合并的 tar 在 ctr import 时可能报
#   "content digest not found"，逐镜像导入更稳健）
# ------------------------------------------------------------
Write-Host "[2/4] 逐镜像 docker save 到临时目录（$($saveImports.Count) 个；$($pullDirect.Count) 个走节点直拉）..." -ForegroundColor Cyan
$imgDir = Join-Path $env:TEMP "monitoring-imgs"
New-Item -ItemType Directory -Path $imgDir -Force | Out-Null
$tarMap = @{}
foreach ($img in $saveImports) {
    $name = ($img -replace '[^A-Za-z0-9._-]', '_')
    $tar  = Join-Path $imgDir "$name.tar"
    if (-not (Test-Path $tar)) {
        Write-Host "  save $img ..." -ForegroundColor DarkGray
        docker save -o $tar $img
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] docker save 失败：$img" -ForegroundColor Red
            exit 1
        }
    }
    $tarMap[$img] = $tar
}
Write-Host "  已生成 $($tarMap.Count) 个单镜像 tar 于 $imgDir" -ForegroundColor DarkGray

# ------------------------------------------------------------
# 第 3 步：逐节点逐镜像导入（docker cp + ctr，幂等）
# 顺序：先节点直拉（registry.k8s.io），再导入 save 镜像
# ------------------------------------------------------------
Write-Host "[3/4] 导入集群节点..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    $have = docker exec $node ctr -n k8s.io images ls 2>&1

    # 3a：节点直拉镜像（registry.k8s.io）
    foreach ($img in $pullDirect) {
        if (-not $Force -and ($have | Where-Object { $_ -match [regex]::Escape($img) })) {
            Write-Host "  [跳过] $node 已有 $img" -ForegroundColor DarkGray
            continue
        }
        Write-Host "  [直拉] $node <- $img ..." -ForegroundColor DarkGray
        docker exec $node ctr -n k8s.io images pull $img
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] ctr pull 失败：$node <- $img" -ForegroundColor Red
            exit 1
        }
    }

    # 3b：导入 save 镜像
    foreach ($img in $saveImports) {
        $full = $img
        if (-not $Force -and ($have | Where-Object { $_ -match [regex]::Escape($full) })) {
            Write-Host "  [跳过] $node 已有 $full" -ForegroundColor DarkGray
            continue
        }
        Write-Host "  导入 $node <- $full ..." -ForegroundColor DarkGray
        $tar = $tarMap[$img]
        docker cp "$tar" "${node}:/tmp/mon-import.tar"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] docker cp 失败：$node" -ForegroundColor Red
            exit 1
        }
        docker exec $node ctr -n k8s.io images import /tmp/mon-import.tar
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [错误] ctr import 失败：$node <- $full" -ForegroundColor Red
            exit 1
        }
        docker exec $node rm -f /tmp/mon-import.tar 2>$null
    }
}

# ------------------------------------------------------------
# 第 4 步：验证各节点镜像
# ------------------------------------------------------------
Write-Host "[4/4] 验证节点镜像..." -ForegroundColor Cyan
foreach ($node in $nodes) {
    $cnt = 0
    foreach ($img in $images) {
        if (docker exec $node ctr -n k8s.io images ls 2>&1 | Select-String -Pattern ([regex]::Escape($img))) { $cnt++ }
    }
    Write-Host "  $node : $cnt / $($images.Count) 个监控镜像" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[完成] 监控栈镜像已就绪。" -ForegroundColor Green
Write-Host "       现在可运行 .\monitoring\install.ps1 部署监控栈。" -ForegroundColor Cyan
