# ============================================================
# publish.ps1 —— 构建 hello-world 镜像并推送到 Harbor
# 用法：.\publish.ps1 [-Tag latest]
#       镜像：localhost:30002/artifact/hello-world:<Tag>
#       前置：Harbor 已部署（localhost:30002）；代理 127.0.0.1:7897 可用
# ============================================================
param(
    [string]$Tag = "latest"
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

# 本机代理（docker build / pull 基础镜像用）
$Proxy = "http://127.0.0.1:7897"
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $Proxy }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $Proxy }

$appDir = Join-Path $RepoRoot "apps\hello-world"
$credFile = Join-Path $RepoRoot "deploy\harbor\.harbor-credentials.json"
$image = "localhost:30002/artifact/hello-world:$Tag"

# 前置检查：docker 与 Harbor 凭据
if (-not (Test-Path $credFile)) {
    Write-Host "[错误] 未找到 Harbor 凭据：$credFile" -ForegroundColor Red
    exit 1
}
$cred = Get-Content $credFile | ConvertFrom-Json

# ------------------------------------------------------------
# 第 1 步：构建镜像
# ------------------------------------------------------------
Write-Host "[1/3] 构建镜像 $image ..." -ForegroundColor Cyan
docker build -t $image $appDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 构建失败。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 2 步：登录 Harbor
# ------------------------------------------------------------
Write-Host "[2/3] 登录 Harbor（localhost:30002）..." -ForegroundColor Cyan
$env:DOCKER_CONFIG = Join-Path $env:TEMP "docker-harbor-login"
New-Item -ItemType Directory -Path $env:DOCKER_CONFIG -Force | Out-Null
docker login localhost:30002 -u $cred.username -p $cred.secret
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] Harbor 登录失败。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 3 步：推送镜像
# ------------------------------------------------------------
Write-Host "[3/3] 推送镜像 $image ..." -ForegroundColor Cyan
docker push $image
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 推送失败。" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[完成] 镜像已推送：$image" -ForegroundColor Green
Write-Host "       可运行 .\hello-world\install.ps1 部署。" -ForegroundColor Cyan
