# down.ps1 —— 删除 k3d 开发集群

# 任一命令失败立即停止
$ErrorActionPreference = "Stop"

function Find-K3d {
    if (Get-Command k3d -ErrorAction SilentlyContinue) { return $true }
    $candidates = @()
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Links" -Filter "k3d*" -ErrorAction SilentlyContinue
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "k3d.exe" -ErrorAction SilentlyContinue
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c.FullName)) {
            $env:Path = "$($c.Directory.FullName);$env:Path"
            Write-Host "已自动定位 k3d：$($c.FullName)" -ForegroundColor DarkGray
            return $true
        }
    }
    return $false
}

# 前置检查：k3d 必须存在
if (-not (Find-K3d)) {
    Write-Host "[错误] 未安装 k3d。" -ForegroundColor Red
    exit 1
}

# 第 1 步：删除集群（容器与内置网络一并清理）
Write-Host "[1/2] 正在删除 k3d 集群 'artifact-scanning'..." -ForegroundColor Cyan
k3d cluster delete artifact-scanning

if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 集群删除失败。" -ForegroundColor Red
    exit $LASTEXITCODE
}

# 第 2 步：确认删除结果，并列出剩余集群便于核对
Write-Host "[2/2] 集群已删除。" -ForegroundColor Green
Write-Host "剩余集群：" -ForegroundColor Cyan
k3d cluster list
