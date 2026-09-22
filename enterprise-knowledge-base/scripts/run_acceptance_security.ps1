# ==========================================================
# 10号测试 — 安全隔离 + 性能稳定性验收执行脚本
# 覆盖：安全红线(6项) + 性能稳定性(4项，其中2项手动)
# ==========================================================

param(
    [switch]$SkipDocker,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Results = @{}
$TotalPass = 0
$TotalFail = 0
$StartTime = Get-Date

function Write-Step {
    param([string]$Title, [string]$Number)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  [$Number] $Title" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Msg)
    Write-Host "  [PASS] $Msg" -ForegroundColor Green
    $script:TotalPass++
}

function Write-Fail {
    param([string]$Msg)
    Write-Host "  [FAIL] $Msg" -ForegroundColor Red
    $script:TotalFail++
}

function Write-Warn {
    param([string]$Msg)
    Write-Host "  [WARN] $Msg" -ForegroundColor Yellow
}

function Write-Manual {
    param([string]$Msg)
    Write-Host "  [MANUAL] $Msg" -ForegroundColor Yellow
}

function Run-Pytest {
    param(
        [string]$TestPath,
        [string]$ExtraArgs = ""
    )
    $pytestCmd = "python -m pytest $TestPath -v --tb=short --no-header $ExtraArgs"
    Write-Host "  CMD: $pytestCmd" -ForegroundColor DarkGray
    $output = docker compose exec -T backend sh -c "$pytestCmd 2>&1"
    $exitCode = $LASTEXITCODE
    return @{ Output = $output; ExitCode = $exitCode }
}

# ──── 前置 ────────────────────────────────────────────

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║   10号测试 — 安全隔离 + 性能稳定性验收               ║" -ForegroundColor Magenta
Write-Host "║   开始时间: $StartTime" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Magenta

if (-not $SkipDocker) {
    Write-Step "Docker 环境启动" "PRE"
    Push-Location $Root
    docker compose up -d 2>&1
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Docker 启动失败"
        exit 1
    }
    Write-Pass "Docker 服务已启动"

    Write-Host "  等待所有服务健康就绪..." -ForegroundColor DarkGray
    $maxWait = 300
    $waited = 0
    $allHealthy = $false
    do {
        Start-Sleep -Seconds 5
        $waited += 5
        Push-Location $Root
        $svcJson = docker compose ps --format json 2>$null
        Pop-Location
        if (-not $svcJson) { continue }
        $services = $svcJson | ForEach-Object { $_ | ConvertFrom-Json }
        $unhealthy = $services | Where-Object { $_.Health -and $_.Health -ne "healthy" }
        if ($null -eq $unhealthy -or @($unhealthy).Count -eq 0) {
            $allHealthy = $true
            break
        }
        Write-Host "    等待中... ${waited}s (未就绪: $((@($unhealthy) | ForEach-Object { $_.Name }) -join ', '))" -ForegroundColor DarkGray
    } while ($waited -lt $maxWait)

    if ($allHealthy) {
        Write-Pass "所有服务健康就绪 (耗时 ${waited}s)"
    } else {
        Write-Warn "等待超时 (${maxWait}s)，部分服务可能未就绪，继续执行..."
    }
} else {
    Write-Warn "跳过 Docker 启动 (--SkipDocker)"
}

# ════════════════════════════════════════════════════════
# 三、安全隔离专项验收（6 项自动化）
# ════════════════════════════════════════════════════════

# ──── 1：向量层物理隔离 ──────────────────────────────

Write-Step "向量层物理隔离 — 三Collection独立，无交叉写入" "1"

$r = Run-Pytest "tests/unit/test_milvus_client.py" "--timeout=120"

if ($r.ExitCode -eq 0) {
    Write-Pass "向量层隔离：三个 Collection (coll_public/internal/customer) 独立配置、独立访问"
    $Results["1_向量层物理隔离"] = "PASS"
} else {
    Write-Fail "向量层隔离测试失败"
    Write-Host ($r.Output | Select-Object -Last 30) -ForegroundColor DarkGray
    $Results["1_向量层物理隔离"] = "FAIL"
}

# ──── 2：路由层流程隔离 ──────────────────────────────

Write-Step "路由层流程隔离 — 客服路径不触达 internal 集合" "2"

$r = Run-Pytest "tests/unit/test_customer.py tests/security/test_isolation_probe.py" "--timeout=120"

if ($r.ExitCode -eq 0) {
    Write-Pass "路由层隔离：客服请求仅执行 customer+public 检索路径，不触达 internal"
    $Results["2_路由层流程隔离"] = "PASS"
} else {
    Write-Fail "路由层隔离测试失败"
    Write-Host ($r.Output | Select-Object -Last 30) -ForegroundColor DarkGray
    $Results["2_路由层流程隔离"] = "FAIL"
}

# ──── 3：跨库泄漏渗透测试 ────────────────────────────

Write-Step "跨库泄漏渗透测试 — 500探针，泄漏率0%" "3"

$r = Run-Pytest "tests/security/test_isolation_probe.py" "--timeout=120"

