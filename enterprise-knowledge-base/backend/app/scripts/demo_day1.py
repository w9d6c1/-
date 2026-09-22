"""Phase 3 Day 1 演示脚本 — 验证 LangChain 底层封装四个模块"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def demo_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def demo_llm() -> None:
    demo_separator("[1/4] LLM 模块")
    from app.agents.llm import LLMConfig, count_tokens, create_llm_config

    cfg = create_llm_config()
    print(f"  模型配置: {cfg.model} @ {cfg.base_url}")
    print(f"  Provider: {cfg.provider}")

    n = count_tokens("你好世界，这是一个企业知识库系统。")
    print(f"  Token 计数: \"你好世界，这是一个企业知识库系统。\" = {n} tokens")

    print(f"  LLM 封装状态: OK (API Key 需在 .env 中配置 LLM_API_KEY)")


def demo_embedding() -> None:
    demo_separator("[2/4] Embedding 模块")
    from app.agents.embedding import create_embed_config, get_embedding_dimension

    cfg = create_embed_config()
    print(f"  模型: {cfg.model}")
    print(f"  设备: {cfg.device}")
    print(f"  向量维度: {get_embedding_dimension()}")

    print(f"  Embedding 封装状态: OK (首次加载需下载模型 ~1.3GB)")


def demo_loader() -> None:
    demo_separator("[3/4] 文档加载器")
    from app.knowledge.loader import DocumentMeta, load_text

    meta = DocumentMeta(source="demo.md", scope="public", title="员工手册-考勤篇", department="技术部")
    content = "第一章 考勤制度\n\n公司实行弹性工作制。\n\n第二章 请假流程\n\n员工通过OA系统提交请假申请。"
    docs = load_text(content, meta, chunk_size=200, chunk_overlap=50)
    print(f"  源文档: {meta.title} ({meta.source})")
    print(f"  Scope: {meta.scope} | Department: {meta.department}")
    print(f"  生成 {len(docs)} 个 LangChain Document:")
    for d in docs:
        print(f"    Chunk[{d.metadata['chunk_index']}]: \"{d.page_content[:50]}...\"")

    print(f"  文档加载器状态: OK")


def demo_rewriter() -> None:
    demo_separator("[4/4] 查询改写")
    from app.knowledge.rewriter import expand_synonyms, normalize_query, rewrite_query

    syn_map: dict[str, list[str]] = {
        "打卡": ["签到", "考勤"],
        "OA": ["办公系统", "审批系统"],
        "请假": ["休假", "调休"],
    }

    queries = ["怎么打卡", "OA登录方式", "Hello World !", "请假流程是什么"]
    for q in queries:
        normalized = normalize_query(q)
        expanded = expand_synonyms(normalized, syn_map)
        rewritten = rewrite_query(q, syn_map)
        print(f"  原始: {q}")
        print(f"    归一化: {normalized}")
        print(f"    扩展:   {expanded}")
        if rewritten != expanded:
            print(f"    改写:   {rewritten}")

    print(f"\n  查询改写状态: OK")


def demo_api() -> None:
    demo_separator("API 端点")
    import httpx

    try:
        r = httpx.get("http://localhost:8000/api/agent/info")
        data = r.json()
        print(f"  GET /api/agent/info → {data['status']}")
        for mod, state in data["modules"].items():
            print(f"    {mod}: {state}")

        r = httpx.post(
            "http://localhost:8000/api/agent/rewrite",
            json={"message": "怎么打卡考勤", "scope": "public"},
        )
        data = r.json()
        print(f"\n  POST /api/agent/rewrite")
        print(f"    original:   {data['original']}")
        print(f"    normalized: {data['normalized']}")
        print(f"    expanded:   {data['expanded']}")

        print(f"\n  Swagger 文档: http://localhost:8000/docs")
    except Exception as e:
        print(f"  API 不可达: {e}")


def main() -> None:
    print("=" * 60)
    print("  Phase 3 Day 1 — LangChain 底层封装 验证")
    print("=" * 60)

    demo_llm()
    demo_embedding()
    demo_loader()
    demo_rewriter()
    demo_api()

    demo_separator("总结")
    print("  4/4 模块就绪: LLM | Embedding | Loader | Rewriter")
    print("  Day 2 任务: ES BM25 + Milvus Dense 双路检索器 + RRF")
    print("  Day 3-5 任务: LangGraph 智能体图构建")
    print(f"\n  运行: pytest tests/unit/ -v --no-cov 查看全量测试")
    print("=" * 60)


if __name__ == "__main__":
    main()
