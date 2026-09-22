#!/bin/bash
# backup.sh — 企业知识库系统全量备份脚本
# 用法: bash scripts/backup.sh [backup_dir]
# 默认备份到 ./backups/YYYYMMDD_HHMMSS/

set -e

BACKUP_ROOT="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-kb_pass_2024}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-langgraph_checkpoint}"

echo "=== 备份开始: $TIMESTAMP ==="

# 1. MySQL (业务数据)
echo "[1/4] MySQL 备份..."
docker compose -f "$COMPOSE_FILE" exec -T mysql \
  mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --all-databases \
  > "$BACKUP_DIR/mysql_all.sql"
echo "  -> $BACKUP_DIR/mysql_all.sql ($(wc -c < "$BACKUP_DIR/mysql_all.sql") bytes)"

# 2. PostgreSQL (LangGraph Checkpoint)
echo "[2/4] PostgreSQL 备份..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "$BACKUP_DIR/postgres_langgraph.sql"
echo "  -> $BACKUP_DIR/postgres_langgraph.sql ($(wc -c < "$BACKUP_DIR/postgres_langgraph.sql") bytes)"

# 3. MinIO (原始文档文件)
echo "[3/4] MinIO 备份..."
if docker compose -f "$COMPOSE_FILE" exec -T minio mc alias list 2>/dev/null | grep -q myminio; then
  docker compose -f "$COMPOSE_FILE" exec -T minio \
    mc cp --recursive myminio/knowledge-docs "$BACKUP_DIR/minio/" 2>/dev/null || true
else
  docker compose -f "$COMPOSE_FILE" exec -T minio \
    mc alias set myminio http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
  docker compose -f "$COMPOSE_FILE" exec -T minio \
    mc cp --recursive myminio/knowledge-docs "$BACKUP_DIR/minio/" 2>/dev/null || true
fi
echo "  -> $BACKUP_DIR/minio/"

# 4. Elasticsearch 索引快照（Snapshot API）
echo "[4/4] Elasticsearch 索引快照注册..."
SNAPSHOT_REPO=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:9200/_snapshot/backup")
if [ "$SNAPSHOT_REPO" = "404" ]; then
  curl -s -X PUT "http://localhost:9200/_snapshot/backup" \
    -H "Content-Type: application/json" \
    -d '{"type": "fs", "settings": {"location": "backup"}}' > /dev/null
fi
curl -s -X PUT "http://localhost:9200/_snapshot/backup/snapshot_$TIMESTAMP?wait_for_completion=true" > /dev/null
echo "  -> ES snapshot: snapshot_$TIMESTAMP"

# 5. Grafana 配置导出
echo "[可选] Grafana 看板导出..."
if curl -s -f "http://localhost:3000/api/health" > /dev/null 2>&1; then
  curl -s "http://admin:admin@localhost:3000/api/search?type=dash-db" \
    | python3 -c "import sys,json; [print(d['title']) for d in json.load(sys.stdin)]" \
    > "$BACKUP_DIR/grafana_dashboards.txt" 2>/dev/null || true
fi

echo ""
echo "=== 备份完成: $BACKUP_DIR ==="
du -sh "$BACKUP_DIR"

echo ""
echo "恢复命令参考:"
echo "  MySQL:    docker compose exec -T mysql mysql -u root -p'$MYSQL_ROOT_PASSWORD' < $BACKUP_DIR/mysql_all.sql"
echo "  Postgres: docker compose exec -T postgres psql -U $POSTGRES_USER $POSTGRES_DB < $BACKUP_DIR/postgres_langgraph.sql"
