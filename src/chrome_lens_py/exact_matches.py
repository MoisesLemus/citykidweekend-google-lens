import html
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote, urlencode, unquote, urljoin, urlparse, urlunparse

import httpx

LENS_UPLOAD_ENDPOINT = "https://lens.google.com/v3/upload"
DEBUG_PLAYWRIGHT_HTML = Path("debug_playwright_final.html")
DEBUG_PLAYWRIGHT_PNG = Path("debug_playwright_final.png")
RETRY_SHELL_MARKERS = (
    "/httpservice/retry/enablejs",
    "knitsail",
    "sg_ss",
    "enablejs",
)
ACTIVE_RETRY_MARKERS = (
    "/httpservice/retry/enablejs",
    "knitsail",
)
BLOCK_MARKERS = (
    "captcha",
    "recaptcha",
    "unusual traffic",
    "automatically detects requests",
)


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def parse_curl(curl_text: str) -> Dict:
    tokens = shlex.split(curl_text.replace("\\\n", " "))
    if not tokens or tokens[0] != "curl":
        raise ValueError("Expected a command starting with curl")

    request = {
        "method": "GET",
        "url": None,
        "headers": {},
        "cookies": {},
        "data": None,
        "follow_redirects": False,
    }

    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in ("-H", "--header"):
            i += 1
            name, value = tokens[i].split(":", 1)
            request["headers"][name.strip()] = value.strip()
        elif token in ("-X", "--request"):
            i += 1
            request["method"] = tokens[i].upper()
        elif token in ("--data", "--data-raw", "--data-binary", "--data-ascii", "-d"):
            i += 1
            request["data"] = tokens[i]
            if request["method"] == "GET":
                request["method"] = "POST"
        elif token in ("-b", "--cookie", "--cookie-jar"):
            i += 1
            if token != "--cookie-jar":
                request["headers"]["Cookie"] = tokens[i]
        elif token in ("-A", "--user-agent"):
            i += 1
            request["headers"]["User-Agent"] = tokens[i]
        elif token in ("-e", "--referer"):
            i += 1
            request["headers"]["Referer"] = tokens[i]
        elif token in ("-L", "--location"):
            request["follow_redirects"] = True
        elif token in ("--compressed", "--http2", "--http3", "-s", "-S", "-i"):
            pass
        elif token.startswith("-"):
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 1
        elif request["url"] is None:
            request["url"] = token
        i += 1

    if not request["url"]:
        raise ValueError("Could not find URL in cURL command")

    cookie_header = request["headers"].get("Cookie") or request["headers"].get("cookie")
    if cookie_header:
        request["cookies"] = parse_cookie_header(cookie_header)
        request["headers"].pop("Cookie", None)
        request["headers"].pop("cookie", None)

    return request


def normalize_request_headers(headers: Dict[str, str]) -> Dict[str, str]:
    excluded = {
        "accept-encoding",
        "connection",
        "content-length",
        "cookie",
        "host",
        "te",
    }
    normalized = {
        key: value for key, value in headers.items() if key.lower() not in excluded
    }
    normalized["Accept-Encoding"] = "gzip, deflate"
    return normalized


