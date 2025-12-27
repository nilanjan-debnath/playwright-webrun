import asyncio
from playwright.async_api import (
    Browser,
    Error as PlaywrightError,
    Request,
    Response,
    ConsoleMessage,
)
from app.core.logger import logger
from typing import List
from app.page.v1.models.logs import NetworkLog, DebugResponse
# --- New Debug/Network Log Function ---

# Your stealth script
STEALTH_JS = """
// navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => false });
// chrome runtime
window.chrome = { runtime: {} };
// plugins
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
// languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
// Permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications' ?
    Promise.resolve({ state: 'granted' }) :
    originalQuery(parameters)
);
// Mock platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
"""


async def get_network_logs(
    url: str, browser: Browser, wait_seconds: int = 5, include_body: bool = False
) -> DebugResponse:
    """
    Loads a page, injects stealth scripts, captures all network and console
    logs, and returns them in a structured format.
    """
    logs: List[NetworkLog] = []

    # --- Define event handlers ---
    def log_console(msg: ConsoleMessage):
        logs.append(NetworkLog(type="console", message=f"[{msg.type}] {msg.text}"))
        logger.debug(f"[Page Console] {msg.type}: {msg.text}")

    async def log_request(req: Request):
        body = None
        if include_body and req.post_data:
            body = req.post_data

        logs.append(
            NetworkLog(
                type="request",
                method=req.method,
                url=req.url,
                resourceType=req.resource_type,
                headers=req.headers,
                body=body,
            )
        )

    async def log_response(res: Response):
        body = None
        if include_body:
            try:
                # Attempt to get text, might fail for binary or if closed
                body = await res.text()
            except Exception:
                pass

        logs.append(
            NetworkLog(
                type="response",
                status=res.status,
                url=res.url,
                resourceType=res.request.resource_type,
                headers=res.headers,
                body=body,
            )
        )
        # Log XHR/fetch specifically
        if res.request.resource_type in ("xhr", "fetch"):
            logger.debug(
                f"  <-- XHR/fetch Response: {res.status} {res.request.method} {res.url}"
            )

    # --- Create context with your settings ---
    logger.debug(f"Creating new debug context for {url}")
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.90 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="Asia/Kolkata",
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    # Inject stealth script
    await context.add_init_script(STEALTH_JS)

    page = await context.new_page()

    # Attach event listeners
    page.on("console", log_console)
    page.on("request", log_request)
    page.on("response", log_response)

    try:
        logger.debug(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)

        # Wait for network to settle
        try:
            logger.debug("Waiting for networkidle...")
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.debug("Network is idle.")
        except PlaywrightError:
            logger.warning("networkidle timed out, proceeding anyway.")

        # Wait for additional time for delayed XHRs
        logger.debug(f"Waiting for {wait_seconds}s for delayed scripts...")
        # Use non-blocking sleep!
        await asyncio.sleep(wait_seconds)
        page_title = "N/A"
        try:
            page_title = await page.title()
        except Exception as e:
            logger.warning(f"Could not get page title: {e}")

        final_url = page.url

        logger.info(f"Log collection finished for {url}. Total logs: {len(logs)}")

        return DebugResponse(
            page_title=page_title, final_url=final_url, total_logs=len(logs), logs=logs
        )
    finally:
        # Ensure context and page are closed
        await page.close()
        await context.close()
        logger.debug("Debug context closed.")
