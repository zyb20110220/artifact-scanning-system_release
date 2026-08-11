# 部署 Harbor 私有镜像仓库到 k3d 集群
# Harbor 部署到 harbor 命名空间，地址 http://localhost:30002
$ErrorActionPreference = "Stop"

$values     = Join-Path $PSScriptRoot "values.yaml"
$namespace  = "harbor"
$release    = "harbor"
$expectedCtx = "k3d-artifact-scanning"

# 自动定位 CLI 工具

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

# 前置检查：helm 与 kubectl
if (-not (Find-Tool "helm")) {
    Write-Host "[错误] 未安装 helm，请先安装：winget install Helm.Helm" -ForegroundColor Red
    exit 1
}
if (-not (Find-Tool "kubectl")) {
    Write-Host "[错误] 未安装 kubectl。" -ForegroundColor Red
    exit 1
}

# 前置检查：确认连接的是 k3d 集群
$ctx = kubectl config current-context
if ($ctx -ne $expectedCtx) {
    Write-Host "[提示] 当前 context 为 $ctx，切换到 $expectedCtx ..." -ForegroundColor Yellow
    kubectl config use-context $expectedCtx | Out-Null
}

# ------------------------------------------------------------
# 第 1 步：添加 Harbor Helm 仓库
# ------------------------------------------------------------
Write-Host "[1/4] 添加 Harbor Helm 仓库..." -ForegroundColor Cyan
helm repo add harbor https://helm.goharbor.io 2>$null | Out-Null
helm repo update harbor

# ------------------------------------------------------------
# 第 2 步：创建命名空间并安装 Harbor（幂等：已存在则升级）
# --wait 会等待所有组件就绪，首次拉取镜像可能较慢（15 分钟上限）
# ------------------------------------------------------------
Write-Host "[2/4] 创建命名空间 $namespace 并安装 Harbor..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
helm upgrade --install $release harbor/harbor -f $values -n $namespace --wait --timeout 15m

# ------------------------------------------------------------
# 第 3 步：等待各 Deployment 就绪
# ------------------------------------------------------------
Write-Host "[3/4] 等待 Harbor 组件就绪..." -ForegroundColor Cyan
kubectl rollout status deployment -n $namespace --timeout=300s

# ------------------------------------------------------------
# 第 4 步：输出部署结果
# ------------------------------------------------------------
Write-Host "[4/4] 部署完成。Pod 状态：" -ForegroundColor Green
kubectl get pods -n $namespace
Write-Host ""
Write-Host "Harbor 地址  ：http://localhost:30002" -ForegroundColor Green
Write-Host "管理员账号  ：admin / Harbor12345（首次登录请修改）" -ForegroundColor Green
Write-Host "重要        ：使用前请确保 Docker Desktop 的 insecure-registries 已加入 localhost:30002" -ForegroundColor Yellow
