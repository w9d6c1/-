# 企业微信接入配置日志

> 记录日期:2026-07-09
> 关联文档:`多渠道接入规划.md`、`操作指南.md`

---

## 状态总览

| 阶段 | 状态 |
|------|------|
| 代码模块开发 | ✅ 完成(33 单元测试通过) |
| `.env` 配置(前 3 项) | ✅ 已写入 |
| `.env` 配置(Token/AESKey) | ⏳ 待第二步生成后回填 |
| 回调 URL 验证 | ⏳ 需公网环境(当前仅内网) |
| 端到端测试 | ⏳ |

---

## 已填写的环境变量(`.env`)

| 变量 | 值 | 来源 |
|------|-----|------|
| `WECOM_CORP_ID` | `<REDACTED>` | 企微后台 → 我的企业 → 企业ID |
| `WECOM_AGENT_ID` | `<REDACTED>` | 企微后台 → 应用详情 |
| `WECOM_SECRET` | `<REDACTED>` | 企微后台 → 应用详情 |
| `WECOM_DEFAULT_ROLE` | `operator` | 默认值 |
| `WECOM_TOKEN` | *(空)* | ⏳ |
| `WECOM_AES_KEY` | *(空)* | ⏳ |

---

## 待完成步骤

### 第二步:生成并回填 Token / EncodingAESKey
1. 进企微后台 → 应用管理 → 对应 AgentId → 接收消息 → 设置API接收
2. 点"随机生成"分别生成 Token 和 EncodingAESKey,记录下来
3. 通知开发者回填到 `.env` 的 `WECOM_TOKEN` / `WECOM_AES_KEY`
4. 加解密方式:**安全模式**

### 第三步:解决公网访问(当前阻塞项)
- **现状**:服务仅在内网运行,企微服务器无法访问回调地址
- **方案 A(测试)**:内网穿透工具(cpolar/花生壳),映射本地端口到公网 HTTPS
- **方案 B(生产)**:云服务器部署 + 域名 + Let's Encrypt 证书

### 第四步:URL 验证
1. 公网就绪后,重启后端:`docker compose -f docker-compose.prod.yml up -d --build backend`
2. 在企微后台「设置API接收」点保存,触发 GET 验证
3. 验证通过后即可测试

### 第五步:生产安全加固
- ⚠️ `WECOM_SECRET` 已在对话中明文暴露,上线后需在企微后台重置 Secret
- 修改 `.env` 中 `DEBUG=false`、`LOG_LEVEL=INFO`

---

## 新增/改动的文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/app/channels/__init__.py` | 新增 | 渠道适配层包 |
| `backend/app/channels/wecom/__init__.py` | 新增 | 企微渠道包 |
| `backend/app/channels/wecom/crypto.py` | 新增 | 消息加解密 + XXE 防护 |
| `backend/app/channels/wecom/client.py` | 新增 | access_token 缓存 + 主动发消息 |
| `backend/app/channels/wecom/service.py` | 新增 | 消息处理 + 对话审计 + 异步回推 |
| `backend/app/channels/wecom/router.py` | 新增 | GET/POST 回调路由 |
| `backend/app/services/identity_service.py` | 新增 | 渠道身份映射 |
| `backend/tests/unit/test_wecom_crypto.py` | 新增 | 加解密测试(18 cases) |
| `backend/tests/unit/test_wecom_service.py` | 新增 | 服务/客户端/XXE 测试(15 cases) |
| `backend/tests/unit/test_identity_service.py` | 新增 | 身份映射测试 |
| `backend/app/core/config.py` | 改动 | +6 个企微配置字段 |
| `backend/app/api/router.py` | 改动 | 挂载 `/api/channels` 路由 |
| `.env` | 改动 | +企微配置块 |
| `.env.example` | 改动 | +企微变量模板 |
| `backend/requirements.txt` | 改动 | +cryptography、+defusedxml |
| `docs/ops/多渠道接入规划.md` | 新增 | 四渠道架构规划 |
| `docs/ops/wecom-config-log.md` | 新增 | 本文件 |

---

## 回调 URL

```
https://<公网域名>/api/channels/wecom/callback
```

> 域名待定,取决于最终选择的公网方案(A 或 B)。
