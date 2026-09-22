# 回滚操作手册 (Rollback Guide)

企业知识库系统紧急回滚操作，目标：**5 分钟内恢复服务**。

## 前置条件

- `deploy.sh` 每次部署时自动执行 `docker tag <app>:latest <app>:previous` 保留上一版镜像
- 镜像版本标签格式: `kb-backend:<git-hash>` / `kb-frontend:<git-hash>`

## 场景 A: Docker 镜像级回滚（推荐，<2 分钟）

```bash
# 1. 确认当前版本
docker images | grep kb-

# 2. 恢复到上一版
docker tag kb-backend:previous kb-backend:latest
docker tag kb-frontend:previous kb-frontend:latest

# 3. 重启服务
docker compose -f docker-compose.prod.yml -f docker-compose.tencent.yml up -d

# 4. 验证
curl -s http://localhost:8000/health | grep healthy
```

## 场景 B: Git 代码级回滚（5 分钟内）

```bash
# 1. 查看部署历史
git log --oneline -5

# 2. 回退到指定 commit
git checkout <target-commit-hash>

# 3. 重新部署
bash deploy.sh
```

## 场景 C: FAQ 内容级回滚（无需重启）

```bash
# 通过 API 回滚 FAQ 到历史版本
curl -X POST http://localhost:8000/api/admin/faqs/{faq_id}/rollback/{version_id} \
  -H "Authorization: Bearer <token>"
```

## 验证检查

部署后执行以下验证：

```bash
# 服务状态
curl -s http://localhost:8000/health | jq .

# 容器状态
docker ps --format "table {{.Names}}\t{{.Status}}"

# 镜像版本
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}" | grep kb-
```
