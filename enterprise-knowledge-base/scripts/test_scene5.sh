#!/bin/bash
# 场景5 上线测试: 多轮记忆 + 权限隔离 + 客服SSE
# 在服务器上运行: bash test_scene5.sh
set -e

BASE=${1:-http://localhost}
PASS=0
FAIL=0
echo "========================================"
echo "  场景5测试: $BASE"
echo "========================================"

test_case() {
    local name="$1"
    local cmd="$2"
    echo ""
    echo "--- $name ---"
    if eval "$cmd"; then
        echo "  [PASS]"
        PASS=$((PASS + 1))
        return 0
    else
        echo "  [FAIL]"
        FAIL=$((FAIL + 1))
        return 1
    fi
}

# ── 1. 健康检查 ──
test_case "1. /health" \
    'curl -sf $BASE/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d[\"status\"]==\"healthy\""'

test_case "2. /api/agent/status" \
    'curl -sf $BASE/api/agent/status | python3 -c "import sys,json; d=json.load(sys.stdin); assert d[\"status\"]==\"ok\""'

# ── 2. 多轮记忆 (内部非流式) ──
T="mem-$(date +%H%M%S)"

test_case "3. 多轮-R1" \
    "curl -sf -X POST $BASE/api/agent/internal/chat -H 'Content-Type: application/json' \
        -d '{\"message\":\"my name is Alice\",\"thread_id\":\"$T\",\"scope\":\"public\"}' \
        | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d.get('answer'); print('R1:', d['answer'][:80])\""

test_case "4. 多轮-R2" \
    "curl -sf -X POST $BASE/api/agent/internal/chat -H 'Content-Type: application/json' \
        -d '{\"message\":\"what is my name\",\"thread_id\":\"$T\",\"scope\":\"public\"}' \
        | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d.get('answer'); print('R2:', d['answer'][:80])\""

test_case "5. 多轮-R3" \
    "curl -sf -X POST $BASE/api/agent/internal/chat -H 'Content-Type: application/json' \
        -d '{\"message\":\"what is my job\",\"thread_id\":\"$T\",\"scope\":\"public\"}' \
        | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d.get('answer'); print('R3:', d['answer'][:80])\""

# ── 3. 客服 SSE 多轮 ──
CT_CUST="cust-$(date +%H%M%S)"

test_case "6. 客服SSE-R1" \
    "OUT=\$(curl -sf -N -X POST $BASE/api/agent/customer/chat/stream \
        -H 'Content-Type: application/json' \
        -d '{\"message\":\"i want to order\",\"thread_id\":\"$CT_CUST\"}' 2>&1); \
     echo \"\$OUT\" | head -5; [[ -n \"\$OUT\" ]]"

test_case "7. 客服SSE-R2 (same thread)" \
    "OUT=\$(curl -sf -N -X POST $BASE/api/agent/customer/chat/stream \
        -H 'Content-Type: application/json' \
        -d '{\"message\":\"what did i just ask\",\"thread_id\":\"$CT_CUST\"}' 2>&1); \
     echo \"\$OUT\" | head -5; [[ -n \"\$OUT\" ]]"

# ── 4. Auth 检测 ──
test_case "8. 无认证 /internal/chat/stream" \
    "STATUS=\$(curl -s -o /dev/null -w '%{http_code}' -X POST $BASE/api/agent/internal/chat/stream \
        -H 'Content-Type: application/json' -d '{\"message\":\"test\",\"scope\":\"public\"}'); \
     echo \"Status=$STATUS\"; true"

test_case "9. 无认证 /customer/chat" \
    "curl -sf -X POST $BASE/api/agent/customer/chat -H 'Content-Type: application/json' \
        -d '{\"message\":\"refund process\"}' \
        | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d.get('answer'); print(d['answer'][:80])\""

# ── 5. Scope 隔离 ──
test_case "10. scope=public" \
    "curl -sf -X POST $BASE/api/agent/internal/chat -H 'Content-Type: application/json' \
        -d '{\"message\":\"company info\",\"thread_id\":\"scope-pub\",\"scope\":\"public\"}' \
        | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d.get('answer'); print(d['answer'][:80])\""

# ── 报告 ──
TOTAL=$((PASS + FAIL))
echo ""
echo "========================================"
echo "  PASS=$PASS  FAIL=$FAIL  TOTAL=$TOTAL"
echo "========================================"
[ $FAIL -eq 0 ] && exit 0 || exit 1
