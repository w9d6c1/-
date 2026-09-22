# 11号测试 — 日志可观测性 + 部署交付物验收报告

> **验收依据**: `C:\Users\TLD\Desktop\知识库\11号.md`
> **对应阶段**: 开发计划「第六章」日志监控 + 「第七、九章」部署交付
> **验收日期**: YYYY-MM-DD
> **执行人**: _______

---

## 五、日志与可观测性验收

### 5.1 对话全链路日志

| 属性 | 内容 |
|------|------|
| **操作方式** | 抽取1轮对话，按会话ID查询详情 |
| **验收标准** | 包含提问、回答、命中知识ID、单节点耗时、节点输入输出；可完整回溯全流程执行细节 |
| **ChatLog 字段** | thread_id / request_id / question / answer / node_name / node_latency_ms / hit_faq_id / hit_chunk_ids / confidence / faq_hit / transfer_human / sensitive_hit |
| **测试文件** | `tests/integration/test_audit_chain.py` |
| **执行命令** | `docker compose exec backend python -m pytest tests/integration/test_audit_chain.py -v -o 'addopts='` |
| **结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 5.2 安全告警日志

| 属性 | 内容 |
|------|------|
| **操作方式** | 触发1次敏感词命中、1次越权访问 |
| **验收标准** | 安全事件实时记录；高危事件触发管理员通知告警 |
| **SecurityLog 表** | event_type / request_id / detail / severity / created_at |
| **Webhook 通知** | `backend/app/core/notifier.py` — 企微/钉钉 Webhook (WEBHOOK_URL) |
| **手动验证** | 发起含敏感词的对话 → 检查 SecurityLog 表 + Webhook 消息 |
| **结果** | ☐ PASS / ☐ FAIL |
| **SecurityLog 记录数** | _____ |
| **Webhook 通知到达** | ☐ 是 / ☐ 否 / ☐ 未配置 |
| **备注** | ___________ |

### 5.3 监控指标上报

| 属性 | 内容 |
|------|------|
| **操作方式** | 查看 Grafana 监控看板 |
| **验收标准** | 覆盖服务健康、LLM调用、检索性能、业务指标、资源使用五大类指标 |
| **Grafana 看板 (4个)** | `kb-service-overview` / `kb-security-posture` / `kb-knowledge-quality` / `kb-business-insight` |
| **Prometheus 告警规则** | `docker/prometheus/alert.rules.yml` (13条规则) |
| **访问地址** | Grafana: http://localhost:3000 (admin/admin) / Prometheus: http://localhost:9090 |
| **结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 5.4 日志留存规则

| 属性 | 内容 |
|------|------|
| **操作方式** | 查看不同类型日志的存储与清理配置 |
| **验收标准** | 操作日志、安全日志永久留存；对话日志默认180天可配置 |
| **Loki 留存** | `docker/loki/loki-config.yml` — retention_period: 744h (31天) |
| **Prometheus 留存** | `docker-compose.yml` — --storage.tsdb.retention.time=30d |
| **MySQL ChatLog 清理** | `backend/app/core/retention.py` — 每24h清理过期 ChatLog |
| **环境变量** | `CHAT_LOG_RETENTION_DAYS=180` |
| **结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

---

## 六、部署与交付物验收

### 6.1 容器化一键部署

| 属性 | 内容 |
|------|------|
| **操作方式** | 执行 `docker compose up -d` 启动全服务 |
| **验收标准** | 所有服务正常启动、健康检查通过；无需额外手动配置环境 |
| **服务总数** | 14 个 (waf/nginx/backend/frontend/mysql/postgres/redis/es/milvus/etcd/minio/prometheus/grafana/loki/promtail) |
| **健康检查覆盖** | 12/14 (redis/backend/frontend 在 dev compose 中无显式健康检查) |
| **结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | ___________ |

### 6.2 备份机制

