import asyncio
import trafilatura
from playwright.async_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
from app.core.logger import logger


class ScrapingError(Exception):
    pass


async def run(browser: Browser, url: str, max_retries: int = 2) -> str:
    # 1. CHANGED: 'networkidle' is much better for dynamic text than 'domcontentloaded'
    wait_strategies = ["networkidle", "domcontentloaded", "load"]

    for attempt in range(max_retries + 1):
        context = None
        page = None
        try:
            logger.debug(f"Attempt {attempt + 1}/{max_retries + 1} for {url}")

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
                java_script_enabled=True,
            )

            # Block media to save bandwidth, but be careful blocking too much
            # (sometimes blocking fonts/icons breaks page scripts)
            await context.route(
                "**/*.{png,jpg,jpeg,gif,webp}",  # Removed fonts/svg/ico to be safer
                lambda route: route.abort(),
            )

            page = await context.new_page()

            html = await _navigate_with_fallback(page, url, wait_strategies)

            if html and len(html.strip()) > 500:
                return html
            else:
                # If content is short, it might be a CAPTCHA or error page
                raise ScrapingError(f"Retrieved content too short ({len(html)} chars)")

        except (PlaywrightTimeoutError, PlaywrightError, Exception) as e:
            logger.warning(f"Error on attempt {attempt + 1}: {e}")
            await _safe_cleanup(page, context)
            if attempt < max_retries:
                await asyncio.sleep(2**attempt)

        # Cleanup if success to avoid leaks
        await _safe_cleanup(page, context)

    raise ScrapingError(f"Failed to scrape {url} after {max_retries + 1} attempts")


async def _navigate_with_fallback(
    page: Page, url: str, wait_strategies: list[str]
) -> str:
    for strategy in wait_strategies:
        try:
            logger.debug(f"Navigating with wait_until='{strategy}'")
            response = await page.goto(url, timeout=30000, wait_until=strategy)

            if response and response.status >= 400:
                logger.warning(f"HTTP {response.status} for {url}")

            # 2. NEW: Scroll down to trigger lazy loading (Vital for modern sites)
            await _auto_scroll(page)

            # 3. NEW: Wait for text stability instead of just a generic selector
            await _wait_for_text_content(page)

            return await page.content()

        except PlaywrightTimeoutError:
            logger.debug(f"Strategy '{strategy}' timed out, trying next...")
            continue

    # Last ditch effort: if all strategies fail, return whatever we have
    try:
        return await page.content()
    except Exception as e:
        logger.error(
            f"Failed to collect page content tying all navigation strategies. \n\nException: \n{e}"
        )
        raise PlaywrightTimeoutError(f"All navigation strategies failed for {url}")


async def _auto_scroll(page: Page):
    """
    Slowly scrolls to the bottom of the page to trigger lazy loading.
    """
    try:
        # Get scroll height
        last_height = await page.evaluate("document.body.scrollHeight")

        # Scroll in chunks
        for i in range(3):  # Scroll 3 times max to save time
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)  # Wait for content to load

            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Scroll back to top (some sites hide content if you are at the bottom)
        await page.evaluate("window.scrollTo(0, 0)")
    except Exception as e:
        logger.warning(f"Scroll failed: {e}")


async def _wait_for_text_content(page: Page) -> None:
    """
    Waits until the page seems to have meaningful text content.
    """
    try:
        # Wait for at least one paragraph with some length
        # This prevents grabbing the page before the main article loads
        await page.wait_for_selector("p, article, [role='main']", timeout=5000)
    except Exception as e:
        logger.warning(
            f"Timeout waiting for selector=\"p, article, [role='main']\" \n\nException: \n{e}"
        )
        pass

    # Give a final "settle" time for hydration (React/Vue)
    await page.wait_for_timeout(2000)


async def _safe_cleanup(page: Page | None, context: any) -> None:
    if page:
        try:
            await page.close()
        except Exception as e:
            logger.warning(f"Failed to close the page \n\nException: \n{e}")
    if context:
        try:
            await context.close()
        except Exception as e:
            logger.warning(f"Failed to close context \n\nException: \n{e}")


async def get_page_content(
    url: str, browser: Browser, format: str = "text", max_retries: int = 2
) -> str:
    html = await run(browser, url=url, max_retries=max_retries)

    if format.lower() == "html":
        return html

    content = trafilatura.extract(
        html, include_links=False, include_images=False, include_comments=False
    )

    if not content:
        return "No main content extracted."

    return content
