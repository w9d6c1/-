#!/bin/bash
# ============================================================
#  preflight-check.sh
#
#  Run before `docker compose up`. Checks prerequisites.
#  Usage:
#    bash scripts/preflight-check.sh            # check + report
#    bash scripts/preflight-check.sh --fix      # check + auto-fix (SSL/dirs)
#    bash scripts/preflight-check.sh --quiet    # exit code only (for CI)
# ============================================================
set -o pipefail

# --------------- Config ----------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REQUIRED_DOCKER_VER=24
REQUIRED_COMPOSE_VER_MAJOR=2
REQUIRED_COMPOSE_VER_MINOR=20
MIN_RAM_GB=4
MIN_DISK_GB=30
MIN_CPU=4

# --------------- State counters ----------------
PASS=0; FAIL=0; WARN=0
QUIET=false; FIX=false

[[ "$*" =~ --quiet ]] && QUIET=true
[[ "$*" =~ --fix ]]   && FIX=true

DIM="\033[2m";   RED="\033[31m";  GREEN="\033[32m"
YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"
BOLD="\033[1m";   RESET="\033[0m"

pass() { ((PASS++)); $QUIET || echo -e "  ${GREEN}[PASS]${RESET} $1"; }
fail() { ((FAIL++)); $QUIET || echo -e "  ${RED}[FAIL]${RESET} $1"; }
warn() { ((WARN++)); $QUIET || echo -e "  ${YELLOW}[WARN]${RESET} $1"; }
info() { $QUIET || echo -e "  ${CYAN}[INFO]${RESET} $1"; }
fixcmd() { $QUIET || echo -e "    ${DIM}fix: $1${RESET}"; }
header() { $QUIET || echo -e "\n${BOLD}${BLUE}======== $1 ========${RESET}"; }

# --------------- Helper functions ----------------
is_docker_available() { docker info &>/dev/null; }
in_container() { grep -q docker /proc/1/cgroup 2>/dev/null || grep -qi docker /proc/1/environ 2>/dev/null; }
get_os() { uname -s | tr '[:upper:]' '[:lower:]'; }

port_free() {
    local port="$1"
    if command -v ss &>/dev/null; then
        ! ss -tlnp 2>/dev/null | grep -q ":${port} "
    elif command -v netstat &>/dev/null; then
        ! netstat -tlnp 2>/dev/null | grep -q ":${port} "
    else
        true  # can't check, assume ok
    fi
}

mb_to_gb() { echo "scale=1; $1 / 1024" | bc 2>/dev/null || echo "?"; }

# ============================================================
header "1. System Environment"
# ============================================================

# --- 1a. OS ---
OS=$(get_os)
case "$OS" in
    linux) pass "OS: Linux" ;;
    darwin) warn "OS: macOS (Linux recommended for production)" ;;
    *)      warn "OS: $OS (only Linux fully supported)" ;;
esac

# --- 1b. Docker version ---
if ! command -v docker &>/dev/null; then
    fail "Docker not installed"
    fixcmd "curl -fsSL https://get.docker.com | sh"
else
    DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null | grep -oE '[0-9]+' | head -1)
    if [ -n "$DOCKER_VER" ] && [ "$DOCKER_VER" -ge "$REQUIRED_DOCKER_VER" ]; then
        pass "Docker v$(docker version --format '{{.Server.Version}}' 2>/dev/null) (required >= $REQUIRED_DOCKER_VER)"
    elif [ -n "$DOCKER_VER" ]; then
        fail "Docker v${DOCKER_VER} too old (required >= $REQUIRED_DOCKER_VER)"
        fixcmd "Upgrade Docker to $REQUIRED_DOCKER_VER+"
    else
        warn "Cannot read Docker version"
    fi
fi

# --- 1c. Docker Compose version ---
if ! docker compose version &>/dev/null; then
    fail "docker compose (v2) unavailable (not docker-compose)"
    fixcmd "Install Docker Compose v2.20+"
