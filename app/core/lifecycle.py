from fastapi import FastAPI
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from playwright.async_api import async_playwright, Browser, Playwright
from app.core.logger import logger
from app.core.ratelimiter import limiter

playwright_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("FastAPI app starting up...")
    try:
        # setup ratelimiter
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        logger.info("Rate limiter setup complete.")

        logger.info("Starting Playwright...")
        playwright: Playwright = await async_playwright().start()
        browser: Browser = await playwright.chromium.launch()
        
        # Store instances in the state dictionary
        playwright_state["playwright"] = playwright
        playwright_state["browser"] = browser
        
        # Make them available in app.state
        app.state.playwright = playwright
        app.state.browser = browser

        logger.info("Playwright started and browser launched successfully.")

        # Yield control to the application
        yield
    finally:
        # --- Shutdown ---
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