"""审计日志业务层 — operate_log / chat_log / security_log"""

from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ChatLog, OperateLog, SecurityLog
from app.core.logging import logger


class AuditLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_chat(
        self,
        thread_id: str,
        request_id: str,
        source: str = "customer",
        user_id: int | None = None,
        question: str = "",
        answer: str | None = None,
        node_name: str | None = None,
        node_status: str = "success",
        node_latency_ms: int = 0,
        hit_faq_id: int | None = None,
        hit_chunk_ids: list[int] | None = None,
        confidence: float | None = None,
        faq_hit: bool = False,
        sensitive_hit: bool = False,
        transfer_human: bool = False,
        node_output: dict | None = None,
    ) -> None:
        try:
            record = ChatLog(
                thread_id=thread_id,
                request_id=request_id,
                source=source,
                user_id=user_id,
                question=question,
                answer=answer,
                node_name=node_name,
                node_status=node_status,
                node_latency_ms=node_latency_ms,
                hit_faq_id=hit_faq_id,
                hit_chunk_ids=hit_chunk_ids,
                confidence=confidence,
                sensitive_hit=1 if sensitive_hit else 0,
                transfer_human=1 if transfer_human else 0,
                node_output=node_output,
            )
            self.db.add(record)
            await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                pass

    async def log_operation(
        self,
        operator_id: int | None = None,
        operator_name: str | None = None,
        operation_type: str = "query",
        target_table: str = "",
        target_id: int | None = None,
        content_before: dict | None = None,
        content_after: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        try:
            record = OperateLog(
                operator_id=operator_id,
                operator_name=operator_name,
                operation_type=operation_type,
                target_table=target_table,
                target_id=target_id,
                content_before=content_before,
                content_after=content_after,
                ip_address=ip_address,
            )
            self.db.add(record)
            await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                logger.warning("audit_rollback_failed", table="operate_log")
        else:
            return
        logger.warning("audit_operate_log_failed", operation_type=operation_type, target_table=target_table)

    async def log_security(
        self,
        event_type: str,
        request_id: str | None = None,
        user_id: int | None = None,
        ip_address: str | None = None,
        detail: dict | None = None,
        severity: str = "medium",
    ) -> None:
        try:
            record = SecurityLog(
                event_type=event_type,
                request_id=request_id,
                user_id=user_id,
                ip_address=ip_address,
                detail=detail,
                severity=severity,
            )
            self.db.add(record)
            await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                logger.warning("audit_rollback_failed", table="security_log")
        else:
            return
        logger.warning("audit_security_log_failed", event_type=event_type)

    async def list_operations(
        self,
        page: int = 1,
        page_size: int = 20,
        operator_name: str | None = None,
        operation_type: str | None = None,
        target_table: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[list[OperateLog], int]:
        stmt = select(OperateLog)
        count_stmt = select(func.count()).select_from(OperateLog)

        if operator_name:
            stmt = stmt.where(OperateLog.operator_name.contains(operator_name))
            count_stmt = count_stmt.where(OperateLog.operator_name.contains(operator_name))
        if operation_type:
            stmt = stmt.where(OperateLog.operation_type == operation_type)
            count_stmt = count_stmt.where(OperateLog.operation_type == operation_type)
        if target_table:
            stmt = stmt.where(OperateLog.target_table == target_table)
            count_stmt = count_stmt.where(OperateLog.target_table == target_table)
        if start_date:
            stmt = stmt.where(OperateLog.created_at >= start_date)
            count_stmt = count_stmt.where(OperateLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(OperateLog.created_at <= end_date)
            count_stmt = count_stmt.where(OperateLog.created_at <= end_date)

        total = (await self.db.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(OperateLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        items = list(result.scalars())
        return items, total

    async def export_operations(
        self,
        operator_name: str | None = None,
        operation_type: str | None = None,
        target_table: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[OperateLog]:
        stmt = select(OperateLog)
        if operator_name:
            stmt = stmt.where(OperateLog.operator_name.contains(operator_name))
        if operation_type:
            stmt = stmt.where(OperateLog.operation_type == operation_type)
        if target_table:
            stmt = stmt.where(OperateLog.target_table == target_table)
        if start_date:
            stmt = stmt.where(OperateLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(OperateLog.created_at <= end_date)
        stmt = stmt.order_by(OperateLog.id.desc()).limit(10000)
        result = await self.db.execute(stmt)
        return list(result.scalars())


async def log_operation_async(
    operator_id: int | None = None,
    operator_name: str | None = None,
    operation_type: str = "query",
    target_table: str = "",
    target_id: int | None = None,
    content_before: dict | None = None,
    content_after: dict | None = None,
) -> None:
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            svc = AuditLogService(db)
            await svc.log_operation(
                operator_id=operator_id,
                operator_name=operator_name,
                operation_type=operation_type,
                target_table=target_table,
                target_id=target_id,
                content_before=content_before,
                content_after=content_after,
            )
    except Exception:
        logger.warning("log_operation_async_failed", operation_type=operation_type, target_table=target_table, exc_info=True)


async def log_security_async(
    event_type: str,
    detail: dict | None = None,
    severity: str = "medium",
    request_id: str | None = None,
) -> None:
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            svc = AuditLogService(db)
            await svc.log_security(
                event_type=event_type,
                request_id=request_id,
                detail=detail,
                severity=severity,
            )
    except Exception:
        logger.warning("log_security_async_failed", event_type=event_type, exc_info=True)
