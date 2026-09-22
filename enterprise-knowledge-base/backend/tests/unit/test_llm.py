"""LLM 统一调用封装 测试 (TDD: RED)"""

import pytest
import tiktoken

from app.agents.llm import LLMConfig, count_tokens, create_llm, create_llm_config


def test_llm_config_from_settings():
    cfg = create_llm_config()
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.base_url == "https://api.deepseek.com"
    assert isinstance(cfg.api_key, str)


def test_llm_config_no_api_key_returns_empty():
    cfg = LLMConfig(api_key="", provider="deepseek", model="deepseek-chat", base_url="https://api.deepseek.com")
    assert cfg.api_key == ""


def test_count_tokens_positive():
    n = count_tokens("你好世界")
    assert n > 0


def test_count_tokens_empty_string():
    n = count_tokens("")
    assert n == 0


def test_create_llm_minimal():
    llm = create_llm(api_key="sk-test-mock-key")
    assert llm is not None
    assert hasattr(llm, "invoke")


def test_create_llm_custom_params():
    llm = create_llm(temperature=0.3, max_tokens=512, api_key="sk-test-mock-key")
    assert llm is not None


def test_create_llm_raises_on_placeholder_key():
    from app.agents.llm import _validate_api_key

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        _validate_api_key("")
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        _validate_api_key("your-api-key-here")
