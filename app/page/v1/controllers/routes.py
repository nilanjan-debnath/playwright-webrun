from fastapi import APIRouter, Request, status, HTTPException, Query
from pydantic import AnyHttpUrl
from app.page.v1.services.page_content import get_page_content
from app.page.v1.services.network_logs import get_network_logs
from app.page.v1.models.logs import DebugResponse
from app.playwright.browser import AppBrowser
from playwright.async_api import Error as PlaywrightError
from app.core.logger import logger
from app.core.config import settings
from app.core.ratelimiter import limiter

router = APIRouter(prefix="/api/v1/page", tags=["page", "v1"])


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    responses={200: {"content": {"text/plain": {}}}},
)
@limiter.limit(settings.ratelimit_guest)
async def get_page(
    request: Request,
    url: AnyHttpUrl,
    browser: AppBrowser,
    format: str = Query("text", description="Output format: 'text' or 'html'"),
) -> str:
    """
    Fetches the content of a single page.
    """
    try:
        content = await get_page_content(str(url), browser, format)
        return content
    except PlaywrightError as e:
        logger.error(f"Playwright error for {url}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Playwright error: {e.message}",
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"An unexpected error occurred for {url}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )


@router.get(
    "/debug-network",
    status_code=status.HTTP_200_OK,
    response_model=DebugResponse,
)
@limiter.limit(settings.ratelimit_guest)
async def debug_page_network(
    request: Request,
    url: AnyHttpUrl,
    browser: AppBrowser,
    wait_seconds: int = Query(
        default=5,
        ge=0,
        le=30,
        description="Additional time (in seconds) to wait for delayed network requests after the page is idle.",
    ),
    include_body: bool = Query(
        default=False,
        description="Whether to capture request/response bodies (can be large).",
    ),
) -> DebugResponse:
    """
    Loads a page with stealth settings, captures all console and network
    logs, waits for a few seconds, and returns a JSON report.
    """
    try:
        debug_data = await get_network_logs(
            str(url), browser, wait_seconds, include_body
        )
        return debug_data
    except PlaywrightError as e:
        logger.error(f"Playwright debug error for {url}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Playwright error: {e.message}",
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(
            f"An unexpected debug error occurred for {url}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )
