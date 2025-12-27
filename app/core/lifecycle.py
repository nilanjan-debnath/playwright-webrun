from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.playwright.browser import start_browser
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
        playwright, browser = await start_browser()

        # Store instances in the state dictionary
        playwright_state["playwright"] = playwright
        playwright_state["browser"] = browser

        # Make them available in app.state
        app.state.playwright = playwright
        app.state.browser = browser

        logger.info("Playwright started and browser launched successfully")
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
