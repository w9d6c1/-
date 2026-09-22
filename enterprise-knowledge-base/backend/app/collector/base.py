"""采集器抽象基类 — 各平台适配器实现 fetch_since 即可接入。"""

from abc import ABC, abstractmethod

from app.collector.models import RawArticle


class BaseCollector(ABC):
    """平台采集器基类。

    子类须设置 ``platform``（与 knowledge_doc.source_type 对齐），并实现 ``fetch_since``。
    ``fetch_since`` 返回 ``(文章列表, 新cursor)``：cursor 为 None 表示全量拉取，
    否则拉取该游标之后的增量内容；返回的新 cursor 由调度层持久化用于下次增量同步。
    """

    platform: str = ""
    source_name: str = ""
    page_delay: float = 0.0

    @abstractmethod
    async def fetch_since(self, cursor: str | None) -> tuple[list[RawArticle], str | None]:
        """拉取 cursor 之后的文章。

        Args:
            cursor: 增量游标；None 表示全量拉取。

        Returns:
            (文章列表, 新游标)。新游标用于下次增量同步的起点。
        """
        raise NotImplementedError

    async def health_check(self) -> bool:
        """凭证/连通性检查。默认 True，依赖外部凭证的适配器应覆盖。"""
        return True
