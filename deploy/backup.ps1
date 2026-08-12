# ============================================================
# backup.ps1 —— 备份集群持久化数据（cluster-data/）
# 用法：.\backup.ps1 [-StopCluster] [-OutDir backup]
#       打包 cluster-data/ → backup\cluster-data-backup-<时间戳>.tar.gz
# ============================================================
param(
    [switch]$StopCluster,
    [string]$OutDir = "backup"
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "lib\common.ps1")

$dataDir = Join-Path $RepoRoot "cluster-data"
$outDir  = Join-Path $RepoRoot $OutDir

# 前置检查：数据目录必须存在且有数据
if (-not (Test-Path $dataDir)) {
    Write-Host "[错误] 未找到 $dataDir。请确认 cluster.yaml 数据卷挂载已生效。" -ForegroundColor Red
    exit 1
}
$hasData = Get-ChildItem $dataDir -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $hasData) {
    Write-Host "[警告] $dataDir 为空，可能挂载尚未生效。" -ForegroundColor Yellow
}

# ------------------------------------------------------------
# 第 1 步：停止集群（可选，保证数据一致性）
# ------------------------------------------------------------
if ($StopCluster) {
    Write-Host "[1/3] 停止集群以保证数据一致..." -ForegroundColor Cyan
    k3d cluster stop artifact-scanning
}

# ------------------------------------------------------------
# 第 2 步：打包 cluster-data
# ------------------------------------------------------------
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$stamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $outDir "cluster-data-backup-$stamp.tar.gz"

Write-Host "[2/3] 打包 $dataDir -> $archive ..." -ForegroundColor Cyan
Write-Host "       正在打包，请稍候..." -ForegroundColor DarkGray
tar -czf $archive -C $RepoRoot cluster-data
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 打包失败。" -ForegroundColor Red
    if ($StopCluster) { k3d cluster start artifact-scanning }
    exit 1
}

# ------------------------------------------------------------
# 第 3 步：重启集群（若第 1 步停止过）并输出结果
# ------------------------------------------------------------
if ($StopCluster) {
    Write-Host "[3/3] 重新启动集群..." -ForegroundColor Cyan
    k3d cluster start artifact-scanning
}

$size = [math]::Round((Get-Item $archive).Length / 1MB, 1)
Write-Host ""
Write-Host "[完成] 备份成功：$archive（$size MB）" -ForegroundColor Green
Write-Host "       迁移时请连同该备份文件一起拷贝到新机器。" -ForegroundColor Cyan
