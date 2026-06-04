import asyncio
import html
import json
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

CURL_FILE = Path("experiments/firefox_exact_match.curl")
OUTPUT_HTML = Path("firefox_replay_exact_match.html")


def parse_curl(curl_text):
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
            # Skip unknown option argument when it has a separate value.
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


def parse_cookie_header(cookie_header):
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def validation_for(text, content):
    lower = text.lower()
    return {
        "contains_exact_matches": "exact matches" in lower,
        "contains_ebay": "ebay" in lower,
        "contains_etsy": "etsy" in lower,
        "contains_master_pieces": "master pieces" in lower,
        "contains_ebay_item_url": "www.ebay.com/itm" in lower,
        "contains_403": "403" in lower,
        "contains_captcha": "captcha" in lower,
        "contains_knitsail": "knitsail" in lower,
        "contains_sg_ss": "sg_ss" in lower,
        "body_bytes": len(content),
        "saved_to": str(OUTPUT_HTML),
    }


def clean_text(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_google_url(value):
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


def extract_result_links(text, limit=10):
    links = []
    seen = set()
    href_pattern = re.compile(
        r"<a\b(?P<attrs>[^>]*?)\bhref=(?P<quote>['\"])(?P<href>.*?)(?P=quote)(?P<tail>[^>]*)>(?P<body>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )

    for match in href_pattern.finditer(text):
        raw_href = match.group("href")
        url = normalize_google_url(raw_href)
        lower_url = url.lower()
        body = clean_text(match.group("body"))
        attrs = f"{match.group('attrs')} {match.group('tail')}"
        aria_match = re.search(r"aria-label=(['\"])(.*?)\1", attrs, re.IGNORECASE | re.DOTALL)
        title = clean_text(aria_match.group(2)) if aria_match else body

        is_match = any(
            needle in lower_url or needle in title.lower()
            for needle in ("ebay", "etsy", "master pieces", "www.ebay.com/itm")
        )
        if not is_match:
            continue
        if url in seen:
            continue

        seen.add(url)
        links.append({"title": title[:240], "url": url})
        if len(links) >= limit:
            break

    return links


def normalize_accept_encoding(headers):
    for key, value in list(headers.items()):
        if key.lower() != "accept-encoding":
            continue

        encodings = [
            item.strip()
            for item in value.split(",")
            if item.strip() and item.strip().lower() in {"gzip", "deflate"}
        ]
        if encodings:
            headers[key] = ", ".join(encodings)
        else:
            headers.pop(key)
        return


def summarize_request(request):
    parsed = urlparse(request["url"])
    params = parse_qs(parsed.query, keep_blank_values=True)
    interesting_params = {
        key: params.get(key)
        for key in (
            "udm",
            "vsrid",
            "vsint",
            "gsessionid",
            "lsessionid",
            "source",
            "lns_surface",
            "lns_vfs",
            "qsubts",
            "biw",
            "bih",
            "hl",
            "sei",
            "ved",
            "sca_esv",
        )
        if key in params
    }
    interesting_headers = {
        key: value
        for key, value in request["headers"].items()
        if key.lower()
        in {
            "accept",
            "accept-language",
            "user-agent",
            "referer",
            "sec-fetch-site",
            "sec-fetch-mode",
            "sec-fetch-dest",
            "sec-fetch-user",
            "upgrade-insecure-requests",
        }
    }
    return {
        "method": request["method"],
        "url_host": parsed.netloc,
        "url_path": parsed.path,
        "interesting_params": interesting_params,
        "interesting_headers": interesting_headers,
        "cookie_names": sorted(request["cookies"].keys()),
    }


async def replay():
    if not CURL_FILE.exists():
        raise FileNotFoundError(
            f"{CURL_FILE} is missing. Save Firefox DevTools Copy as cURL there first."
        )

    request = parse_curl(CURL_FILE.read_text(encoding="utf-8"))
    # Firefox exports zstd in Accept-Encoding. httpx may not decode it in this env.
    normalize_accept_encoding(request["headers"])
    timeout = httpx.Timeout(60.0, connect=15.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async with httpx.AsyncClient(
        cookies=request["cookies"],
        follow_redirects=request["follow_redirects"],
        timeout=timeout,
        limits=limits,
        http2=True,
    ) as client:
        response = await client.request(
            request["method"],
            request["url"],
            headers=request["headers"],
            content=request["data"],
        )
        text = response.text
        content = response.content

    OUTPUT_HTML.write_text(text, encoding="utf-8")
    result_links = extract_result_links(text)
    return {
        "request_summary": summarize_request(request),
        "status_code": response.status_code,
        "final_url": str(response.url),
        "history": [
            {"status_code": item.status_code, "location": item.headers.get("location")}
            for item in response.history
        ],
        "validation": validation_for(text, content),
        "first_10_matched_results": result_links,
    }


if __name__ == "__main__":
    try:
        result = asyncio.run(replay())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, sort_keys=True))
