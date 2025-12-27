import random
import asyncio
from typing import Literal
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import (
    Browser,
    Page,
    Route,
    Request as PlaywrightRequest,
    Response,
)
from fastapi import HTTPException, status
import trafilatura
from app.core.logger import logger

# Thread pool for CPU-bound trafilatura extraction
_executor = ThreadPoolExecutor(max_workers=4)

# User agents rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# URL patterns to block (only tracking/ads - NOT resources needed for rendering)
BLOCKED_URL_PATTERNS = (
    "google-analytics.com",
    "googletagmanager.com",
    "facebook.net",
    "doubleclick.net",
    "googlesyndication.com",
    "adservice.google",
    "hotjar.com",
    "mixpanel.com",
    "segment.io",
    "amplitude.com",
    "sentry.io",
    "newrelic.com",
    "nr-data.net",
)

# Content selectors to wait for
CONTENT_SELECTORS = [
    '[data-testid="job-detail"]',
    ".job-description",
    ".job-details",
    ".position-description",
    '[class*="JobDescription"]',
    '[class*="jobDescription"]',
    "article",
    "main",
    '[role="main"]',
    "#root > div > div",
    "#app > div > div",
    "#__next > div > div",
]

# Stealth JavaScript
STEALTH_SCRIPT = """
() => {
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });

    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
            ];
            Object.setPrototypeOf(plugins, PluginArray.prototype);
            return plugins;
        },
        configurable: true,
    });

    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true,
    });

    if (!window.chrome) window.chrome = {};
    window.chrome.runtime = { id: undefined };

    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }
}
"""


async def _handle_route(route: Route, request: PlaywrightRequest) -> None:
    """Block only tracking/analytics - allow everything else for SPAs."""
    url = request.url.lower()

    # Only block known trackers/analytics
    if any(pattern in url for pattern in BLOCKED_URL_PATTERNS):
        await route.abort()
        return

    await route.continue_()


async def _create_stealth_context_and_page(
    browser: Browser,
    user_agent: str,
    block_resources: bool = True,
) -> Page:
    """Create a new browser context and page with stealth settings."""
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={"width": 1920, "height": 1080},
        screen={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York",
        color_scheme="light",
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        java_script_enabled=True,
        ignore_https_errors=True,
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
        },
    )

    page = await context.new_page()
    await page.add_init_script(STEALTH_SCRIPT)

    if block_resources:
        await page.route("**/*", _handle_route)

    return page


async def _navigate_with_retry(
    page: Page,
    url: str,
    timeout: int = 45000,
) -> Response | None:
    """
    Navigate to URL with multiple strategies and retries.
    """
    strategies = [
        {"wait_until": "commit", "timeout": timeout},
        {"wait_until": "domcontentloaded", "timeout": timeout},
        {"wait_until": "load", "timeout": timeout},
    ]

    last_error = None
    response = None

    for i, strategy in enumerate(strategies):
        try:
            logger.debug(
                f"Navigation attempt {i + 1} with strategy: {strategy['wait_until']}"
            )

            response = await page.goto(url, **strategy)

            # If we got here with "commit", wait a bit for content
            if strategy["wait_until"] == "commit":
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass  # Continue anyway

            return response

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()

            # If it's a definitive error, don't retry
            if any(
                x in error_msg
                for x in ["net::err_name_not_resolved", "net::err_connection_refused"]
            ):
                raise

            logger.warning(f"Navigation attempt {i + 1} failed: {type(e).__name__}")

            # Small delay before retry
            if i < len(strategies) - 1:
                await asyncio.sleep(1)
                continue

    # All strategies failed
    if last_error:
        raise last_error

    return response


async def _wait_for_content_render(page: Page, timeout: int = 20000) -> bool:
    """
    Wait for meaningful content to render on the page.
    Returns True if content found, False otherwise.
    """
    start_time = asyncio.get_event_loop().time()

    # Try to wait for network idle first (with short timeout)
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
    except Exception:
        pass

    # Try content selectors
    for selector in CONTENT_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=2000, state="attached")
            logger.debug(f"Found content selector: {selector}")
            return True
        except Exception:
            continue

    # Wait for substantial text content
    remaining = timeout - int((asyncio.get_event_loop().time() - start_time) * 1000)
    if remaining > 0:
        try:
            await page.wait_for_function(
                """() => {
                    const text = document.body?.innerText || '';
                    return text.length > 300;
                }""",
                timeout=remaining,
            )
            return True
        except Exception:
            pass

    return False


