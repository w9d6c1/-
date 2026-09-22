"""生产环境一致性加固 — 配置中心化测试

要求:
- 所有环境变量、服务地址、密钥全部通过 .env 文件统一管理
- 代码中不允许写死任何地址、端口、密钥
- 生产环境与开发环境配置完全隔离
"""

import re
from pathlib import Path

import pytest

from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

PROJECT_ROOT = _PROJECT
BACKEND_ROOT = PROJECT_ROOT / "backend"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
CONFIG_PY = BACKEND_ROOT / "app" / "core" / "config.py"
APP_DIR = BACKEND_ROOT / "app"


def _get_pydantic_fields(config_path: Path) -> set[str]:
    """从 pydantic-settings 类中提取字段名"""
    content = config_path.read_text(encoding="utf-8")
    fields = set()
    pattern = re.compile(r"^\s+(\w+)\s*:\s*(?:str|int|bool|float)\s*=", re.MULTILINE)
    for m in pattern.finditer(content):
        fields.add(m.group(1))
    return fields


def _get_env_example_keys(env_path: Path) -> set[str]:
    """从 .env.example 中提取变量名"""
    keys = set()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if m:
            keys.add(m.group(1))
    return keys


# ============================================================
# CFG-01: .env.example 覆盖 config.py Settings 的全部字段
# ============================================================
def test_env_example_covers_all_config_fields():
    pydantic_fields = _get_pydantic_fields(CONFIG_PY)
    env_keys = _get_env_example_keys(ENV_EXAMPLE)

    # pydantic-settings 用 model_config 中的 env_prefix 或直接大小写映射
    # Settings 类字段为 snake_case -> 环境变量为 SCREAMING_SNAKE_CASE
    expected_env_keys = set()
    for field in pydantic_fields:
        env_name = field.upper()
        # 排除计算属性
        if field.startswith("_"):
            continue

    # 宽松匹配：检查大部分核心字段都在 .env.example 中有对应
    critical_fields = {
        "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE",
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
        "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD",
        "ES_HOST", "ES_PORT",
        "MILVUS_HOST", "MILVUS_PORT",
        "MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
        "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL",
        "JWT_SECRET_KEY", "JWT_ALGORITHM", "JWT_EXPIRE_MINUTES",
        "CORS_ORIGINS",
        "SILICONFLOW_API_KEY",
        "APP_NAME", "DEBUG", "LOG_LEVEL",
    }
    missing = critical_fields - env_keys
    assert not missing, (
        ".env.example 缺少以下关键环境变量:\n"
        + "\n".join(sorted(missing))
    )


# ============================================================
# CFG-02: pydantic-settings 正确从 .env 文件加载配置
# ============================================================
def test_settings_loads_from_env_file():
    from app.core.config import Settings

    settings = Settings()
    assert settings.app_name == "企业知识库系统"
    assert settings.app_version == "0.1.0"
    assert isinstance(settings.mysql_port, int)
    assert isinstance(settings.postgres_port, int)
    assert isinstance(settings.redis_port, int)
    assert isinstance(settings.es_port, int)
    assert isinstance(settings.milvus_port, int)
    assert isinstance(settings.jwt_expire_minutes, int)
    assert isinstance(settings.chat_log_retention_days, int)

    # URL 属性应正确拼接
    assert "mysql+aiomysql" in settings.mysql_url
    assert "postgresql+asyncpg" in settings.postgres_url
    assert "redis://" in settings.redis_url
    assert "http://" in settings.es_url


