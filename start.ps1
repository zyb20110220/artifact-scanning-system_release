# ============================================================
# start.ps1 —— 一键启动「文物断代与鉴定系统」本地开发环境
#
# 启动内容（全部幂等，可重复运行）：
#   1. Ollama   ：docker 容器 ollama-local（主机 11435 -> 容器 11434）
#   2. Milvus   ：kubectl port-forward 19530（本脚本托管的后台 job）
#   3. Neo4j    ：kubectl port-forward 7687 （本脚本托管的后台 job）
#   4. 后端     ：uvicorn artifact_scan.api:app :8000（并托管前端）
#
# 用法：
#   .\start.ps1             一键启动，完成后自动打开浏览器
#   .\start.ps1 -NoBrowser  不自动打开浏览器
#   .\start.ps1 -SkipOllama 跳过 Ollama 容器检查
#   或在资源管理器双击 start.bat
#
# 停止：在本脚本界面按 Ctrl+C，会自动清理端口转发与后端进程。
# ============================================================
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipOllama
)
$ErrorActionPreference = "Stop"

# 公共库（kubectl/docker 自动定位）
. (Join-Path $PSScriptRoot "deploy\lib\common.ps1")

$RepoRoot    = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPort = 8000
$PortOllama  = 11435
$PortMilvus  = 19530
$PortNeo4j   = 7687