async def _scroll_and_wait(page: Page) -> None:
    """Scroll page to trigger lazy loading."""
    try:
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(r => setTimeout(r, ms));
                const height = Math.max(document.body.scrollHeight, 2000);

                for (let y = 0; y < height; y += 400) {
                    window.scrollTo(0, y);
                    await delay(100);
                }
                window.scrollTo(0, 0);
            }
        """)
    except Exception:
        pass

    await asyncio.sleep(0.5)


async def _check_real_404(page: Page) -> bool:
    """Check if page is a real 404 vs soft 404 with content."""
    try:
        return await page.evaluate("""
            () => {
                const text = (document.body?.innerText || '').toLowerCase();

                if (text.length < 300) {
                    const notFound = ['page not found', '404', 'not found', 'does not exist'];
                    return notFound.some(s => text.includes(s));
                }

                // Check for job-related content
                const jobTerms = ['apply', 'description', 'responsibilities', 'qualifications', 'requirements', 'experience'];
                return !jobTerms.some(t => text.includes(t));
            }
        """)
    except Exception:
        return True


def _extract_with_trafilatura(html: str, output_format: str) -> str | None:
    """Synchronous trafilatura extraction."""
    kwargs = {
        "include_tables": True,
        "include_comments": False,
        "favor_recall": True,
        "deduplicate": True,
    }

    if output_format == "html":
        return trafilatura.extract(
            html,
            output_format="html",
            include_links=True,
            include_images=True,
            include_formatting=True,
            **kwargs,
        )
    return trafilatura.extract(
        html,
        output_format="txt",
        include_links=False,
        include_images=False,
        **kwargs,
    )


async def _extract_content_async(html: str, output_format: str) -> str | None:
    """Run trafilatura in thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor,
        partial(_extract_with_trafilatura, html, output_format),
    )


async def _get_fallback_content(page: Page, output_format: str) -> str:
    """Fallback content extraction via JS."""
    if output_format == "html":
        return await page.evaluate("""
            () => {
                const el = document.querySelector('article, main, [role="main"], [class*="job"], [class*="content"]') || document.body;
                return el?.innerHTML || '';
            }
        """)

    return await page.evaluate("""
        () => {
            const selectors = ['article', 'main', '[role="main"]', '[class*="job"]', '[class*="content"]'];
            let el = null;
            for (const s of selectors) {
                el = document.querySelector(s);
                if (el) break;
            }
            if (!el) el = document.body;

            const clone = el.cloneNode(true);
            clone.querySelectorAll('script, style, noscript, iframe, nav, header, footer, aside').forEach(e => e.remove());
            return (clone.innerText || '').trim();
        }
    """)


async def get_page_content(
    url: str,
    browser: Browser,
    output_format: Literal["text", "html"] = "text",
    timeout: int = 45000,
) -> str:
    """
    Fetch and extract page content using Playwright.
    Handles SPAs and JavaScript-heavy sites with retry strategies.
    """
    page: Page | None = None

    try:
        user_agent = random.choice(USER_AGENTS)
        logger.info(f"Fetching: {url}")

        # Create page with stealth settings
        page = await _create_stealth_context_and_page(browser, user_agent)

        # Navigate with retry strategies
        response = await _navigate_with_retry(page, url, timeout=timeout)

        # Get status code (may be None for some navigations)
        status_code = response.status if response else 200

        # Wait for content to render
        logger.debug("Waiting for content to render...")
        content_found = await _wait_for_content_render(page, timeout=20000)

        if not content_found:
            logger.warning(
                f"Content selectors not found for {url}, continuing anyway..."
            )

        # Handle HTTP errors - but check for real 404 on SPAs
        if status_code >= 400:
            is_real_404 = await _check_real_404(page)
            if is_real_404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND
                    if status_code == 404
                    else status.HTTP_502_BAD_GATEWAY,
                    detail=f"Target URL returned HTTP {status_code}",
                )
            logger.info(f"Soft {status_code} detected, page has content")

        # Scroll to trigger lazy loading
        await _scroll_and_wait(page)

        # Get HTML content
        html_content = await page.content()

        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="Page returned empty content",
            )

        # Extract with trafilatura
        extracted = await _extract_content_async(html_content, output_format)

        # Fallback if trafilatura fails
        if not extracted or len(extracted.strip()) < 50:
            logger.warning(f"Using fallback extraction for {url}")
            extracted = await _get_fallback_content(page, output_format)

        if not extracted or not extracted.strip():
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="Could not extract content from page",
            )

        logger.info(f"Success: {url} (length={len(extracted)})")
        return extracted.strip()

    except HTTPException:
        raise

    except asyncio.TimeoutError:
        logger.error(f"Timeout: {url}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Request timed out",
        )

    except Exception as e:
        logger.error(f"Error fetching {url}: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch: {type(e).__name__}",
        )

    finally:
        if page:
            try:
                ctx = page.context
                await page.close()
                await ctx.close()
            except Exception:
                pass
