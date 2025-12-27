import random
import asyncio
import re
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
from playwright_stealth import Stealth
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

# URL patterns to block
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

# Content selectors for job pages (priority order)
JOB_CONTENT_SELECTORS = [
    '[data-testid="job-detail"]',
    '[data-testid="job-description"]',
    '[class*="job-description"]',
    '[class*="jobDescription"]',
    '[class*="JobDescription"]',
    '[class*="position-description"]',
    '[class*="job-detail"]',
    '[class*="jobDetail"]',
    '[class*="job-content"]',
    '[class*="jobContent"]',
    '[class*="career-detail"]',
    '[id*="job-description"]',
    '[id*="jobDescription"]',
    'article[class*="job"]',
    'section[class*="job"]',
    'div[class*="job"][class*="detail"]',
]

# Generic content selectors (fallback)
GENERIC_CONTENT_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    ".content",
    "#content",
    "#main-content",
    ".main-content",
]

# DOM cleaning script
DOM_CLEANING_SCRIPT = """
() => {
    const removeSelectors = [
        'script', 'style', 'noscript', 'iframe', 'svg', 'canvas', 'video', 'audio',
        'nav', 'header', 'footer', 'aside',
        '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]', '[role="complementary"]',
        '[aria-hidden="true"]',
        '[class*="cookie"]', '[class*="Cookie"]', '[class*="banner"]', '[class*="Banner"]',
        '[class*="popup"]', '[class*="Popup"]', '[class*="modal"]', '[class*="Modal"]',
        '[class*="overlay"]', '[class*="Overlay"]', '[class*="sidebar"]', '[class*="Sidebar"]',
        '[class*="footer"]', '[class*="Footer"]', '[class*="header"]', '[class*="Header"]',
        '[class*="navbar"]', '[class*="Navbar"]', '[class*="nav-"]', '[class*="Nav-"]',
        '[class*="menu"]', '[class*="Menu"]', '[class*="share"]', '[class*="Share"]',
        '[class*="social"]', '[class*="Social"]', '[class*="breadcrumb"]', '[class*="Breadcrumb"]',
        '[class*="related"]', '[class*="Related"]', '[class*="similar"]', '[class*="Similar"]',
        '[class*="recommendation"]', '[class*="Recommendation"]',
        '[class*="language-selector"]', '[class*="LanguageSelector"]',
        '[id*="cookie"]', '[id*="banner"]', '[id*="popup"]', '[id*="modal"]',
        '[id*="nav"]', '[id*="menu"]', '[id*="sidebar"]', '[id*="footer"]', '[id*="header"]',
    ];

    removeSelectors.forEach(selector => {
        try {
            document.querySelectorAll(selector).forEach(el => el.remove());
        } catch (e) {}
    });
}
"""


async def _handle_route(route: Route, request: PlaywrightRequest) -> None:
    """Block tracking/analytics resources."""
    url = request.url.lower()
    if any(pattern in url for pattern in BLOCKED_URL_PATTERNS):
        await route.abort()
        return
    await route.continue_()


async def _create_stealth_page(
    browser: Browser,
    stealth: Stealth | None = None,
    user_agent: str | None = None,
) -> Page:
    """
    Create a new browser context and page with stealth applied.

    If using Stealth().use_async(), stealth is auto-applied to new contexts.
    This function still sets up custom headers and resource blocking.
    """
    user_agent = user_agent or random.choice(USER_AGENTS)

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

    # If stealth wasn't applied globally via use_async(), apply it manually
    if stealth and hasattr(stealth, "apply_stealth_async"):
        try:
            await stealth.apply_stealth_async(context)
            logger.debug("Stealth applied to context manually")
        except Exception as e:
            logger.debug(f"Stealth already applied or error: {e}")

    page = await context.new_page()

    # Set up resource blocking
    await page.route("**/*", _handle_route)

    return page


async def _navigate_with_retry(
    page: Page, url: str, timeout: int = 45000
) -> Response | None:
    """Navigate to URL with multiple strategies."""
    strategies = [
        {"wait_until": "commit", "timeout": timeout},
        {"wait_until": "domcontentloaded", "timeout": timeout},
    ]

    last_error = None
    for i, strategy in enumerate(strategies):
        try:
            logger.debug(f"Navigation attempt {i + 1}: {strategy['wait_until']}")
            response = await page.goto(url, **strategy)

            if strategy["wait_until"] == "commit":
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

            return response

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()
            if any(
                x in error_msg
                for x in ["net::err_name_not_resolved", "net::err_connection_refused"]
            ):
                raise

            if i < len(strategies) - 1:
                await asyncio.sleep(1)

    if last_error:
        raise last_error
    return None


