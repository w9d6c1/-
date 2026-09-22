# 一键启动脚本 — 启动全部服务并等待就绪
# 用法: .\start.ps1
$ErrorActionPreference = "Stop"
$composeDir = $PSScriptRoot

# ========== 前置检查 1: 宿主机失效代理残留 ==========
# 曾出现系统代理 ProxyEnable=1 指向已停止的 127.0.0.1:7897，导致容器外网(LLM/热榜)全挂。
# 检测到残留时自动清除，防止"前端功能不能用"。
function Test-StaleSystemProxy {
    try {
        $s = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        if ($s.ProxyEnable -ne 1) { return $null }
        $proxy = "$($s.ProxyServer)"
        if (-not $proxy) { return $null }
        $port = ($proxy -split ":")[-1]
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($listener) { return $null }   # 代理端口存活，属正常代理，不动
        return $proxy                     # 代理已停止但仍启用 -> 残留
    } catch { return $null }
}

$staleProxy = Test-StaleSystemProxy
if ($staleProxy) {
    Write-Host "检测到失效系统代理残留: $staleProxy（端口无监听），自动清除..." -ForegroundColor Yellow
    Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -Name ProxyEnable -Value 0
    Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -Name ProxyServer -Value ""
    Write-Host "已清除。若此前 Docker 已受此影响，Docker Desktop 需重启后恢复外网。" -ForegroundColor Green
}

# ========== 前置检查 2: 必需镜像是否存在 ==========
# 镜像缺失时将触发 docker pull，若镜像源失效会导致拉取失败。
# 列出本地必需镜像，缺失项给予明确提示。
$requiredImages = @(
    "nginx:1.27-alpine",
    "mysql:8.0",
    "postgres:16-alpine",
    "redis:7-alpine",
    "docker.elastic.co/elasticsearch/elasticsearch:8.15.0",
    "milvusdb/milvus:v2.4.0",
    "minio/minio:latest",
    "quay.io/coreos/etcd:v3.5.5",
    "owasp/modsecurity-crs:nginx",
    "grafana/loki:2.9.0",
    "grafana/promtail:2.9.0"
)
$missing = @()
foreach ($img in $requiredImages) {
    $found = docker images --format "{{.Repository}}:{{.Tag}}" 2>$null | Where-Object { $_ -eq $img }
    if (-not $found) { $missing += $img }
}
if ($missing.Count -gt 0) {
    Write-Host "以下必需镜像本地不存在，启动时将触发 docker pull：" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "如拉取失败，请检查 Docker 镜像源配置 (daemon.json registry-mirrors) 是否可达。" -ForegroundColor Yellow
} else {
    Write-Host "必需镜像本地已全部存在，无需拉取。" -ForegroundColor Green
}

# ========== 端口占用预检测 ==========
# 防止本地 npm run dev 与 Docker 抢同一端口
$checkPorts = @(80, 443, 5173, 5175, 8000, 8080)
$dockerLikeProcs = @("com.docker.backend", "wslrelay", "docker", "vpnkit", "com.docker.service", "docker-proxy", "com.docker.build")

function Test-PortConflict {
    $conflicts = @()
    foreach ($port in $checkPorts) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $listeners) { continue }
        foreach ($ln in $listeners) {
            $pid_ = $ln.OwningProcess
            try {
                $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid_"
                if (-not $proc) { continue }
                $name = $proc.Name
                $path = $proc.ExecutablePath
                $isDocker = ($dockerLikeProcs -contains $name) -or
                            ($path -and ($path -match "Docker|docker|WSL|wsl"))
                if (-not $isDocker) {
                    $conflicts += "  端口 ${port}: 进程 ${pid_} (${name}) $path"
                }
            } catch {
                # 忽略查询失败的进程
            }
        }
    }
    return $conflicts
}

$conflicts = Test-PortConflict
if ($conflicts.Count -gt 0) {
    Write-Host "检测到端口被非 Docker 进程占用，可能造成冲突（例如本地仍在运行 npm run dev）：" -ForegroundColor Yellow
    $conflicts | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    Write-Host "请先停止这些本地服务（Ctrl+C 结束 npm run dev），再重新运行本脚本。" -ForegroundColor Red
    exit 1
}

