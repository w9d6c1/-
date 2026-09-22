# 上线 Checklist

> 使用此清单在每次部署/发布前逐项验证，全部通过后方可上线。

## 1. 基础设施

- [ ] 所有 Docker 服务运行中：`docker compose -f docker-compose.prod.yml ps`（13/13 healthy）
- [ ] WAF 服务健康：`curl -s http://localhost:8080/health` 返回 200
- [ ] Nginx HTTPS 证书有效：浏览器访问 `https://<host>` 无警告
- [ ] DNS/域名解析正确（如有配置）
- [ ] 防火墙：仅开放 80/443 端口，其他端口只对内网
- [ ] 磁盘空间 ≥30% 可用：`df -h`
- [ ] 内存使用正常：`free -h`（≥4GB 可用）

## 2. 应用健康

- [ ] API 健康检查通过：`curl -k https://localhost/api/health`
- [ ] 管理后台可访问：`curl -k https://localhost/api/admin/status`
- [ ] 智能体状态正常：`curl -k https://localhost/api/agent/status`
- [ ] 管理后台 IP 白名单生效：外网 IP 访问 `/api/admin/*` 返回 403

## 3. 数据库与存储

- [ ] MySQL 连接正常：`docker compose exec mysql mysqladmin ping -u root -p`
- [ ] PostgreSQL 连接正常：`docker compose exec postgres pg_isready`
- [ ] Redis 连接正常：`docker compose exec redis redis-cli PING`
- [ ] Elasticsearch 集群状态 Green：`curl -s http://localhost:9200/_cluster/health | grep status`
- [ ] Milvus 集合可访问：`curl -s http://localhost:9091/healthz`
- [ ] MinIO 健康检查：`curl -s http://localhost:9000/minio/health/live`

## 4. 安全验证

- [ ] JWT_SECRET_KEY 已使用 `openssl rand -hex 32` 生成（≥64字符）
- [ ] 所有数据库密码已替换默认值（MYSQL/POSTGRES/MINIO）
- [ ] DEBUG=false（`.env` 中确认）
- [ ] LOG_LEVEL=INFO（`.env` 中确认）
- [ ] CORS_ORIGINS 已配置生产域名
- [ ] LLM_API_KEY 已配置
- [ ] Grafana 密码已修改（非 admin/admin）
- [ ] 速率限制生效：`/auth/login` 多次快速请求触发 429
- [ ] **WAF 拦截验证**：`curl -X POST http://localhost:8080/api/agent/internal/chat -H "Content-Type: application/json" -d '{"question":"1 UNION SELECT * FROM users"}'` 返回 403
- [ ] **WAF 正常请求通过**：正常问答请求不被 WAF 误拦（运行安全测试套 `pytest tests/security/`）
- [ ] **WAF 审计日志**：`docker compose exec waf cat /var/log/modsec_audit.log | head` 有内容

## 5. 业务功能验证

- [ ] 内部智能体：`POST /api/agent/internal/chat` 返回正常回答
- [ ] 客服智能体：`POST /api/agent/customer/chat` 仅返回 public+customer 范围
- [ ] SSE 流式：`POST /api/agent/internal/chat/stream` 逐 token 返回
- [ ] 管理后台登录：`POST /api/admin/auth/login` 返回 token
- [ ] 权限隔离：readonly 用户无法写 FAQ/文档
- [ ] 敏感词拦截：包含禁止讨论词时 is_blocked=True
- [ ] FAQ 向量刷新：创建 FAQ 后向量自动更新
- [ ] 文档审批流：创建→上传→分块→审核→上线
- [ ] 审计日志：登录失败记录到 security_log

## 6. 备份与恢复

- [ ] 定时备份 cron 已配置：`0 2 * * * /opt/knowledge-base/scripts/backup.sh`
- [ ] 备份目录存在：`ls backups/`
- [ ] 备份恢复流程已验证：参考 `docs/ops/BACKUP.md`

## 7. 监控与告警

- [ ] Grafana 可访问：`http://localhost:3000`
- [ ] 四大看板加载正常：服务概览 / 业务洞察 / 知识质量 / 安全态势
- [ ] Prometheus 指标采集正常：`http://localhost:9090/targets`
- [ ] Loki 日志可查询：Grafana → Explore → 选择 Loki
- [ ] 告警规则已配置（如有）

## 8. 性能基准

- [ ] FAQ 匹配延迟 < 200ms（运行 `pytest tests/performance/ --benchmark-only --no-cov`）
- [ ] 并发 20 QPS 不超时
- [ ] 文档分块 < 5s/MB
- [ ] 全量单元测试通过：`python -m pytest tests/unit/ tests/integration/ tests/security/ -q --no-cov`

## 9. 数据就绪

- [ ] FAQ 种子已导入：`docker compose exec backend python -m app.scripts.import_seed_data --faq data/faq_internal.csv`（再同法导入 `faq_public.csv`、`faq_customer.csv`）
- [ ] 至少 3 个知识分类（public/customer/internal）
- [ ] 至少 10 条 FAQ（覆盖三个 scope）
- [ ] 至少 3 篇文档（已审核+向量化）

## 10. 文档与交接

- [ ] `docs/ops/STARTUP.md` 可指导首次部署
- [ ] `docs/ops/TROUBLESHOOTING.md` 覆盖常见问题
- [ ] `docs/ops/BACKUP.md` 覆盖备份恢复
- [ ] `docs/ops/MONITORING.md` 覆盖监控指标
- [ ] 管理员账号密码已交付
- [ ] API 文档可访问：`https://<host>/api/docs`

---

## 验证命令速查

```bash
# 一键健康检查
docker compose -f docker-compose.prod.yml ps

# 全量测试
docker compose exec backend python -m pytest tests/unit/ tests/integration/ tests/security/ -q --no-cov

# 性能基准
docker compose exec backend python -m pytest tests/performance/ --benchmark-only --no-cov

# 备份验证
ls -la backups/$(date +%Y%m%d)

# Grafana 健康
curl -s http://localhost:3000/api/health

# 看板全量导入 (如果手动导入)
ls docker/grafana/provisioning/dashboards/kb-*.json
```

## 签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 开发负责人 | | | |
| 运维负责人 | | | |
| 业务验收人 | | | |

---

> 所有复选框打钩后，方可执行上线操作。