else
    COMPOSE_VER=$(docker compose version --short 2>/dev/null | grep -oE '[0-9]+' | head -2)
    COMPOSE_MAJOR=$(echo "$COMPOSE_VER" | head -1)
    COMPOSE_MINOR=$(echo "$COMPOSE_VER" | tail -1)
    COMPOSE_STR=$(docker compose version --short 2>/dev/null)
    if [ "$COMPOSE_MAJOR" -ge "$REQUIRED_COMPOSE_VER_MAJOR" ] && [ "$COMPOSE_MINOR" -ge "$REQUIRED_COMPOSE_VER_MINOR" ]; then
        pass "docker compose v${COMPOSE_STR} (required >= $REQUIRED_COMPOSE_VER_MAJOR.$REQUIRED_COMPOSE_VER_MINOR)"
    else
        fail "docker compose v${COMPOSE_STR} too old (required >= $REQUIRED_COMPOSE_VER_MAJOR.$REQUIRED_COMPOSE_VER_MINOR)"
    fi
fi

# --- 1d. Docker daemon ---
if is_docker_available; then
    pass "Docker daemon running"
else
    fail "Docker daemon not running"
    fixcmd "systemctl start docker"
fi

# ============================================================
header "2. System Resources"
# ============================================================

# --- 2a. Memory ---
if command -v free &>/dev/null; then
    RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
    RAM_GB=$((RAM_MB / 1024))
    if [ "$RAM_GB" -ge "$MIN_RAM_GB" ]; then
        pass "Memory: ${RAM_GB}GB (required >= ${MIN_RAM_GB}GB)"
    else
        fail "Memory: ${RAM_GB}GB too low (required >= ${MIN_RAM_GB}GB, Milvus needs 4G + ES 2G)"
        fixcmd "Increase server RAM to ${MIN_RAM_GB}GB+"
    fi
elif [ "$OS" = "linux" ]; then
    RAM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null)
    RAM_GB=$((RAM_MB / 1024))
    if [ "$RAM_GB" -ge "$MIN_RAM_GB" ]; then
        pass "Memory: ${RAM_GB}GB (required >= ${MIN_RAM_GB}GB)"
    else
        fail "Memory: ${RAM_GB}GB too low (required >= ${MIN_RAM_GB}GB)"
    fi
else
    warn "Cannot detect memory"
fi

# --- 2b. Disk ---
DISK_AVAIL_KB=$(df -k "$PROJECT_DIR" 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "$DISK_AVAIL_KB" ]; then
    DISK_AVAIL_GB=$((DISK_AVAIL_KB / 1024 / 1024))
    if [ "$DISK_AVAIL_GB" -ge "$MIN_DISK_GB" ]; then
        pass "Disk available: ${DISK_AVAIL_GB}GB (required >= ${MIN_DISK_GB}GB)"
    else
        fail "Disk available: ${DISK_AVAIL_GB}GB too low (required >= ${MIN_DISK_GB}GB)"
        fixcmd "df -h to check disk usage"
    fi
else
    warn "Cannot detect disk space"
fi

# --- 2c. CPU ---
if command -v nproc &>/dev/null; then
    CPU_CORES=$(nproc)
elif [ "$OS" = "linux" ]; then
    CPU_CORES=$(grep -c ^processor /proc/cpuinfo 2>/dev/null)
else
    CPU_CORES=0
fi
if [ "$CPU_CORES" -ge "$MIN_CPU" ]; then
    pass "CPU cores: ${CPU_CORES} (recommended >= ${MIN_CPU})"
elif [ "$CPU_CORES" -gt 0 ]; then
    warn "CPU cores: ${CPU_CORES} low (recommended >= ${MIN_CPU})"
else
    warn "Cannot detect CPU cores"
fi

# --- 2d. Swap ---
if [ "$OS" = "linux" ]; then
    SWAP_MB=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
    if [ "${SWAP_MB:-0}" -lt 1024 ]; then
        warn "Swap: ${SWAP_MB}MB (< 1GB, may OOM under load)"
        fixcmd "fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile"
    else
        pass "Swap: $((SWAP_MB / 1024))GB"
    fi
fi

# ============================================================
header "3. Required Files & Directories"
# ============================================================

cd "$PROJECT_DIR"

