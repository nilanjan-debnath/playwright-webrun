from fastapi import Request, Depends
from playwright.async_api import Browser
from typing import Annotated


def get_browser(request: Request) -> Browser:
    """
    Dependency to get the persistent browser instance from the app state.
    """
    return request.app.state.browser

AppBrowser = Annotated[Browser, Depends(get_browser)]
