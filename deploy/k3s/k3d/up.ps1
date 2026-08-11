# 创建 / 启动 k3d 开发集群

# 任一命令失败立即停止，避免在错误状态下继续执行
$ErrorActionPreference = "Stop"

# 集群配置文件的绝对路径（脚本所在目录下的 cluster.yaml）
$config = Join-Path $PSScriptRoot "cluster.yaml"

# 自动定位 k3d 可执行文件
function Find-K3d {
    # 已存在于 PATH 则直接可用
    if (Get-Command k3d -ErrorAction SilentlyContinue) { return $true }

    # 候选路径：winget 的 Links 目录（命令别名）与 Packages 目录（真实 exe）
    $candidates = @()
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Links" -Filter "k3d*" -ErrorAction SilentlyContinue
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "k3d.exe" -ErrorAction SilentlyContinue

    foreach ($c in $candidates) {
        # 逐个校验存在性，命中则将所在目录加入 PATH
        if ($c -and (Test-Path $c.FullName)) {
            $env:Path = "$($c.Directory.FullName);$env:Path"
            Write-Host "已自动定位 k3d：$($c.FullName)" -ForegroundColor DarkGray
            return $true
        }
    }
    return $false
}

# 前置检查 1：k3d 必须存在
if (-not (Find-K3d)) {
    Write-Host "[错误] 未安装 k3d，请先安装：" -ForegroundColor Red
    Write-Host "  winget install k3d" -ForegroundColor Yellow
    exit 1
}

# 前置检查 2：kubectl 必须存在（Docker Desktop 自带）
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未安装 kubectl，请安装 kubectl 或使用 Docker Desktop 自带的。" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 第 1 步：幂等创建集群
# 若同名集群已存在（例如上次运行遗留），跳过创建，避免报错
# ------------------------------------------------------------
Write-Host "[1/3] 检查集群 'artifact-scanning' 状态..." -ForegroundColor Cyan
$clusterExists = k3d cluster list 2>$null | Select-String "artifact-scanning"
if ($clusterExists) {
    Write-Host "集群 'artifact-scanning' 已存在，跳过创建。" -ForegroundColor Yellow
} else {
    Write-Host "正在创建 k3d 集群 'artifact-scanning'（1 个 server + 2 个 agent）..." -ForegroundColor Cyan
    k3d cluster create --config $config
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] 集群创建失败。" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# 将集群的访问信息合并进默认 kubeconfig（~/.kube/config），
# 确保后续 kubectl 命令能连上该集群（重复合并是幂等的）
k3d kubeconfig merge artifact-scanning --kubeconfig-merge-default 2>$null

# ------------------------------------------------------------
# 第 2 步：等待所有节点就绪
# ------------------------------------------------------------
Write-Host "[2/3] 正在等待节点就绪..." -ForegroundColor Cyan
kubectl wait --for=condition=Ready node --all --timeout=180s

# ------------------------------------------------------------
# 第 3 步：输出最终节点状态
# ------------------------------------------------------------
Write-Host "[3/3] 集群已启动。节点：" -ForegroundColor Green
kubectl get nodes -o wide

Write-Host ""
Write-Host "集群已就绪，可用 .\verify.ps1 验证。" -ForegroundColor Green
