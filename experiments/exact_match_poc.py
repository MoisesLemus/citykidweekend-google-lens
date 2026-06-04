import asyncio
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

LENS_UPLOAD_ENDPOINT = "https://lens.google.com/v3/upload"
COOKIE_FILE = "cookies_lens_test.json"
OUTPUT_HTML = Path("exact_match_test.html")
CHALLENGE_IMAGE_URL = "https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS9m4zOb/$_57.JPG"

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Not-A.Brand";v="8", "Chromium";v="135", "Google Chrome";v="135"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Origin": "https://www.google.com",
    "Referer": "https://www.google.com/",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


async def save_cookies(cookies, cookie_file):
    cookies_dict = {}
    for cookie in cookies.jar:
        cookies_dict[cookie.name] = cookie.value

    with open(cookie_file, "w", encoding="utf-8") as f:
        json.dump(cookies_dict, f, indent=2)


async def load_cookies(cookie_file):
    if not os.path.exists(cookie_file):
        return {}

    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def extract_ids_from_url(url_string):
    query_params = parse_qs(urlparse(url_string).query)
    return query_params.get("vsrid", [None])[0], query_params.get("lsessionid", [None])[0]


def exact_matches_url_from_redirect(final_url):
    parsed = urlparse(final_url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    query_params["udm"] = ["48"]
    new_query = urlencode(query_params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


async def fetch_image(client, image_url):
    response = await client.get(image_url, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
    filename = Path(urlparse(image_url).path).name or "image.jpg"
    return filename, response.content, content_type


async def run(image_url=CHALLENGE_IMAGE_URL):
    loaded_cookies = await load_cookies(COOKIE_FILE)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    timeout = httpx.Timeout(30.0, connect=10.0)

    async with httpx.AsyncClient(
        cookies=loaded_cookies,
        follow_redirects=True,
        timeout=timeout,
        limits=limits,
        http2=True,
        verify=True,
    ) as client:
        filename, image_data, content_type = await fetch_image(client, image_url)
        files = {"encoded_image": (filename, image_data, content_type)}
        params_upload = {
            "hl": "en",
            "re": "av",
            "vpw": "1903",
            "vph": "953",
            "ep": "gsbubb",
            "st": str(int(time.time() * 1000)),
        }

        upload_request = client.build_request(
            "POST",
            LENS_UPLOAD_ENDPOINT,
            headers=HEADERS,
            files=files,
            params=params_upload,
        )
        logging.info("upload request URL: %s", upload_request.url)

        upload_response = await client.send(upload_request, follow_redirects=False)
        await save_cookies(client.cookies, COOKIE_FILE)
        logging.info("upload response status: %s", upload_response.status_code)

        redirect_location = upload_response.headers.get("location")
        logging.info("redirect location: %s", redirect_location)

        if upload_response.status_code not in (302, 303, 307, 308):
            upload_response.raise_for_status()

        final_url = redirect_location or str(upload_response.url)
        logging.info("final URL: %s", final_url)

        vsrid, lsessionid = extract_ids_from_url(final_url)
        logging.info("extracted vsrid: %s", vsrid)
        logging.info("extracted lsessionid: %s", lsessionid)

        exact_url = exact_matches_url_from_redirect(final_url)
        logging.info("exact matches URL: %s", exact_url)

        exact_headers = HEADERS.copy()
        exact_headers["Referer"] = final_url
        exact_headers["Sec-Fetch-Site"] = "same-origin"
        exact_headers.pop("Origin", None)

        exact_response = await client.get(exact_url, headers=exact_headers)
        await save_cookies(client.cookies, COOKIE_FILE)
        logging.info("exact matches response status: %s", exact_response.status_code)
        logging.info("exact matches final URL: %s", exact_response.url)

        OUTPUT_HTML.write_text(exact_response.text, encoding="utf-8")
        body_lower = exact_response.text.lower()
        validation = {
            "contains_exact_matches": "exact matches" in exact_response.text,
            "contains_ebay": "ebay" in body_lower,
            "contains_etsy": "etsy" in body_lower,
            "contains_403": "403" in body_lower,
            "contains_captcha": "captcha" in body_lower,
            "body_bytes": len(exact_response.content),
            "saved_to": str(OUTPUT_HTML),
        }
        logging.info("validation: %s", validation)
        return {
            "upload_status": upload_response.status_code,
            "redirect_location": redirect_location,
            "final_url": final_url,
            "vsrid": vsrid,
            "lsessionid": lsessionid,
            "exact_url": exact_url,
            "exact_status": exact_response.status_code,
            "exact_final_url": str(exact_response.url),
            "validation": validation,
        }


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(result, indent=2))
