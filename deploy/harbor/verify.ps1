# 验证 Harbor 部署健康状态
$ErrorActionPreference = "Stop"

$namespace = "harbor"
$expectedCtx = "k3d-artifact-scanning"

# 自动定位 kubectl（同 install.ps1 逻辑）
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
            return $Name
        }
    }
    return $null
}

if (-not (Find-Tool "kubectl")) {
    Write-Host "[错误] 未安装 kubectl。" -ForegroundColor Red
    exit 1
}

$ctx = kubectl config current-context
if ($ctx -ne $expectedCtx) {
    Write-Host "[提示] 当前 context 为 $ctx，切换到 $expectedCtx ..." -ForegroundColor Yellow
    kubectl config use-context $expectedCtx | Out-Null
}

# 检查 Harbor 各组件 Pod
Write-Host "===== Harbor 组件 Pod =====" -ForegroundColor Cyan
kubectl get pods -n $namespace

# 检查核心服务与 NodePort
Write-Host ""
Write-Host "===== Harbor Service（NodePort）=====" -ForegroundColor Cyan
kubectl get svc -n $namespace | Select-String "harbor-core|harbor-portal|harbor-registry"

# 探测 Web 门户是否可达（通过 port-forward 避免依赖 nodePort 网络）
Write-Host ""
Write-Host "===== Web 门户可达性探测 =====" -ForegroundColor Cyan
$job = Start-Job -ScriptBlock { kubectl port-forward -n harbor svc/harbor-portal 30002:80 }
Start-Sleep -Seconds 3
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:30002" -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -eq 200) {
        Write-Host "[OK] Harbor Web 门户可访问（HTTP $($resp.StatusCode)）" -ForegroundColor Green
    } else {
        Write-Host "[警告] Web 门户返回状态码 $($resp.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[错误] Web 门户不可达：$($_.Exception.Message)" -ForegroundColor Red
}
Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null

Write-Host ""
Write-Host "[完成] 若 Pod 均为 Running/Completed 且门户可达，则 Harbor 部署成功。" -ForegroundColor Green
