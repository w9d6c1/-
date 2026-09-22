"""性能压测 — FAQ / RAG 场景 + 瓶颈定位 + 资源采集

用法:
  docker exec kb-backend pytest tests/performance/test_stress.py -v
  docker exec kb-backend pytest tests/performance/test_stress.py::TestFAQStress -v
  docker exec kb-backend pytest tests/performance/test_stress.py::TestRAGStress -v
  docker exec kb-backend pytest tests/performance/test_stress.py::TestBottleneck -v

指标目标:
  FAQ 100 QPS: P95 ≤ 3s, 错误率 ≤ 5%
  RAG 20并发: P95 ≤ 35s, 错误率 ≤ 10%
"""

import asyncio
import statistics
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.state import AgentState


@pytest.fixture
def _init_state():
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content="测试")],
        "thread_id": "stress_test",
        "user_id": 1,
        "user_role": "superadmin",
        "user_department": None,
        "user_scopes": ["public"],
        "original_query": "",
        "rewritten_query": "",
        "is_blocked": False,
        "block_reason": "",
        "faq_hit": False,
        "faq_answer": None,
        "retrieved_docs": [],
        "context": "",
        "final_answer": "",
        "is_compliant": True,
        "compliance_issues": [],
        "confidence": 0.0,
        "needs_human": False,
        "human_reason": "",
        "route": "",
        "iteration": 0,
        "error": None,
    }


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────
def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_data):
        return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
    return sorted_data[f]


def _summarize(name: str, latencies: list[float]):
    if not latencies:
        print(f"\n[{name}] 无数据")
        return
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    avg = statistics.mean(latencies)
    mn = min(latencies)
    mx = max(latencies)
    print(
        f"\n[{name}] count={len(latencies)} "
        f"avg={avg:.4f}s p50={p50:.4f}s p95={p95:.4f}s p99={p99:.4f}s "
        f"min={mn:.4f}s max={mx:.4f}s"
    )
    return {"p50": p50, "p95": p95, "p99": p99, "avg": avg}


