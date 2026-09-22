# 性能压测与容量基线摸底 — 测试用例

> **版本:** v1.0  
> **日期:** 2026-07-21  
> **目标:** 摸清 FAQ 场景（100QPS）和 RAG 长文档场景（20QPS）的性能天花板，定位瓶颈，建立运维告警基线  

---

## 目录

1. [测试环境与前置条件](#1-测试环境与前置条件)
2. [用例总览](#2-用例总览)
3. [专项一：FAQ 场景基准压测 — 目标 100QPS](#3-专项一faq-场景基准压测--目标-100qps)
4. [专项二：RAG 长文档场景基准压测 — 目标 20QPS](#4-专项二rag-长文档场景基准压测--目标-20qps)
5. [专项三：三大瓶颈定位](#5-专项三三大瓶颈定位)
6. [专项四：资源基线采集与告警阈值](#6-专项四资源基线采集与告警阈值)
7. [测试执行计划](#7-测试执行计划)
8. [验收标准](#8-验收标准)

---

## 1. 测试环境与前置条件

### 1.1 服务器配置

| 资源 | 配置 |
|------|------|
| CPU | 记录 `nproc` 输出 |
| 内存 | Docker Desktop 分配 7.3GB（开发机） |
| 磁盘 | SSD / HDD |
| 网络 | 内网 / 公网（SiliconFlow API 依赖公网） |

### 1.2 被测服务拓扑

```
Nginx (443) → WAF (ModSecurity, 8080) → Backend (uvicorn, 8000)
                                            ├── MySQL 8.0 (3306)
                                            ├── PostgreSQL 16 (5432, Checkpoint)
                                            ├── Redis 7 (6379)
                                            ├── Elasticsearch 8.15 (9200)
                                            └── Milvus 2.4 (19530)

外部依赖: SiliconFlow API (Embedding + Reranker + LLM)
```

### 1.3 数据准备

- [ ] `coll_public` 向量 ≥ 500 条（覆盖常见 FAQ 场景）
- [ ] `coll_customer` 向量 ≥ 300 条
- [ ] `coll_internal` 向量 ≥ 386 条
- [ ] ES `idx_bm25_public` 文档 ≥ 50 篇（含长文档 ≥ 5KB 各 5 篇）
- [ ] FAQ 条目 ≥ 100 条（customer scope）
- [ ] SiliconFlow API Key 有效，配额 ≥ 100K tokens

### 1.4 监控就绪

- [ ] Docker Stats 可采集：`docker stats --no-stream`
- [ ] Backend 日志可采集：`docker logs kb-backend --tail`
- [ ] Milvus 指标端点：`curl http://localhost:9091/healthz`
- [ ] ES 集群状态：`curl http://localhost:9200/_cluster/health`
- [ ] 压测工具：Python `asyncio` + `httpx`，或 `wrk` / `locust`

---

## 2. 用例总览

| 专项 | 用例数 | 目标 QPS | 预估耗时 | 优先级 |
|------|--------|----------|----------|--------|
| 专项一：FAQ 场景基准压测 | 8 | 100 QPS | 30 min | 🔴 CRITICAL |
| 专项二：RAG 长文档场景基准压测 | 8 | 20 QPS | 40 min | 🔴 CRITICAL |
| 专项三：三大瓶颈定位 | 9 | — | 30 min | 🟡 HIGH |
| 专项四：资源基线采集 | 6 | — | 20 min | 🟡 HIGH |
| **合计** | **31** | | **~120 min** | |

---

## 3. 专项一：FAQ 场景基准压测 — 目标 100QPS

### 场景定义

FAQ 链路：`validate → auth → route → faq → output`，无 LLM 调用或仅润色（≤ 150 字），走 Redis 缓存 + Milvus 向量匹配。

### PF-FAQ-001: 单用户 FAQ 基准延迟

| 项目 | 内容 |
|------|------|
| **前置条件** | FAQ 向量库 100 条已缓存 |
| **压测方法** | 单线程串行发送 100 次 FAQ 查询 |
| **请求** | `POST /api/agent/customer/chat` `{"message": "特莱顿电渗透是什么", "scope": "customer"}` |
| **采集指标** | P50、P95、P99 延迟，最小/最大延迟 |
| **通过标准** | P50 ≤ 500ms，P95 ≤ 1s |

### PF-FAQ-002: 10 并发 FAQ 吞吐

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | `asyncio.gather` 10 并发，持续 30 秒 |
| **采集指标** | QPS、P50/P95/P99、错误率 |
| **通过标准** | QPS ≥ 10，错误率 = 0%，P95 ≤ 1.5s |

### PF-FAQ-003: 50 并发 FAQ 吞吐 — 接近目标

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 50 并发，持续 60 秒 |
| **采集指标** | QPS、P50/P95/P99、错误率 |
| **通过标准** | QPS ≥ 50，错误率 ≤ 1%，P95 ≤ 2s |

### PF-FAQ-004: 100 并发 FAQ 吞吐 — 目标线

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 100 并发，持续 60 秒 |
| **采集指标** | QPS、P50/P95/P99、错误率 |
| **通过标准** | QPS ≥ 100，错误率 ≤ 5%，P95 ≤ 3s |

### PF-FAQ-005: 150 并发 FAQ 探顶

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 150 并发，持续 30 秒 |
| **采集指标** | QPS、错误率、是否出现 502/503、CPU/内存 |
| **通过标准** | 记录极限 QPS 和首个 5xx 出现时的并发数 |

### PF-FAQ-006: FAQ 缓存命中率压测

| 项目 | 内容 |
|------|------|
| **前置条件** | Redis 缓存已预热 |
| **压测方法** | 发送 200 条查询（100 条热 key + 100 条冷 key） |
| **采集指标** | 缓存命中率、命中/未命中 P95 |
| **通过标准** | 热 key 命中率 ≥ 90%，命中 P95 ≤ 100ms |

### PF-FAQ-007: FAQ 持续 5 分钟稳定性

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 50 并发持续 5 分钟 |
| **采集指标** | QPS 趋势、延迟趋势、内存趋势 |
| **通过标准** | QPS 波动 ≤ ±10%，内存无持续增长（无泄漏），30s 平均延迟不递增 |

### PF-FAQ-008: FAQ 冷启动压测

| 项目 | 内容 |
|------|------|
| **前置条件** | Redis 缓存清空，FAQ 向量未加载 |
| **压测方法** | 10 并发初始请求 |
| **采集指标** | 首请求 P95（含向量加载 + 缓存回填） |
| **通过标准** | 首请求 P95 ≤ 3s（含 Milvus load），后续请求回归正常 |

---

## 4. 专项二：RAG 长文档场景基准压测 — 目标 20QPS

### 场景定义

RAG 全链路：`validate → auth → rewrite → route → retrieve → tools → context → generate → output`，含 Milvus + ES 混合检索 + Reranker 重排 + LLM 生成（500 字），非流式。

### PF-RAG-001: 单次 RAG 全链路基准延迟

| 项目 | 内容 |
|------|------|
| **前置条件** | ES + Milvus 含 50 篇文档，SiliconFlow API 正常 |
| **压测方法** | 单线程串行 20 次 RAG 查询 |
| **请求** | `POST /api/agent/internal/chat` `{"message": "公司年度考核制度的具体流程是什么？请详细说明", "scope": "internal"}` |
| **采集指标** | 全链路 P50/P95/P99，分阶段：检索耗时 / Reranker 耗时 / LLM 首 Token / LLM 总耗时 |
| **通过标准** | P95 ≤ 30s，检索 + Reranker P95 ≤ 3s，LLM 首 Token P95 ≤ 3s |

### PF-RAG-002: 5 并发 RAG 吞吐

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 5 并发，持续 60 秒 |
| **采集指标** | QPS、P50/P95/P99、错误率 |
| **通过标准** | QPS ≥ 2，错误率 ≤ 5%，P95 ≤ 35s |

### PF-RAG-003: 10 并发 RAG 吞吐 — 中期目标

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 10 并发，持续 60 秒 |
| **采集指标** | QPS、P50/P95/P99、错误率、SiliconFlow API 429 次数 |
| **通过标准** | QPS ≥ 5，错误率 ≤ 10%，不触发 API 限流熔断 |

### PF-RAG-004: 20 并发 RAG 吞吐 — 目标线

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 20 并发，持续 60 秒 |
| **采集指标** | QPS、P50/P95/P99、错误率、超时率 |
| **通过标准** | QPS ≥ 10（考虑 LLM 耗时瓶颈），记录实际值 |

### PF-RAG-005: 30 并发 RAG 探顶

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **压测方法** | 30 并发，持续 30 秒 |
| **采集指标** | 极限 QPS、首个 502/504 出现时机、SiliconFlow 429 频率 |
| **通过标准** | 记录系统天花板：单实例最大并发请求数 + LLM API 限流阈值 |

### PF-RAG-006: 长文档检索精度压测

| 项目 | 内容 |
|------|------|
| **前置条件** | ES 含 10 篇 ≥ 10KB 的长文档 |
| **压测方法** | 对每个长文档发送 3 个相关查询 |
| **采集指标** | 检索耗时、Top-5 命中率、Reranker 耗时 P95 |
| **通过标准** | 长文档检索耗时 ≤ 标准文档 1.5 倍，Top-5 命中率 ≥ 70% |

### PF-RAG-007: 流式 RAG 场景基准

| 项目 | 内容 |
|------|------|
| **前置条件** | SSE 端点正常 |
| **压测方法** | `POST /api/agent/internal/chat/stream` 10 并发 |
| **采集指标** | 首 Token 延迟 P95、done 事件完整率、连接中断率 |
| **通过标准** | 首 Token P95 ≤ 2s，done 事件率 = 100% |

### PF-RAG-008: 30 分钟长时间浸泡

| 项目 | 内容 |
|------|------|
| **前置条件** | 系统稳定运行 |
| **压测方法** | 5 并发 RAG 持续 30 分钟，每 5 分钟记录一次指标 |
| **采集指标** | 延迟趋势、CPU/内存趋势、Milvus/ES 响应趋势、LLM API 延迟趋势 |
| **通过标准** | 延迟波动 ≤ ±20%，内存无持续增长，无服务重启 |

---

## 5. 专项三：三大瓶颈定位

### 5.1 Reranker 推理耗时瓶颈 — PF-BOT-001 ~ 003

#### PF-BOT-001: Reranker 单次调用耗时

| 项目 | 内容 |
|------|------|
| **前置条件** | SiliconFlow API 正常 |
| **测试步骤** | 构造 10/20/50 条候选文档，记录 rerank 调用耗时 |
| **采集指标** | 10 候选 P95、20 候选 P95、50 候选 P95 |
| **通过标准** | 10 条 ≤ 500ms，20 条 ≤ 800ms，50 条 ≤ 1.5s |

#### PF-BOT-002: Reranker 降级时延影响

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **测试步骤** | Mock SiliconFlow Reranker 超时，观察降级耗时 |
| **采集指标** | 降级触发时间、降级后排序耗时 |
| **通过标准** | 降级触发 ≤ 30s（timeout），降级后 ≤ 100ms |

#### PF-BOT-003: Reranker 缓存优化效果

| 项目 | 内容 |
|------|------|
| **前置条件** | 同一 query + 同一候选集 |
| **测试步骤** | 连续调用 5 次相同 rerank，记录耗时变化 |
| **采集指标** | 首次 vs 第 5 次耗时 |
| **通过标准** | 无缓存时记录原始耗时（作为是否需加缓存的决策依据） |

### 5.2 Milvus 查询耗时瓶颈 — PF-BOT-004 ~ 006

#### PF-BOT-004: Dense Search 基准耗时

| 项目 | 内容 |
|------|------|
| **前置条件** | coll_public 已加载 |
| **测试步骤** | 执行 50 次 `dense_search`，记录耗时分布 |
| **采集指标** | P50/P95/P99，Top-K=10 vs Top-K=50 |
| **通过标准** | P95 ≤ 200ms（500 条向量），P95 ≤ 500ms（5000 条） |

#### PF-BOT-005: Collection Load 耗时

| 项目 | 内容 |
|------|------|
| **前置条件** | coll_internal 含 386 条实体 |
| **测试步骤** | `coll.load()` 计时，重复 5 次 |
| **采集指标** | Min/Max/Avg load 时间 |
| **通过标准** | Avg ≤ 5s（已知问题：偶尔超时 10s，需确认频率） |

#### PF-BOT-006: 混合检索 Dense + BM25 对比

| 项目 | 内容 |
|------|------|
| **前置条件** | ES + Milvus 同时可用 |
| **测试步骤** | 同一 query 分别走 Dense Only / BM25 Only / Hybrid + RRF，记录耗时 |
| **采集指标** | 各路径 P95、RRF 融合额外耗时 |
| **通过标准** | Hybrid ≤ Dense + BM25 + 100ms，RRF 融合 ≤ 50ms |

### 5.3 LLM 首 Token 延迟瓶颈 — PF-BOT-007 ~ 009

#### PF-BOT-007: DeepSeek 首 Token 延迟

| 项目 | 内容 |
|------|------|
| **前置条件** | DeepSeek API 正常 |
| **测试步骤** | 发送 20 条不同长度的 prompt（短 200 token / 中 1000 token / 长 3000 token），记录首 Token |
| **采集指标** | 短 prompt P95、中 prompt P95、长 prompt P95 |
| **通过标准** | 短 ≤ 1s，中 ≤ 2s，长 ≤ 4s |

#### PF-BOT-008: LLM Token 生成速率

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **测试步骤** | 记录流式生成 token 速率（tokens/s） |
| **采集指标** | 平均 tokens/s、P50/P95 |
| **通过标准** | 平均 ≥ 30 tokens/s |

#### PF-BOT-009: LLM API 限流触发阈值

| 项目 | 内容 |
|------|------|
| **前置条件** | 同上 |
| **测试步骤** | 逐步增加并发 LLM 调用，直到触发 429 |
| **采集指标** | 触发 429 的并发数、429 恢复时间 |
| **通过标准** | 记录 DeepSeek 免费/付费 tier 的限流阈值作为并发上限 |

---

## 6. 专项四：资源基线采集与告警阈值

### PF-RES-001: 空载资源基线

| 项目 | 内容 |
|------|------|
| **前置条件** | 所有容器启动完成，无请求负载 |
| **采集方法** | `docker stats --no-stream` |
| **采集指标** | 各容器 CPU%、MEM USAGE、MEM%、NET I/O、BLOCK I/O |
| **记录内容** | MySQL / PostgreSQL / Redis / ES / Milvus / Backend / Nginx / WAF |

### PF-RES-002: 10 QPS 资源水位

| 项目 | 内容 |
|------|------|
| **前置条件** | 混合 FAQ + RAG 负载达到 10 QPS |
| **采集方法** | `docker stats` 每 5 秒采样，持续 60 秒 |
| **采集指标** | 同 PF-RES-001 |
| **通过标准** | Backend CPU ≤ 60%，内存增长 ≤ 50MB |

### PF-RES-003: 20 QPS 资源水位

| 项目 | 内容 |
|------|------|
| **前置条件** | 混合 FAQ + RAG 负载达到 20 QPS |
| **采集方法** | `docker stats` 每 5 秒采样，持续 60 秒 |
| **采集指标** | 同 PF-RES-001 |
| **通过标准** | Backend CPU ≤ 80%，内存增长 ≤ 100MB，无 OOM 风险 |

### PF-RES-004: 极限 QPS 资源水位

| 项目 | 内容 |
|------|------|
| **前置条件** | 负载增至首个 5xx 出现 |
| **采集方法** | `docker stats` 实时记录 |
| **采集指标** | 极限 QPS、瓶颈容器名称、瓶颈资源类型（CPU/MEM/IO） |
| **通过标准** | 记录天花板数据，作为扩容决策依据 |

### PF-RES-005: Milvus 资源开销

| 项目 | 内容 |
|------|------|
| **前置条件** | 3 个 Collection（coll_public/coll_internal/coll_customer）已加载 |
| **采集方法** | `docker stats kb-milvus` + `curl http://localhost:9091/metrics` |
| **采集指标** | 内存占用、搜索 QPS、load 耗时趋势 |
| **通过标准** | 空载内存 ≤ 1GB，搜索时内存增长 ≤ 200MB |

### PF-RES-006: ES 资源开销

| 项目 | 内容 |
|------|------|
| **前置条件** | 3 个 Index，≥ 100 条文档 |
| **采集方法** | `curl http://localhost:9200/_nodes/stats` |
| **采集指标** | Heap 使用率、搜索 QPS、索引速率 |
| **通过标准** | Heap 使用率 ≤ 75%，搜索 QPS 不降级 |

---

## 7. 测试执行计划

### 7.1 执行顺序

| 阶段 | 内容 | 用例 | 耗时 | 依赖 |
|------|------|------|------|------|
| **Phase 0** | 资源基线空载采集 | PF-RES-001 | 5 min | 系统就绪 |
| **Phase 1** | FAQ 基准压测 | PF-FAQ-001 ~ 005 | 20 min | Phase 0 |
| **Phase 2** | FAQ 稳定性 | PF-FAQ-006 ~ 008 | 10 min | Phase 1 |
| **Phase 3** | RAG 基准压测 | PF-RAG-001 ~ 005 | 30 min | Phase 0 |
| **Phase 4** | RAG 稳定性 | PF-RAG-006 ~ 008 | 10 min | Phase 3 |
| **Phase 5** | 瓶颈定位 | PF-BOT-001 ~ 009 | 30 min | Phase 3 |
| **Phase 6** | 负载资源采集 | PF-RES-002 ~ 006 | 15 min | Phase 1~5 |

### 7.2 压测脚本框架

```python
# tests/performance/test_stress.py — 新增
import asyncio
import time
import statistics
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

# FAQ 并发压测
async def _faq_worker(client, query, results: list):
    t0 = time.perf_counter()
    try:
        resp = await client.post("/api/agent/customer/chat", json={
            "message": query,
        })
        elapsed = time.perf_counter() - t0
        results.append({"status": resp.status_code, "elapsed": elapsed})
    except Exception as e:
        results.append({"status": 0, "elapsed": time.perf_counter() - t0, "error": str(e)})

async def _run_concurrent(client, concurrency, duration_sec):
    results = []
    queries = [f"问题{i}关于特莱顿" for i in range(concurrency * 10)]
    t_end = time.perf_counter() + duration_sec
    idx = 0

    async def _runner():
        nonlocal idx
        while time.perf_counter() < t_end:
            q = queries[idx % len(queries)]
            idx += 1
            await _faq_worker(client, q, results)

    tasks = [_runner() for _ in range(concurrency)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results

# 资源采集
async def _collect_docker_stats(duration_sec: int, interval_sec: float = 5.0):
    """采集 docker stats 并写 CSV"""
    ...
```

### 7.3 快速命令

```bash
# Phase 1-2: FAQ 压测（需 Docker 内运行）
docker exec kb-backend pytest tests/performance/test_stress.py::TestFAQStress -v

# Phase 3-4: RAG 压测
docker exec kb-backend pytest tests/performance/test_stress.py::TestRAGStress -v

# Phase 5: 瓶颈定位
docker exec kb-backend pytest tests/performance/test_stress.py::TestBottleneck -v

# 资源采集（PowerShell）
.\scripts\collect_stats.ps1 -DurationSec 300 -IntervalSec 5 -OutputFile "baseline.csv"
```

---

## 8. 验收标准

### 8.1 量化指标

| 指标 | FAQ 目标 | RAG 目标 | 告警黄线 | 告警红线 |
|------|----------|----------|----------|----------|
| QPS | ≥ 100 | ≥ 10 (20 并发) | < 60% 目标 | < 30% 目标 |
| P95 延迟 | ≤ 3s | ≤ 35s | > 1.5x 基线 | > 3x 基线 |
| 错误率 | ≤ 5% | ≤ 10% | > 2% | > 10% |
| Backend CPU | ≤ 80% | ≤ 80% | > 70% | > 90% |
| Backend MEM | ≤ 3.5GB | ≤ 3.5GB | > 3GB | > 4GB |
| Milvus MEM | ≤ 1.2GB | ≤ 1.2GB | > 800MB | > 1.5GB |
| LLM 首 Token | ≤ 1.5s | ≤ 3s | > 2s | > 5s |
| Reranker P95 | ≤ 1s | ≤ 1.5s | > 1.5s | > 3s |
| Dense Search P95 | ≤ 200ms | ≤ 500ms | > 300ms | > 1s |

### 8.2 准出判定

| 结果 | 判定 |
|------|------|
| FAQ 100 QPS + RAG 10 QPS 达标 + 无内存泄漏 | 🟢 **通过** |
| 任一场景 P95 超过红线，但瓶颈可明确定位 | 🟡 **有条件通过**（记录优化 TODO） |
| 出现 OOM / 服务崩溃 / API 限流不可恢复 | 🔴 **BLOCKED** |

### 8.3 产出一览

| 产出物 | 文件名 | 内容 |
|--------|--------|------|
| 压测报告 | `docs/ops/PERF_BENCHMARK_20260721.md` | 全部指标、图表、瓶颈分析 |
| 资源基线 CSV | `docs/ops/baseline_20260721.csv` | 空载/10QPS/20QPS 资源数据 |
| 告警阈值配置 | `docs/ops/alerting_thresholds.md` | 黄线/红线阈值表 |
| 瓶颈优化 TODO | `docs/ops/bottleneck_findings.md` | Reranker / Milvus / LLM 优化建议 |
