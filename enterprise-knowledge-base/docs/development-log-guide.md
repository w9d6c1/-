# 开发日志指南

本项目日志体系分为三层：运行时日志、业务审计日志、可观测性平台。

## 一、终端实时查看日志

```bash
# 所有服务
docker compose logs -f --tail=50

# 只看 AI 后端
docker compose logs -f backend

# 只看错误
docker compose logs 2>&1 | grep -iE "error|exception|traceback"

# 追踪一次完整问答 (按 request_id)
docker compose logs backend | grep "req_abc123"
```

## 二、结构化 JSON 日志 + jq 过滤

后端使用 structlog 输出 JSON 格式日志，每条日志格式如下：

```json
{
  "timestamp": "2026-06-29T14:32:01.123Z",
  "level": "info",
  "request_id": "req_abc123",
  "thread_id": "thr_xyz789",
  "node": "混合检索节点",
  "event": "检索完成",
  "bm25_count": 20,
  "dense_count": 20,
  "rrf_merged": 28,
  "latency_ms": 342
}
```

常用过滤命令：

```bash
# 只看某会话的完整链路
docker compose logs backend | jq 'select(.thread_id == "thr_xyz789")'

# 只看延迟超过 1s 的节点
docker compose logs backend | jq 'select(.latency_ms > 1000)'

# 只看错误
docker compose logs backend | jq 'select(.level == "error")'
```

## 三、管理后台 Web 页面 (阶段二完成后)

| 日志类型 | 页面路径 | 内容 |
|---------|---------|------|
| 操作日志 | `/admin/logs/operate` | 增删改查、操作人、修改前后对比 |
| 对话日志 | `/admin/logs/chat` | 每轮问答完整节点链路，支持 session drill-down |
| 安全日志 | `/admin/logs/security` | 敏感词命中、越权尝试、异常访问 |

## 四、Grafana 看板

访问 `http://localhost:3000` (admin/admin)

| 看板 | 用途 |
|------|------|
| 服务概览 | 各容器健康状态、QPS |
| 对话链路追踪 | 按 thread_id 搜索完整对话 |
| 检索质量 | Recall/MRR/NDCG 趋势 |
| 安全态势 | 拦截统计、异常来源 |

## 五、日志关联 ID

```
request_id → 贯穿三层日志：应用日志 + chat_log + security_log
thread_id  → 会话维度：chat_log + PostgresSaver Checkpoint
```

开发调试时只需记下一个 `request_id`，就可在终端、数据库、Grafana 三处找到完整链路。

## 六、其他常用命令

```bash
# 进入 PostgreSQL 查 chat_log
docker compose exec postgres psql -U postgres -d langgraph_checkpoint -c "SELECT * FROM chat_log WHERE thread_id='thr_xyz' ORDER BY created_at;"

# ES 索引状态
curl -s http://localhost:9200/_cat/indices?v

# 日志磁盘占用
docker system df
```

## 七、日志配置位置

- structlog 配置: `backend/app/core/logging.py`
- Loki 配置: `docker/loki/loki-config.yml`
- Promtail 配置: `docker/loki/promtail-config.yml`
- 日志留存: chat_log 默认 180 天，Grafana Loki 30 天，Prometheus 30 天
