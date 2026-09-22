"""后台管理 — 词库(同义词/敏感词/禁答词) + 反馈路由"""

import csv
import io
from typing import Annotated

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.core.dependencies import DbDep, require_auth, require_permission
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.core.database import Base as DbBase
from app.services.audit_service import log_operation_async
from sqlalchemy import Integer, String, JSON, Text, DateTime, func as sqla_func, Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime


# ---------- 简易模型(内联) ----------

class Synonym(DbBase):
    __tablename__ = "synonym"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    synonyms: Mapped[list] = mapped_column(JSON, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sqla_func.now())


class SensitiveWord(DbBase):
    __tablename__ = "sensitive_word"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    word_type: Mapped[str] = mapped_column(String(20), nullable=False, default="sensitive")
    answer: Mapped[str | None] = mapped_column(Text, default=None)
    scope: Mapped[str] = mapped_column(String(20), default="all")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sqla_func.now())


class Feedback(DbBase):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rating: Mapped[str | None] = mapped_column(String(20), default=None)
    suggestion: Mapped[str | None] = mapped_column(Text, default=None)
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sqla_func.now())


class UnansweredQuestion(DbBase):
    __tablename__ = "unanswered_question"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sqla_func.now())


# ---------- Schema ----------

class SynonymCreate(BaseModel):
    word: str = Field(min_length=1, max_length=100)
    synonyms: list[str]
    scope: str = "public"


class SynonymResponse(SynonymCreate):
    id: int
    model_config = {"from_attributes": True}


class SensitiveWordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    word_type: str = "sensitive"
    answer: str | None = None
    scope: str = "all"


class SensitiveWordResponse(SensitiveWordCreate):
    id: int
    model_config = {"from_attributes": True}


class FeedbackCreate(BaseModel):
    thread_id: str
    rating: str | None = None
    suggestion: str | None = None


class ForbidWordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    word_type: str = "forbid"
    answer: str | None = None
    scope: str = "all"


class UnansweredCreate(BaseModel):
    thread_id: str
    question: str
    source: str = "customer"


# ---------- Router ----------

router = APIRouter(tags=["admin-dictionary-feedback"])


class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


async def _reload_word_caches(db: AsyncSession) -> None:
    from app.agents.nodes.output import update_sensitive_rules
    from app.knowledge.rewriter import invalidate_synonym_cache

    invalidate_synonym_cache()

    from app.agents.nodes.validate import load_words_from_db

    words = await load_words_from_db(db)
    update_sensitive_rules(words["sensitive_rules"])


@router.post("/synonyms", response_model=SynonymResponse, status_code=201)
async def create_synonym(
    payload: SynonymCreate, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> SynonymResponse:
    syn = Synonym(word=payload.word, synonyms=payload.synonyms, scope=payload.scope)
    db.add(syn)
    await db.commit()
    await db.refresh(syn)
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="create", target_table="synonym", target_id=syn.id,
        content_after={"word": syn.word, "synonyms": syn.synonyms, "scope": syn.scope},
    ))
    return syn  # type: ignore[return-value]


@router.get("/synonyms", response_model=PaginatedResponse[SynonymResponse])
async def list_synonyms(
    db: DbDep, _u: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[SynonymResponse]:
    count_r = await db.execute(select(func.count()).select_from(Synonym))
    total = count_r.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(select(Synonym).order_by(Synonym.id).offset(offset).limit(page_size))
    items = list(result.scalars())
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


@router.post("/sensitive-words", response_model=SensitiveWordResponse, status_code=201)
async def create_sensitive_word(
    payload: SensitiveWordCreate, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> SensitiveWordResponse:
    sw = SensitiveWord(word=payload.word, word_type=payload.word_type, answer=payload.answer, scope=payload.scope)
    db.add(sw)
    await db.commit()
    await db.refresh(sw)
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="create", target_table="sensitive_word", target_id=sw.id,
        content_after={"word": sw.word, "word_type": sw.word_type},
    ))
    return sw  # type: ignore[return-value]


@router.get("/sensitive-words", response_model=PaginatedResponse[SensitiveWordResponse])
async def list_sensitive_words(
    db: DbDep, _u: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[SensitiveWordResponse]:
    count_r = await db.execute(select(func.count()).select_from(SensitiveWord).where(SensitiveWord.word_type == "sensitive"))
    total = count_r.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        select(SensitiveWord).where(SensitiveWord.word_type == "sensitive").order_by(SensitiveWord.id).offset(offset).limit(page_size)
    )
    items = list(result.scalars())
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