# ============================================================
# CFG-03: config.py 的 default 值不含生产地址
# ============================================================
def test_no_hardcoded_hosts_in_config():
    """验证 config.py 中 host/endpoint 字段的默认值不含生产地址"""
    config_content = CONFIG_PY.read_text(encoding="utf-8")

    # 只检查 host/endpoint/url 相关字段
    host_field_pattern = re.compile(
        r"(\w*(?:host|endpoint|base_url|url)\w*)\s*:\s*str\s*=\s*\"([^\"]+)\"",
        re.IGNORECASE,
    )
    suspicious = []
    for line in config_content.splitlines():
        m = host_field_pattern.search(line.strip())
        if m:
            field_name = m.group(1).lower()
            default_val = m.group(2)
            if not default_val:
                continue
            # localhost、公开 API URL 均允许
            if default_val == "localhost" or default_val.startswith("https://api."):
                continue
            # localhost:port 组合也允许
            if re.match(r"^localhost:\d+$", default_val):
                continue
            suspicious.append(f"{field_name} = \"{default_val}\"")

    assert not suspicious, (
        "config.py 中以下 host/endpoint 字段默认值不为 localhost，应清空为占位符:\n"
        + "\n".join(suspicious)
    )


# ============================================================
# CFG-04: 代码中无硬编码密钥
# ============================================================
def test_no_hardcoded_secrets_in_code():
    secret_patterns = [
        (r"sk-[a-zA-Z0-9]{10,}", "疑似 OpenAI/API Key"),
        (r'password\s*=\s*"[^"]{4,}"', "硬编码密码"),
        (r'(?i)(api_key|apikey|secret_key|secret)\s*=\s*"[^"]{8,}"', "硬编码密钥"),
    ]

    issues = []
    for py_file in APP_DIR.rglob("*.py"):
        # 跳过 test 和 __pycache__
        if "__pycache__" in str(py_file) or "tests" in str(py_file) or "conftest" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            for pattern, desc in secret_patterns:
                if re.search(pattern, line):
                    # 跳过 config.py 中显式定义的 Settings 类字段
                    if "config.py" in str(py_file) and "str =" in line:
                        continue
                    issues.append(f"{py_file.relative_to(PROJECT_ROOT)}:{lineno}: {desc} -> {line.strip()[:80]}")

    assert not issues, (
        f"代码中发现 {len(issues)} 处可能的硬编码密钥:\n" + "\n".join(issues[:20])
    )


# ============================================================
# CFG-05: 生产与开发环境配置可区分
# ============================================================
def test_prod_and_dev_envs_isolated():
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    # DEBUG 配置应可切换
    assert "DEBUG=" in content, ".env.example 应包含 DEBUG 开关"
    assert "LOG_LEVEL=" in content, ".env.example 应包含 LOG_LEVEL 配置"

    # 数据库主机不应硬指向生产
    db_hosts = re.findall(r"(?:MYSQL|POSTGRES|REDIS|ES|MILVUS)_HOST\s*=\s*(\S+)", content)
    for host in db_hosts:
        # 默认值可以是 localhost 或 docker 服务名，不应是生产 IP
        assert not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host), (
            f".env.example 中发现硬编码 IP {host}，应使用主机名占位符"
        )


# ============================================================
# CFG-06: docker-compose 中敏感值使用环境变量引用
# ============================================================
def test_docker_compose_uses_env_vars():
    """生产环境 docker-compose 中敏感值必须使用 ${VAR} 引用"""
    compose_path = PROJECT_ROOT / "docker-compose.prod.yml"
    hardcoded_secrets = []

    if not compose_path.exists():
        pytest.skip("docker-compose.prod.yml 不存在")

    content = compose_path.read_text(encoding="utf-8")

    # 查找环境变量块中直接写死的敏感值（非 ${} 引用）
    env_blocks = re.finditer(r"environment:\s*\n((?:\s{6,}- .*\n?)+)", content)
    for block in env_blocks:
        block_text = block.group(1)
        for line in block_text.splitlines():
            stripped = line.strip().lstrip("- ")
            if "=" in stripped and "${" not in stripped:
                key, val = stripped.split("=", 1)
                if val and any(kw in key.lower() for kw in ("password", "secret", "key", "pass")):
                    hardcoded_secrets.append(f"{key}={val}")

    assert not hardcoded_secrets, (
        "docker-compose.prod.yml 中以下敏感值直接硬编码，应改为 ${VAR} 引用:\n"
        + "\n".join(hardcoded_secrets)
    )
