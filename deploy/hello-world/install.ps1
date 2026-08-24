# ============================================================
# install.ps1 —— 部署 hello-world（首个 Helm Chart 部署验证）
# 用法：.\install.ps1
#       创建命名空间 + imagePullSecret（Harbor robot 凭据）
#       + Helm 安装（镜像从 Harbor 拉取）+ port-forward 验证
# ============================================================
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$namespace = "hello-world"
$release   = "hello-world"
$chart     = Join-Path $PSScriptRoot "..\charts\hello-world"
$credFile  = Join-Path $RepoRoot "deploy\harbor\.harbor-credentials.json"

# 前置检查：helm 与 kubectl，并确保连接 k3d 集群
Require-Tool "helm" "请先安装：winget install Helm.Helm"
Require-Tool "kubectl"
Ensure-Context

# 读取 Harbor robot 凭据（用于集群拉取镜像的 imagePullSecret）
if (-not (Test-Path $credFile)) {
    Write-Host "[错误] 未找到 Harbor 凭据：$credFile" -ForegroundColor Red
    exit 1
}
$cred = Get-Content $credFile | ConvertFrom-Json
$registryServer = "host.k3d.internal:30002"

# ------------------------------------------------------------
# 第 1 步：创建命名空间
# ------------------------------------------------------------
Write-Host "[1/5] 创建命名空间 $namespace ..." -ForegroundColor Cyan
kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null

# ------------------------------------------------------------
# 第 2 步：创建 imagePullSecret（Harbor robot 凭据）
# ------------------------------------------------------------
Write-Host "[2/5] 创建 imagePullSecret（Harbor robot $($cred.username)）..." -ForegroundColor Cyan
kubectl delete secret harbor-registry -n $namespace --ignore-not-found | Out-Null
kubectl create secret docker-registry harbor-registry -n $namespace `
    --docker-server=$registryServer `
    --docker-username=$cred.username `
    --docker-password=$cred.secret | Out-Null

# ------------------------------------------------------------
# 第 3 步：Helm 安装（幂等：已存在则升级）
# ------------------------------------------------------------
Write-Host "[3/5] Helm 安装 $release ..." -ForegroundColor Cyan
helm upgrade --install $release $chart -n $namespace --wait --timeout 5m

# ------------------------------------------------------------
# 第 4 步：等待 Deployment 就绪
# ------------------------------------------------------------
Write-Host "[4/5] 等待 Deployment 就绪..." -ForegroundColor Cyan
kubectl rollout status deployment/$release -n $namespace --timeout=180s

# ------------------------------------------------------------
# 第 5 步：验证服务访问（port-forward + curl）
# ------------------------------------------------------------
Write-Host "[5/5] 验证服务访问（port-forward + curl）..." -ForegroundColor Cyan
$pf = Start-Job -ScriptBlock { kubectl port-forward -n hello-world svc/hello-world 38080:80 }
Start-Sleep -Seconds 6
try {
    $code = curl.exe -s -o NUL -w "%{http_code}" http://localhost:38080
    $body = curl.exe -s http://localhost:38080
    Write-Host "  HTTP $code" -ForegroundColor DarkGray
    Write-Host "  响应内容：" -ForegroundColor DarkGray
    $body | Select-String -Pattern "<h1>.*</h1>" | ForEach-Object { Write-Host "    $($_.Matches.Value)" -ForegroundColor DarkGray }
    if ($code -eq "200") {
        Write-Host "[完成] hello-world 部署验证通过。" -ForegroundColor Green
    } else {
        Write-Host "[警告] HTTP 状态码非 200（$code）。" -ForegroundColor Yellow
    }
} finally {
    Stop-Job $pf -ErrorAction SilentlyContinue
    Remove-Job $pf -ErrorAction SilentlyContinue
}

Write-Host "访问方式：kubectl port-forward -n $namespace svc/$release 38080:80 后打开 http://localhost:38080" -ForegroundColor Cyan