async def _wait_for_content_render(page: Page, timeout: int = 20000) -> bool:
    """Wait for content to render."""
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
    except Exception:
        pass

    # Try job-specific selectors first
    for selector in JOB_CONTENT_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=2000, state="attached")
            logger.debug(f"Found job content: {selector}")
            return True
        except Exception:
            continue

    # Try generic selectors
    for selector in GENERIC_CONTENT_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=1500, state="attached")
            return True
        except Exception:
            continue

    # Wait for text content
    try:
        await page.wait_for_function(
            "() => (document.body?.innerText || '').length > 300",
            timeout=5000,
        )
        return True
    except Exception:
        return False


async def _scroll_and_wait(page: Page) -> None:
    """Scroll to trigger lazy loading."""
    try:
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(r => setTimeout(r, ms));
                for (let y = 0; y < Math.min(document.body.scrollHeight, 3000); y += 400) {
                    window.scrollTo(0, y);
                    await delay(100);
                }
                window.scrollTo(0, 0);
            }
        """)
    except Exception:
        pass
    await asyncio.sleep(0.5)


async def _clean_dom(page: Page) -> None:
    """Clean the DOM by removing noise elements."""
    try:
        await page.evaluate(DOM_CLEANING_SCRIPT)
    except Exception as e:
        logger.debug(f"DOM cleaning error: {e}")


async def _extract_job_content(page: Page) -> str | None:
    """Try to extract job-specific content directly."""
    for selector in JOB_CONTENT_SELECTORS:
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                if text and len(text.strip()) > 100:
                    logger.debug(f"Extracted from selector: {selector}")
                    return text.strip()
        except Exception:
            continue
    return None


async def _check_real_404(page: Page) -> bool:
    """Check if page is a real 404."""
    try:
        return await page.evaluate("""
            () => {
                const text = (document.body?.innerText || '').toLowerCase();
                if (text.length < 300) {
                    const notFound = ['page not found', '404', 'not found', 'does not exist'];
                    return notFound.some(s => text.includes(s));
                }
                const jobTerms = ['apply', 'description', 'responsibilities', 'qualifications', 'requirements', 'experience'];
                return !jobTerms.some(t => text.includes(t));
            }
        """)
    except Exception:
        return True


def _clean_extracted_text(text: str) -> str:
    """Clean up extracted text by removing noise patterns."""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    skip_patterns = [
        re.compile(r"^\s*\{.*\}\s*$"),
        re.compile(r"^\s*\[.*\]\s*$"),
        re.compile(r'"[a-zA-Z_]+"\s*:\s*'),
        re.compile(r"var\s*\(\s*--"),
        re.compile(r"--[a-z-]+:\s*"),
        re.compile(r"^\s*#[0-9a-fA-F]{3,8}\s*$"),
        re.compile(r"^-\s*$"),
        re.compile(
            r"^\s*-\s*(About|Home|Contact|Careers|Jobs|Menu|Search|Login|Sign)\s*$",
            re.I,
        ),
        re.compile(
            r"^(English|Español|Français|Deutsch|中文|日本語|English-UK)\s*$", re.I
        ),
        re.compile(r"^(English\s+)+", re.I),
        re.compile(r"themeOptions|customTheme|varTheme", re.I),
        re.compile(r"pcsx-|primary-color|accent-color|button-", re.I),
        re.compile(r"^\s*$"),
    ]

    seen_short_lines = {}

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if any(p.search(line) for p in skip_patterns):
            continue

        if len(line) < 50:
            seen_short_lines[line] = seen_short_lines.get(line, 0) + 1
            if seen_short_lines[line] > 2:
                continue

        alpha_ratio = sum(c.isalpha() or c.isspace() for c in line) / max(len(line), 1)
        if alpha_ratio < 0.5 and len(line) > 20:
            continue

        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Deduplicate paragraphs
    paragraphs = result.split("\n\n")
    seen_paragraphs = set()
    unique_paragraphs = []

    for para in paragraphs:
        para_normalized = " ".join(para.split()).lower()
        if len(para_normalized) > 20:
            if para_normalized not in seen_paragraphs:
                seen_paragraphs.add(para_normalized)
                unique_paragraphs.append(para)
        else:
            unique_paragraphs.append(para)

    return "\n\n".join(unique_paragraphs).strip()


def _clean_html_content(html: str) -> str:
    """Pre-clean HTML before trafilatura processing."""
    if not html:
        return ""

    html = re.sub(
        r'<script[^>]*>[\s\S]*?\{[\s\S]*?"[a-zA-Z]+"[\s\S]*?\}[\s\S]*?</script>',
        "",
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(r'\{"\w+"\s*:\s*\{[^}]+\}[^}]*\}', "", html)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<noscript[^>]*>[\s\S]*?</noscript>", "", html, flags=re.IGNORECASE)

    return html


def _extract_with_trafilatura(html: str, output_format: str) -> str | None:
    """Synchronous trafilatura extraction."""
    html = _clean_html_content(html)

    kwargs = {
        "include_tables": True,
        "include_comments": False,
        "favor_recall": True,
        "deduplicate": True,
        "no_fallback": False,
    }

    if output_format == "html":
        result = trafilatura.extract(
            html,
            output_format="html",
            include_links=True,
            include_images=False,
            include_formatting=True,
            **kwargs,
        )
    else:
        result = trafilatura.extract(
            html,
            output_format="txt",
            include_links=False,
            include_images=False,
            **kwargs,
        )

    if result and output_format == "text":
        result = _clean_extracted_text(result)

    return result


async def _extract_content_async(html: str, output_format: str) -> str | None:
    """Run trafilatura in thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor,
        partial(_extract_with_trafilatura, html, output_format),
    )