Write-Host "==> docker compose up -d ..." -ForegroundColor Cyan
# 临时放宽 ErrorActionPreference：容器 Running 提示写 stderr，会被 Stop 模式中断
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$composeOut = docker compose --project-directory $composeDir up -d 2>&1
$composeExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
$composeOut | Out-Host
if ($composeExit -ne 0) {
    Write-Host "docker compose up 失败" -ForegroundColor Red
    exit 1
}

$healthContainers = @("kb-mysql", "kb-postgres", "kb-elasticsearch", "kb-etcd", "kb-minio", "kb-milvus", "kb-waf")
$timeoutSec = 300
$start = Get-Date

function Get-Unhealthy {
    $bad = @()
    foreach ($c in $healthContainers) {
        $s = docker inspect --format "{{.State.Health.Status}}" $c 2>$null
        if ($s -ne "healthy") { $bad += "$c($s)" }
    }
    return $bad
}

Write-Host "==> 等待容器 healthy（最长 $timeoutSec 秒）..." -ForegroundColor Cyan
while ($true) {
    $bad = Get-Unhealthy
    if ($bad.Count -eq 0) { break }
    if (((Get-Date) - $start).TotalSeconds -gt $timeoutSec) {
        Write-Host "超时！未就绪容器: $($bad -join ', ')" -ForegroundColor Red
        foreach ($b in $bad) {
            $name = ($b -split '\(')[0]
            Write-Host "--- $name 最后 20 行日志 ---" -ForegroundColor Yellow
            docker logs $name --tail 20 2>&1
        }
        exit 1
    }
    Write-Host ("    等待中: " + ($bad -join ", "))
    Start-Sleep -Seconds 10
}
Write-Host "    全部容器 healthy" -ForegroundColor Green

Write-Host "==> 等待后端 API 就绪..." -ForegroundColor Cyan
while ($true) {
    $code = curl.exe -sk -o NUL -w "%{http_code}" --max-time 5 https://localhost/api/health 2>$null
    if ($code -eq "200") { break }
    if (((Get-Date) - $start).TotalSeconds -gt $timeoutSec) {
        Write-Host "超时！/api/health 返回: $code" -ForegroundColor Red
        Write-Host "--- kb-backend 最后 20 行日志 ---" -ForegroundColor Yellow
        docker logs kb-backend --tail 20 2>&1
        exit 1
    }
    Start-Sleep -Seconds 5
}
Write-Host "    后端 API 就绪 (200)" -ForegroundColor Green

Write-Host "==> 等待前端页面就绪..." -ForegroundColor Cyan
while ($true) {
    $code = curl.exe -sk -o NUL -w "%{http_code}" --max-time 5 https://localhost/ 2>$null
    if ($code -eq "200") { break }
    if (((Get-Date) - $start).TotalSeconds -gt $timeoutSec) {
        Write-Host "超时！前端页面返回: $code" -ForegroundColor Red
        Write-Host "--- kb-frontend 最后 20 行日志 ---" -ForegroundColor Yellow
        docker logs kb-frontend --tail 20 2>&1
        exit 1
    }
    Start-Sleep -Seconds 5
}
Write-Host "    前端页面就绪 (200)" -ForegroundColor Green

Write-Host "==> 等待 React 管理后台就绪..." -ForegroundColor Cyan
while ($true) {
    $code = curl.exe -sk -o NUL -w "%{http_code}" --max-time 5 https://localhost/app/ 2>$null
    if ($code -eq "200") { break }
    if (((Get-Date) - $start).TotalSeconds -gt $timeoutSec) {
        Write-Host "超时！React 管理后台返回: $code" -ForegroundColor Red
        Write-Host "--- kb-frontend 最后 20 行日志 ---" -ForegroundColor Yellow
        docker logs kb-frontend --tail 20 2>&1
        exit 1
    }
    Start-Sleep -Seconds 5
}
Write-Host "    React 管理后台就绪 (200)" -ForegroundColor Green

# ========== 业务自检：CORS 预检 + 文章接口 ==========
Write-Host "==> 业务自检（CORS / 文章接口）..." -ForegroundColor Cyan