# --- 3a. .env ---
if [ -f ".env" ]; then
    ENV_SIZE=$(wc -c < .env)
    if [ "$ENV_SIZE" -lt 200 ]; then
        fail ".env exists but too small (${ENV_SIZE} bytes), may be missing config"
        fixcmd "cp .env.example .env && vi .env"
    else
        pass ".env (${ENV_SIZE} bytes)"
    fi
else
    fail ".env does not exist"
    fixcmd "cp .env.example .env && vi .env"
fi

# --- 3b. .env.prod ---
if [ -f ".env.prod" ]; then
    pass ".env.prod exists"
else
    warn ".env.prod missing (deploy.sh needs this file)"
    fixcmd "cp .env .env.prod && vi .env.prod"
fi

# --- 3c. SSL cert ---
if [ -f "docker/ssl/server.crt" ] && [ -f "docker/ssl/server.key" ]; then
    pass "SSL cert: docker/ssl/server.crt + server.key"
else
    if $FIX; then
        info "Generating self-signed SSL cert..."
        mkdir -p docker/ssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout docker/ssl/server.key \
            -out docker/ssl/server.crt \
            -subj "/CN=localhost" 2>/dev/null
        pass "Generated self-signed SSL cert (CN=localhost)"
    else
        fail "SSL cert missing: docker/ssl/ has no server.crt/server.key"
        fixcmd "bash scripts/preflight-check.sh --fix"
        fixcmd "  mkdir -p docker/ssl"
        fixcmd '  openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout docker/ssl/server.key -out docker/ssl/server.crt -subj "/CN=your-domain"'
    fi
fi

# --- 3d. MySQL schema ---
if [ -f "docker/mysql/init/01-schema.sql" ]; then
    pass "MySQL init schema: 01-schema.sql"
else
    fail "MySQL schema missing: docker/mysql/init/01-schema.sql"
fi

# --- 3e. docker-compose files ---
COMPOSE_FILES=("docker-compose.yml" "docker-compose.prod.yml")
for cf in "${COMPOSE_FILES[@]}"; do
    if [ -f "$cf" ]; then
        pass "$cf"
    else
        fail "$cf missing"
    fi
done

# --- 3f. Nginx config ---
for nf in docker/nginx/nginx.conf docker/nginx/conf.d/default.conf docker/nginx/conf.d/ip-whitelist.inc; do
    if [ -f "$nf" ]; then
        pass "$nf"
    else
        fail "$nf missing"
    fi
done

# --- 3g. Prometheus config ---
if [ -f "docker/prometheus/prometheus.yml" ]; then
    pass "docker/prometheus/prometheus.yml"
else
    fail "Prometheus config missing"
fi

# --- 3h. WAF config ---
for wf in docker/waf/waf-proxy.conf docker/waf/modsecurity.conf; do
    if [ -f "$wf" ]; then
        pass "$wf"
    else
        fail "$wf missing"
    fi
done

# ============================================================
header "4. Environment Variables"
# ============================================================

load_env_var() {
    grep -E "^${1}=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/^"//;s/"$//' | xargs
}

ENV_LOADED=false
[ -f ".env" ] && [ "$(wc -c < .env)" -ge 200 ] && ENV_LOADED=true

