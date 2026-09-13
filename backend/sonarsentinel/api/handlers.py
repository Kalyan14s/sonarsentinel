"""Error handlers and CORS shared by the real and the mock API apps."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sonarsentinel.errors import SonarSentinelError

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def install_handlers(app: FastAPI) -> None:
    """Error model for every failure (``{"error": {code, message, details}}``) and dev CORS."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(SonarSentinelError)
    async def sonarsentinel_error(_: Request, exc: SonarSentinelError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def request_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())[1:]) or "request",
                "message": str(err.get("msg", "invalid value")),
            }
            for err in exc.errors()
        ]
        body = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": {"errors": errors},
            }
        }
        return JSONResponse(status_code=400, content=body)
