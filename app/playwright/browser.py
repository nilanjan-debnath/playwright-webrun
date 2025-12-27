from fastapi import Request, Depends
from playwright.async_api import async_playwright, Playwright, Browser
from typing import Annotated


async def start_browser() -> tuple[Playwright, Browser]:
    playwright: Playwright = await async_playwright().start()

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-web-security",
        "--disable-setuid-sandbox",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--start-maximized",
        "--ignore-certificate-errors",
        "--allow-running-insecure-content",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-infobars",
        "--hide-scrollbars",
        "--mute-audio",
    ]

    browser: Browser = await playwright.chromium.launch(args=browser_args)
    return playwright, browser


async def get_browser(request: Request) -> Browser:
    """
    Dependency to get the persistent browser instance from the app state.
    """
    return request.app.state.browser


AppBrowser = Annotated[Browser, Depends(get_browser)]