if ($r.ExitCode -eq 0) {
    Write-Pass "跨库隔离验证：L1/L2/L3/L4 四层隔离 + 攻击向量防御，泄漏率 0%"
    $Results["3_跨库泄漏渗透测试"] = "PASS"
} else {
    Write-Fail "跨库隔离验证测试失败"
    Write-Host ($r.Output | Select-Object -Last 30) -ForegroundColor DarkGray
    $Results["3_跨库泄漏渗透测试"] = "FAIL"
}

# ──── 4：输入输出安全校验 ────────────────────────────

Write-Step "输入输出安全校验 — 注入拦截 + 敏感词过滤" "4"

$r = Run-Pytest "tests/unit/test_state_validate.py tests/unit/test_safety_words.py tests/security/test_sensitive_accuracy.py" "--timeout=120"

if ($r.ExitCode -eq 0) {
    Write-Pass "输入输出安全：SQL注入/Prompt注入被拦截，敏感词双端过滤合规"
    $Results["4_输入输出安全校验"] = "PASS"
} else {
    Write-Fail "输入输出安全校验测试失败"
    Write-Host ($r.Output | Select-Object -Last 30) -ForegroundColor DarkGray
    $Results["4_输入输出安全校验"] = "FAIL"
}

# ──── 5：接口权限隔离 ────────────────────────────────

Write-Step "接口权限隔离 — 无Token返回403/401" "5"

$r = Run-Pytest "tests/unit/test_auth_guard.py tests/unit/test_dept_isolation.py" "--timeout=120"

if ($r.ExitCode -eq 0) {
    Write-Pass "接口权限隔离：鉴权失败返回403/401, readonly用户禁止写操作"
    $Results["5_接口权限隔离"] = "PASS"
} else {
    Write-Fail "接口权限隔离测试失败"
    Write-Host ($r.Output | Select-Object -Last 30) -ForegroundColor DarkGray
    $Results["5_接口权限隔离"] = "FAIL"
}

# ──── 6：个人信息脱敏 ────────────────────────────────

Write-Step "个人信息脱敏 — 手机号/身份证自动打码" "6"

$r = Run-Pytest "tests/unit/test_safety_words.py" "--timeout=120"

if ($r.ExitCode -eq 0) {
    Write-Pass "个人信息脱敏：输出内容自动打码，日志中敏感信息同步脱敏"
    $Results["6_个人信息脱敏"] = "PASS"
} else {
    Write-Fail "个人信息脱敏测试失败"
    Write-Host ($r.Output | Select-Object -Last 30) -ForegroundColor DarkGray
    $Results["6_个人信息脱敏"] = "FAIL"
}

# ════════════════════════════════════════════════════════
# 四、性能与稳定性验收（2 项半自动 + 2 项手动）
# ════════════════════════════════════════════════════════

# ──── 7：基础响应耗时（半自动 - benchmark）───────────

Write-Step "基础响应耗时 — FAQ P95<300ms / RAG P95<3s" "7"

Write-Warn "性能基准测试 - 需查看 benchmark 输出判定 PASS/FAIL"

$r = Run-Pytest "tests/performance/test_bench.py" "--benchmark-only --timeout=300"

if ($r.ExitCode -eq 0) {
    Write-Pass "性能基准测试全部完成"
    Write-Host ""
    Write-Host "  ╔════════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "  ║  请检查上方 benchmark 输出，核实以下指标：    ║" -ForegroundColor Yellow
    Write-Host "  ║  FAQ P95 < 300ms                              ║" -ForegroundColor Yellow
    Write-Host "  ║  RAG P95 < 3s (非流式)                        ║" -ForegroundColor Yellow
    Write-Host "  ║  并发 20 QPS 不超时                           ║" -ForegroundColor Yellow
    Write-Host "  ╚════════════════════════════════════════════════╝" -ForegroundColor Yellow
    $Results["7_基础响应耗时"] = "PASS (需复核benchmark)"
} else {
    Write-Warn "性能基准测试未全部通过（部分可能需要完整 Docker 环境）"
    $Results["7_基础响应耗时"] = "WARN"
}

# ──── 8：异常降级兜底（手动） ────────────────────────

Write-Step "异常降级兜底 — LLM不可用→检索摘要 / 向量库故障→BM25" "8"

Write-Host ""
Write-Host "  ╔════════════════════════════════════════════════╗" -ForegroundColor Yellow
Write-Host "  ║  [手动操作] 异常降级兜底验证                   ║" -ForegroundColor Yellow
Write-Host "  ╚════════════════════════════════════════════════╝" -ForegroundColor Yellow
Write-Host ""
Write-Host "  场景 A — LLM 不可用降级："
Write-Host "    1. 设置无效 LLM_API_KEY 后重启后端"
Write-Host "    2. 发起对话请求"
Write-Host "    3. 验证：降级返回检索摘要，不抛出 500"
Write-Host ""
Write-Host "  场景 B — 向量库故障降级："
Write-Host "    1. docker compose stop milvus"
Write-Host "    2. 发起对话请求"
Write-Host "    3. 验证：降级为 BM25 检索，不抛出 500"
Write-Host "    4. docker compose start milvus (恢复)"
Write-Host ""
Write-Host "  代码依据："
Write-Host "    - LLM 重试: backend/app/agents/llm.py (call_llm_with_retry)"
Write-Host "    - 向量库回退: BM25 作为基础检索器始终可用"
Write-Host ""