if $ENV_LOADED; then

    # --- 4a. LLM API Key ---
    LLM_KEY=$(load_env_var "LLM_API_KEY")
    if [ -n "$LLM_KEY" ] && [ "$LLM_KEY" != "your-api-key-here" ] && [ "$LLM_KEY" != "sk-your-api-key" ]; then
        pass "LLM_API_KEY configured (${LLM_KEY:0:10}...)"
    else
        fail "LLM_API_KEY not configured or default value"
        fixcmd "Edit .env, set LLM_API_KEY=your DeepSeek API Key"
    fi

    # --- 4b. JWT Secret ---
    JWT_SECRET=$(load_env_var "JWT_SECRET_KEY")
    if [ -n "$JWT_SECRET" ] && [ "${#JWT_SECRET}" -ge 16 ] && [ "$JWT_SECRET" != "your-secret-key-here-min-32-chars" ]; then
        pass "JWT_SECRET_KEY configured (${#JWT_SECRET} chars)"
    elif [ -n "$JWT_SECRET" ] && [ "$JWT_SECRET" != "your-secret-key-here-min-32-chars" ]; then
        warn "JWT_SECRET_KEY short (${#JWT_SECRET} chars, recommended >= 32)"
        fixcmd "openssl rand -hex 32"
    else
        fail "JWT_SECRET_KEY not configured or default value"
        fixcmd "openssl rand -hex 32"
    fi

    # --- 4c. MySQL ---
    MYSQL_PW=$(load_env_var "MYSQL_PASSWORD")
    if [ -n "$MYSQL_PW" ] && [ "$MYSQL_PW" != "kb_pass_2024" ]; then
        pass "MYSQL_PASSWORD changed (non-default)"
    elif [ -n "$MYSQL_PW" ]; then
        warn "MYSQL_PASSWORD still default kb_pass_2024"
    else
        fail "MYSQL_PASSWORD not configured"
    fi

    MYSQL_ROOT_PW=$(load_env_var "MYSQL_ROOT_PASSWORD")
    if [ -n "$MYSQL_ROOT_PW" ] && [ "$MYSQL_ROOT_PW" != "root_pass_2024" ]; then
        pass "MYSQL_ROOT_PASSWORD changed (non-default)"
    elif [ -n "$MYSQL_ROOT_PW" ]; then
        warn "MYSQL_ROOT_PASSWORD still default root_pass_2024"
    else
        info "MYSQL_ROOT_PASSWORD not set explicitly (compose default root_pass_2024)"
    fi

    # --- 4d. PostgreSQL ---
    PG_PW=$(load_env_var "POSTGRES_PASSWORD")
    if [ -n "$PG_PW" ] && [ "$PG_PW" != "pg_pass_2024" ]; then
        pass "POSTGRES_PASSWORD changed (non-default)"
    elif [ -n "$PG_PW" ]; then
        warn "POSTGRES_PASSWORD still default pg_pass_2024"
    else
        fail "POSTGRES_PASSWORD not configured"
    fi

    # --- 4e. MinIO ---
    MINIO_AK=$(load_env_var "MINIO_ACCESS_KEY")
    MINIO_SK=$(load_env_var "MINIO_SECRET_KEY")
    if [ "$MINIO_AK" != "minioadmin" ] && [ "$MINIO_SK" != "minioadmin" ]; then
        pass "MinIO credentials changed (non-default)"
    else
        warn "MinIO credentials still default minioadmin/minioadmin"
    fi

    # --- 4f. SMS config ---
    SMS_AK=$(load_env_var "SMS_ACCESS_KEY_ID")
    if [ -n "$SMS_AK" ]; then
        pass "Aliyun SMS configured (verification codes available)"
    else
        info "Aliyun SMS not configured (codes returned in API response)"
    fi

    # --- 4g. SiliconFlow ---
    SF_KEY=$(load_env_var "SILICONFLOW_API_KEY")
    if [ -n "$SF_KEY" ]; then
        info "SiliconFlow API configured (cloud embedding/reranker)"
    else
        info "SiliconFlow not configured (using local models)"
    fi

    # --- 4h. DEBUG mode ---
    DEBUG_VAL=$(load_env_var "DEBUG")
    if [ "$DEBUG_VAL" = "true" ]; then
        warn "DEBUG=true (should be false in production)"
        fixcmd "Edit .env, set DEBUG=false"
    elif [ "$DEBUG_VAL" = "false" ]; then
        pass "DEBUG=false (production mode)"
    fi

    # --- 4i. CORS ---
    CORS_VAL=$(load_env_var "CORS_ORIGINS")
    if echo "$CORS_VAL" | grep -q "localhost"; then
        warn "CORS_ORIGINS contains localhost (should be real domain in prod)"
        fixcmd "Edit .env, set CORS_ORIGINS=your-domain"
    elif [ -n "$CORS_VAL" ]; then
        pass "CORS_ORIGINS: $CORS_VAL"
    fi

    # --- 4j. Production key vars quick scan ---
    info "Scanning production key variables"
    for var in MYSQL_HOST MYSQL_DATABASE POSTGRES_DB REDIS_HOST ES_HOST MILVUS_HOST MINIO_ENDPOINT MINIO_BUCKET LLM_MODEL LLM_BASE_URL APP_NAME; do
        val=$(load_env_var "$var")
        if [ -n "$val" ]; then
            pass "  $var = $val"
        else
            fail "  $var not set"
        fi
    done