| 属性 | 内容 |
|------|------|
| **操作方式** | 手动触发一次 MySQL、MinIO、PostgreSQL 备份 |
| **验收标准** | 备份文件正常生成；可执行恢复验证流程 |
| **备份脚本** | `scripts/backup.sh` |
| **备份文档** | `docs/ops/BACKUP.md` |
| **手动执行** | `bash scripts/backup.sh` |
| **结果** | ☐ PASS / ☐ FAIL |
| **MySQL 备份** | ☐ 文件生成 |
| **PostgreSQL 备份** | ☐ 文件生成 |
| **MinIO 备份** | ☐ 文件生成 |
| **备注** | ___________ |

### 6.3 配置热更新

| 属性 | 内容 |
|------|------|
| **操作方式** | 修改 Prompt 模板、检索参数、阈值配置 |
| **验收标准** | 无需重启服务即可生效；支持秒级回滚 |
| **API 端点** | `POST /api/admin/config/reload` |
| **实现范围** | 禁答词模式 + 敏感词模式运行时重载 |
| **手动验证** | 在管理后台添加禁答词 → 调用 reload 端点 → 新的禁答词生效 |
| **结果** | ☐ PASS / ☐ FAIL |
| **实际表现** | ___________ |
| **备注** | Prompt 模板修改仍需重启；热更新目前覆盖禁答词/敏感词重载 |

### 6.4 交付物完整性核对

| # | 交付物 | 路径 | 状态 |
|---|--------|------|------|
| 1 | 知识库管理后台源码 | `backend/` | ☐ |
| 2 | AI 智能体服务源码 | `backend/app/agents/` | ☐ |
| 3 | 数据库设计文档 | `docker/mysql/init/01-schema.sql` (296行DDL) | ☐ |
| 4 | API 接口文档 | FastAPI 自动 OpenAPI → `/docs` | ☐ |
| 5 | LangGraph 节点说明文档 | `docs/LANGGRAPH_NODES.md` | ☐ |
| 6 | 系统架构图 | `docs/ARCHITECTURE.md` (Mermaid) | ☐ |
| 7 | 部署操作手册 | `docs/ops/STARTUP.md` | ☐ |
| 8 | 运维 SOP | `docs/ops/TROUBLESHOOTING.md` + OPTIMIZATION.md + MONITORING.md | ☐ |
| 9 | 备份恢复手册 | `docs/ops/BACKUP.md` | ☐ |
| 10 | 测试报告 | `docs/ACCEPTANCE.md` + ACCEPTANCE_REPORT_AI.md + ACCEPTANCE_REPORT_SECURITY.md | ☐ |
| 11 | 安全审计报告 | `docs/ACCEPTANCE_REPORT_SECURITY.md` | ☐ |
| 12 | 性能基准报告 | `backend/tests/performance/test_bench.py` (339行, 13 benchmarks) | ☐ |
| 13 | Prometheus 告警规则 | `docker/prometheus/alert.rules.yml` (13条规则) | ☐ |
| 14 | Grafana 看板 JSON | `docker/grafana/provisioning/dashboards/kb-*.json` (4个) | ☐ |
| 15 | 知识库导入模板 | `backend/app/scripts/import_seed_data.py` | ☐ |

**总计**: __ / 15 项齐全

---

## 汇总

| # | 检查项 | 结果 | 类型 |
|---|--------|------|------|
| 1 | 对话全链路日志 | ☐ | 自动化 (测试) |
| 2 | 安全告警日志 | ☐ | 半自动 (代码 + 手动验证) |
| 3 | 监控指标上报 | ☐ | 自动化 (文件检查) |
| 4 | 日志留存规则 | ☐ | 自动化 (代码检查) |
| 5 | 容器化一键部署 | ☐ | 自动化 (Docker检查) |
| 6 | 备份机制 | ☐ | 半自动 (文件 + 手动执行) |
| 7 | 配置热更新 | ☐ | 半自动 (代码 + 手动触发) |
| 8 | 交付物完整性 | ☐ | 自动化 (文件检查) |

**总计**: __ / 8 项通过

## 执行记录

| 项目 | 内容 |
|------|------|
| 执行时间 | ___________ |
| 完成时间 | ___________ |
| 总耗时 | ___________ |
| 环境状态 | Docker: ☐ 运行中 / ☐ 已停止 |

---

> 本报告模板对应 11号.md 全部 8 个检查项。自动执行: `scripts\run_acceptance_obs.ps1`
