# 初始化 Harbor（创建项目 + CI 机器人账号）
$ErrorActionPreference = "Stop"

$baseUrl   = "http://localhost:30002"
$adminUser = "admin"
$adminPass = if ($env:HARBOR_ADMIN_PASSWORD) { $env:HARBOR_ADMIN_PASSWORD } else { "Harbor12345" }
$project   = "artifact"
$robotName = "cicd"

# Basic Auth 请求头
$cred = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$($adminUser):$($adminPass)"))
$headers = @{ Authorization = "Basic $cred"; "Content-Type" = "application/json" }

# ------------------------------------------------------------
# 第 1 步：幂等创建项目（public）
# ------------------------------------------------------------
Write-Host "[1/2] 检查/创建项目 $project ..." -ForegroundColor Cyan
$projects = Invoke-RestMethod -Uri "$baseUrl/api/v2.0/projects" -Headers $headers
if ($projects.name -contains $project) {
    Write-Host "项目 $project 已存在，跳过。" -ForegroundColor Yellow
} else {
    $body = @{ project_name = $project; metadata = @{ public = "true" } } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "$baseUrl/api/v2.0/projects" -Method Post -Headers $headers -Body $body
    Write-Host "项目 $project 创建成功（public）。" -ForegroundColor Green
}

# ------------------------------------------------------------
# 第 2 步：幂等创建机器人账号（push/pull 权限）
# ------------------------------------------------------------
Write-Host "[2/2] 检查/创建机器人账号 $robotName ..." -ForegroundColor Cyan

# 构造机器人权限请求体
$body = @{
    name      = $robotName
    duration  = -1          # 永不过期
    level     = "project"
    disable   = $false
    permissions = @(
        @{
            kind      = "project"
            namespace = $project
            access    = @(
                @{ resource = "repository"; action = "push" },
                @{ resource = "repository"; action = "pull" },
                @{ resource = "artifact";  action = "read" },
                @{ resource = "tag";       action = "create" },
                @{ resource = "tag";       action = "delete" }
            )
        }
    )
} | ConvertTo-Json -Depth 5

$robotUsername = "robot`$$project+$robotName"

# 幂等策略：直接创建，捕获 CONFLICT（已存在）视为跳过。
# 说明：Harbor 的 GET /robots 列表接口返回空数组不可靠，故不依赖列表查询。
try {
    $result = Invoke-RestMethod -Uri "$baseUrl/api/v2.0/robots" -Method Post -Headers $headers -Body $body
    $secret = $result.secret

    # 保存凭据（敏感文件，请勿提交）
    $credFile = Join-Path $PSScriptRoot ".harbor-credentials.json"
    @{ username = $robotUsername; secret = $secret; registry = $baseUrl } | ConvertTo-Json | Set-Content -Path $credFile -Encoding UTF8

    Write-Host "机器人账号创建成功。" -ForegroundColor Green
    Write-Host "  用户名 : $robotUsername" -ForegroundColor Cyan
    Write-Host "  secret : $secret" -ForegroundColor Cyan
    Write-Host "  已保存 : $credFile " -ForegroundColor Yellow
} catch {
    if ($_.Exception.Message -match "already exists|CONFLICT") {
        Write-Host "机器人账号已存在，跳过。" -ForegroundColor Yellow
    } else {
        throw
    }
}

Write-Host ""
Write-Host "初始化完成。CI 推送示例：" -ForegroundColor Green
Write-Host "  docker login localhost:30002 -u robot`$$project+$robotName --password-stdin" -ForegroundColor Cyan
Write-Host "  docker tag <image> localhost:30002/$project/<name>:<tag>" -ForegroundColor Cyan
Write-Host "  docker push localhost:30002/$project/<name>:<tag>" -ForegroundColor Cyan
