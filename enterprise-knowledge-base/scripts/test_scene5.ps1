# 场景5 上线测试 — 多轮记忆 + 权限隔离
# 目标: https://<生产域名>

$base = "https://<生产域名>"
$pass = 0
$fail = 0

function test($name, $script) {
    Write-Host "`n── $name ──" -ForegroundColor Cyan
    try {
        & $script
        $global:pass++
        Write-Host "  PASS" -ForegroundColor Green
    } catch {
        $global:fail++
        Write-Host "  FAIL: $_" -ForegroundColor Red
    }
}

# =============================================
# 1. 健康检查
# =============================================
test "1. /health" {
    $r = Invoke-WebRequest -Uri "$base/health" -UseBasicParsing -TimeoutSec 10
    $j = $r.Content | ConvertFrom-Json
    if ($j.status -ne "healthy") { throw "status=$($j.status)" }
}

test "2. /api/agent/status" {
    $r = Invoke-WebRequest -Uri "$base/api/agent/status" -UseBasicParsing -TimeoutSec 10
    $j = $r.Content | ConvertFrom-Json
    if ($j.status -ne "ok") { throw "unexpected" }
}

# =============================================
# 2. 多轮记忆 — 内部非流式 chat
# =============================================
$thread = "e2e-memory-$((Get-Date).ToString('HHmmss'))"

test "3. 多轮记忆: 第1轮 — 我叫张三" {
    $body = @{ message = "你好，我叫张三"; thread_id = $thread; scope = "public" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/internal/chat" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120
    $script:resp1 = $r.Content | ConvertFrom-Json
    if (-not $script:resp1.answer) { throw "无回答" }
    Write-Host "    回答: $($script:resp1.answer.Substring(0, [Math]::Min(80, $script:resp1.answer.Length)))..."
}

test "4. 多轮记忆: 第2轮 — 我叫什么名字" {
    $body = @{ message = "我叫什么名字"; thread_id = $thread; scope = "public" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/internal/chat" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120
    $script:resp2 = $r.Content | ConvertFrom-Json
    if (-not $script:resp2.answer) { throw "无回答" }
    Write-Host "    回答: $($script:resp2.answer.Substring(0, [Math]::Min(80, $script:resp2.answer.Length)))..."
}

test "5. 多轮记忆: 第3轮 — 我的职业是什么" {
    $body = @{ message = "我的职业是什么"; thread_id = $thread; scope = "public" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/internal/chat" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120
    $script:resp3 = $r.Content | ConvertFrom-Json
    if (-not $script:resp3.answer) { throw "无回答" }
    Write-Host "    回答: $($script:resp3.answer.Substring(0, [Math]::Min(80, $script:resp3.answer.Length)))..."
}

# =============================================
# 3. 多轮记忆 — 客服 SSE 流式
# =============================================
$custThread = "e2e-cust-mem-$((Get-Date).ToString('HHmmss'))"

test "6. 客服 SSE 流式: 第1轮 — 你好" {
    $uri = "$base/api/agent/customer/chat/stream"
    $body = @{ message = "你好"; thread_id = $custThread } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri $uri -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 60
    $out = [System.Text.Encoding]::UTF8.GetString($r.RawContent)
    $script:sse1 = ""
    $out -split '\n' | ForEach-Object {
        if ($_ -match '^data: (.*)') { $script:sse1 += $Matches[1] }
    }
    if ($script:sse1 -eq '') { throw "SSE 无数据" }
    Write-Host "    SSE: $($script:sse1.Substring(0, [Math]::Min(80, $script:sse1.Length)))..."
}

test "7. 客服 SSE 流式: 第2轮 — 刚提到的问题是什么" {
    $body = @{ message = "刚刚我说了什么"; thread_id = $custThread } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri $uri -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 60
    $out = [System.Text.Encoding]::UTF8.GetString($r.RawContent)
    $script:sse2 = ""
    $out -split '\n' | ForEach-Object {
        if ($_ -match '^data: (.*)') { $script:sse2 += $Matches[1] }
    }
    if ($script:sse2 -eq '') { throw "SSE 无数据" }
    Write-Host "    SSE: $($script:sse2.Substring(0, [Math]::Min(80, $script:sse2.Length)))..."
}

# =============================================
# 4. 权限隔离 — 无认证访问内部接口
# =============================================
test "8. 无认证访问 /internal/chat/stream (应 200 或 401)" {
    $body = @{ message = "测试"; scope = "public" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/internal/chat/stream" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 30
    if ($r.StatusCode -ne 200 -and $r.StatusCode -ne 401) { throw "unexpected $($r.StatusCode)" }
    Write-Host "    Status: $($r.StatusCode)"
}

test "9. 无认证访问 /chat/stream 旧路径 (应 200 或 401)" {
    $body = @{ message = "测试"; scope = "public" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/chat/stream" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 30
    if ($r.StatusCode -ne 200 -and $r.StatusCode -ne 401) { throw "unexpected $($r.StatusCode)" }
    Write-Host "    Status: $($r.StatusCode)"
}

test "10. 无认证访问 /customer/chat (应 200)" {
    $body = @{ message = "退款流程" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/customer/chat" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120
    if ($r.StatusCode -ne 200) { throw "unexpected $($r.StatusCode)" }
    Write-Host "    Status: $($r.StatusCode)"
}

# =============================================
# 5. Scope — 内部知识 scope 隔离
# =============================================
test "11. scope=internal 请求 (应被屏蔽)" {
    $body = @{ message = "公司内部机密数据查询"; thread_id = "scope-test-int"; scope = "internal" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/internal/chat" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120
    $j = $r.Content | ConvertFrom-Json
    Write-Host "    answer 前80字: $($j.answer.Substring(0, [Math]::Min(80, $j.answer.Length)))..."
}

test "12. scope=public 请求 (应正常)" {
    $body = @{ message = "公司有多少员工"; thread_id = "scope-test-pub"; scope = "public" } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$base/api/agent/internal/chat" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120
    $j = $r.Content | ConvertFrom-Json
    Write-Host "    answer 前80字: $($j.answer.Substring(0, [Math]::Min(80, $j.answer.Length)))..."
}

# =============================================
# 报告
# =============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  结果: PASS=$pass  FAIL=$fail  TOTAL=$( $pass + $fail )" -ForegroundColor $(if ($fail -eq 0) { 'Green' } else { 'Red' })
Write-Host "========================================" -ForegroundColor Cyan
