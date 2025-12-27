from fastapi import Request, Depends
from playwright.async_api import Browser
from playwright_stealth import Stealth
from typing import Annotated


# Stealth instance with all evasions enabled
def get_stealth_instance() -> Stealth:
    return Stealth(
        navigator_languages_override=("en-US", "en"),
    )


async def get_browser(request: Request) -> Browser:
    """Dependency to get the browser instance."""
    return request.app.state.browser


async def get_stealth(request: Request) -> Stealth:
    """Dependency to get the stealth instance."""
    return request.app.state.stealth


AppBrowser = Annotated[Browser, Depends(get_browser)]
AppStealth = Annotated[Stealth, Depends(get_stealth)]


# Browser args used in lifecycle
BROWSER_ARGS = [
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
