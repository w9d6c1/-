"""后台管理 — 操作日志查询与导出"""

import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.dependencies import DbDep, require_auth
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.services.audit_service import AuditLogService

router = APIRouter(prefix="/operations", tags=["admin-operations"])


class OperationResponse(dict):
    pass


@router.get("", response_model=PaginatedResponse[dict])
async def list_operations(
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    operator_name: str | None = None,
    operation_type: str | None = None,
    target_table: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    items, total = await AuditLogService(db).list_operations(
        page=page, page_size=page_size,
        operator_name=operator_name,
        operation_type=operation_type,
        target_table=target_table,
        start_date=start_dt,
        end_date=end_dt,
    )
    return {
        "items": [
            {
                "id": op.id,
                "operator_id": op.operator_id,
                "operator_name": op.operator_name,
                "operation_type": op.operation_type,
                "target_table": op.target_table,
                "target_id": op.target_id,
                "content_before": op.content_before,
                "content_after": op.content_after,
                "ip_address": op.ip_address,
                "created_at": op.created_at.isoformat() if op.created_at else None,
            }
            for op in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total > 0 else 0,
    }


@router.get("/export")
async def export_operations(
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
    operator_name: str | None = None,
    operation_type: str | None = None,
    target_table: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> StreamingResponse:
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    items = await AuditLogService(db).export_operations(
        operator_name=operator_name,
        operation_type=operation_type,
        target_table=target_table,
        start_date=start_dt,
        end_date=end_dt,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "操作人", "操作类型", "目标表", "目标ID", "操作前", "操作后", "IP", "时间"])
    for op in items:
        writer.writerow([
            op.id,
            op.operator_name or "",
            op.operation_type or "",
            op.target_table or "",
            op.target_id or "",
            str(op.content_before) if op.content_before else "",
            str(op.content_after) if op.content_after else "",
            op.ip_address or "",
            op.created_at.isoformat() if op.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=operations.csv"},
    )
