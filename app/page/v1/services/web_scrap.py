# services/web_scrap.py
from bs4 import BeautifulSoup
from playwright.async_api import Browser
from app.core.logger import logger

async def run(browser: Browser, url: str) -> str:
    """
    Uses the persistent browser to create a new, isolated context
    and page for scraping.
    """
    logger.debug("Creating new browser context...")
    # Using a new context is much faster than launching a new browser
    # and provides isolation.
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    
    try:
        logger.debug("Navigating to %s", url)
        await page.goto(url=url, timeout=90000, wait_until="domcontentloaded")
        
        logger.debug("Waiting for page content to become visible...")
        await page.wait_for_selector("body", state="visible", timeout=60000)
        
        html = await page.content()
        return html
    finally:
        # Ensure context and page are closed to free up resources
        await page.close()
        await context.close()
        logger.debug("Browser context closed.")


async def get_page_content(url: str, browser: Browser) -> str:
    """
    Main service function, now requires the browser instance.
    """
    html = await run(browser, url=url)
    soup = BeautifulSoup(html, "html.parser")
    
    # You can simplify your text extraction with get_text()
    content: str = soup.get_text(separator="\n", strip=True)
    
    logger.info(f"Web content collected successfully for {url=}")
    return content
