# ============================================================
# down.ps1 —— 删除 k3d 开发集群
# 用法：.\down.ps1
#       删除集群容器与内置网络（不影响宿主机数据卷）。
# ============================================================
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\..\lib\common.ps1")

# 前置检查：k3d 必须存在
Require-Tool "k3d"

# ------------------------------------------------------------
# 第 1 步：删除集群（容器与内置网络一并清理）
# ------------------------------------------------------------
Write-Host "[1/2] 正在删除 k3d 集群 'artifact-scanning'..." -ForegroundColor Cyan
k3d cluster delete artifact-scanning

if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 集群删除失败。" -ForegroundColor Red
    exit $LASTEXITCODE
}

# ------------------------------------------------------------
# 第 2 步：确认删除结果，并列出剩余集群便于核对
# ------------------------------------------------------------
Write-Host "[2/2] 确认删除结果..." -ForegroundColor Cyan
k3d cluster list
Write-Host ""
Write-Host "[完成] 集群已删除。" -ForegroundColor Green
