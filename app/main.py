from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, obs
from . import schemas as S
from .agent import AgentError, Tutor
from .llm import make_llm
from .ratelimit import DailyBudget, SlidingWindowLimiter
from .skills import SKILLS

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="AIの使い方を教えます", docs_url=None, redoc_url=None, openapi_url=None)
limiter = SlidingWindowLimiter(config.RATE_LIMIT_REQUESTS, config.RATE_LIMIT_WINDOW_SEC)
budget = DailyBudget(config.DAILY_LLM_CALL_LIMIT)
_tutor: Tutor | None = None


def tutor() -> Tutor:
    global _tutor
    if _tutor is None:
        _tutor = Tutor(make_llm(), budget)
    return _tutor


def set_tutor(t: Tutor | None) -> None:  # テスト用
    global _tutor
    _tutor = t


def client_key(request: Request) -> str:
    # Cloud Run は X-Forwarded-For の末尾に実クライアントIPを付ける
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()[:64]
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.exception_handler(AgentError)
async def agent_error(_: Request, e: AgentError):
    return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError):
    return JSONResponse({"error": {"code": "invalid", "message": "入力の形式または長さが正しくありません。"}}, status_code=422)


def _limit(request: Request) -> None:
    ok, wait = limiter.allow(client_key(request))
    if not ok:
        obs.log("WARNING", "rate_limited")
        raise AgentError(429, "rate_limit", f"短時間に使いすぎです。{max(1, wait // 60)}分ほど待ってから、もう一度お試しください。")


@app.get("/healthz")
@app.get("/api/health")  # Cloud Run の *.run.app では /healthz が Google 側で 404 になる。こちらを使う
def healthz():
    return {"status": "ok"}


@app.get("/api/config")
def api_config():
    return {
        "skills": [{"skill_id": k, **v} for k, v in SKILLS.items()],
        "limits": {"goal": config.MAX_GOAL_CHARS, "prompt": config.MAX_PROMPT_CHARS},
        "mode": config.LLM_MODE,
    }


@app.post("/api/plan")
def api_plan(body: S.PlanIn, request: Request):
    _limit(request)
    return tutor().plan(body.goal)


@app.post("/api/review")
def api_review(body: S.ReviewIn, request: Request):
    _limit(request)
    return tutor().review(body.goal, body.skill_ids, body.prompt)


@app.post("/api/run")
def api_run(body: S.RunIn, request: Request):
    _limit(request)
    return tutor().run(body.goal, body.prompt, body.risk_level)


@app.post("/api/quiz")
def api_quiz(body: S.QuizIn, request: Request):
    _limit(request)
    return tutor().quiz(body.goal, body.prompt, body.skill_ids, body.weak_skill_ids)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
