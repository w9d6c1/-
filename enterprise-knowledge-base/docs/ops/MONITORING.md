# 监控指南

## 访问地址

| 工具 | 地址 | 默认账号 | 密码来源 |
|------|------|---------|---------|
| Grafana | `http://localhost:3000` | 见 `.env` `GRAFANA_USER` | 见 `.env` `GRAFANA_PASSWORD` |
| Prometheus | `http://localhost:9090` | 无认证 | — |
| Loki | `http://localhost:3100` | 无认证 | — |

## Grafana 看板

访问 `http://localhost:3000` 登录后，在 Dashboards 中可查看：

| 看板 | 内容 |
|------|------|
| 服务概览 | 所有容器健康状态、CPU/内存、QPS |
| 对话链路追踪 | 按 `thread_id` 搜索完整对话节点 |
| 检索质量 | Recall / MRR / NDCG 趋势 |
| 安全态势 | 拦截统计、异常来源 IP |

### 添加数据源

如果 Grafana 数据源未自动配置，手动添加：

1. Configuration → Data Sources → Add
2. Prometheus：URL `http://prometheus:9090`
3. Loki：URL `http://loki:3100`

## Prometheus 指标

Prometheus 每 15 秒抓取一次后端指标。关键查询：

```promql
# 请求速率 (QPS)
rate(http_requests_total[1m])

# 请求延迟 (p95)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# 错误率
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[1m])

# Milvus 向量数
milvus_collection_num_entities

# ES 集群状态
elasticsearch_cluster_health_status

# 容器内存使用
container_memory_usage_bytes{name=~"kb-.*"}
```

## Loki 日志查询

Grafana → Explore → 选择 Loki 数据源：

```logql
# 查看后端所有日志
{container_name="kb-backend"}

# 过滤错误
{container_name="kb-backend"} |= "error"

# 按 thread_id 追踪对话
{container_name="kb-backend"} |= "thr_xyz789"

# 查看慢查询（延迟 >1s）
{container_name="kb-backend"} | json | latency_ms > 1000
```

## 终端实时日志

```bash
# 所有服务
docker compose -f docker-compose.prod.yml logs -f --tail=50

# 仅后端
docker compose logs -f backend --tail=100

# 过滤错误
docker compose logs 2>&1 | grep -iE "error|exception|traceback"

# 结构化日志（structlog JSON 格式）
docker compose logs backend | grep "{" | head -5
```

## 日志关联

```
request_id → 贯穿三层：应用日志 + chat_log + security_log
thread_id  → 会话维度：chat_log + PostgresSaver Checkpoint
```

记下 `request_id` 后可在终端、数据库、Grafana 三处追踪完整链路：

```bash
# 终端
docker compose logs backend | grep "req_abc123"

# 数据库
docker compose exec postgres psql -U postgres -d langgraph_checkpoint \
  -c "SELECT * FROM chat_log WHERE request_id='req_abc123';"

# Grafana
# Explore → Loki → {container_name="kb-backend"} |= "req_abc123"
```

## 数据库日志查询

```bash
# 进入 MySQL 查 chat_log
docker compose exec mysql mysql -u root -p -D knowledge_base \
  -e "SELECT id, thread_id, question, node_name, node_latency_ms, created_at FROM chat_log ORDER BY created_at DESC LIMIT 20;"

# 安全事件
docker compose exec mysql mysql -u root -p -D knowledge_base \
  -e "SELECT id, event_type, severity, detail, created_at FROM security_log ORDER BY created_at DESC LIMIT 20;"

# ES 索引状态
curl -s http://localhost:9200/_cat/indices?v
```

## 磁盘与资源

```bash
# Docker 磁盘占用
docker system df

# 日志磁盘占用 (Loki 保留 30 天)
du -sh docker/volumes/loki-data/

# 数据卷占用
docker system df -v | grep -E "VOLUME|mysql|postgres|milvus|es|minio"
```