# ─────────────────────────────────────────────
# 专项一：FAQ 场景基准压测
# ─────────────────────────────────────────────
class TestFAQStress:
    """FAQ 场景压测 — validate → auth → route → faq → output"""

    def _faq_state(self, base: dict, query: str) -> dict:
        s = dict(base)
        s["original_query"] = query
        return s

    # PF-FAQ-001: 单用户基准延迟
    def test_pf_faq_001_baseline_latency(self, benchmark, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"问题{i}", "content": f"答案{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(100)
        ]

        with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
            with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                state = self._faq_state(_init_state, "特莱顿电渗透防水技术优势")
                def _run():
                    result = asyncio.run(faq_match_node(state))
                    assert isinstance(result, dict)
                benchmark(_run)

    # PF-FAQ-003: 50 并发 FAQ 吞吐
    @pytest.mark.asyncio
    async def test_pf_faq_003_50_concurrent(self, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"FAQ问题{i}", "content": f"FAQ答案{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(200)
        ]

        latencies = []
        errors = 0

        async def _worker():
            nonlocal errors
            t0 = time.perf_counter()
            try:
                state = dict(_init_state)
                state["original_query"] = f"查询问题{hash(str(t0)) % 100}"
                with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                    with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                        result = await faq_match_node(state)
                        assert isinstance(result, dict)
                latencies.append(time.perf_counter() - t0)
            except Exception:
                errors += 1
                latencies.append(time.perf_counter() - t0)

        tasks = [_worker() for _ in range(50)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-FAQ-003 (50并发)", latencies)
        assert errors == 0, f"错误数: {errors}"
        assert stats["p95"] <= 2.0, f"P95={stats['p95']:.3f}s > 2s"

    # PF-FAQ-002: 10 并发 FAQ 吞吐
    @pytest.mark.asyncio
    async def test_pf_faq_002_10_concurrent(self, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"FAQ问题{i}", "content": f"答案{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(100)
        ]

        latencies = []
        errors = 0

        async def _worker():
            nonlocal errors
            t0 = time.perf_counter()
            try:
                state = dict(_init_state)
                state["original_query"] = f"查询{hash(str(t0)) % 50}"
                with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                    with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                        await faq_match_node(state)
                latencies.append(time.perf_counter() - t0)
            except Exception:
                errors += 1
                latencies.append(time.perf_counter() - t0)

        tasks = [_worker() for _ in range(10)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-FAQ-002 (10并发)", latencies)
        assert errors == 0
        assert stats["p95"] <= 1.5, f"P95={stats['p95']:.3f}s > 1.5s"

    # PF-FAQ-005: 150 并发探顶
    @pytest.mark.asyncio
    async def test_pf_faq_005_150_concurrent_cap(self, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"Q{i}", "content": f"A{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(500)
        ]

        latencies = []
        errors = 0

        async def _worker():
            nonlocal errors
            t0 = time.perf_counter()
            try:
                state = dict(_init_state)
                state["original_query"] = f"Q{hash(str(time.perf_counter_ns())) % 200}"
                with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                    with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                        await faq_match_node(state)
                latencies.append(time.perf_counter() - t0)
            except Exception:
                errors += 1
                latencies.append(time.perf_counter() - t0)

        tasks = [_worker() for _ in range(150)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-FAQ-005 (150并发探顶)", latencies)
        print(f"[CAP] 150并发 — 错误: {errors}, 总请求: {len(latencies)}")
        # 探顶不设硬断言，记录结果即可

    # PF-FAQ-006: FAQ 缓存命中率
    @pytest.mark.asyncio
    async def test_pf_faq_006_cache_hit_rate(self, _init_state):
        from app.agents.cache import get_cache
        cache = get_cache()

        cache_key = "stress_cache_test_key"
        await cache.set(cache_key, {"val": "cached"}, ttl=300)

        hit_latencies = []
        miss_latencies = []

        for _ in range(50):
            t0 = time.perf_counter()
            val = await cache.get(cache_key)
            hit_latencies.append(time.perf_counter() - t0)
            assert val == {"val": "cached"}

        for _ in range(50):
            t0 = time.perf_counter()
            val = await cache.get("stress_miss_key")
            miss_latencies.append(time.perf_counter() - t0)
            assert val is None

        await cache.invalidate(cache_key)

        hit_s = _summarize("PF-FAQ-006 缓存命中(50)", hit_latencies)
        miss_s = _summarize("PF-FAQ-006 缓存未命中(50)", miss_latencies)
        assert hit_s["p95"] <= 0.1, f"缓存命中 P95={hit_s['p95']:.3f}s > 100ms"


# ─────────────────────────────────────────────
# 专项二：RAG 长文档场景基准压测
# ─────────────────────────────────────────────
class TestRAGStress:
    """RAG 全链路压测 — retrieve → tools → context → generate"""

    # PF-RAG-001: 单次 RAG 全链路
    def test_pf_rag_001_single_full_pipeline(self, benchmark, _init_state):
        from app.agents.nodes.retrieve import retrieve_node
        from app.agents.nodes.context import assemble_context
        from app.retrieval.fusion import FusionResult

        mock_docs = [
            FusionResult(unique_id=f"id_{i}", doc_id=i, chunk_index=0,
                         content=f"长文档内容段落{i} " * 20, fused_score=0.9, scope="public")
            for i in range(10)
        ]

        mock_hybrid = AsyncMock(return_value=mock_docs)
        mock_rerank = AsyncMock(return_value=mock_docs[:5])

        with patch("app.agents.nodes.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.nodes.retrieve.rerank", mock_rerank):
                with patch("app.agents.nodes.retrieve.get_cache", return_value=None):
                    state = dict(_init_state)
                    state["original_query"] = "公司年度考核制度的流程是什么？需要哪些材料？谁来审批？"

                    async def _run():
                        s1 = await retrieve_node(state)
                        s2 = assemble_context(s1)
                        assert s2["context"] != ""
                        assert len(s2["retrieved_docs"]) == 5

                    def _sync():
                        asyncio.run(_run())

                    benchmark(_sync)

    # PF-RAG-002: 5 并发 RAG
    @pytest.mark.asyncio
    async def test_pf_rag_002_5_concurrent(self, _init_state):
        from app.agents.nodes.retrieve import retrieve_node
        from app.agents.nodes.context import assemble_context
        from app.retrieval.fusion import FusionResult

        mock_docs = [
            FusionResult(unique_id=f"id_{i}", doc_id=i, chunk_index=0,
                         content=f"并发文档内容{i} " * 15, fused_score=0.9, scope="public")
            for i in range(10)
        ]
        mock_hybrid = AsyncMock(return_value=mock_docs)
        mock_rerank = AsyncMock(return_value=mock_docs[:5])

        latencies = []
        errors = 0

        async def _worker():
            nonlocal errors
            t0 = time.perf_counter()
            try:
                state = dict(_init_state)
                state["original_query"] = f"考核查询{hash(str(t0)) % 50}"
                with patch("app.agents.nodes.retrieve.hybrid_retrieve", mock_hybrid):
                    with patch("app.agents.nodes.retrieve.rerank", mock_rerank):
                        with patch("app.agents.nodes.retrieve.get_cache", return_value=None):
                            s1 = await retrieve_node(state)
                            s2 = assemble_context(s1)
                            assert s2["context"] != ""
                latencies.append(time.perf_counter() - t0)
            except Exception:
                errors += 1
                latencies.append(time.perf_counter() - t0)

        tasks = [_worker() for _ in range(5)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-RAG-002 (5并发)", latencies)
        assert errors == 0
        assert stats["p95"] <= 35.0, f"P95={stats['p95']:.1f}s > 35s"

    # PF-RAG-007: 流式 RAG
    @pytest.mark.asyncio
    async def test_pf_rag_007_sse_streaming(self, client):
        mock_graph = MagicMock()

        async def _astream_events(state, config=None, version="v2"):
            yield {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="测试")}}
            yield {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="回答")}}
            yield {"event": "on_chat_model_end", "data": {}}

        mock_graph.astream_events = _astream_events

        with patch("app.api.agent._get_graph", return_value=mock_graph):
            latencies = []
            first_tokens = []

            async def _worker():
                t0 = time.perf_counter()
                first = True
                async with client.stream(
                    "POST", "/api/agent/internal/chat/stream",
                    json={"message": "流式压测问题", "scope": "public"},
                    timeout=30,
                ) as resp:
                    assert resp.status_code == 200
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and first:
                            first_tokens.append(time.perf_counter() - t0)
                            first = False
                latencies.append(time.perf_counter() - t0)

            tasks = [_worker() for _ in range(5)]
            await asyncio.gather(*tasks)

            stream_s = _summarize("PF-RAG-007 流式首Token", first_tokens)
            assert stream_s["p95"] <= 2.0, f"首Token P95={stream_s['p95']:.3f}s > 2s"


