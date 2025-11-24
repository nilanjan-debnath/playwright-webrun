from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page
from app.core.logger import logger

# --- Existing Functions (Refactored) ---


async def run(browser: Browser, url: str) -> str:
    """
    Uses the persistent browser to create a new, isolated context
    and page for scraping.
    """
    logger.debug("Creating new browser context...")
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    )
    page: Page = await context.new_page()

    try:
        logger.debug("Navigating to %s", url)
        await page.goto(url=url, timeout=90000, wait_until="domcontentloaded")

        logger.debug("Waiting for page content to become visible...")
        await page.wait_for_selector("body", state="visible", timeout=60000)

        html = await page.content()
        return html
    finally:
        await page.close()
        await context.close()
        logger.debug("Browser context closed.")


async def get_page_content(url: str, browser: Browser, format: str = "text") -> str:
    """
    Main service function, now requires the browser instance.
    """
    html = await run(browser, url=url)

    if format.lower() == "html":
        logger.info(f"Web content (HTML) collected successfully for {url=}")
        return html

    soup = BeautifulSoup(html, "html.parser")
    content: str = soup.get_text(separator="\n", strip=True)
    logger.info(f"Web content (text) collected successfully for {url=}")
    return content