else
    warn "Skipping env var checks (.env invalid or missing)"
fi

# ============================================================
header "5. SSL Cert Details"
# ============================================================

if [ -f "docker/ssl/server.crt" ]; then
    if command -v openssl &>/dev/null; then
        EXPIRY=$(openssl x509 -in docker/ssl/server.crt -noout -enddate 2>/dev/null | cut -d= -f2)
        if [ -n "$EXPIRY" ]; then
            EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$EXPIRY" +%s 2>/dev/null)
            NOW_EPOCH=$(date +%s)
            if [ -n "$EXPIRY_EPOCH" ]; then
                DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
                if [ "$DAYS_LEFT" -lt 0 ]; then
                    fail "SSL cert EXPIRED! (expired: $EXPIRY)"
                    fixcmd "Regenerate: bash scripts/preflight-check.sh --fix"
                elif [ "$DAYS_LEFT" -lt 30 ]; then
                    warn "SSL cert expires in ${DAYS_LEFT} days ($EXPIRY)"
                    fixcmd "Regenerate or apply Let's Encrypt cert"
                else
                    pass "SSL cert valid for ${DAYS_LEFT} days ($EXPIRY)"
                fi
            else
                pass "SSL cert expires: $EXPIRY"
            fi
        else
            warn "Cannot parse SSL cert expiry"
        fi

        # Subject / CN
        SUBJECT=$(openssl x509 -in docker/ssl/server.crt -noout -subject 2>/dev/null | sed 's/^subject=//')
        info "Cert subject: $SUBJECT"
    else
        warn "openssl not installed, skipping cert details"
        fixcmd "apt install openssl -y  or  yum install openssl -y"
    fi
fi

# ============================================================
header "6. Port Availability"
# ============================================================

PORT_MAP=(
    "80:HTTP (Nginx entry)"
    "443:HTTPS (Nginx SSL)"
    "3306:MySQL"
    "5432:PostgreSQL"
    "6379:Redis"
    "8000:Backend API"
    "8080:WAF Proxy"
    "9200:Elasticsearch"
    "19530:Milvus"
    "9000:MinIO S3"
    "9001:MinIO Console"
    "9090:Prometheus"
    "3000:Grafana"
    "3100:Loki"
)

for entry in "${PORT_MAP[@]}"; do
    PORT="${entry%%:*}"
    LABEL="${entry#*:}"
    if port_free "$PORT"; then
        pass "Port $PORT free ($LABEL)"
    else
        fail "Port $PORT in use ($LABEL)"
        PROCESS=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | awk '{print $NF}' | head -1 || true)
        fixcmd "Check: lsof -i :$PORT  or  ss -tlnp | grep :$PORT  # process: ${PROCESS:-unknown}"
    fi
done

# ============================================================
header "7. Existing Containers"
# ============================================================

EXISTING_CONTAINERS=$(docker ps -a --filter "name=kb-" --format "{{.Names}}" 2>/dev/null)

if [ -n "$EXISTING_CONTAINERS" ]; then
    warn "Found existing kb-* containers:"
    echo "$EXISTING_CONTAINERS" | while read -r name; do
        STATUS=$(docker ps --filter "name=$name" --format "{{.Status}}" 2>/dev/null)
        if [ -n "$STATUS" ]; then
            info "  $name -> running ($STATUS)"
        else
            STATUS=$(docker ps -a --filter "name=$name" --format "{{.Status}}" 2>/dev/null)
            info "  $name -> stopped ($STATUS)"
        fi
    done
    info "Recommend cleaning old containers before deploy: docker compose down"
else
    pass "No existing kb-* containers"
fi

# Check docker volumes
EXISTING_VOLUMES=$(docker volume ls --filter "name=kb_" -q 2>/dev/null || docker volume ls --filter "name=enterprise-knowledge-base" -q 2>/dev/null)
if [ -n "$EXISTING_VOLUMES" ]; then
    info "Existing Docker volumes (reused on first start):"
    echo "$EXISTING_VOLUMES" | while read -r vol; do
        info "  $vol"
    done