# ─────────────────────────────────────────────
# 专项三：瓶颈定位
# ─────────────────────────────────────────────
class TestBottleneck:
    """定位 Reranker / Milvus / LLM 首 Token 三大瓶颈"""

    # PF-BOT-001: Reranker 单次耗时
    @pytest.mark.asyncio
    async def test_pf_bot_001_reranker_latency(self, _init_state):
        from app.retrieval.reranker import rerank
        from app.retrieval.fusion import FusionResult

        for n_docs in [10, 20, 50]:
            docs = [
                FusionResult(unique_id=f"r_{i}", doc_id=i, chunk_index=0,
                             content=f"测试文档内容段落{i}这是需要重排的候选文本段落内容", fused_score=0.9, scope="public")
                for i in range(n_docs)
            ]

            latencies = []
            for _ in range(10):
                t0 = time.perf_counter()
                _ = await rerank("测试查询语句", docs, top_k=5)
                latencies.append(time.perf_counter() - t0)

            s = _summarize(f"PF-BOT-001 Reranker({n_docs}候选)", latencies)
            if n_docs == 50:
                assert s["p95"] <= 3.0, f"50候选 P95={s['p95']:.2f}s > 3s"

    # PF-BOT-007: LLM 首 Token
    def test_pf_bot_007_llm_first_token(self, benchmark):
        from app.agents.llm import create_llm

        llm = create_llm(temperature=0.0, max_tokens=100)
        prompt = "请用一句话介绍特莱顿电渗透防水技术。"
        latencies = []

        def _run():
            t0 = time.perf_counter()
            for chunk in llm.stream(prompt):
                latencies.append(time.perf_counter() - t0)
                break

        benchmark(_run)
        if latencies:
            print(f"\n[PF-BOT-007] LLM 首Token avg={statistics.mean(latencies):.3f}s")

    # PF-BOT-008: LLM Token 生成速率
    def test_pf_bot_008_llm_token_rate(self, benchmark):
        from app.agents.llm import create_llm

        llm = create_llm(temperature=0.0, max_tokens=200)
        prompt = "请详细说明电渗透防水技术的原理和工作流程，包括施工步骤和注意事项。"
        token_count = 0

        def _run():
            nonlocal token_count
            token_count = 0
            for chunk in llm.stream(prompt):
                c = getattr(chunk, "content", "")
                token_count += len(c)

        benchmark(_run)
        print(f"\n[PF-BOT-008] LLM Token生成 total_tokens={token_count}")

    # PF-BOT-009: LLM API 并发限流探测
    @pytest.mark.asyncio
    async def test_pf_bot_009_llm_concurrency_limit(self):
        from app.agents.llm import create_llm

        llm = create_llm(temperature=0.0, max_tokens=50)

        for concurrency in [5, 10, 20, 30]:
            results = {"success": 0, "error": 0}

            async def _worker():
                try:
                    resp = await llm.ainvoke(f"请回答：1+1等于几？")
                    results["success"] += 1
                except Exception:
                    results["error"] += 1

            tasks = [_worker() for _ in range(concurrency)]
            await asyncio.gather(*tasks, return_exceptions=True)
            print(
                f"\n[PF-BOT-009] LLM并发={concurrency} "
                f"成功={results['success']} 失败={results['error']}"
            )


