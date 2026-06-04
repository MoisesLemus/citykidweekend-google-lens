import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CHALLENGE_IMAGE_URL = "https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS9m4zOb/$_57.JPG"
DEBUG_HTML = Path("debug_playwright_final.html")
DEBUG_PNG = Path("debug_playwright_final.png")


def main():
    base_url = os.environ.get("PROJECT4_API_URL", "http://127.0.0.1:8000/google-lens")
    image_url = os.environ.get("PROJECT4_IMAGE_URL", CHALLENGE_IMAGE_URL)
    timeout = float(os.environ.get("PROJECT4_API_TIMEOUT", "240"))
    api_key = os.environ.get("LENS_API_KEY")
    url = f"{base_url}?{urlencode({'imageUrl': image_url})}"

    headers = {"Accept": "text/html"}
    if api_key:
        headers["X-API-KEY"] = api_key
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            source = response.headers.get("X-Google-Lens-Source")
            direct_attempt = response.headers.get("X-Google-Lens-Direct-Attempt")
            status = response.status
    except HTTPError as error:
        body = error.read()
        source = error.headers.get("X-Google-Lens-Source")
        direct_attempt = error.headers.get("X-Google-Lens-Direct-Attempt")
        status = error.code

    text = body.decode("utf-8", errors="replace")

    lower = text.lower()
    contains_exact_matches = "exact matches" in lower
    contains_ebay = "ebay" in lower
    contains_etsy = "etsy" in lower
    contains_master_pieces = "master pieces" in lower
    contains_ebay_item_url = "www.ebay.com/itm" in lower
    contains_captcha = any(
        marker in lower
        for marker in (
            "captcha",
            "recaptcha",
            "unusual traffic",
            "automatically detects requests",
        )
    )
    contains_403 = any(
        marker in lower
        for marker in ("403 forbidden", "http error 403", "<title>403", "error 403")
    )
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
        and not contains_captcha
        and not contains_403
    )
    validation = {
        "status": status,
        "source": source,
        "direct_attempt": direct_attempt,
        "direct_attempt_skipped": direct_attempt == "skipped",
        "body_bytes": len(body),
        "valid_exact_match_html": valid_exact_match_html,
        "contains_exact_matches": contains_exact_matches,
        "contains_ebay": contains_ebay,
        "contains_etsy": contains_etsy,
        "contains_master_pieces": contains_master_pieces,
        "contains_ebay_item_url": contains_ebay_item_url,
        "contains_retry_enablejs": "/httpservice/retry/enablejs" in lower,
        "contains_enablejs": "enablejs" in lower,
        "contains_captcha": contains_captcha,
        "contains_403": contains_403,
        "body_preview": text[:500],
    }
    if status == 502:
        validation["debug_html"] = str(DEBUG_HTML.resolve()) if DEBUG_HTML.exists() else None
        validation["debug_png"] = str(DEBUG_PNG.resolve()) if DEBUG_PNG.exists() else None
    print(json.dumps(validation, indent=2, sort_keys=True))

    return 0 if valid_exact_match_html and direct_attempt == "skipped" else 1


if __name__ == "__main__":
    sys.exit(main())
