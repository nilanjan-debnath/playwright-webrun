# controllers/routes.py
from fastapi import APIRouter, status, HTTPException
from pydantic import AnyHttpUrl
from app.page.v1.services.web_scrap import get_page_content
from app.playwright.browser import AppBrowser
from app.core.logger import logger
from playwright.async_api import Error as PlaywrightError

router = APIRouter(prefix="/api/v1/page", tags=["page", "v1"])

@router.get("/", status_code=status.HTTP_200_OK)
async def get_page(
    url: AnyHttpUrl,
    browser: AppBrowser
) -> str:
    try:
        # Pass the browser instance to your service
        content = await get_page_content(str(url), browser)
        return content
    except PlaywrightError as e:
        # Catch specific errors from Playwright (like timeouts)
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Playwright error: {e.message}",
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        # Don't leak the full exception message in production
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )