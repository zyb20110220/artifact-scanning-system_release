# ============================================================
# remap-data.ps1 —— 数据重映射（将备份旧 PVC 数据复制到新 PVC 目录）
# 用法：.\remap-data.ps1
#       集群重建并恢复数据后必须执行，否则数据不会被加载。
# ============================================================
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "lib\common.ps1")

$namespace = "harbor"
$release   = "harbor"
$dataDir   = Join-Path $RepoRoot "cluster-data"

# 前置检查：kubectl，并确保连接 k3d 集群
Require-Tool "kubectl"
Ensure-Context

# 组件映射：PVC 名称（目录后缀）→ 工作负载
$workloads = [ordered]@{
    "database-data-harbor-database-0" = "statefulset/harbor-database"
    "harbor-registry"                 = "deployment/harbor-registry"
    "data-harbor-redis-0"             = "statefulset/harbor-redis"
    "harbor-jobservice"               = "deployment/harbor-jobservice"
    "data-harbor-trivy-0"             = "statefulset/harbor-trivy"
}

# ------------------------------------------------------------
# 第 1 步：识别当前在用 PVC（新目录）
# ------------------------------------------------------------
Write-Host "[1/3] 识别当前在用 PVC..." -ForegroundColor Cyan
$pvcJson = kubectl get pvc -n $namespace -o json
$newNames = @{}
foreach ($p in ($pvcJson | ConvertFrom-Json).items) {
    $newNames[$p.metadata.name] = "pvc-$($p.metadata.uid)_${release}_$($p.metadata.name)"
    Write-Host "  在用: $($p.metadata.name) -> $($newNames[$p.metadata.name])" -ForegroundColor DarkGray
}

# 扫描 cluster-data 下所有 pvc 目录
$allDirs = @(Get-ChildItem $dataDir -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^pvc-.*_${release}_" })

# ------------------------------------------------------------
# 第 2 步：对每个组件执行重映射（旧数据 → 新目录 + 重启）
# ------------------------------------------------------------
Write-Host "[2/3] 复制旧数据并重启组件..." -ForegroundColor Cyan
foreach ($pvcName in $workloads.Keys) {
    $workload = $workloads[$pvcName]
    $newName  = $newNames[$pvcName]
    if (-not $newName) {
        Write-Host "[跳过] $pvcName ：无当前在用 PVC" -ForegroundColor DarkGray
        continue
    }

    # 该组件的全部目录：新（uid 匹配 PVC）+ 旧（备份恢复，其他）
    $compDirs = $allDirs | Where-Object { $_.Name -like "*_${release}_${pvcName}" }
    $newDir   = $compDirs | Where-Object { $_.Name -eq $newName } | Select-Object -First 1
    $oldDir   = $compDirs | Where-Object { $_.Name -ne $newName } | Select-Object -First 1

    if (-not $oldDir) {
        Write-Host "[跳过] $pvcName ：无备份旧目录" -ForegroundColor DarkGray
        continue
    }
    $oldFiles = (Get-ChildItem $oldDir.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($oldFiles -eq 0) {
        Write-Host "[跳过] $pvcName ：旧目录为空" -ForegroundColor DarkGray
        continue
    }

    Write-Host ""
    Write-Host ">>> $pvcName" -ForegroundColor Green
    Write-Host "    旧目录: $($oldDir.FullName.Replace($dataDir,''))  [$oldFiles 文件]" -ForegroundColor DarkGray
    Write-Host "    新目录: $($newDir.FullName.Replace($dataDir,''))" -ForegroundColor DarkGray

    # 停止组件
    Write-Host "    停止 $workload ..." -ForegroundColor Cyan
    kubectl scale $workload -n $namespace --replicas=0
    Start-Sleep -Seconds 6   # 等待 Pod 终止，避免与数据复制冲突

    # 镜像复制：/MIR 清空目标并复制源全部（含清掉新初始化的空库）
    Write-Host "    复制旧数据 -> 新目录 ..." -ForegroundColor Cyan
    robocopy $oldDir.FullName $newDir.FullName /MIR /NFL /NDL /NJH /NJS /R:2 /W:2 | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Host "    [错误] $pvcName 数据复制失败（robocopy 退出码 $LASTEXITCODE）" -ForegroundColor Red
        kubectl scale $workload -n $namespace --replicas=1
        continue
    }

    # 启动组件
    Write-Host "    启动 $workload ..." -ForegroundColor Cyan
    kubectl scale $workload -n $namespace --replicas=1
}

# ------------------------------------------------------------
# 第 3 步：等待所有组件就绪
# ------------------------------------------------------------
Write-Host "[3/3] 等待组件就绪..." -ForegroundColor Cyan
kubectl rollout status deployment -n $namespace --timeout=240s
kubectl rollout status statefulset -n $namespace --timeout=240s

Write-Host ""
Write-Host "[完成] 数据重映射完成。请验证：admin 自定义密码是否可登录、项目/镜像是否复现。" -ForegroundColor Green
Write-Host "       验证参考：docs/reproducibility.md 第 7 步或 Harbor API。" -ForegroundColor Cyan
