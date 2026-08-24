# 开发规范（Development Guidelines）

> 阶段 0.5：代码风格 / 提交规范 / 代码审查 / 质量门禁。
> 适用于本仓库（基础设施脚本、配置、文档）。提交消息细节另见
> 本地约定文档 `docs/contributing.md`（该文档不入库）。

## 1. 代码风格

### 1.1 PowerShell 脚本（deploy/ 下）

**文件结构**（脚本模板）：

```powershell
# ============================================================
# xxx.ps1 —— 一句话说明（做什么）
# 用法：.\xxx.ps1 [参数]
#       补充说明：幂等性 / 前置条件 / 输出结果
# ============================================================
param(
    [switch]$Force
)
$ErrorActionPreference = "Stop"

# 引入公共库（工具定位、仓库根）
. (Join-Path $PSScriptRoot "..\lib\common.ps1")

# 前置检查：依赖命令必须存在
Require-Tool "helm" "请先安装：winget install Helm.Helm"
Require-Tool "kubectl"
Ensure-Context

# ------------------------------------------------------------
# 第 1 步：步骤标题
# ------------------------------------------------------------
Write-Host "[1/3] 步骤描述..." -ForegroundColor Cyan
...
Write-Host "[完成] 部署完成。" -ForegroundColor Green
```

**关键约定**：

| 项 | 约定 |
|----|------|
| 文件头 | `# ===...===` 分隔线块：脚本名、用途、用法、幂等/前置说明 |
| 错误策略 | 顶部 `$ErrorActionPreference = "Stop"` |
| 公共库 | `deploy/lib/common.ps1` 提供 `Find-Tool` / `Require-Tool` / `Ensure-Context` / `$RepoRoot`；引用相对层级：`deploy/` 用 `lib\`，`deploy/k3s/k3d` 用 `..\..\lib\`，`deploy/{harbor,monitoring}` 用 `..\lib\` |
| 步骤分隔 | `# ---...---` + `# 第 N 步：描述`（步骤块） |
| 进度输出 | `Write-Host "[N/M] 描述..." -ForegroundColor Cyan`（M = 总步数，与文件头对应） |
| 子步骤 | 两空格缩进：`Write-Host "  子步骤..." -ForegroundColor DarkGray` |
| 幂等 | 脚本可重复执行；已存在则跳过，`-Force` 强制 |
| 外部命令 | 用 `$LASTEXITCODE` 检查退出码，非 0 时 `[错误]` + `exit 1` |
| 语言 | 注释与用户可见输出用中文 |

**输出颜色约定**：

| 颜色 | 用途 |
|------|------|
| Cyan | 步骤进度 `[N/M]` |
| DarkGray | 子步骤、跳过提示 |
| Yellow | 警告 / 提示 |
| Red | 错误 `[错误]`（通常后接 `exit 1`） |
| Green | 成功 `[完成]`、结果地址 |

**公共函数（common.ps1）风格**：`---` 分隔线注释块（函数名、用途、参数说明）+ `function` 定义 + `param()` 默认值。

### 1.2 配置与 YAML（cluster.yaml / values.yaml）

- 关键配置项用中文注释说明用途
- 分组注释（如 k3d 端口映射、Harbor / 监控栈组件）
- 敏感信息（密码 / 凭据）不写入提交文件；运行凭据放独立文件并排除
- 端口等常量在文档中与配置保持一致

### 1.3 文档（docs/）

- 所有 Markdown 统一放 `docs/`，索引见 [docs/README.md](README.md)
- 各目录下不放说明 md，统一链接回 docs/
- 内容避免重复：命令速查 / 完整流程只保留在单一文档
- 使用表格、分节、代码块，中文撰写

## 2. 提交规范

- **纯标题**，格式：`type: 阶段X任务0.Y - 描述(要点); 补充说明`
- **type**：`feat` / `fix` / `docs` 等 Conventional Commits 前缀
- 例：`feat: 阶段0任务0.3 - GitHub Actions CI(云端校验,无需本地常驻机器); 8步校验`
- **提交范围**：提交所有文件（除 `.git/info/exclude` 排除的运行时数据 / 备份 / 离线镜像 / 本地配置）
- **提交管控**：无用户明确指令不 `commit` / `push`；历史重写需确认后 `--force-with-lease`
- 详见本地约定文档 `docs/contributing.md`（不入库）

## 3. 代码审查

**流程**（改动合并前逐项核对）：

1. **变更清单**：`git status` 确认本次改动范围，排除不应提交的文件
2. **脚本语法**：用 PowerShell AST 校验（`Parser.ParseFile`），与 CI 第 1 步一致
3. **幂等与错误处理**：脚本可重复执行；`$LASTEXITCODE` 检查；失败有明确 `[错误]` 提示
4. **敏感信息**：密码 / 凭据 / token 不落入提交文件
5. **文档同步**：新组件 / 端口 / 命令同步到 docs/ 对应文档与索引
6. **配置一致性**：YAML 端口与文档、脚本默认值一致
7. **CI 通过**：推送后 8 步校验全绿

**重点关注**（本仓库易错点）：

- 节点过滤必须排除 `*serverlb*` 与 `*tools*`（k3d 辅助节点无 ctr）
- registry.k8s.io 镜像走节点直拉（Docker Desktop `docker save` 导出 bug）
- 多镜像合并 tar 的 `ctr import` 不可靠，需逐镜像导入
- 禁用 admissionWebhooks 时须同时关闭 `prometheusOperator.tls.enabled`

## 4. 质量门禁（GitHub Actions CI）

推送 / PR 到 `main` 触发 8 步云端校验（见 `.github/workflows/ci.yml`）：

| # | 校验 |
|---|------|
| 1 | PowerShell 脚本语法（pwsh AST） |
| 2 | docs 相对链接目标存在 |
| 3 | git exclude 规则（backup / cluster-data / offline 未被跟踪） |
| 4 | YAML 配置（cluster.yaml + values.yaml 可解析） |
| 5 | 公共库冒烟测试（common.ps1 函数可用） |
| 6 | 离线镜像清单一致性（import-images 与文档对齐） |
| 7 | actionlint（GitHub Actions 语法） |

> CI 为云端校验，无需本地常驻机器；新增脚本 / 配置 / 文档后应确认 CI 通过。
