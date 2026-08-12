# ============================================================
# common.ps1 —— 公共函数库（供 deploy/ 下各脚本引用）
# 用法：. (Join-Path $PSScriptRoot "..\lib\common.ps1")
#       路径层级：deploy/k3s/k3d 用 "..\..\lib\common.ps1"
#                 deploy/harbor 用 "..\lib\common.ps1"
#                 deploy/ 直接用 "lib\common.ps1"
# 功能：仓库根定位、winget CLI 自动定位、kubectl context 切换
# ============================================================
$ErrorActionPreference = "Stop"

# 仓库根目录（deploy/lib/ 的上上级）
$Global:RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

# ------------------------------------------------------------
# Find-Tool —— 自动定位 winget 安装的 CLI 工具（k3d/helm/kubectl 等）
# 背景：winget 安装后需重启 shell 才刷新 PATH，这里自动搜索
#       WinGet Links / Packages 目录并临时加入当前会话 PATH。
# 返回：找到返回 $Name，否则返回 $null
# ------------------------------------------------------------
function Find-Tool {
    param([string]$Name)
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return $Name }

    $links = "$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    $pkgs  = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
    $cands = @()
    $cands += Get-ChildItem $links -Filter "$Name*" -ErrorAction SilentlyContinue
    $cands += Get-ChildItem $pkgs -Recurse -Filter "$Name.exe" -ErrorAction SilentlyContinue

    foreach ($c in $cands) {
        if ($c -and (Test-Path $c.FullName)) {
            $env:Path = "$($c.Directory.FullName);$env:Path"
            Write-Host "已自动定位 $Name：$($c.FullName)" -ForegroundColor DarkGray
            return $Name
        }
    }
    return $null
}

# ------------------------------------------------------------
# Require-Tool —— 确保命令可用（自动定位），否则报错退出
# 参数：-Name 命令名，-Hint 缺失时的安装提示
# ------------------------------------------------------------
function Require-Tool {
    param([string]$Name, [string]$Hint = "")
    if (-not (Find-Tool $Name)) {
        Write-Host "[错误] 未安装 $Name。$Hint" -ForegroundColor Red
        exit 1
    }
}

# ------------------------------------------------------------
# Ensure-Context —— 确保 kubectl 使用指定集群 context
# 参数：-Expected 期望的 context 名（默认 k3d 开发集群）
# ------------------------------------------------------------
function Ensure-Context {
    param([string]$Expected = "k3d-artifact-scanning")
    $ctx = kubectl config current-context
    if ($ctx -ne $Expected) {
        Write-Host "[提示] 当前 context 为 $ctx，切换到 $Expected ..." -ForegroundColor Yellow
        kubectl config use-context $Expected | Out-Null
    }
}
