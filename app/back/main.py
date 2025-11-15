from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates

from .core.config import settings

from app.back.core.config import settings
from app.back.core.db import init_db
from .routers import web_auth, web_dashboard, web_users, web_stores, web_products, api_kiosks, web_kiosks

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Wecandoit Admin",
    docs_url=None,
    redoc_url=None,
)

# 세션 (로그인 상태 유지용)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="wecandoit_admin_session",
)

# 정적 파일
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(static_dir)),
    name="static",
)

# 템플릿 (필요하면 main에서 쓸 수도 있어서 남겨둠)
templates_dir = BASE_DIR / "templates"
templates_dir.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# 라우터 등록
app.include_router(web_auth.router)
app.include_router(web_dashboard.router)
app.include_router(web_users.router)
app.include_router(web_stores.router)
app.include_router(web_products.router)
app.include_router(web_kiosks.router)
app.include_router(api_kiosks.router)


# 헬스체크 (Render용 포함)
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    # 개발 단계용: 테이블 자동 생성
    await init_db()