async def _get_fallback_content(page: Page, output_format: str) -> str:
    """Fallback content extraction via JS."""
    job_content = await _extract_job_content(page)
    if job_content and len(job_content) > 100:
        if output_format == "text":
            return _clean_extracted_text(job_content)
        return job_content

    if output_format == "html":
        result = await page.evaluate("""
            () => {
                const el = document.querySelector('article, main, [role="main"]') || document.body;
                return el?.innerHTML || '';
            }
        """)
    else:
        result = await page.evaluate("""
            () => {
                const selectors = [
                    '[class*="job-description"]',
                    '[class*="jobDescription"]',
                    '[class*="job-detail"]',
                    '[class*="position"]',
                    'article', 'main', '[role="main"]',
                ];

                let el = null;
                for (const s of selectors) {
                    el = document.querySelector(s);
                    if (el && el.innerText.length > 200) break;
                }
                if (!el) el = document.body;

                return (el.innerText || '').trim();
            }
        """)
        result = _clean_extracted_text(result)

    return result or ""


async def get_page_content(
    url: str,
    browser: Browser,
    output_format: Literal["text", "html"] = "text",
    timeout: int = 45000,
    stealth: Stealth | None = None,
) -> str:
    """
    Fetch and extract page content using Playwright with stealth.

    Args:
        url: The URL to fetch
        browser: Playwright browser instance
        output_format: Output format - 'text' or 'html'
        timeout: Navigation timeout in milliseconds
        stealth: Optional Stealth instance for manual application
    """
    page: Page | None = None

    try:
        user_agent = random.choice(USER_AGENTS)
        logger.info(f"Fetching: {url}")

        # Create stealth page
        page = await _create_stealth_page(browser, stealth, user_agent)

        # Navigate
        response = await _navigate_with_retry(page, url, timeout=timeout)
        status_code = response.status if response else 200

        # Wait for content
        logger.debug("Waiting for content...")
        await _wait_for_content_render(page, timeout=20000)

        # Handle HTTP errors
        if status_code >= 400:
            is_real_404 = await _check_real_404(page)
            if is_real_404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND
                    if status_code == 404
                    else status.HTTP_502_BAD_GATEWAY,
                    detail=f"Target URL returned HTTP {status_code}",
                )
            logger.info(f"Soft {status_code}, page has content")

        # Scroll to trigger lazy loading
        await _scroll_and_wait(page)

        # Clean DOM
        await _clean_dom(page)

        # Try job-specific extraction first
        if output_format == "text":
            job_content = await _extract_job_content(page)
            if job_content and len(job_content) > 200:
                cleaned = _clean_extracted_text(job_content)
                if len(cleaned) > 150:
                    logger.info(
                        f"Success (job selector): {url} (length={len(cleaned)})"
                    )
                    return cleaned

        # Get HTML and extract
        html_content = await page.content()

        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="Page returned empty content",
            )

        # Extract with trafilatura
        extracted = await _extract_content_async(html_content, output_format)

        # Fallback if needed
        if not extracted or len(extracted.strip()) < 50:
            logger.warning(f"Using fallback for {url}")
            extracted = await _get_fallback_content(page, output_format)

        if not extracted or not extracted.strip():
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="Could not extract content",
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
        logger.error(f"Error: {url}: {e!r}", exc_info=True)
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