def exact_matches_url_from_redirect(redirect_url: str) -> str:
    parsed = urlparse(redirect_url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    query_params["udm"] = ["48"]
    return urlunparse(parsed._replace(query=urlencode(query_params, doseq=True)))


def extract_ids_from_url(url_string: str) -> Dict[str, Optional[str]]:
    query_params = parse_qs(urlparse(url_string).query)
    return {
        "vsrid": query_params.get("vsrid", [None])[-1],
        "gsessionid": query_params.get("gsessionid", [None])[0],
        "lsessionid": query_params.get("lsessionid", [None])[0],
    }


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", value).strip()


def normalize_google_url(value: str) -> str:
    value = html.unescape(value)
    value = value.replace(r"\u003d", "=").replace(r"\u0026", "&")
    value = value.replace("\\/", "/")
    parsed = urlparse(value)
    if parsed.path == "/url":
        params = parse_qs(parsed.query)
        target = params.get("q", params.get("url", [None]))[0]
        if target:
            return unquote(target)
    return value


def extract_result_links(text: str, limit: int = 10) -> List[Dict[str, str]]:
    links = []
    seen = set()
    pattern = re.compile(
        r"<a\b(?P<attrs>[^>]*?)\bhref=(?P<quote>['\"])(?P<href>.*?)(?P=quote)"
        r"(?P<tail>[^>]*)>(?P<body>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    needles = ("ebay", "etsy", "master pieces", "www.ebay.com/itm")

    for match in pattern.finditer(text):
        url = normalize_google_url(match.group("href"))
        body = clean_text(match.group("body"))
        attrs = f"{match.group('attrs')} {match.group('tail')}"
        aria_match = re.search(r"aria-label=(['\"])(.*?)\1", attrs, re.IGNORECASE)
        title = clean_text(aria_match.group(2)) if aria_match else body

        haystack = f"{url} {title}".lower()
        if not any(needle in haystack for needle in needles):
            continue
        if url in seen:
            continue

        seen.add(url)
        links.append({"title": title[:240], "url": url})
        if len(links) >= limit:
            break
    return links


def validate_exact_html(text: str) -> Dict[str, object]:
    lower = text.lower()
    contains_exact_matches = "exact matches" in lower
    contains_ebay = "ebay" in lower
    contains_etsy = "etsy" in lower
    contains_master_pieces = "master pieces" in lower
    contains_ebay_item_url = "www.ebay.com/itm" in lower
    contains_google_block = is_google_block_page(text)
    valid_exact_match_html = (
        contains_exact_matches
        and any(
            (
                contains_ebay,
                contains_etsy,
                contains_master_pieces,
                contains_ebay_item_url,
            )
        )
        and not contains_google_block
    )
    return {
        "valid_exact_match_html": valid_exact_match_html,
        "contains_exact_matches": contains_exact_matches,
        "contains_ebay": contains_ebay,
        "contains_etsy": contains_etsy,
        "contains_master_pieces": contains_master_pieces,
        "contains_ebay_item_url": contains_ebay_item_url,
        "contains_403": "403" in lower,
        "contains_captcha": "captcha" in lower,
        "contains_google_block": contains_google_block,
        "contains_knitsail": "knitsail" in lower,
        "contains_sg_ss": "sg_ss" in lower,
        "first_10_matched_results": extract_result_links(text),
    }


def is_retry_shell(text: str) -> bool:
    lower = text.lower()
    return any(marker.lower() in lower for marker in RETRY_SHELL_MARKERS)


def is_active_retry_page(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in ACTIVE_RETRY_MARKERS)


def is_google_block_page(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in BLOCK_MARKERS)


def is_likely_exact_matches(text: str) -> bool:
    return bool(validate_exact_html(text)["valid_exact_match_html"])


@dataclass
class ExactMatchResponse:
    html: str
    upload_status: int
    redirect_location: str
    exact_url: str
    exact_status: int
    final_url: str
    ids: Dict[str, Optional[str]]
    source: str = "direct_http"


class GoogleLensExactMatchesClient:
    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
        browser_timeout: float = 45.0,
        proxy: Optional[str] = None,
        headless: bool = True,
        profile_dir: Optional[Path] = None,
    ):
        self.headers = normalize_request_headers(headers or {})
        self.cookies = cookies or {}
        self.timeout = timeout
        self.browser_timeout = browser_timeout
        self.proxy = proxy
        self.headless = headless
        self.profile_dir = Path(profile_dir) if profile_dir else None

    @classmethod
    def from_firefox_curl(cls, curl_path: Path, **kwargs):
        request = parse_curl(curl_path.read_text(encoding="utf-8"))
        return cls(
            headers=request["headers"],
            cookies=request["cookies"],
            **kwargs,
        )

    async def fetch_exact_matches(self, image_url: str) -> ExactMatchResponse:
        timeout = httpx.Timeout(self.timeout, connect=15.0)
        async with httpx.AsyncClient(
            cookies=self.cookies,
            follow_redirects=True,
            timeout=timeout,
            http2=True,
            proxy=self.proxy,
        ) as client:
            filename, image_bytes, content_type = await self._fetch_image(client, image_url)
            redirect_location, upload_status = await self._upload_image(
                client, filename, image_bytes, content_type
            )
            exact_url = exact_matches_url_from_redirect(redirect_location)
            html_text, exact_status, final_url = await self._fetch_exact_html(
                client, exact_url, redirect_location
            )

        return ExactMatchResponse(
            html=html_text,
            upload_status=upload_status,
            redirect_location=redirect_location,
            exact_url=exact_url,
            exact_status=exact_status,
            final_url=final_url,
            ids=extract_ids_from_url(redirect_location),
            source="direct_http",
        )

    async def fetch_exact_matches_with_fallback(self, image_url: str) -> ExactMatchResponse:
        direct_result = await self.fetch_exact_matches(image_url)
        if not is_retry_shell(direct_result.html):
            return direct_result
        return await self.fetch_exact_matches_with_firefox(image_url, direct_result)

    async def fetch_exact_matches_with_firefox(
        self, image_url: str, direct_result: ExactMatchResponse
    ) -> ExactMatchResponse:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise RuntimeError(
                "Direct HTTP returned Google retry shell and Playwright is not installed. "
                "Install dependencies with `pip install -r requirements.txt` and run "
                "`python3 -m playwright install firefox`."
            ) from error

        timeout_ms = int(self.browser_timeout * 1000)
        async with async_playwright() as playwright:
            context_options = {
                "locale": "en-US",
                "viewport": {"width": 1365, "height": 900},
            }
            if self.headers.get("User-Agent") and not self.profile_dir:
                context_options["user_agent"] = self.headers["User-Agent"]

            browser = None
            if self.profile_dir:
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                context = await playwright.firefox.launch_persistent_context(
                    str(self.profile_dir),
                    headless=self.headless,
                    **context_options,
                )
            else:
                browser = await playwright.firefox.launch(headless=self.headless)
                context = await browser.new_context(**context_options)

            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            try:
                await page.goto("https://www.google.com/", wait_until="domcontentloaded")
                await self._dismiss_google_consent(page)

                browser_url = await self._open_lens_uploadbyurl(page, image_url)
                if browser_url:
                    direct_result.exact_url = exact_matches_url_from_redirect(browser_url)
                    direct_result.ids = extract_ids_from_url(browser_url)

                await self._open_exact_matches_in_browser(page, direct_result.exact_url)
                html_text = await self._wait_for_browser_exact_html(page)
                final_url = page.url
            except Exception:
                await self._save_playwright_debug(page)
                raise
            finally:
                await context.close()
                if browser:
                    await browser.close()

        return ExactMatchResponse(
            html=html_text,
            upload_status=direct_result.upload_status,
            redirect_location=direct_result.redirect_location,
            exact_url=direct_result.exact_url,
            exact_status=200,
            final_url=final_url,
            ids=direct_result.ids,
            source="playwright_firefox",
        )

    async def _wait_for_browser_exact_html(self, page):
        deadline = time.monotonic() + self.browser_timeout
        last_html = await page.content()

        while time.monotonic() < deadline:
            current_html = await page.content()
            last_html = current_html
            if is_likely_exact_matches(current_html):
                return current_html
            if is_google_block_page(current_html):
                await self._save_playwright_debug(page)
                await page.wait_for_timeout(1000)
                continue

            retry_link = page.locator('a[href*="/httpservice/retry/enablejs"], a[href*="emsg=SG_REL"]').first
            if await retry_link.count():
                try:
                    await retry_link.click(timeout=1500)
                except Exception:
                    pass

            await page.wait_for_timeout(1000)

        validation = validate_exact_html(last_html)
        raise RuntimeError(f"Timed out waiting for Exact Matches HTML: {validation}")

    async def _save_playwright_debug(self, page):
        try:
            DEBUG_PLAYWRIGHT_HTML.write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass
        try:
            await page.screenshot(path=str(DEBUG_PLAYWRIGHT_PNG), full_page=True)
        except Exception:
            pass

    async def _open_lens_uploadbyurl(self, page, image_url: str) -> Optional[str]:
        upload_url = f"https://lens.google.com/uploadbyurl?url={quote(image_url, safe='')}&hl=en"
        try:
            await page.goto(
                upload_url,
                wait_until="domcontentloaded",
                timeout=int(self.browser_timeout * 1000),
            )
            await page.wait_for_timeout(2500)
            return page.url
        except Exception:
            return None

    async def _open_exact_matches_in_browser(self, page, exact_url: str):
        exact_link = page.get_by_text(re.compile(r"exact matches", re.I)).first
        try:
            if await exact_link.count():
                await exact_link.click(timeout=3000)
                await page.wait_for_timeout(1500)
                return
        except Exception:
            pass

        await page.goto(
            exact_url,
            wait_until="domcontentloaded",
            timeout=int(self.browser_timeout * 1000),
        )

    async def _dismiss_google_consent(self, page):
        labels = (
            "Accept all",
            "I agree",
            "Reject all",
            "Accept",
        )
        for label in labels:
            try:
                button = page.get_by_role("button", name=re.compile(label, re.I)).first
                if await button.count():
                    await button.click(timeout=1500)
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    async def _fetch_image(self, client, image_url: str):
        response = await client.get(image_url, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        filename = Path(urlparse(image_url).path).name or "image.jpg"
        return filename, response.content, content_type

    async def _upload_image(self, client, filename: str, image_bytes: bytes, content_type: str):
        headers = self.headers.copy()
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        headers["Origin"] = "https://www.google.com"
        headers["Referer"] = "https://www.google.com/"
        headers["Sec-Fetch-Site"] = "same-site"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Dest"] = "document"

        params = {
            "hl": "en",
            "re": "av",
            "vpw": "1903",
            "vph": "953",
            "ep": "gsbubu",
            "st": str(int(time.time() * 1000)),
        }
        files = {"encoded_image": (filename, image_bytes, content_type)}
        response = await client.post(
            LENS_UPLOAD_ENDPOINT,
            params=params,
            headers=headers,
            files=files,
            follow_redirects=False,
        )
        if response.status_code not in (302, 303, 307, 308):
            response.raise_for_status()

        location = response.headers.get("location")
        if not location:
            raise RuntimeError("Lens upload did not return a redirect location")
        return urljoin(str(response.url), location), response.status_code

    async def _fetch_exact_html(self, client, exact_url: str, referer: str):
        headers = self.headers.copy()
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-User"] = "?1"
        headers.pop("Origin", None)

        response = await client.get(exact_url, headers=headers)
        return response.text, response.status_code, str(response.url)
