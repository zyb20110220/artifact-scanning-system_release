# 验证 k3d 开发集群健康状态

# 任一命令失败立即停止
$ErrorActionPreference = "Stop"

# 前置检查：kubectl 必须存在
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未安装 kubectl。" -ForegroundColor Red
    exit 1
}

# 集群信息：控制平面地址与核心组件（CoreDNS / metrics-server）
Write-Host "===== 集群信息 =====" -ForegroundColor Cyan
kubectl cluster-info

# 节点状态：应为 1 个 control-plane + 2 个 agent，且全部 Ready
Write-Host ""
Write-Host "===== 节点（应为 1 个 server + 2 个 agent）=====" -ForegroundColor Cyan
kubectl get nodes -o wide

# 系统组件：Traefik / CoreDNS / local-path 等是否 Running 或 Completed
Write-Host ""
Write-Host "===== 全部命名空间 / Pod =====" -ForegroundColor Cyan
kubectl get pods -A

# 存储类：确认 local-path 为默认，供后续 PVC 使用
Write-Host ""
Write-Host "===== 存储类（StorageClass）=====" -ForegroundColor Cyan
kubectl get storageclass

# 判定依据：节点 Ready + Pod Running/Completed 即视为集群健康
Write-Host ""
Write-Host "[完成] 如果节点为 Ready、Pod 为 Running/Completed，则集群健康。" -ForegroundColor Green