@router.delete("/synonyms/{syn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_synonym(
    syn_id: int, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> None:
    syn = await db.get(Synonym, syn_id)
    if syn is None:
        raise HTTPException(status_code=404, detail="Synonym not found")
    await db.delete(syn)
    await db.commit()
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="delete", target_table="synonym", target_id=syn_id,
    ))


@router.post("/synonyms/bulk-delete")
async def bulk_delete_synonyms(
    payload: BulkIds, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    deleted, failed = 0, []
    for sid in payload.ids:
        syn = await db.get(Synonym, sid)
        if syn is None:
            failed.append({"id": sid, "reason": "not found"})
            continue
        await db.delete(syn)
        deleted += 1
        asyncio.create_task(log_operation_async(
            operator_id=_u.id, operator_name=_OP_DICT(_u),
            operation_type="delete", target_table="synonym", target_id=sid,
        ))
    await db.commit()
    await _reload_word_caches(db)
    return {"deleted": deleted, "failed": failed}


@router.delete("/sensitive-words/{sw_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensitive_word(
    sw_id: int, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> None:
    sw = await db.get(SensitiveWord, sw_id)
    if sw is None:
        raise HTTPException(status_code=404, detail="Sensitive word not found")
    await db.delete(sw)
    await db.commit()
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="delete", target_table="sensitive_word", target_id=sw_id,
    ))


@router.post("/sensitive-words/bulk-delete")
async def bulk_delete_sensitive_words(
    payload: BulkIds, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    deleted, failed = 0, []
    for sid in payload.ids:
        sw = await db.get(SensitiveWord, sid)
        if sw is None:
            failed.append({"id": sid, "reason": "not found"})
            continue
        await db.delete(sw)
        deleted += 1
        asyncio.create_task(log_operation_async(
            operator_id=_u.id, operator_name=_OP_DICT(_u),
            operation_type="delete", target_table="sensitive_word", target_id=sid,
        ))
    await db.commit()
    await _reload_word_caches(db)
    return {"deleted": deleted, "failed": failed}


# ── 更新同义词 ──

class SynonymUpdate(BaseModel):
    word: str | None = Field(default=None, min_length=1, max_length=100)
    synonyms: list[str] | None = None
    scope: str | None = None


@router.put("/synonyms/{syn_id}", response_model=SynonymResponse)
async def update_synonym(
    syn_id: int, payload: SynonymUpdate, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> SynonymResponse:
    syn = await db.get(Synonym, syn_id)
    if syn is None:
        raise HTTPException(status_code=404, detail="Synonym not found")
    if payload.word is not None:
        syn.word = payload.word
    if payload.synonyms is not None:
        syn.synonyms = payload.synonyms
    if payload.scope is not None:
        syn.scope = payload.scope
    await db.commit()
    await db.refresh(syn)
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="update", target_table="synonym", target_id=syn_id,
        content_after={"word": syn.word, "synonyms": syn.synonyms, "scope": syn.scope},
    ))
    return syn  # type: ignore[return-value]


# ── 批量导入 ──

class BatchImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


@router.post("/synonyms/import", response_model=BatchImportResult)
async def import_synonyms_csv(
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
    file: UploadFile = File(...),
) -> BatchImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    content = await file.read()
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped, errors = 0, 0, []
    for row_num, row in enumerate(reader, start=2):
        word = (row.get("word") or row.get("\ufeffword") or "").strip()
        syns_text = (row.get("synonyms") or "").strip()
        scope = (row.get("scope") or "public").strip()

        if not word:
            skipped += 1
            continue
        if not syns_text:
            skipped += 1
            continue

        syn_list = [s.strip() for s in syns_text.split(",") if s.strip()]
        if not syn_list:
            skipped += 1
            continue

        try:
            syn = Synonym(word=word, synonyms=syn_list, scope=scope)
            db.add(syn)
            imported += 1
        except Exception as e:
            errors.append(f"行 {row_num}: {e}")
            skipped += 1

    await db.commit()
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="create", target_table="synonym",
        content_after={"imported": imported, "skipped": skipped},
    ))
    return BatchImportResult(imported=imported, skipped=skipped, errors=errors)