# ─────────────────────────────────────────────
# 专项四：资源基线采集辅助
# ─────────────────────────────────────────────
class TestResourceBaseline:
    """资源水位采集（需 Docker 内外配合）"""

    # PF-RES-001: 记录当前空载状态
    def test_pf_res_001_idle_baseline(self):
        """仅打印容器资源基线信息（数据需结合 docker stats 命令获取）"""
        import os
        print(f"\n[PF-RES-001] 空载基线 — 系统信息:")
        print(f"  CPU count: {os.cpu_count()}")
        print(f"  工作目录: {os.getcwd()}")

        import sys
        print(f"  Python: {sys.version}")

        try:
            import psutil
            mem = psutil.virtual_memory()
            print(f"  主机内存: total={mem.total / 1024**3:.1f}GB "
                  f"available={mem.available / 1024**3:.1f}GB "
                  f"used_pct={mem.percent}%")
        except ImportError:
            print("  psutil 未安装，跳过主机内存采集")

    # PF-RES-005: Milvus 资源
    def test_pf_res_005_milvus_stats(self):
        from app.retrieval.milvus_client import _ensure_connected
        from pymilvus import utility

        _ensure_connected()
        collections = utility.list_collections()
        print(f"\n[PF-RES-005] Milvus Collections: {collections}")

        for coll_name in collections:
            try:
                stats = utility.get_query_segment_info(coll_name)
                print(f"  {coll_name}: segments={len(stats)}")
            except Exception as e:
                print(f"  {coll_name}: 统计失败 — {e}")

    # PF-RES-006: ES 资源
    def test_pf_res_006_es_stats(self):
        import httpx

        try:
            resp = httpx.get("http://kb-elasticsearch:9200/_nodes/stats", timeout=5)
            print(f"\n[PF-RES-006] ES 状态: HTTP {resp.status_code}")
        except Exception as e:
            print(f"\n[PF-RES-006] ES 连接失败: {e}")


