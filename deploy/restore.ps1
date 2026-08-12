# ============================================================
# restore.ps1 —— 从备份还原集群持久化数据（cluster-data/）
# 用法：.\restore.ps1 -BackupFile "backup\xxx.tar.gz" [-Force]
#       -Force：跳过"目标已有数据"确认，用于自动化/脚本场景。
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [switch]$Force
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "lib\common.ps1")

$dataDir = Join-Path $RepoRoot "cluster-data"

# 将相对路径解析为相对仓库根，便于从任意目录调用
if (-not [System.IO.Path]::IsPathRooted($BackupFile)) {
    $BackupFile = Join-Path $RepoRoot $BackupFile
}

# 校验备份文件
if (-not (Test-Path $BackupFile)) {
    Write-Host "[错误] 未找到备份文件：$BackupFile" -ForegroundColor Red
    exit 1
}

# 目标目录存在且有数据时需确认（-Force 跳过交互确认）
if (-not $Force -and (Test-Path $dataDir) -and (Get-ChildItem $dataDir -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    Write-Host "[警告] $dataDir 已有数据，恢复将覆盖。" -ForegroundColor Yellow
    $ans = Read-Host "确认继续？(y/N)"
    if ($ans -notin @("y", "Y")) {
        Write-Host "已取消。" -ForegroundColor Cyan
        exit 0
    }
}

# ------------------------------------------------------------
# 第 1 步：解包备份（覆盖式，tar 会创建 cluster-data 及其子目录）
# ------------------------------------------------------------
Write-Host "[1/2] 解包备份到 $dataDir ..." -ForegroundColor Cyan
tar -xzf $BackupFile -C $RepoRoot
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 解包失败。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 2 步：校验恢复结果
# ------------------------------------------------------------
Write-Host "[2/2] 校验恢复结果..." -ForegroundColor Cyan
$count = (Get-ChildItem $dataDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host ""
Write-Host "[完成] 已恢复 $count 个文件到 $dataDir" -ForegroundColor Green

Write-Host ""
Write-Host "[完成] 数据已恢复。" -ForegroundColor Green
Write-Host "       请确认集群已用含数据卷挂载的 cluster.yaml 创建（up.ps1），" -ForegroundColor Cyan
Write-Host "       然后启动 Harbor（install.ps1）。" -ForegroundColor Cyan