@router.post("/sensitive-words/import", response_model=BatchImportResult)
async def import_sensitive_words_csv(
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
    file: UploadFile = File(...),
) -> BatchImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    content = await file.read()
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped, errors = 0, 0, []
    for row_num, row in enumerate(reader, start=2):
        word = (row.get("word") or row.get("\ufeffword") or "").strip()
        word_type = (row.get("word_type") or "sensitive").strip()
        answer = (row.get("answer") or "").strip() or None
        scope = (row.get("scope") or "all").strip()

        if not word:
            skipped += 1
            continue
        if word_type not in ("sensitive", "forbid"):
            word_type = "sensitive"

        existing = await db.execute(select(SensitiveWord).where(SensitiveWord.word == word))
        if existing.scalar():
            skipped += 1
            continue

        try:
            sw = SensitiveWord(word=word, word_type=word_type, answer=answer, scope=scope)
            db.add(sw)
            imported += 1
        except Exception as e:
            errors.append(f"行 {row_num}: {e}")
            skipped += 1

    await db.commit()
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="create", target_table="sensitive_word",
        content_after={"imported": imported, "skipped": skipped},
    ))
    return BatchImportResult(imported=imported, skipped=skipped, errors=errors)


# ── 禁答词 CRUD (独立端点) ──

@router.post("/forbid-words", response_model=SensitiveWordResponse, status_code=201)
async def create_forbid_word(
    payload: ForbidWordCreate, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> SensitiveWordResponse:
    sw = SensitiveWord(word=payload.word, word_type="forbid", answer=payload.answer, scope=payload.scope)
    db.add(sw)
    await db.commit()
    await db.refresh(sw)
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="create", target_table="sensitive_word", target_id=sw.id,
        content_after={"word": sw.word, "word_type": "forbid"},
    ))
    return sw  # type: ignore[return-value]


@router.get("/forbid-words", response_model=PaginatedResponse[SensitiveWordResponse])
async def list_forbid_words(
    db: DbDep, _u: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[SensitiveWordResponse]:
    count_r = await db.execute(select(func.count()).select_from(SensitiveWord).where(SensitiveWord.word_type == "forbid"))
    total = count_r.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        select(SensitiveWord).where(SensitiveWord.word_type == "forbid").order_by(SensitiveWord.id).offset(offset).limit(page_size)
    )
    items = list(result.scalars())
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


@router.delete("/forbid-words/{sw_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_forbid_word(
    sw_id: int, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> None:
    sw = await db.get(SensitiveWord, sw_id)
    if sw is None or sw.word_type != "forbid":
        raise HTTPException(status_code=404, detail="Forbid word not found")
    await db.delete(sw)
    await db.commit()
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="delete", target_table="sensitive_word", target_id=sw_id,
    ))