# ------------------------------------------------------------
# 小工具
# ------------------------------------------------------------
function Test-PortListening([int]$Port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

# 返回一个自带 fastapi/uvicorn 的 python.exe 绝对路径
function Find-BackendPython {
    $cands = @()
    $known = "C:\Users\zyb\AppData\Local\Programs\Python\Python314\python.exe"
    if (Test-Path $known) { $cands += $known }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { $cands += $py.Source }
    foreach ($c in $cands) {
        try {
            $null = & $c -c "import fastapi,uvicorn" 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch {}
    }
    return $null
}

Write-Host ""
Write-Host "  ┌──────────────────────────────────────────────┐" -ForegroundColor DarkYellow
Write-Host "  │   文物断代与鉴定系统 · 一键启动               │" -ForegroundColor DarkYellow
Write-Host "  └──────────────────────────────────────────────┘" -ForegroundColor DarkYellow
Write-Host ""
Set-Location $RepoRoot

$forwardJobs = @()
$backendProc = $null

# 清理本脚本上一次遗留的同名 job（端口已被占用时会自动跳过重建）
Get-Job -Name "fw-*" -ErrorAction SilentlyContinue |
    Remove-Job -Force -ErrorAction SilentlyContinue

try {
    # ---- 前置检查 ----
    Require-Tool "kubectl" "请安装 kubectl（或使用 Docker Desktop 自带的）。"
    if (-not $SkipOllama) { Require-Tool "docker" "请安装并启动 Docker Desktop。" }

    # ---- 1. Ollama ----
    if ($SkipOllama) {
        Write-Host "[1/4] 已跳过 Ollama 检查（-SkipOllama）" -ForegroundColor DarkGray
    } else {
        Write-Host "[1/4] Ollama（docker 容器 ollama-local）..." -ForegroundColor Cyan
        $c = docker ps -a --filter "name=^/ollama-local$" --format "{{.Names}}" 2>$null
        if ($c) {
            docker start ollama-local | Out-Null
            Write-Host "      ollama-local 已就绪（端口 $PortOllama）" -ForegroundColor Green
        } else {
            Write-Host "      [警告] 未找到容器 ollama-local，LLM 详细报告将不可用（快速模式不受影响）" -ForegroundColor Yellow
        }
    }

    # ---- 2/3. Milvus / Neo4j 端口转发 ----
    Write-Host "[2/4] Milvus / Neo4j 端口转发..." -ForegroundColor Cyan
    $fw = @(
        @{ Name = "milvus"; Ns = "milvus"; Svc = "milvus"; Port = $PortMilvus },
        @{ Name = "neo4j";  Ns = "neo4j";  Svc = "neo4j";  Port = $PortNeo4j }
    )
    foreach ($f in $fw) {
        if (Test-PortListening $f.Port) {
            Write-Host "      $($f.Name) :$($f.Port) 已在监听，跳过" -ForegroundColor Green
        } else {
            Write-Host "      启动 $($f.Name) port-forward :$($f.Port) ..." -ForegroundColor Yellow
            $j = Start-Job -Name "fw-$($f.Name)" -ScriptBlock {
                param($ns, $svc, $port)
                kubectl port-forward -n $ns svc/$svc "$($port):$($port)"
            } -ArgumentList $f.Ns, $f.Svc, $f.Port
            $forwardJobs += $j
        }
    }
    # 等待端口就绪（最多 90s）
    $deadline = (Get-Date).AddSeconds(90)
    foreach ($f in $fw) {
        while (-not (Test-PortListening $f.Port) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 800
        }
        if (Test-PortListening $f.Port) {
            Write-Host "      $($f.Name) :$($f.Port) 就绪" -ForegroundColor Green
        } else {
            Write-Host "      $($f.Name) :$($f.Port) 未就绪（将影响相似检索 / 证据图谱）" -ForegroundColor Red
        }
    }

    # ---- 4. 后端 ----
    Write-Host "[3/4] 启动后端（uvicorn :$BackendPort）..." -ForegroundColor Cyan
    if (Test-PortListening $BackendPort) {
        Write-Host "      :$BackendPort 已被占用（后端可能已在运行），跳过启动" -ForegroundColor Yellow
    } else {
        $PyPath = Find-BackendPython
        if (-not $PyPath) {
            throw "未找到带 fastapi/uvicorn 的 Python，请先安装依赖（pip install -r requirements.txt 或 pyproject.toml）"
        }
        Write-Host "      使用解释器：$PyPath" -ForegroundColor DarkGray
        $outLog = Join-Path $env:TEMP "artifact-backend.out.log"
        $errLog = Join-Path $env:TEMP "artifact-backend.err.log"
        $env:PYTHONPATH = "src"
        $backendProc = Start-Process -FilePath $PyPath `
            -ArgumentList @("-m", "uvicorn", "artifact_scan.api:app",
                            "--host", "127.0.0.1", "--port", "$BackendPort") `
            -WorkingDirectory $RepoRoot `
            -RedirectStandardOutput $outLog `
            -RedirectStandardError $errLog `
            -WindowStyle Hidden -PassThru
    }

    # 等待后端就绪（首次启动可能加载特征模型）
    Write-Host "      等待后端就绪..." -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds(180)
    $health = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 5
            break
        } catch { Start-Sleep -Seconds 2 }
    }
    if ($health) {
        Write-Host "      后端就绪，服务状态：" -ForegroundColor Green
        foreach ($k in $health.services.PSObject.Properties.Name) {
            $up = $health.services.$k -eq "up"
            $mark = if ($up) { "up ✔" } else { "down ✘" }
            Write-Host ("        {0,-8} {1}" -f $k, $mark) -ForegroundColor $(if ($up) { "Green" } else { "Red" })
        }
    } else {
        Write-Host "      [警告] 后端未能在 180s 内就绪，最近日志：" -ForegroundColor Red
        if (Test-Path $errLog) {
            Get-Content $errLog -Tail 15 -ErrorAction SilentlyContinue |
                ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
        }
    }

    # ---- 打开浏览器 ----
    if (-not $NoBrowser) {
        Write-Host "[4/4] 打开浏览器 http://127.0.0.1:$BackendPort ..." -ForegroundColor Cyan
        Start-Process "http://127.0.0.1:$BackendPort"
    }

    Write-Host ""
    Write-Host "[完成] 系统已启动。访问：http://127.0.0.1:$BackendPort" -ForegroundColor Green
    Write-Host "      按 Ctrl+C 停止（会同时清理端口转发与后端进程）。" -ForegroundColor Green
    Write-Host ""

    # ---- 保持前台运行，实时回显后端日志 ----
    $shown = 0
    while ($true) {
        Start-Sleep -Seconds 2
        if ($backendProc -and $backendProc.HasExited) {
            Write-Host "      [提示] 后端进程已退出，自动清理并退出。" -ForegroundColor Yellow
            break
        }
        if (Test-Path $errLog) {
            $lines = @(Get-Content $errLog -ErrorAction SilentlyContinue)
            if ($lines.Count -gt $shown) {
                $lines | Select-Object -Skip $shown |
                    ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
                $shown = $lines.Count
            }
        }
    }
}
finally {
    Write-Host ""
    Write-Host "[停止] 清理后台进程..." -ForegroundColor Yellow
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    foreach ($j in $forwardJobs) {
        Stop-Job $j -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $j -Force -ErrorAction SilentlyContinue | Out-Null
    }
    Write-Host "[停止] 完成。再见！" -ForegroundColor Yellow
}
