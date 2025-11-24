from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.ratelimiter import limiter
from app.core.lifecycle import lifespan
from app.core.logger import logger, LoggingMiddleware
from app.page.v1.controllers.routes import router as page_v1_router
from app.playwright.browser import AppBrowser
from app.page.v1.services.page_content import get_page_content
from fastapi import HTTPException, status


# Initialize the FastAPI app with the lifespan manager
app = FastAPI(
    title="FastAPI with Centralized Lifespan",
    docs_url=None if settings.env == "prod" else "/docs",
    redoc_url=None if settings.env == "prod" else "/redoc",
    openapi_url=None if settings.env == "prod" else "/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins.split(" "),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Add Logging middleware
app.add_middleware(LoggingMiddleware)


app.include_router(page_v1_router)


@app.get("/")
@limiter.limit(settings.ratelimit_guest)
async def root(request: Request):
    logger.info("logging message from root endpoint")
    return {"message": f"FastAPI is running on {settings.env} Environment"}


@app.get("/healthz")
@limiter.limit(settings.ratelimit_guest)
async def health_check(request: Request, browser: AppBrowser):
    try:
        # Attempt to scrape a simple, reliable page to verify Playwright is working
        await get_page_content("http://example.com", browser)
        return {"status": "ok", "playwright": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {e}",
        )