@router.post("/forbid-words/bulk-delete")
async def bulk_delete_forbid_words(
    payload: BulkIds, db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    deleted, failed = 0, []
    for sid in payload.ids:
        sw = await db.get(SensitiveWord, sid)
        if sw is None or sw.word_type != "forbid":
            failed.append({"id": sid, "reason": "not found"})
            continue
        await db.delete(sw)
        deleted += 1
        asyncio.create_task(log_operation_async(
            operator_id=_u.id, operator_name=_OP_DICT(_u),
            operation_type="delete", target_table="sensitive_word", target_id=sid,
        ))
    await db.commit()
    await _reload_word_caches(db)
    return {"deleted": deleted, "failed": failed}


@router.post("/forbid-words/import", response_model=BatchImportResult)
async def import_forbid_words_csv(
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
    file: UploadFile = File(...),
) -> BatchImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    content = await file.read()
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped, errors = 0, 0, []
    for row_num, row in enumerate(reader, start=2):
        word = (row.get("word") or row.get("\ufeffword") or "").strip()
        answer = (row.get("answer") or "").strip() or None
        scope = (row.get("scope") or "all").strip()
        if not word:
            skipped += 1
            continue

        existing = await db.execute(select(SensitiveWord).where(SensitiveWord.word == word))
        if existing.scalar():
            skipped += 1
            continue

        try:
            sw = SensitiveWord(word=word, word_type="forbid", answer=answer, scope=scope)
            db.add(sw)
            imported += 1
        except Exception as e:
            errors.append(f"行 {row_num}: {e}")
            skipped += 1

    await db.commit()
    await _reload_word_caches(db)
    asyncio.create_task(log_operation_async(
        operator_id=_u.id, operator_name=_OP_DICT(_u),
        operation_type="create", target_table="sensitive_word",
        content_after={"imported": imported, "skipped": skipped, "word_type": "forbid"},
    ))
    return BatchImportResult(imported=imported, skipped=skipped, errors=errors)


_OP_DICT = lambda u: u.display_name or u.username or "unknown"


@router.post("/feedbacks", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreate, db: DbDep,
    current_user: Annotated[User, Depends(require_auth)],
) -> dict[str, str]:
    fb = Feedback(thread_id=payload.thread_id, rating=payload.rating, suggestion=payload.suggestion, user_id=current_user.id)
    db.add(fb)
    await db.commit()
    return {"status": "ok"}


@router.post("/unanswered", status_code=status.HTTP_201_CREATED)
async def submit_unanswered(
    payload: UnansweredCreate, db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
) -> dict[str, str]:
    ua = UnansweredQuestion(
        thread_id=payload.thread_id, question=payload.question,
        source=payload.source,
    )
    db.add(ua)
    await db.commit()
    await db.refresh(ua)
    return {"status": "ok", "id": str(ua.id)}  # type: ignore[arg-type]


# ── 反馈列表 + 统计 ──

@router.get("/feedbacks")
async def list_feedbacks(
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
    rating: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> list[dict]:
    stmt = select(Feedback).order_by(Feedback.id.desc())
    if rating:
        stmt = stmt.where(Feedback.rating == rating)
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {"id": r.id, "thread_id": r.thread_id, "rating": r.rating, "suggestion": r.suggestion, "user_id": r.user_id, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/feedbacks/stats")
async def get_feedback_stats(
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
) -> dict:
    total_result, likes_result, dislikes_result = await asyncio.gather(
        db.execute(select(func.count()).select_from(Feedback)),
        db.execute(select(func.count()).select_from(Feedback).where(Feedback.rating == "like")),
        db.execute(select(func.count()).select_from(Feedback).where(Feedback.rating == "dislike")),
    )
    total = total_result.scalar() or 0
    likes = likes_result.scalar() or 0
    dislikes = dislikes_result.scalar() or 0

    return {"total": total, "likes": likes, "dislikes": dislikes}


# ── 未命中问题列表 + 状态管理 ──

@router.get("/unanswered")
async def list_unanswered(
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
    status: str | None = Query(None),
    source: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> list[dict]:
    stmt = select(UnansweredQuestion).order_by(UnansweredQuestion.id.desc())
    if status:
        stmt = stmt.where(UnansweredQuestion.status == status)
    if source:
        stmt = stmt.where(UnansweredQuestion.source == source)
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {"id": r.id, "thread_id": r.thread_id, "question": r.question, "source": r.source, "status": r.status, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


class UnansweredUpdate(BaseModel):
    status: str


@router.patch("/unanswered/{ua_id}")
async def update_unanswered(
    ua_id: int,
    payload: UnansweredUpdate,
    db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
) -> dict:
    ua = await db.get(UnansweredQuestion, ua_id)
    if ua is None:
        raise HTTPException(status_code=404, detail="Not found")
    ua.status = payload.status
    await db.commit()
    await db.refresh(ua)
    return {"id": ua.id, "thread_id": ua.thread_id, "question": ua.question, "source": ua.source, "status": ua.status, "created_at": ua.created_at.isoformat()}


@router.post("/unanswered/{ua_id}/convert")
async def convert_unanswered_to_faq(
    ua_id: int,
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    ua = await db.get(UnansweredQuestion, ua_id)
    if ua is None:
        raise HTTPException(status_code=404, detail="Not found")

    # LLM 生成建议答案
    generated_answer = ""
    try:
        from app.agents.llm import clean_response, create_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = create_llm(temperature=0.3, max_tokens=512, top_p=0.85)
        messages = [
            SystemMessage(content="你是一个知识库撰写助手。请根据用户问题生成一个专业、简洁、准确的FAQ答案。只输出答案文本，不要加任何前缀说明。"),
            HumanMessage(content=f"用户问题：{ua.question}"),
        ]
        resp = await llm.ainvoke(messages)
        generated_answer = clean_response(str(resp.content).strip())
    except Exception:
        generated_answer = ua.question

    # 创建 FAQ 草稿
    from app.models.faq import KnowledgeFAQ

    faq = KnowledgeFAQ(
        category_id=1,
        question=ua.question,
        answer=generated_answer,
        scope="customer" if ua.source == "customer" else "public",
        status="draft",
        review_status="pending",
    )
    db.add(faq)
    await db.commit()
    await db.refresh(faq)

    # 标记未命中为已转换
    ua.status = "converted"
    await db.commit()

    return {"faq_id": faq.id, "question": ua.question, "generated_answer": generated_answer}