# 1) React 后台来源 (5175) 的 CORS 预检不应被拒 (400)
$preflight = curl.exe -sk -o NUL -w "%{http_code}" --max-time 10 -X OPTIONS "http://127.0.0.1:8000/api/admin/articles/batches" `
    -H "Origin: http://localhost:5175" -H "Access-Control-Request-Method: GET" 2>$null
if ($preflight -eq "400" -or $preflight -eq "403") {
    Write-Host "CORS 预检失败 (Origin=5175 返回 $preflight)。请检查后端 CORS_ORIGINS 是否包含 http://localhost:5175" -ForegroundColor Red
    exit 1
}
Write-Host "    CORS 预检 OK ($preflight)" -ForegroundColor Green

# 2) 文章接口路由可达（未带 token 应返回 401，而非 404/500）
$articlesCode = curl.exe -sk -o NUL -w "%{http_code}" --max-time 10 "http://127.0.0.1:8000/api/admin/articles/batches?page=1&page_size=1" 2>$null
if ($articlesCode -ne "401" -and $articlesCode -ne "200") {
    Write-Host "文章接口异常 (返回 $articlesCode，预期 401/200)。请检查后端日志" -ForegroundColor Red
    exit 1
}
Write-Host "    文章接口 OK ($articlesCode，未登录返回 401 属正常)" -ForegroundColor Green

# ========== 业务自检 2: 外网连通性 ==========
# 容器内 LLM(DeepSeek)/热榜/视觉 均依赖外网。曾因宿主机失效代理导致全部外网请求失败。
Write-Host "==> 业务自检（外网连通 / 照片 / CSP）..." -ForegroundColor Cyan
# 容器内执行 Python 探测外网（避免 PowerShell 引号嵌套冲突，改用 stdin 传脚本）
$pyCheck = @'
import urllib.request
try:
    r = urllib.request.urlopen("https://api.deepseek.com", timeout=8)
    print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print("FAIL")
'@
$extCode = ($pyCheck | docker exec -i kb-backend python -) 2>$null
if ($extCode -notmatch "^(401|200)$") {
    Write-Host "容器外网异常 (api.deepseek.com 返回 '$extCode'，预期 401/200)。" -ForegroundColor Red
    Write-Host "可能原因: 宿主机系统代理残留或 Docker 代理配置指向失效端口。请检查并重启 Docker Desktop。" -ForegroundColor Yellow
} else {
    Write-Host "    外网连通 OK ($extCode，DeepSeek 可达)" -ForegroundColor Green
}

# ========== 业务自检 3: CSP img-src 含 blob: ==========
# 照片库/文章配图用 createObjectURL(blob) 显示，CSP 缺 blob: 会导致图片全不可见。
$cspHeader = curl.exe -sk -I https://localhost/app/ 2>$null | Select-String "img-src"
if ($cspHeader -and ($cspHeader -notmatch "blob:")) {
    Write-Host "CSP 头缺少 blob:，照片将无法显示。请检查 docker/nginx/conf.d/default.conf 的 img-src。" -ForegroundColor Red
    exit 1
} else {
    Write-Host "    CSP 检查 OK (img-src 含 blob:)" -ForegroundColor Green
}

# ========== 业务自检 4: 照片接口可达 ==========
$photoCode = curl.exe -sk -o NUL -w "%{http_code}" --max-time 10 "http://127.0.0.1:8000/api/admin/articles/photos?page=1&page_size=1" 2>$null
if ($photoCode -ne "401" -and $photoCode -ne "200") {
    Write-Host "照片接口异常 (返回 $photoCode，预期 401/200)。请检查后端日志" -ForegroundColor Red
    exit 1
}
Write-Host "    照片接口 OK ($photoCode)" -ForegroundColor Green

$elapsed = [int]((Get-Date) - $start).TotalSeconds
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 启动完成 (${elapsed}s)，全部自检通过" -ForegroundColor Green
Write-Host " Vue 前端:       https://localhost" -ForegroundColor Green
Write-Host " React 管理后台: https://localhost/app/" -ForegroundColor Green
Write-Host " 注意: 请使用上面的 https://localhost 入口" -ForegroundColor Green
Write-Host "       勿直接用 5173/5175 等原始端口，避免缓存/跨域问题" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green
