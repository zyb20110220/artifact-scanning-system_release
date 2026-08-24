# ============================================================
# up.ps1 —— 创建 / 启动 k3d 开发集群（幂等）
# 用法：.\up.ps1
#       集群已存在则跳过创建，仅合并 kubeconfig 并等待节点就绪。
# ============================================================
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\..\lib\common.ps1")

# 集群配置文件的绝对路径（脚本所在目录下的 cluster.yaml）
$config = Join-Path $PSScriptRoot "cluster.yaml"

# 前置检查：k3d 与 kubectl 必须存在
Require-Tool "k3d" "请先安装：winget install k3d"
Require-Tool "kubectl" "请安装 kubectl 或使用 Docker Desktop 自带的。"

# ------------------------------------------------------------
# 第 1 步：幂等创建集群（已存在则跳过）
# ------------------------------------------------------------
Write-Host "[1/4] 检查集群 'artifact-scanning' 状态..." -ForegroundColor Cyan
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
# 第 2 步：修正 kubeconfig 的 API server 地址
# k3d 默认写入 host.docker.internal:<端口>，但本机（Docker Desktop）
# 无法连通该域名，需改用 127.0.0.1；端口从 serverlb 的 6443 映射
# 动态获取（每次重建集群端口会变化）。
# ------------------------------------------------------------
Write-Host "[2/4] 修正 kubeconfig API server 地址..." -ForegroundColor Cyan
$server = kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}' 2>$null
if ($server -like "*host.docker.internal*") {
    $lbPort = (docker port k3d-artifact-scanning-serverlb 2>$null |
        Select-String "6443/tcp ->" | Select-Object -First 1) -replace '.*->.*:(\d+).*', '$1'
    if ($lbPort) {
        $newServer = "https://127.0.0.1:$lbPort"
        kubectl config set-cluster k3d-artifact-scanning --server=$newServer | Out-Null
        Write-Host "已修正：$server -> $newServer" -ForegroundColor Yellow
    } else {
        Write-Host "[警告] 未能获取 serverlb 6443 端口，跳过修正。" -ForegroundColor Yellow
    }
}

# ------------------------------------------------------------
# 第 3 步：等待所有节点就绪
# ------------------------------------------------------------
Write-Host "[3/4] 正在等待节点就绪..." -ForegroundColor Cyan
kubectl wait --for=condition=Ready node --all --timeout=180s

# ------------------------------------------------------------
# 第 4 步：输出最终节点状态
# ------------------------------------------------------------
Write-Host "[4/4] 等待完成。节点：" -ForegroundColor Cyan
kubectl get nodes -o wide
Write-Host ""
Write-Host "[完成] 集群已就绪。可继续 deploy/harbor/install.ps1 部署 Harbor。" -ForegroundColor Green
