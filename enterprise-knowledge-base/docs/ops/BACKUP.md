# 备份恢复指南

## 需备份的数据

| 数据 | 存储位置 | 方式 |
|------|---------|------|
| MySQL (业务数据) | `mysql-data` 卷 | `mysqldump` |
| PostgreSQL (Checkpoint) | `postgres-data` 卷 | `pg_dump` |
| Milvus (向量数据) | `milvus-data` 卷 | `pymilvus` 导出 |
| MinIO (原始文件) | `minio-data` 卷 | 直接复制 |
| Elasticsearch (BM25 索引) | `es-data` 卷 | 快照 API / 重建 |
| Redis (验证码/Session) | `redis-data` 卷 | 可跳过 |

## 快速备份（全量）

创建 `scripts/backup.sh`：

```bash
#!/bin/bash
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. MySQL
docker compose -f docker-compose.prod.yml exec -T mysql \
  mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --all-databases \
  > "$BACKUP_DIR/mysql_all.sql"

# 2. PostgreSQL
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "$BACKUP_DIR/postgres_langgraph.sql"

# 3. MinIO（mc 工具）
# 需先在 MinIO 容器内安装 mc 客户端
# docker compose exec minio mc cp --recursive /data "$BACKUP_DIR/minio/"

echo "Backup complete: $BACKUP_DIR"
```

## 定时备份（cron）

```bash
# 每日凌晨 2 点备份，保留最近 7 天
0 2 * * * cd /opt/knowledge-base && bash scripts/backup.sh
0 3 * * * find /opt/knowledge-base/backups -type d -mtime +7 -exec rm -rf {} \;
```

## MySQL 备份与恢复

```bash
# 备份所有数据库
docker compose -f docker-compose.prod.yml exec -T mysql \
  mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --all-databases \
  > mysql_backup.sql

# 恢复
docker compose -f docker-compose.prod.yml exec -T mysql \
  mysql -u root -p"$MYSQL_ROOT_PASSWORD" < mysql_backup.sql
```

## PostgreSQL 备份与恢复

```bash
# 备份
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres langgraph_checkpoint > pg_backup.sql

# 恢复（需先清空目标库）
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d langgraph_checkpoint < pg_backup.sql
```

## Elasticsearch 索引重建

ES 的 BM25 索引可从 MySQL `doc_chunk` 表重建：

```bash
# 进入后端容器
docker compose exec backend python -c "
import asyncio
from app.retrieval.sync import rebuild_bm25_index
from app.core.database import AsyncSessionLocal

async def rebuild():
    async with AsyncSessionLocal() as db:
        await rebuild_bm25_index(db)
    print('ES index rebuilt')

asyncio.run(rebuild())
"
```

## Milvus 向量重建

```bash
# 进入后端容器
docker compose exec backend python -c "
import asyncio
from app.retrieval.sync import rebuild_vector_collection
from app.core.database import AsyncSessionLocal

async def rebuild():
    async with AsyncSessionLocal() as db:
        await rebuild_vector_collection(db)
    print('Milvus collection rebuilt')

asyncio.run(rebuild())
"
```

## 备份验证

```bash
# 检查 MySQL 备份完整性
head -5 mysql_backup.sql
tail -5 mysql_backup.sql

# 检查最近备份目录
ls -la backups/

# 测试恢复到临时环境
docker compose -f docker-compose.test.yml up -d mysql
docker compose -f docker-compose.test.yml exec -T mysql \
  mysql -u root -p"test_pass" < mysql_backup.sql
```
