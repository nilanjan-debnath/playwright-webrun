from contextlib import asynccontextmanager
from fastapi import FastAPI
from playwright.async_api import async_playwright, Browser, Playwright
from app.core.logger import logger

# Store instances in a dictionary to be attached to app.state
playwright_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the Playwright browser lifecycle.
    """
    logger.info("FastAPI app starting up...")
    try:
        logger.info("Starting Playwright...")
        playwright: Playwright = await async_playwright().start()

        # Add the stealth arguments from your debug.py
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

        # Store instances in the state dictionary
        playwright_state["playwright"] = playwright
        playwright_state["browser"] = browser

        # Make them available in app.state
        app.state.playwright = playwright
        app.state.browser = browser

        logger.info(
            f"Playwright started and browser launched successfully with args: {browser_args}"
        )
        yield

    finally:
        logger.info("FastAPI app shutting down...")
        browser = playwright_state.get("browser")
        playwright = playwright_state.get("playwright")

        if browser:
            logger.info("Closing browser...")
            await browser.close()
        if playwright:
            logger.info("Stopping Playwright...")
            await playwright.stop()
        logger.info("Cleanup finished.")
