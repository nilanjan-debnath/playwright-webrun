import random
import asyncio
from typing import Literal
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import Browser, Page, Route, Request as PlaywrightRequest
from fastapi import HTTPException, status
import trafilatura
from app.core.logger import logger

# Thread pool for CPU-bound trafilatura extraction
_executor = ThreadPoolExecutor(max_workers=4)

# User agents for rotation (updated, realistic agents)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# Resource types to block for faster loading
BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font", "stylesheet"})

# URL patterns to block (analytics, ads, tracking)
BLOCKED_URL_PATTERNS = (
    "google-analytics.com",
    "googletagmanager.com",
    "facebook.net",
    "doubleclick.net",
    "googlesyndication.com",
    "adservice.google",
    "analytics.",
    "tracking.",
    "advertisement",
    "/ads/",
    "hotjar.com",
    "mixpanel.com",
    "segment.io",
    "amplitude.com",
)

# Stealth JavaScript to inject
STEALTH_SCRIPT = """
() => {
    // Override webdriver property
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });

    // Override plugins
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

    // Override languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true,
    });

    // Add chrome runtime
    if (!window.chrome) {
        window.chrome = {};
    }
    window.chrome.runtime = { id: undefined };

    // Override permissions
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }

    // Override connection rtt
    if (navigator.connection) {
        Object.defineProperty(navigator.connection, 'rtt', {
            get: () => 50,
            configurable: true,
        });
    }

    // Mask automation indicators in Error stack traces
    const originalError = Error;
    window.Error = function(...args) {
        const error = new originalError(...args);
        const stack = error.stack;
        if (stack) {
            error.stack = stack.replace(/\\n.*playwright.*\\n/gi, '\\n');
        }
        return error;
    };
    window.Error.prototype = originalError.prototype;

    // Override toString for various functions to avoid detection
    const nativeToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === navigator.permissions.query) {
            return 'function query() { [native code] }';
        }
        return nativeToString.call(this);
    };
}
"""


async def _handle_route(route: Route, request: PlaywrightRequest) -> None:
    """Handle route - block unnecessary resources for faster loading."""
    resource_type = request.resource_type
    url = request.url.lower()

    # Block by resource type
    if resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return

    # Block by URL pattern
    if any(pattern in url for pattern in BLOCKED_URL_PATTERNS):
        await route.abort()
        return

    await route.continue_()


async def _create_stealth_page(browser: Browser, user_agent: str) -> Page:
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Cache-Control": "max-age=0",
            "DNT": "1",
        },
    )

    page = await context.new_page()

    # Inject stealth scripts before any navigation
    await page.add_init_script(STEALTH_SCRIPT)

    # Set up resource blocking
    await page.route("**/*", _handle_route)

    return page


async def _wait_for_content(page: Page) -> None:
    """Wait for page content to load using multiple strategies."""
    try:
        # Primary: wait for network idle
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        try:
            # Fallback: wait for DOM content loaded
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

    # Try to wait for main content selectors
    content_selectors = ["article", "main", '[role="main"]', ".content", "#content"]
    for selector in content_selectors:
        try:
            await page.wait_for_selector(selector, timeout=2000, state="attached")
            break
        except Exception:
            continue

    # Small random delay to mimic human behavior and allow JS rendering
    await asyncio.sleep(random.uniform(0.3, 0.8))


def _extract_with_trafilatura(html: str, output_format: str) -> str | None:
    """
    Synchronous trafilatura extraction (runs in thread pool).
    """
    common_kwargs = {
        "include_tables": True,
        "include_comments": False,
        "favor_precision": False,
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
            **common_kwargs,
        )
    else:
        return trafilatura.extract(
            html,
            output_format="txt",
            include_links=False,
            include_images=False,
            include_formatting=False,
            **common_kwargs,
        )


async def _extract_content_async(html: str, output_format: str) -> str | None:
    """Run trafilatura extraction in thread pool to avoid blocking."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor,
        partial(_extract_with_trafilatura, html, output_format),
    )


async def _get_fallback_content(page: Page, output_format: str) -> str:
    """Get fallback content when trafilatura extraction fails."""
    if output_format == "html":
        # Get the body innerHTML
        return await page.evaluate(
            """() => {
                const article = document.querySelector('article') ||
                               document.querySelector('main') ||
                               document.querySelector('[role="main"]') ||
                               document.body;
                return article.innerHTML;
            }"""
        )
    else:
        # Get clean text content
        return await page.evaluate(
            """() => {
                // Remove script and style elements
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, noscript, iframe, nav, footer, header, aside')
                    .forEach(el => el.remove());

                // Get text content
                return clone.innerText || clone.textContent || '';
            }"""
        )


async def get_page_content(
    url: str,
    browser: Browser,
    output_format: Literal["text", "html"] = "text",
    timeout: int = 30000,
) -> str:
    """
    Fetch and extract page content using Playwright with anti-bot measures.

    Args:
        url: The URL to fetch
        browser: Playwright browser instance
        output_format: Output format - 'text' or 'html'
        timeout: Navigation timeout in milliseconds

    Returns:
        Extracted content as string

    Raises:
        HTTPException: On various error conditions
    """
    page: Page | None = None

    try:
        # Select random user agent
        user_agent = random.choice(USER_AGENTS)
        logger.debug(f"Fetching URL: {url}")

        # Create stealth page
        page = await _create_stealth_page(browser, user_agent)

        # Navigate with retries
        response = None
        last_error = None

        for attempt in range(2):
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout,
                )
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Facing exception in {attempt=} \n\nException: \n{last_error}"
                )
                if attempt < 1:
                    await asyncio.sleep(1)
                    continue
                raise

        if response is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to receive response from target URL",
            )

        # Check for error status codes
        if response.status >= 400:
            status_code = (
                status.HTTP_404_NOT_FOUND
                if response.status == 404
                else status.HTTP_502_BAD_GATEWAY
            )
            raise HTTPException(
                status_code=status_code,
                detail=f"Target URL returned HTTP {response.status}",
            )

        # Wait for content to load
        await _wait_for_content(page)

        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(0.3)

        # Get page HTML
        html_content = await page.content()

        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="Page returned empty or minimal content",
            )

        # Extract content using trafilatura (in thread pool)
        extracted_content = await _extract_content_async(html_content, output_format)

        # Fallback if trafilatura fails
        if not extracted_content or len(extracted_content.strip()) < 50:
            logger.warning(
                f"Trafilatura extraction insufficient for {url}, using fallback"
            )
            extracted_content = await _get_fallback_content(page, output_format)

        if not extracted_content or len(extracted_content.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="Could not extract meaningful content from the page",
            )

        logger.info(
            f"Successfully extracted content from {url} "
            f"(format={output_format}, length={len(extracted_content)})"
        )

        return extracted_content.strip()

    except HTTPException:
        raise

    except asyncio.TimeoutError:
        logger.error(f"Timeout while fetching {url}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Request timed out while fetching the page",
        )

    except Exception as e:
        logger.error(f"Error fetching {url}: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch page content: {type(e).__name__}",
        )

    finally:
        # Cleanup: close page and its context
        if page:
            context = page.context
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
