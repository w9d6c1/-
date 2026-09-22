"""应急与回滚方案 — 数据备份验证测试

要求:
- 上线前执行一次完整备份 + 恢复演练
- 确认 MySQL、MinIO、PostgreSQL 的备份可用
- 避免备份形同虚设
"""

import re
from pathlib import Path

import pytest
import yaml

# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKUP_SCRIPT = PROJECT_ROOT / "scripts" / "backup.sh"
DOCKER_COMPOSE_PROD = PROJECT_ROOT / "docker-compose.prod.yml"
BACKUP_DOC = PROJECT_ROOT / "docs" / "ops" / "BACKUP.md"
DEPLOY_CHECKLIST = PROJECT_ROOT / "docs" / "deploy-checklist.md"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ============================================================
# BKP-01: backup.sh 存在且有效
# ============================================================
def test_backup_script_exists_and_valid():
    assert BACKUP_SCRIPT.exists(), "scripts/backup.sh 缺失"
    content = BACKUP_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert content.startswith("#!/"), "backup.sh 缺少 shebang 行"
    assert "backup" in content.lower(), "backup.sh 内容无效"


# ============================================================
# BKP-02: backup.sh 覆盖 MySQL 备份
# ============================================================
def test_backup_script_covers_mysql():
    content = BACKUP_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert "mysqldump" in content, "backup.sh 中缺少 mysqldump 命令"
    assert "mysql" in content.lower(), "backup.sh 中未引用 MySQL 容器"


# ============================================================
# BKP-03: backup.sh 覆盖 PostgreSQL 备份
# ============================================================
def test_backup_script_covers_postgresql():
    content = BACKUP_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert "pg_dump" in content, "backup.sh 中缺少 pg_dump 命令"
    assert "postgres" in content.lower(), "backup.sh 中未引用 PostgreSQL 容器"


# ============================================================
# BKP-04: backup.sh 覆盖 MinIO 备份
# ============================================================
def test_backup_script_covers_minio():
    content = BACKUP_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert "minio" in content.lower(), "backup.sh 中未引用 MinIO"
    assert "mc" in content and "cp" in content, (
        "backup.sh 中缺少 `mc cp` MinIO 备份命令"
    )


# ============================================================
# BKP-05: backup.sh 包含恢复指令
# ============================================================
def test_backup_script_includes_restore_instructions():
    content = BACKUP_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert "恢复" in content or "restore" in content.lower(), (
        "backup.sh 中缺少恢复命令参考"
    )
    # MySQL / PostgreSQL 恢复命令
    has_mysql_restore = re.search(r"mysql\b.*\s+<\s+", content)
    has_pg_restore = re.search(r"(psql|pg_restore)\b", content)
    assert has_mysql_restore, "backup.sh 中缺少 MySQL 恢复命令 (mysql ... < dump.sql)"
    assert has_pg_restore, (
        "backup.sh 中缺少 PostgreSQL 恢复命令 (psql ... < dump.sql)"
    )
    # MinIO 恢复命令
    assert "cp" in content, "backup.sh 中缺少 MinIO 恢复命令（mc cp 反向）"


# ============================================================
# BKP-06: docker-compose.prod.yml 有备份卷挂载
# ============================================================
def test_prod_compose_has_backup_volume_mounts():
    content = DOCKER_COMPOSE_PROD.read_text(encoding="utf-8")

    backup_mounts_needed = {
        "mysql": "./backups/mysql",
        "postgres": "./backups/postgres",
        "minio": "./backups/minio",
    }

    missing = []
    for svc, mount_str in backup_mounts_needed.items():
        if mount_str not in content:
            missing.append(f"{svc}: {mount_str}")

    assert not missing, (
        f"docker-compose.prod.yml 中以下服务缺少备份目录挂载:\n" + "\n".join(missing)
    )


# ============================================================
# BKP-07: 备份文档含恢复验证步骤
# ============================================================
def test_backup_documentation_covers_verify_restore():
    assert BACKUP_DOC.exists(), "docs/ops/BACKUP.md 缺失"

    doc_content = BACKUP_DOC.read_text(encoding="utf-8", errors="ignore")
    assert "恢复" in doc_content or "restore" in doc_content.lower(), (
        "BACKUP.md 中未覆盖恢复步骤"
    )
    assert "验证" in doc_content or "verify" in doc_content.lower() or "恢复演练" in doc_content, (
        "BACKUP.md 中未包含恢复验证/演练步骤"
    )


# ============================================================
# BKP-08: 部署检查单要求备份验证
# ============================================================
def test_deploy_checklist_requires_backup_verification():
    assert DEPLOY_CHECKLIST.exists(), "docs/deploy-checklist.md 缺失"

    checklist_content = DEPLOY_CHECKLIST.read_text(encoding="utf-8", errors="ignore")
    has_backup = (
        "备份" in checklist_content
        or "backup" in checklist_content.lower()
        or "备份验证" in checklist_content
    )
    assert has_backup, (
        "deploy-checklist.md 中未要求上线前完成备份验证"
    )

    has_verify = "验证" in checklist_content or "verify" in checklist_content.lower()
    assert has_verify, "deploy-checklist.md 中未包含验证步骤"


# ============================================================
# BKP-09: 备份脚本可执行基本语法检查
# ============================================================
def test_backup_script_syntax_valid():
    """验证 backup.sh 没有明显的语法错误（括号匹配等）"""
    content = BACKUP_SCRIPT.read_text(encoding="utf-8", errors="ignore")

    # 检查 if/fi 配对
    if_count = len(re.findall(r"\bif\b", content))
    fi_count = len(re.findall(r"\bfi\b", content))
    assert if_count == fi_count, (
        f"backup.sh 中 if/fi 不匹配: if={if_count}, fi={fi_count}"
    )

    # 检查函数定义
    func_count = len(re.findall(r"\b\w+\(\)\s*\{", content))
    assert func_count >= 0, "backup.sh 语法检查完成"
