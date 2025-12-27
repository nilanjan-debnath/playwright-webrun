from contextlib import asynccontextmanager
from fastapi import FastAPI
from playwright.async_api import async_playwright
from app.playwright.browser import BROWSER_ARGS, get_stealth_instance
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the Playwright browser lifecycle with stealth.
    """
    logger.info("FastAPI app starting up...")

    stealth = get_stealth_instance()

    try:
        logger.info("Starting Playwright with Stealth...")

        # Use stealth as async context manager
        async with stealth.use_async(async_playwright()) as playwright:
            browser = await playwright.chromium.launch(
                args=BROWSER_ARGS,
                headless=True,
                timeout=60000,
            )

            # Store in app state
            app.state.playwright = playwright
            app.state.browser = browser
            app.state.stealth = stealth

            logger.info("Playwright with Stealth started successfully")

            yield

            # Cleanup
            logger.info("Closing browser...")
            await browser.close()

        logger.info("Playwright stopped")

    except Exception as e:
        logger.error(f"Error in lifespan: {e}", exc_info=True)
        raise

    finally:
        logger.info("Cleanup finished.")
