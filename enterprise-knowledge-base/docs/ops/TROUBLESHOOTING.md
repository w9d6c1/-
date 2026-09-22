# 故障排查指南

## 快速诊断命令

```bash
# 查看所有容器状态
docker compose -f docker-compose.prod.yml ps

# 查看某个服务日志
docker compose logs -f backend --tail=100
docker compose logs -f mysql --tail=50

# 查看最近错误
docker compose logs 2>&1 | grep -iE "error|exception|fail"

# 资源占用
docker stats --no-stream
```

## 1. 容器启动失败

### 症状：容器反复重启，状态 `Restarting`

```bash
docker compose logs <service-name> --tail=50
```

| 原因 | 解决方案 |
|------|---------|
| 端口冲突 | `netstat -tlnp` 检查端口占用，修改 `docker-compose.prod.yml` |
| 内存不足 | 降低 ES `-Xmx512m`、Milvus `memory` limits |
| 磁盘满 | `df -h`，清理 Docker 缓存 `docker system prune -a` |
| .env 未配置 | 检查 `.env` 是否存在且包含所有必需变量 |

## 2. 数据库连接失败

### 症状：后端日志 `Can't connect to MySQL`

```bash
# 进入后端容器测试连接
docker compose exec backend python -c "import asyncio; from app.core.database import AsyncSessionLocal; asyncio.run(AsyncSessionLocal().execute(...))"

# 测试 MySQL 连通性
docker compose exec mysql mysqladmin ping -u root -p
```

检查 `.env` 中：
- `MYSQL_HOST=mysql`（服务名，非 IP）
- 密码与 `docker-compose.prod.yml` 中 `MYSQL_ROOT_PASSWORD` 一致

## 3. AI 问答无响应 / 报错

### 症状：`/api/agent/chat` 返回 500

```bash
# 检查 LLM API Key
docker compose exec backend python -c "from app.core.config import settings; print('API Key:', settings.llm_api_key[:10] + '...' if settings.llm_api_key else 'EMPTY')"

# 测试 LLM 连通性
docker compose exec backend python -c "
from langchain_openai import ChatOpenAI
import asyncio
llm = ChatOpenAI(model='deepseek-chat', api_key='your-key', base_url='https://api.deepseek.com')
async def test(): print((await llm.ainvoke('hi')).content)
asyncio.run(test())
"
```

| 原因 | 解决方案 |
|------|---------|
| API Key 未设置 | 检查 `LLM_API_KEY` 在 `.env` 中 |
| 网络不通 | 测试 `docker compose exec backend curl https://api.deepseek.com` |
| Embedding 模型未下载 | 首次自动下载 `bge-large-zh-v1.5`(~1.3GB)，需等待 |

## 4. 检索结果为空

### 症状：AI 回答不包含知识库内容

```bash
# 检查 ES 索引
curl http://localhost:9200/_cat/indices?v

# 检查 Milvus 集合
docker compose exec backend python -c "
from pymilvus import connections, utility
connections.connect(host='milvus', port='19530')
print(utility.list_collections())
"

# 检查向量同步
docker compose exec backend python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.document import DocChunk
from sqlalchemy import select
async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(DocChunk).where(DocChunk.last_sync_at.isnot(None)))
        print(f'Synced chunks: {len(r.scalars().all())}')
asyncio.run(check())
"
```

## 5. 前端白屏 / 加载失败

### 症状：浏览器访问后白屏

```bash
# 检查前端容器
docker compose logs frontend --tail=30

# 检查 API 可达性
curl -k https://localhost/api/health
```

| 原因 | 解决方案 |
|------|---------|
| CORS 域名不匹配 | 修改 `.env` 中 `CORS_ORIGINS` 包含前端域名 |
| API 地址错误 | 前端打包时 `VITE_API_BASE_URL` 需与生产一致 |
| 静态资源 404 | 检查 `frontend/docker/nginx-frontend.conf` 中 root 路径 |

## 6. 性能慢

### 症状：API 响应时间 >5s

```bash
# 查看后端延迟日志
docker compose logs backend | grep -i "latency"

# 数据库慢查询
docker compose exec mysql mysql -u root -p -e "SHOW FULL PROCESSLIST;"

# ES 集群状态
curl -s http://localhost:9200/_cluster/stats | python -m json.tool
```

| 优化项 | 操作 |
|------|------|
| Embedding 首次下载 | 等待模型下载完成，约 1-3 分钟 |
| ES 内存不足 | 增加 `ES_JAVA_OPTS=-Xmx1g` |
| 数据库索引缺失 | 检查 `docker/mysql/init/01-schema.sql` 索引 |
| 连接池耗尽 | 增加 `config.py` 中 `pool_size` 和 `max_overflow` |

## 7. 常用诊断命令

```bash
# 进入后端容器
docker compose exec backend bash

# 运行全部测试
docker compose exec backend python -m pytest tests/unit/ -q --no-cov --asyncio-mode=auto

# 重启单个服务
docker compose restart backend

# 完全重建（会删除数据卷）
docker compose down -v
docker compose up -d --build
```