fi

# ============================================================
header "8. Firewall"
# ============================================================

if [ "$OS" = "linux" ]; then
    if command -v ufw &>/dev/null; then
        UFW_STATUS=$(ufw status 2>/dev/null | head -1)
        if echo "$UFW_STATUS" | grep -q "active"; then
            info "ufw active"

            for p in 80 443 22; do
                if ufw status 2>/dev/null | grep -q "${p}/tcp.*ALLOW"; then
                    pass "  Port $p/tcp allowed"
                else
                    warn "  Port $p/tcp not allowed"
                    fixcmd "ufw allow $p/tcp"
                fi
            done
        else
            info "ufw inactive (for cloud servers, check security group rules)"
        fi
    elif command -v firewall-cmd &>/dev/null; then
        if systemctl is-active firewalld &>/dev/null; then
            info "firewalld active"
            for p in 80 443; do
                if firewall-cmd --list-ports 2>/dev/null | grep -q "$p/tcp"; then
                    pass "  Port $p/tcp allowed"
                else
                    warn "  Port $p/tcp not allowed"
                fi
            done
        fi
    else
        info "No ufw/firewalld detected (check cloud provider security group manually)"
    fi
else
    info "Not Linux, skipping firewall check"
fi

# ============================================================
header "9. Domain Resolution (optional)"
# ============================================================

DOMAIN_VALUE=$(load_env_var "DOMAIN" 2>/dev/null || true)
if [ -z "$DOMAIN_VALUE" ]; then
    DOMAIN_VALUE=$(grep '^DOMAIN=' "$PROJECT_DIR/deploy.sh" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"' | xargs)
fi

if [ -n "$DOMAIN_VALUE" ]; then
    info "Domain: $DOMAIN_VALUE"

    if command -v dig &>/dev/null; then
        RESOLVED=$(dig +short "$DOMAIN_VALUE" 2>/dev/null | head -1)
    elif command -v nslookup &>/dev/null; then
        RESOLVED=$(nslookup "$DOMAIN_VALUE" 2>/dev/null | awk '/^Address: /{print $2}' | head -1)
    else
        RESOLVED=""
    fi

    if [ -n "$RESOLVED" ]; then
        SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        if echo "$SERVER_IP" | grep -q "^$RESOLVED$" 2>/dev/null || echo "$RESOLVED" | grep -q "^$SERVER_IP$" 2>/dev/null; then
            pass "$DOMAIN_VALUE -> $RESOLVED (points to this host)"
        else
            info "$DOMAIN_VALUE -> $RESOLVED (this host IP: ${SERVER_IP:-unknown})"
        fi
    else
        warn "$DOMAIN_VALUE cannot be resolved (DNS not configured?)"
        fixcmd "Add A record in DNS console: $DOMAIN_VALUE -> server public IP"
    fi
else
    info "No domain configured (skipping)"
fi

# ============================================================
header "10. Summary Report"
# ============================================================

echo ""
TOTAL=$((PASS + FAIL + WARN))
echo "  ${BOLD}Total checks:${RESET} $TOTAL"
echo "  ${GREEN}PASS: $PASS${RESET}"
echo "  ${RED}FAIL: $FAIL${RESET}"
echo "  ${YELLOW}WARN: $WARN${RESET}"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}Conclusion: all preflight checks passed, ready to deploy!${RESET}"
    echo ""
    echo "  Start commands:"
    echo "    # Development"
    echo "    docker compose up -d --build"
    echo ""
    echo "    # Production"
    echo "    docker compose -f docker-compose.prod.yml -f docker-compose.tencent.yml up -d --build"
    echo ""
    if [ "$WARN" -gt 0 ]; then
        echo -e "  ${YELLOW}Note: $WARN warning(s), recommended to handle before launch.${RESET}"
    fi
    exit 0
else
    echo -e "  ${RED}${BOLD}Conclusion: $FAIL check(s) failed, fix them before deploying.${RESET}"
    echo ""
    echo "  Quick fix:"
    echo "    bash scripts/preflight-check.sh --fix"
    echo ""
    exit 1
fi
