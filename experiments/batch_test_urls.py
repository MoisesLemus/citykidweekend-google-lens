import csv
import json
import os
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = os.environ.get("PROJECT4_API_URL", "http://127.0.0.1:8000/google-lens")
OUTPUT_JSON = Path("batch_test_results.json")
OUTPUT_CSV = Path("batch_test_results.csv")

IMAGE_URLS = [
    "https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS9m4zOb/$_57.JPG",
    "https://picsum.photos/id/10/640/480.jpg",
    "https://picsum.photos/id/20/640/480.jpg",
    "https://picsum.photos/id/30/640/480.jpg",
    "https://picsum.photos/id/40/640/480.jpg",
    "https://picsum.photos/id/50/640/480.jpg",
    "https://picsum.photos/id/60/640/480.jpg",
    "https://picsum.photos/id/70/640/480.jpg",
    "https://picsum.photos/id/80/640/480.jpg",
    "https://picsum.photos/id/90/640/480.jpg",
    "https://picsum.photos/id/100/640/480.jpg",
    "https://picsum.photos/id/110/640/480.jpg",
    "https://picsum.photos/id/120/640/480.jpg",
    "https://picsum.photos/id/130/640/480.jpg",
    "https://picsum.photos/id/140/640/480.jpg",
    "https://picsum.photos/id/150/640/480.jpg",
    "https://picsum.photos/id/160/640/480.jpg",
    "https://picsum.photos/id/170/640/480.jpg",
    "https://picsum.photos/id/180/640/480.jpg",
    "https://picsum.photos/id/190/640/480.jpg",
]


def validate_html(text):
    lower = text.lower()
    contains_exact_matches = "exact matches" in lower
    contains_ebay = "ebay" in lower
    contains_etsy = "etsy" in lower
    contains_master_pieces = "master pieces" in lower
    contains_ebay_item_url = "www.ebay.com/itm" in lower
    contains_no_matches = any(
        marker in lower for marker in ("no matches for your search", "no exact matches")
    )
    contains_result_links = any(
        marker in lower
        for marker in (
            "href=",
            "www.ebay.com/itm",
            "etsy.com/listing",
            "master pieces",
        )
    ) and not contains_no_matches
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
    valid_exact_match_with_results = (
        contains_exact_matches
        and contains_result_links
        and not contains_captcha
        and not contains_403
    )
    valid_exact_match_page = (
        contains_exact_matches
        and (contains_result_links or contains_no_matches)
        and not contains_captcha
        and not contains_403
    )
    return {
        "valid_exact_match_html": valid_exact_match_page,
        "valid_exact_match_page": valid_exact_match_page,
        "valid_exact_match_with_results": valid_exact_match_with_results,
        "contains_exact_matches": contains_exact_matches,
        "contains_ebay": contains_ebay,
        "contains_etsy": contains_etsy,
        "contains_master_pieces": contains_master_pieces,
        "contains_ebay_item_url": contains_ebay_item_url,
        "contains_result_links": contains_result_links,
        "contains_no_matches": contains_no_matches,
        "contains_captcha": contains_captcha,
        "contains_403": contains_403,
    }


def parse_error_detail(text):
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        lowered = detail.lower()
        if "retry" in lowered or "enablejs" in lowered:
            reason = "direct_http_retry_shell"
        elif "captcha" in lowered or "unusual traffic" in lowered:
            reason = "captcha"
        elif "no matches" in lowered:
            reason = "no_matches_page"
        elif "exact match" in lowered:
            reason = "no_exact_match_tab"
        elif "403" in lowered or "upstream request failed" in lowered:
            reason = "browser_navigation_failed"
        else:
            reason = "validation_failed"
        return {"reason": reason, "message": detail}
    return None


def fetch_one(index, image_url):
    url = f"{API_URL}?{urlencode({'imageUrl': image_url})}"
    started = time.perf_counter()
    status_code = None
    source = None
    body = b""
    error = None
    error_detail = None

    try:
        request = Request(url, headers={"Accept": "text/html"})
        with urlopen(request, timeout=240) as response:
            status_code = response.status
            source = response.headers.get("X-Google-Lens-Source")
            body = response.read()
    except HTTPError as exc:
        status_code = exc.code
        source = exc.headers.get("X-Google-Lens-Source")
        body = exc.read()
        error = str(exc)
    except URLError as exc:
        error = str(exc)
    except TimeoutError as exc:
        error = str(exc)

    latency_seconds = time.perf_counter() - started
    text = body.decode("utf-8", errors="replace")
    if status_code and status_code >= 400:
        error_detail = parse_error_detail(text)
    validation = validate_html(text)
    result = {
        "index": index,
        "image_url": image_url,
        "status_code": status_code,
        "latency_seconds": round(latency_seconds, 3),
        "source": source,
        "body_bytes": len(body),
        "error": error,
        "error_detail": error_detail,
        "error_reason": error_detail.get("reason") if error_detail else None,
        **validation,
    }
    if not result["valid_exact_match_page"]:
        fail_path = Path(f"batch_fail_{index:03d}.html")
        fail_path.write_bytes(body)
        result["failed_body_path"] = str(fail_path)
    else:
        result["failed_body_path"] = None
    return result


def write_outputs(results):
    OUTPUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")

    fieldnames = [
        "index",
        "image_url",
        "status_code",
        "latency_seconds",
        "source",
        "body_bytes",
        "contains_exact_matches",
        "contains_ebay",
        "contains_etsy",
        "contains_master_pieces",
        "contains_ebay_item_url",
        "contains_result_links",
        "contains_no_matches",
        "contains_captcha",
        "contains_403",
        "valid_exact_match_html",
        "valid_exact_match_page",
        "valid_exact_match_with_results",
        "error_reason",
        "error_detail",
        "failed_body_path",
        "error",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results):
    total = len(results)
    valid_pages = sum(1 for result in results if result["valid_exact_match_page"])
    valid_pages_with_results = sum(
        1 for result in results if result["valid_exact_match_with_results"]
    )
    no_match_pages = sum(
        1
        for result in results
        if result["valid_exact_match_page"] and result["contains_no_matches"]
    )
    true_failures = total - valid_pages
    failure_reasons = Counter(
        result["error_reason"] or "unknown"
        for result in results
        if not result["valid_exact_match_page"]
    )
    latencies = [result["latency_seconds"] for result in results]
    average_latency = sum(latencies) / total if total else 0
    max_latency = max(latencies) if latencies else 0

    print(
        json.dumps(
            {
                "total": total,
                "valid_pages": valid_pages,
                "valid_pages_with_results": valid_pages_with_results,
                "no_match_pages": no_match_pages,
                "true_failures": true_failures,
                "failure_reasons": dict(sorted(failure_reasons.items())),
                "average_latency": round(average_latency, 3),
                "max_latency": round(max_latency, 3),
                "success_rate": round(valid_pages / total if total else 0, 3),
                "json": str(OUTPUT_JSON),
                "csv": str(OUTPUT_CSV),
            },
            indent=2,
            sort_keys=True,
        )
    )


def main():
    results = []
    for index, image_url in enumerate(IMAGE_URLS, start=1):
        print(f"[{index}/{len(IMAGE_URLS)}] {image_url}")
        result = fetch_one(index, image_url)
        results.append(result)
        print(
            f"  status={result['status_code']} "
            f"source={result['source']} "
            f"latency={result['latency_seconds']}s "
            f"valid_page={result['valid_exact_match_page']} "
            f"with_results={result['valid_exact_match_with_results']} "
            f"reason={result['error_reason']}"
        )

    write_outputs(results)
    print_summary(results)


if __name__ == "__main__":
    main()
