"""
LangChain / LangGraph 基础环境验证脚本
运行方式: python scripts/verify_ai_stack.py
"""

import sys


def check_imports() -> list[tuple[str, bool]]:
    modules = [
        "langchain",
        "langchain_community",
        "langgraph",
        "langgraph.checkpoint.postgres",
        "langchain_openai",
        "pymilvus",
        "elasticsearch",
        "sentence_transformers",
        "FlagEmbedding",
    ]
    results = []
    for module in modules:
        try:
            __import__(module)
            results.append((module, True))
        except ImportError:
            results.append((module, False))
    return results


def main():
    print("=" * 50)
    print("LangChain / LangGraph 基础环境验证")
    print("=" * 50)

    results = check_imports()
    all_ok = True
    for module, ok in results:
        status = "OK" if ok else "FAILED"
        if not ok:
            all_ok = False
        print(f"  [{status}] {module}")

    print(f"\n总计: {sum(1 for _, ok in results if ok)}/{len(results)} 模块可用")

    if all_ok:
        print("\n所有依赖模块验证通过")
    else:
        print("\n部分模块未安装，运行: pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