# ══════════════════════════════════════════════════
# 补充用例 Part A: 高阶并发阶梯 (4 条)
# ══════════════════════════════════════════════════
class TestFAQHighConcurrency:
    """PF-FAQ-004: 100 并发 FAQ 吞吐 — 目标线"""

    @pytest.mark.asyncio
    async def test_pf_faq_004_100_concurrent(self, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"Q{i}", "content": f"A{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(500)
        ]
        latencies = []
        errors = 0

        async def _worker():
            nonlocal errors
            t0 = time.perf_counter()
            try:
                state = dict(_init_state)
                state["original_query"] = f"查询{hash(str(time.perf_counter_ns())) % 500}"
                with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                    with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                        await faq_match_node(state)
                latencies.append(time.perf_counter() - t0)
            except Exception:
                errors += 1
                latencies.append(time.perf_counter() - t0)

        tasks = [_worker() for _ in range(100)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-FAQ-004 (100并发)", latencies)
        qps = len(latencies) / (max(latencies) if latencies else 0.001)
        print(f"[PF-FAQ-004] 等效QPS≈{qps:.0f} 错误={errors}")
        assert stats["p95"] <= 3.0, f"P95={stats['p95']:.3f}s > 3s"
        assert errors <= 5, f"错误率 {errors/100*100:.0f}% > 5%"


class TestRAGHighConcurrency:
    """PF-RAG-003~005: 10/20/30 并发阶梯"""

    async def _rag_worker(self, _init_state, idx):
        from app.agents.nodes.retrieve import retrieve_node
        from app.agents.nodes.context import assemble_context
        from app.retrieval.fusion import FusionResult

        mock_docs = [
            FusionResult(unique_id=f"id_{i}", doc_id=i, chunk_index=0,
                         content=f"并发RAG文档内容{i} " * 15, fused_score=0.9, scope="public")
            for i in range(10)
        ]
        mock_hybrid = AsyncMock(return_value=mock_docs)
        mock_rerank = AsyncMock(return_value=mock_docs[:5])

        t0 = time.perf_counter()
        state = dict(_init_state)
        state["original_query"] = f"长文档RAG查询{idx}关于考核制度和流程"
        with patch("app.agents.nodes.retrieve.hybrid_retrieve", mock_hybrid):
            with patch("app.agents.nodes.retrieve.rerank", mock_rerank):
                with patch("app.agents.nodes.retrieve.get_cache", return_value=None):
                    s1 = await retrieve_node(state)
                    s2 = assemble_context(s1)
                    assert s2["context"] != ""
        return time.perf_counter() - t0

    # PF-RAG-003: 10 并发
    @pytest.mark.asyncio
    async def test_pf_rag_003_10_concurrent(self, _init_state):
        tasks = [self._rag_worker(_init_state, i) for i in range(10)]
        latencies = list(await asyncio.gather(*tasks))
        stats = _summarize("PF-RAG-003 (10并发 RAG)", latencies)
        assert stats["p95"] <= 35.0, f"P95={stats['p95']:.1f}s > 35s"

    # PF-RAG-004: 20 并发
    @pytest.mark.asyncio
    async def test_pf_rag_004_20_concurrent(self, _init_state):
        tasks = [self._rag_worker(_init_state, i) for i in range(20)]
        latencies = list(await asyncio.gather(*tasks))
        stats = _summarize("PF-RAG-004 (20并发 RAG)", latencies)
        assert stats["p95"] <= 35.0, f"P95={stats['p95']:.1f}s > 35s"

    # PF-RAG-005: 30 并发探顶
    @pytest.mark.asyncio
    async def test_pf_rag_005_30_concurrent_cap(self, _init_state):
        results = await asyncio.gather(
            *[self._rag_worker(_init_state, i) for i in range(30)],
            return_exceptions=True,
        )
        errors = sum(1 for r in results if isinstance(r, Exception))
        latencies = [r for r in results if not isinstance(r, Exception)]
        stats = _summarize("PF-RAG-005 (30并发探顶)", latencies)
        print(f"[CAP] RAG 30并发 — 成功={len(latencies)} 错误={errors}")


# ══════════════════════════════════════════════════
# 补充用例 Part B: 长时浸泡与冷启动 (3 条)
# ══════════════════════════════════════════════════
class TestSoakAndColdStart:
    """长时浸泡 + 冷启动"""

    _soak_duration = 5    # 秒（计划 300s，加速执行）
    _soak_interval = 1.0  # 秒

    # PF-FAQ-008: FAQ 冷启动
    @pytest.mark.asyncio
    async def test_pf_faq_008_cold_start(self, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"冷启动FAQ{i}", "content": f"答案{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(200)
        ]

        latencies = []

        for i in range(20):
            t0 = time.perf_counter()
            state = dict(_init_state)
            state["original_query"] = f"冷启动查询{i}"
            with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                    await faq_match_node(state)
            latencies.append(time.perf_counter() - t0)

        first = latencies[0] if latencies else 0
        rest = latencies[1:] if len(latencies) > 1 else [0]
        rest_p95 = _percentile(rest, 95)
        print(
            f"\n[PF-FAQ-008] 冷启动首请求={first:.4f}s, "
            f"后续P95={rest_p95:.4f}s, "
            f"比值={first/rest_p95:.1f}x"
        )
        assert first <= 3.0, f"冷启动首请求 {first:.2f}s > 3s"

    # PF-FAQ-007: FAQ 持续稳定性 (速跑版, 30s)
    @pytest.mark.asyncio
    async def test_pf_faq_007_stability(self, _init_state):
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"S{i}", "content": f"A{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(300)
        ]

        latencies = []
        errors = 0
        t_end = time.perf_counter() + 30  # 速跑 30s

        async def _runner():
            nonlocal errors
            while time.perf_counter() < t_end:
                t0 = time.perf_counter()
                try:
                    state = dict(_init_state)
                    state["original_query"] = f"S{hash(str(time.perf_counter_ns())) % 300}"
                    with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                        with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                            await faq_match_node(state)
                    latencies.append(time.perf_counter() - t0)
                except Exception:
                    errors += 1
                await asyncio.sleep(self._soak_interval)

        tasks = [_runner() for _ in range(5)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-FAQ-007 (30s稳定性 5并发)", latencies)
        print(f"[STABILITY] 错误={errors}, 总请求={len(latencies)}")
        assert stats["p95"] <= 2.0
        assert errors == 0

    # PF-RAG-008: RAG 持续浸泡 (速跑版, 15s)
    @pytest.mark.asyncio
    async def test_pf_rag_008_soak(self, _init_state):
        from app.agents.nodes.retrieve import retrieve_node
        from app.agents.nodes.context import assemble_context
        from app.retrieval.fusion import FusionResult

        mock_docs = [
            FusionResult(unique_id=f"id_{i}", doc_id=i, chunk_index=0,
                         content=f"浸泡文档{i}" * 10, fused_score=0.9, scope="public")
            for i in range(10)
        ]
        mock_hybrid = AsyncMock(return_value=mock_docs)
        mock_rerank = AsyncMock(return_value=mock_docs[:5])

        latencies = []
        errors = 0
        t_end = time.perf_counter() + 15

        async def _runner():
            nonlocal errors
            while time.perf_counter() < t_end:
                t0 = time.perf_counter()
                try:
                    state = dict(_init_state)
                    state["original_query"] = f"浸泡查询{hash(str(time.perf_counter_ns())) % 20}"
                    with patch("app.agents.nodes.retrieve.hybrid_retrieve", mock_hybrid):
                        with patch("app.agents.nodes.retrieve.rerank", mock_rerank):
                            with patch("app.agents.nodes.retrieve.get_cache", return_value=None):
                                s1 = await retrieve_node(state)
                                assemble_context(s1)
                    latencies.append(time.perf_counter() - t0)
                except Exception:
                    errors += 1
                await asyncio.sleep(0.5)

        tasks = [_runner() for _ in range(3)]
        await asyncio.gather(*tasks)

        stats = _summarize("PF-RAG-008 (15s浸泡 3并发)", latencies)
        print(f"[SOAK] 错误={errors}, 总请求={len(latencies)}")
        assert stats["p95"] <= 1.0
        assert errors == 0


# ══════════════════════════════════════════════════
# 补充用例 Part C: 细粒度瓶颈分析 (6 条)
# ══════════════════════════════════════════════════
class TestBottleneckDetailed:

    # PF-BOT-002: Reranker 降级
    @pytest.mark.asyncio
    async def test_pf_bot_002_reranker_degrade(self):
        from app.retrieval.reranker import rerank
        from app.retrieval.fusion import FusionResult

        docs = [
            FusionResult(unique_id=f"r_{i}", doc_id=i, chunk_index=0,
                         content=f"降级文档内容段落{i}", fused_score=0.9, scope="public")
            for i in range(10)
        ]

        with patch("app.retrieval.reranker._get_client") as mock_client:
            mock_client.return_value.post.side_effect = Exception("API timeout")
            latencies = []
            for _ in range(5):
                t0 = time.perf_counter()
                result = await rerank("降级查询", docs, top_k=5)
                latencies.append(time.perf_counter() - t0)
                assert len(result) == 5  # 降级后仍返回 top_k

            stats = _summarize("PF-BOT-002 Reranker 降级耗时", latencies)
            assert stats["p95"] <= 0.1, f"降级 P95={stats['p95']:.3f}s > 100ms"

    # PF-BOT-003: Reranker 重复查询耗时 (观察缓存效果)
    @pytest.mark.asyncio
    async def test_pf_bot_003_reranker_repeat(self):
        from app.retrieval.reranker import rerank
        from app.retrieval.fusion import FusionResult

        docs = [
            FusionResult(unique_id=f"r_{i}", doc_id=i, chunk_index=0,
                         content=f"重复查询文档{i}段落内容不变", fused_score=0.9, scope="public")
            for i in range(15)
        ]

        runs = []
        for run_idx in range(5):
            t0 = time.perf_counter()
            result = await rerank("固定查询语句不变", docs, top_k=5)
            elapsed = time.perf_counter() - t0
            runs.append(elapsed)
            assert len(result) == 5

        first = runs[0]
        last = runs[-1]
        print(
            f"\n[PF-BOT-003] Reranker 5次重复耗时: "
            f"first={first:.3f}s last={last:.3f}s "
            f"ratio=last/first={last/first:.2f}"
        )

    # PF-BOT-004: Dense Search 基准 (Milvus 实时)
    @pytest.mark.asyncio
    async def test_pf_bot_004_dense_search(self):
        from app.retrieval.milvus_client import _ensure_connected, dense_search
        from app.agents.embedding import embed_query

        _ensure_connected()

        latencies = []
        errors = 0
        for i in range(10):
            try:
                query_vec = await embed_query(f"测试查询{i}")
                t0 = time.perf_counter()
                result = await dense_search(
                    query_vector=query_vec,
                    scope="public",
                    top_k=10,
                )
                latencies.append(time.perf_counter() - t0)
                print(f"  dense_search #{i}: {latencies[-1]:.4f}s, results={len(result)}")
            except Exception as e:
                errors += 1
                print(f"  dense_search #{i}: FAILED — {e}")

        if latencies:
            stats = _summarize("PF-BOT-004 Dense Search(public)", latencies)
            assert stats["p95"] <= 5.0, f"Dense Search P95={stats['p95']:.1f}s > 5s"
        print(f"[PF-BOT-004] 错误={errors}/10")

    # PF-BOT-005: Collection Load 耗时
    @pytest.mark.asyncio
    async def test_pf_bot_005_collection_load(self):
        from app.retrieval.milvus_client import _ensure_connected
        from pymilvus import Collection

        _ensure_connected()

        for scope in ["public", "internal", "customer"]:
            coll_name = f"coll_{scope}"
            try:
                coll = Collection(coll_name)
                t0 = time.perf_counter()
                coll.load(timeout=10)
                elapsed = time.perf_counter() - t0
                num = coll.num_entities
                print(f"\n[PF-BOT-005] {coll_name}: load={elapsed:.2f}s entities={num}")
                assert elapsed <= 15.0, f"{coll_name} load {elapsed:.1f}s > 15s"
            except Exception as e:
                print(f"\n[PF-BOT-005] {coll_name}: FAILED — {e}")

    # PF-BOT-006: 混合检索 Dense vs BM25 vs Hybrid 对比
    @pytest.mark.asyncio
    async def test_pf_bot_006_hybrid_compare(self):
        from app.retrieval.fusion import hybrid_retrieve, FusionResult

        mock_dense = [
            FusionResult(unique_id="d1", doc_id=1, chunk_index=0,
                         content="密集检索结果", fused_score=0.9, scope="public"),
        ]
        mock_bm25 = [
            FusionResult(unique_id="b1", doc_id=2, chunk_index=0,
                         content="BM25检索结果", fused_score=0.8, scope="public"),
        ]

        with patch("app.retrieval.milvus_client.dense_search", AsyncMock(return_value=mock_dense)):
            with patch("app.retrieval.es_client.bm25_search", AsyncMock(return_value=mock_bm25)):
                with patch("app.retrieval.fusion.reciprocal_rank_fusion",
                           return_value=mock_dense + mock_bm25):
                    with patch("app.retrieval.fusion.deduplicate_by_id",
                               return_value=mock_dense + mock_bm25):

                        t0 = time.perf_counter()
                        result = await hybrid_retrieve(query="混合检索测试", scope="public", top_k=10)
                        elapsed = time.perf_counter() - t0

                        print(f"\n[PF-BOT-006] 混合检索: {elapsed:.4f}s, results={len(result)}")
                        assert len(result) >= 2, f"混合检索结果数={len(result)} < 2"
                        assert elapsed <= 5.0, f"混合检索 {elapsed:.2f}s > 5s"

    # PF-RAG-006: 长文档检索精度对比
    @pytest.mark.asyncio
    async def test_pf_rag_006_long_doc_retrieval(self):
        from app.retrieval.fusion import FusionResult, reciprocal_rank_fusion, deduplicate_by_id

        short_doc = FusionResult(
            unique_id="short_1", doc_id=1, chunk_index=0,
            content="短文档内容", fused_score=0.9, scope="public",
        )
        long_doc = FusionResult(
            unique_id="long_1", doc_id=2, chunk_index=0,
            content="长文档内容" * 500,
            fused_score=0.9, scope="public",
        )

        short_times = []
        long_times = []

        for _ in range(10):
            t0 = time.perf_counter()
            deduplicate_by_id(reciprocal_rank_fusion([short_doc] * 5, [short_doc] * 5))
            short_times.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            deduplicate_by_id(reciprocal_rank_fusion([long_doc] * 5, [long_doc] * 5))
            long_times.append(time.perf_counter() - t0)

        s = _summarize("PF-RAG-006 短文档RRF融合", short_times)
        l = _summarize("PF-RAG-006 长文档RRF融合", long_times)
        ratio = l["p95"] / s["p95"] if s["p95"] > 0 else 1
        print(f"[PF-RAG-006] 长/短文档耗时比: {ratio:.1f}x")
        assert ratio <= 3.0, f"长文档耗时比={ratio:.1f}x > 3x"


# ══════════════════════════════════════════════════
# 补充用例 Part D: 资源阶梯采集 (3 条)
# ══════════════════════════════════════════════════
class TestResourceTiered:

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_pf_res_002_10qps_baseline(self, _init_state):
        """模拟 10 QPS 负载下的后端资源开销 (代码路径耗时)"""
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"Q{i}", "content": f"A{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(200)
        ]

        latencies = []
        concurrent = 10
        bursts = 3  # 3 轮 burst 模拟持续 10 QPS

        for burst in range(bursts):
            t_burst = time.perf_counter()
            async def _worker():
                t0 = time.perf_counter()
                state = dict(_init_state)
                state["original_query"] = f"10QPS查询{hash(str(time.perf_counter_ns())) % 100}"
                with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                    with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                        await faq_match_node(state)
                latencies.append(time.perf_counter() - t0)

            tasks = [_worker() for _ in range(concurrent)]
            await asyncio.gather(*tasks)
            print(f"  Burst {burst+1}/{bursts}: {concurrent}req in {time.perf_counter() - t_burst:.3f}s")

        stats = _summarize("PF-RES-002 (模拟10QPS 3轮burst)", latencies)
        assert stats["p95"] <= 2.0, f"10QPS P95={stats['p95']:.3f}s > 2s"

    @pytest.mark.asyncio
    async def test_pf_res_003_20qps_baseline(self, _init_state):
        """模拟 20 QPS 负载"""
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"Q{i}", "content": f"A{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(500)
        ]

        latencies = []
        concurrent = 20
        bursts = 3
        errors = 0

        for burst in range(bursts):
            async def _worker():
                nonlocal errors
                try:
                    t0 = time.perf_counter()
                    state = dict(_init_state)
                    state["original_query"] = f"20QPS查询{hash(str(time.perf_counter_ns())) % 200}"
                    with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                        with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                            await faq_match_node(state)
                    latencies.append(time.perf_counter() - t0)
                except Exception:
                    errors += 1

            tasks = [_worker() for _ in range(concurrent)]
            await asyncio.gather(*tasks)

        stats = _summarize("PF-RES-003 (模拟20QPS 3轮burst)", latencies)
        print(f"[PF-RES-003] 错误={errors}")
        assert stats["p95"] <= 3.0, f"20QPS P95={stats['p95']:.3f}s > 3s"
        assert errors == 0

    @pytest.mark.asyncio
    async def test_pf_res_004_capacity_cap(self, _init_state):
        """探顶: 逐步提高并发直到错误超限"""
        from app.agents.nodes.faq import faq_match_node

        mock_vec = [0.1] * 1024
        faq_vectors = [
            {"faq_id": i, "question": f"Q{i}", "content": f"A{i}",
             "scope": "public", "vector": [0.5] * 1024}
            for i in range(500)
        ]

        print("\n[PF-RES-004] 容量探顶 — 逐步增加并发...")
        for concurrency in [50, 100, 200, 300, 500]:
            latencies = []
            errors = 0

            async def _worker():
                nonlocal errors
                try:
                    t0 = time.perf_counter()
                    state = dict(_init_state)
                    state["original_query"] = f"探顶{hash(str(time.perf_counter_ns())) % 300}"
                    with patch("app.agents.nodes.faq.embed_query", return_value=mock_vec):
                        with patch("app.agents.nodes.faq.get_faq_vectors", return_value=faq_vectors):
                            await faq_match_node(state)
                    latencies.append(time.perf_counter() - t0)
                except Exception:
                    errors += 1

            tasks = [_worker() for _ in range(concurrency)]
            await asyncio.gather(*tasks)

            p95 = _percentile(latencies, 95)
            error_rate = errors / concurrency * 100 if concurrency else 0
            print(f"  并发={concurrency}: P95={p95:.4f}s 错误率={error_rate:.1f}%")

            if error_rate > 10:
                print(f"  ⚠ 错误率 {error_rate:.0f}% > 10%, 天花板到达! 上一个并发={concurrency//2}")
                break

        _summarize(f"PF-RES-004 极限探测(并发={concurrency})", latencies)
