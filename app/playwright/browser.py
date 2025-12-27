from fastapi import Request, Depends
from playwright.async_api import async_playwright, Playwright, Browser
from typing import Annotated


async def start_browser() -> tuple[Playwright, Browser]:
    playwright: Playwright = await async_playwright().start()

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]

    browser: Browser = await playwright.chromium.launch(
        args=browser_args,
        headless=True,  # Set to False for debugging
        timeout=60000,  # Increase launch timeout
    )
    return playwright, browser


async def get_browser(request: Request) -> Browser:
    """
    Dependency to get the persistent browser instance from the app state.
    """
    return request.app.state.browser


AppBrowser = Annotated[Browser, Depends(get_browser)]
