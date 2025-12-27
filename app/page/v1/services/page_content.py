import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
from playwright_stealth import stealth_async
from app.core.logger import logger


class ScrapingError(Exception):
    """Custom exception for scraping failures."""

    pass


async def run(browser: Browser, url: str, max_retries: int = 2) -> str:
    """
    Uses the persistent browser to create a new, isolated context
    and page for scraping with retry logic and fallback strategies.
    """
    last_exception: Exception | None = None

    # Different wait strategies to try (in order of strictness)
    wait_strategies = ["domcontentloaded", "commit"]

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

            # Block unnecessary resources to speed up loading
            await context.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,otf}",
                lambda route: route.abort(),
            )

            page = await context.new_page()
            await stealth_async(page)

            # Try navigation with fallback wait strategies
            html = await _navigate_with_fallback(page, url, wait_strategies)

            if html and len(html.strip()) > 500:
                return html
            else:
                raise ScrapingError(f"Retrieved content too short ({len(html)} chars)")

        except PlaywrightTimeoutError as e:
            last_exception = e
            logger.warning(f"Timeout on attempt {attempt + 1} for {url}: {e}")

        except PlaywrightError as e:
            last_exception = e
            logger.warning(f"Playwright error on attempt {attempt + 1} for {url}: {e}")

        except Exception as e:
            last_exception = e
            logger.error(f"Unexpected error on attempt {attempt + 1} for {url}: {e}")

        finally:
            await _safe_cleanup(page, context)

        # Exponential backoff before retry
        if attempt < max_retries:
            wait_time = 2**attempt
            logger.debug(f"Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)

    raise ScrapingError(
        f"Failed to scrape {url} after {max_retries + 1} attempts"
    ) from last_exception


async def _navigate_with_fallback(
    page: Page, url: str, wait_strategies: list[str]
) -> str:
    """
    Attempts navigation with progressively less strict wait conditions.
    """
    last_error: Exception | None = None

    for strategy in wait_strategies:
        try:
            logger.debug(f"Trying navigation with wait_until='{strategy}'")

            response = await page.goto(
                url=url,
                timeout=45000,  # 45 seconds
                wait_until=strategy,
            )

            if response and response.status >= 400:
                logger.warning(f"HTTP {response.status} for {url}")

            # Try to wait for body, but don't fail if timeout
            await _wait_for_content(page)

            return await page.content()

        except PlaywrightTimeoutError as e:
            last_error = e
            logger.debug(f"Strategy '{strategy}' timed out, trying next...")

            # Even if goto times out, try to get whatever content loaded
            try:
                html = await page.content()
                if html and "<body" in html.lower():
                    logger.info(f"Partial content retrieved despite timeout for {url}")
                    return html
            except Exception:
                pass

            continue

    raise last_error or PlaywrightTimeoutError(
        f"All navigation strategies failed for {url}"
    )


async def _wait_for_content(page: Page) -> None:
    """
    Waits for page content with multiple fallback selectors.
    Non-blocking - logs warning but doesn't raise on timeout.
    """
    selectors_to_try = [
        ("body", 10000),
        ("main", 5000),
        ("div", 5000),
    ]

    for selector, timeout in selectors_to_try:
        try:
            await page.wait_for_selector(selector, state="visible", timeout=timeout)
            logger.debug(f"Selector '{selector}' found and visible")

            # Brief pause for any dynamic content
            await asyncio.sleep(0.5)
            return

        except PlaywrightTimeoutError:
            logger.debug(f"Selector '{selector}' not visible within {timeout}ms")
            continue

    logger.warning("No content selectors matched, proceeding with available content")


async def _safe_cleanup(page: Page | None, context: any) -> None:
    """
    Safely closes page and context, suppressing any errors.
    """
    if page:
        try:
            await page.close()
        except Exception as e:
            logger.debug(f"Error closing page: {e}")

    if context:
        try:
            await context.close()
        except Exception as e:
            logger.debug(f"Error closing context: {e}")
        else:
            logger.debug("Browser context closed.")


async def get_page_content(
    url: str, browser: Browser, format: str = "text", max_retries: int = 2
) -> str:
    """
    Main service function to get page content.

    Args:
        url: The URL to scrape
        browser: Playwright browser instance
        format: 'text' or 'html'
        max_retries: Number of retry attempts

    Returns:
        Page content as text or HTML

    Raises:
        ScrapingError: If scraping fails after all retries
    """
    html = await run(browser, url=url, max_retries=max_retries)

    if format.lower() == "html":
        logger.info(f"Web content (HTML) collected successfully for {url}")
        return html

    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements for cleaner text
    for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        element.decompose()

    content: str = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    content = "\n".join(lines)

    logger.info(f"Web content (text) collected successfully for {url}")
    return content