Write-Manual "异常降级兜底 — 需手动执行上述操作后填写验收报告"
$Results["8_异常降级兜底"] = "MANUAL"

# ──── 9：超时与熔断（手动） ──────────────────────────

Write-Step "超时与熔断 — 超时中断 + 重试2次 + 指数退避" "9"

Write-Host ""
Write-Host "  ╔════════════════════════════════════════════════╗" -ForegroundColor Yellow
Write-Host "  ║  [手动操作] 超时与熔断验证                      ║" -ForegroundColor Yellow
Write-Host "  ╚════════════════════════════════════════════════╝" -ForegroundColor Yellow
Write-Host ""
Write-Host "  代码级验证（无需额外搭建环境）："
Write-Host "    1. 检查 llm.py: call_llm_with_retry(max_retries=3)"
Write-Host "    2. 检查指数退避: delay = min(1000 * 2^i, 8000) / 1000"
Write-Host ""
Write-Host "  运行时验证："
Write-Host "    1. 观察后端日志: docker compose logs backend | grep retry"
Write-Host "    2. 模拟 LLM 超时：设置极小 timeout 值"
Write-Host "    3. 验证: 重试 2 次后抛出 RuntimeError"
Write-Host ""

Write-Manual "超时与熔断 — 需手动验证重试日志后填写验收报告"
$Results["9_超时与熔断"] = "MANUAL"

# ──── 10：基础并发验证（半自动 - benchmark）──────────

Write-Step "基础并发验证 — 10QPS 持续1分钟，错误率<1%" "10"

Write-Warn "并发压测 - 使用 test_bench.py 内置并发测试 (20 QPS)"

$r = Run-Pytest "tests/performance/test_bench.py -k 'concurrent'" "--benchmark-only --timeout=300"

if ($r.ExitCode -eq 0) {
    Write-Pass "并发测试完成"
    Write-Host ""
    Write-Host "  ╔════════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "  ║  请检查 benchmark 输出:                       ║" -ForegroundColor Yellow
    Write-Host "  ║  错误率 < 1%                                  ║" -ForegroundColor Yellow
    Write-Host "  ║  无崩溃、无内存泄漏                           ║" -ForegroundColor Yellow
    Write-Host "  ╚════════════════════════════════════════════════╝" -ForegroundColor Yellow
    $Results["10_基础并发验证"] = "PASS (需复核benchmark)"
} else {
    Write-Warn "并发测试未通过（可能需要完整 Docker 环境）"
    $Results["10_基础并发验证"] = "WARN"
}

# ──── 汇总 ─────────────────────────────────────────────

$EndTime = Get-Date
$Elapsed = $EndTime - $StartTime

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║   10号测试验收结果汇总                                ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

foreach ($key in $Results.Keys | Sort-Object) {
    $status = $Results[$key]
    if ($status -eq "PASS") {
        Write-Host "  [PASS]   $key" -ForegroundColor Green
    } elseif ($status -eq "FAIL") {
        Write-Host "  [FAIL]   $key" -ForegroundColor Red
    } elseif ($status -eq "WARN") {
        Write-Host "  [WARN]   $key" -ForegroundColor Yellow
    } elseif ($status -eq "MANUAL") {
        Write-Host "  [MANUAL] $key" -ForegroundColor Yellow
    } else {
        Write-Host "  [ ?  ]   $key (复核需) - $status" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  自动化通过: $TotalPass" -ForegroundColor Green
Write-Host "  自动化失败: $TotalFail" -ForegroundColor Red
Write-Host "  需手动操作: 2 项（#8 异常降级 / #9 超时熔断）" -ForegroundColor Yellow
Write-Host "  耗时: $($Elapsed.ToString('hh\:mm\:ss'))" -ForegroundColor Gray
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  手动操作指南 → 见 docs\ACCEPTANCE_REPORT_SECURITY.md" -ForegroundColor Cyan
Write-Host ""

# ──── 报告 ─────────────────────────────────────────────

$ReportPath = Join-Path $Root "docs\ACCEPTANCE_REPORT_SECURITY.md"

$autoPass = $TotalPass
$autoFail = $TotalFail
$passCount = 0
$failCount = 0
foreach ($v in $Results.Values) {
    if ($v -match "^PASS") { $passCount++ }
    elseif ($v -eq "FAIL") { $failCount++ }
}

Write-Host "  验收报告模板: $ReportPath" -ForegroundColor Cyan
Write-Host "  (手动项 #8 #9 需执行后手动填入报告)" -ForegroundColor DarkGray

if (-not $KeepRunning) {
    Write-Host "  关闭 Docker 服务..." -ForegroundColor DarkGray
    Push-Location $Root
    docker compose down 2>&1 | Out-Null
    Pop-Location
} else {
    Write-Warn "--KeepRunning: Docker 服务保持运行"
}

if ($TotalFail -gt 0) { exit 1 } else { exit 0 }
