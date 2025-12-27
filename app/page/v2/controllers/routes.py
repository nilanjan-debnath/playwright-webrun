from fastapi import APIRouter, Request, status, HTTPException, Query
from pydantic import AnyHttpUrl
from app.page.v2.services.page_content import get_page_content
from app.playwright.browser import AppBrowser
from playwright.async_api import Error as PlaywrightError
from app.core.logger import logger
from app.core.config import settings
from app.core.ratelimiter import limiter

router = APIRouter(prefix="/api/v2/page", tags=["page", "v2"])


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
