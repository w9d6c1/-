"""统一异常处理与 API 响应格式"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.logging import logger


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.warning("validation_error", errors=exc.errors(), path=str(request.url))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning("http_exception", status_code=exc.status_code, detail=exc.detail, path=str(request.url))
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", error=str(exc), path=str(request.url), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal server error"}},
    )
