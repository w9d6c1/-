# 系统架构图

```mermaid
graph TB
    subgraph "外部"
        USER["用户/员工<br/>浏览器"]
        CS["客服人员"]
        ADMIN["管理员<br/>管理后台"]
    end

    subgraph "网关层"
        WAF["WAF<br/>ModSecurity + OWASP CRS<br/>:8080"]
        NGINX["Nginx 1.27<br/>反向代理 + HTTPS<br/>:80 / :443"]
    end

    subgraph "应用层"
        FRONTEND["Vue3 + Element Plus<br/>前端 SPA<br/>:5173"]
        BACKEND["FastAPI<br/>AI 智能体服务<br/>:8000"]
        ADMIN_UI["管理后台<br/>知识库 / 权限 / 审计"]
    end

    subgraph "AI 引擎层"
        LANGRAPH["LangGraph<br/>对话编排引擎"]
        LLM["DeepSeek<br/>大模型 API<br/>(外部)"]
        EMBEDDING["BGE-Large-ZH<br/>嵌入模型<br/>1024维"]
        RERANKER["BGE-Reranker-v2-m3<br/>重排序"]
    end

    subgraph "检索层"
        MILVUS["Milvus 2.4<br/>向量数据库<br/>coll_public / internal / customer<br/>:19530"]
        ELASTIC["Elasticsearch 8.15<br/>BM25 全文检索<br/>idx_bm25_public / internal / customer<br/>:9200"]
        FUSION["RRF 融合<br/>+ Reranker 重排"]
    end

    subgraph "存储层"
        MYSQL[("MySQL 8.0<br/>业务数据<br/>11张表<br/>:3306")]
        POSTGRES[("PostgreSQL 16<br/>LangGraph Checkpoint<br/>对话状态持久化<br/>:5432")]
        REDIS[("Redis 7<br/>缓存 + Session<br/>:6379")]
        MINIO[("MinIO<br/>对象存储<br/>原始文档<br/>:9000")]
    end

    subgraph "可观测性"
        PROMETHEUS["Prometheus<br/>指标采集<br/>:9090"]
        GRAFANA["Grafana<br/>4大看板 + 告警<br/>:3000"]
        LOKI["Loki + Promtail<br/>日志聚合<br/>:3100"]
    end

    USER --> NGINX
    CS --> NGINX
    ADMIN --> NGINX
    NGINX --> WAF
    WAF --> FRONTEND
    WAF --> BACKEND
    FRONTEND --> BACKEND
    ADMIN_UI --> BACKEND

    BACKEND --> LANGRAPH
    LANGRAPH --> LLM
    LANGRAPH --> EMBEDDING
    LANGRAPH --> RERANKER
    LANGRAPH --> FUSION

    FUSION --> MILVUS
    FUSION --> ELASTIC

    BACKEND --> MYSQL
    BACKEND --> POSTGRES
    BACKEND --> REDIS
    BACKEND --> MINIO

    BACKEND --> PROMETHEUS
    PROMETHEUS --> GRAFANA
    LOKI --> GRAFANA
    BACKEND --> LOKI

    subgraph "安全隔离 — 三重隔离"
        direction LR
        ISO1["向量层<br/>三Collection 独立"]
        ISO2["路由层<br/>_strip_internal_scopes"]
        ISO3["接口层<br/>API Key + JWT 鉴权"]
    end
```

## 核心数据流

```
用户提问
  → Nginx (HTTPS + WAF)
  → FastAPI (/api/agent/*/chat)
  → LangGraph Workflow:
      1. 输入校验 (SQL注入/禁答词/Prompt注入)
      2. 鉴权 (JWT → scope > permission)
      3. 查询改写 (同义词+指代消解)
      4. 路由分发 (FAQ or RAG)
      5a. FAQ 匹配 (余弦相似度 ≥0.92 短路)
      5b. 混合检索 (BM25{Dense→RRF k=60→Reranker topK=First)
      6. 工具调用 (ReAct 循环, max 3 iterations)
      7. 上下文组装 (Token 预算截断)
      8. 答案生成 (DeepSeek + Prompt 模板)
      9. 输出校验 (敏感词脱敏+置信度)
      10. 日志记录 (ChatLog/OperateLog/SecurityLog)
  → SSE 流式输出
  → ChatLog 异步落库 (MySQL)
  → Checkpoint 状态保存 (PostgreSQL)
```

## 双智能体对比

| 特性 | 内部智能体 | 客服智能体 |
|------|-----------|-----------|
| 入口 | `/api/agent/internal/chat` | `/api/agent/customer/chat` |
| Scope | public + internal | public + customer |
| FAQ 匹配 | all_scopes | customer + public (硬编码) |
| 转人工 | 不支持 | 4 类触发条件 |
| 工具调用 | search_kb + decompose | 不支持 |
| 速率限制 | 30/min | 60/min |

## 部署架构

```
docker compose up -d (15 个服务)

kb-waf        :8080 → ModSecurity WAF 代理
kb-nginx      :80/443 → 反向代理
kb-backend    :8000 → FastAPI (uvicorn, hot-reload)
kb-frontend   :5173 → Vue3 + React 管理后台 (合并构建)
kb-mysql      :3306 → 业务库
kb-postgres   :5432 → Checkpoint 库
kb-redis      :6379 → 缓存
kb-es         :9200 → BM25 检索
kb-milvus     :19530 → 向量检索
kb-etcd       :2379 → Milvus 元数据
kb-minio      :9000 → 对象存储
kb-prometheus :9090 → 指标采集
kb-grafana    :3000 → 监控看板
kb-loki       :3100 → 日志聚合
kb-promtail   (无端口) → 日志采集
```
