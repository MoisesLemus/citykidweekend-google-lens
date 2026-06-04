import argparse
import asyncio
import csv
import json
import os
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API_URL = os.environ.get("PROJECT4_API_URL", "http://127.0.0.1:8000/google-lens")
API_KEY = os.environ.get("LENS_API_KEY") or os.environ.get("PROJECT4_API_KEY")
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
CHALLENGE_IMAGE_URL = IMAGE_URLS[0]
CAPTCHA_STOP_THRESHOLD = 3


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
    contains_unusual_traffic = any(
        marker in lower
        for marker in (
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
        "contains_unusual_traffic": contains_unusual_traffic,
        "captcha_or_unusual_traffic": contains_captcha or contains_unusual_traffic,
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


def endpoint_from_base_url(base_url):
    base = base_url.rstrip("/")
    if base.endswith("/google-lens"):
        return base
    return f"{base}/google-lens"


def base_url_from_endpoint(api_url):
    parsed = urlparse(api_url)
    if not parsed.scheme or not parsed.netloc:
        return api_url
    return f"{parsed.scheme}://{parsed.netloc}"


def fetch_one(index, image_url):
    url = f"{API_URL}?{urlencode({'imageUrl': image_url})}"
    started = time.perf_counter()
    status_code = None
    source = None
    direct_attempt = None
    body = b""
    error = None
    error_detail = None

    try:
        headers = {"Accept": "text/html"}
        if API_KEY:
            headers["X-API-KEY"] = API_KEY
        request = Request(url, headers=headers)
        with urlopen(request, timeout=240) as response:
            status_code = response.status
            source = response.headers.get("X-Google-Lens-Source")
            direct_attempt = response.headers.get("X-Google-Lens-Direct-Attempt")
            body = response.read()
    except HTTPError as exc:
        status_code = exc.code
        source = exc.headers.get("X-Google-Lens-Source")
        direct_attempt = exc.headers.get("X-Google-Lens-Direct-Attempt")
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
        "imageUrl": image_url,
        "image_url": image_url,
        "status": status_code,
        "status_code": status_code,
        "latency_seconds": round(latency_seconds, 3),
        "source": source,
        "direct_attempt": direct_attempt,
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


def build_image_urls(limit):
    if limit <= len(IMAGE_URLS):
        return IMAGE_URLS[:limit]

    urls = IMAGE_URLS[:]
    next_index = len(urls) + 1
    while len(urls) < limit:
        urls.append(f"https://picsum.photos/seed/project4-batch-{next_index:03d}/640/480.jpg")
        next_index += 1
    return urls


def percentile(values, percentile_value):
    if not values:
        return 0
    ordered = sorted(values)
    index = int(round((percentile_value / 100) * (len(ordered) - 1)))
    return ordered[index]


def write_outputs(results, output_json, output_csv):
    output_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    fieldnames = [
        "index",
        "imageUrl",
        "image_url",
        "status",
        "status_code",
        "latency_seconds",
        "source",
        "direct_attempt",
        "body_bytes",
        "contains_exact_matches",
        "contains_ebay",
        "contains_etsy",
        "contains_master_pieces",
        "contains_ebay_item_url",
        "contains_result_links",
        "contains_no_matches",
        "contains_captcha",
        "contains_unusual_traffic",
        "captcha_or_unusual_traffic",
        "contains_403",
        "valid_exact_match_html",
        "valid_exact_match_page",
        "valid_exact_match_with_results",
        "error_reason",
        "error_detail",
        "failed_body_path",
        "error",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results, wall_clock_seconds, output_json, output_csv):
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
    p95_latency = percentile(latencies, 95)
    captcha_pages = sum(
        1
        for result in results
        if result["contains_captcha"] or result["error_reason"] == "captcha"
    )

    summary = {
        "total": total,
        "wall_clock_seconds": round(wall_clock_seconds, 3),
        "valid_pages": valid_pages,
        "valid_pages_with_results": valid_pages_with_results,
        "no_match_pages": no_match_pages,
        "true_failures": true_failures,
        "captcha_pages": captcha_pages,
        "failure_reasons": dict(sorted(failure_reasons.items())),
        "average_latency": round(average_latency, 3),
        "max_latency": round(max_latency, 3),
        "p95_latency": round(p95_latency, 3),
        "requests_per_hour_estimate": round(
            (total / wall_clock_seconds) * 3600 if wall_clock_seconds else 0, 1
        ),
        "success_rate": round(valid_pages / total if total else 0, 3),
        "json": str(output_json),
        "csv": str(output_csv),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run serial /google-lens reliability tests against public image URLs."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=len(IMAGE_URLS),
        help="Number of sequential requests to run. Use --limit 100 for the pre-ngrok run.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Full /google-lens endpoint URL. Overrides --base-url.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base server URL, for example https://example.trycloudflare.com.",
    )
    parser.add_argument(
        "--api-key",
        default=API_KEY,
        help="API key sent as X-API-KEY. Defaults to LENS_API_KEY or PROJECT4_API_KEY.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent requests. Keep at 1 or 2 for this local profile.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help=(
            "Path for JSON results. Defaults to batch_test_results_public_<limit>.json "
            "with --base-url, or batch_test_results_1000.json for --limit 1000."
        ),
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help=(
            "Path for CSV results. Defaults to batch_test_results_public_<limit>.csv "
            "with --base-url, or batch_test_results_1000.csv for --limit 1000."
        ),
    )
    return parser.parse_args()


def output_paths_for_args(args):
    is_public = bool(args.base_url) and not args.api_url
    default_json = OUTPUT_JSON
    default_csv = OUTPUT_CSV
    if is_public:
        default_json = Path(f"batch_test_results_public_{args.limit}.json")
        default_csv = Path(f"batch_test_results_public_{args.limit}.csv")
    elif args.limit == 1000:
        default_json = Path("batch_test_results_1000.json")
        default_csv = Path("batch_test_results_1000.csv")
    return Path(args.output_json or default_json), Path(args.output_csv or default_csv)


def print_config(base_url, image_urls, args, output_json, output_csv):
    print("batch_config:", flush=True)
    print(f"  base_url: {base_url}", flush=True)
    print(f"  api_url: {API_URL}", flush=True)
    print(f"  total_limit: {args.limit}", flush=True)
    print(f"  concurrency: {args.concurrency}", flush=True)
    print(f"  api_key_present: {'yes' if API_KEY else 'no'}", flush=True)
    print(f"  output_json: {output_json}", flush=True)
    print(f"  output_csv: {output_csv}", flush=True)
    print("  first_5_test_image_urls:", flush=True)
    for url in image_urls[:5]:
        print(f"    - {url}", flush=True)


def run_preflight():
    print("preflight:", flush=True)
    result = fetch_one(0, CHALLENGE_IMAGE_URL)
    print(
        f"  status={result['status_code']} "
        f"source={result['source']} "
        f"direct_attempt={result['direct_attempt']} "
        f"latency={result['latency_seconds']}s "
        f"valid_page={result['valid_exact_match_page']} "
        f"reason={result['error_reason']}",
        flush=True,
    )
    if result["status_code"] != 200 or not result["valid_exact_match_html"]:
        raise SystemExit("Preflight failed; stopping before batch.")
    print("  ok=true", flush=True)


async def run_batch(image_urls, concurrency, output_json, output_csv):
    queue = asyncio.Queue()
    for item in enumerate(image_urls, start=1):
        queue.put_nowait(item)

    results = []
    captcha_pages = 0
    lock = asyncio.Lock()
    stop_event = asyncio.Event()

    async def worker():
        nonlocal captcha_pages
        while not stop_event.is_set():
            try:
                index, image_url = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            should_print_detail = len(image_urls) <= 100 or index == 1 or index % 25 == 0
            if should_print_detail:
                print(f"[{index}/{len(image_urls)}] {image_url}", flush=True)
            result = await asyncio.to_thread(fetch_one, index, image_url)
            async with lock:
                results.append(result)
                if result["contains_captcha"] or result["error_reason"] == "captcha":
                    captcha_pages += 1
                if should_print_detail:
                    print(
                        f"  status={result['status_code']} "
                        f"source={result['source']} "
                        f"latency={result['latency_seconds']}s "
                        f"valid_page={result['valid_exact_match_page']} "
                        f"with_results={result['valid_exact_match_with_results']} "
                        f"reason={result['error_reason']}",
                        flush=True,
                    )
                if len(results) % 25 == 0:
                    write_outputs(sorted(results, key=lambda item: item["index"]), output_json, output_csv)
                if captcha_pages > CAPTCHA_STOP_THRESHOLD:
                    print(
                        "Stopping early: captcha/unusual traffic appeared "
                        f"{captcha_pages} times.",
                        flush=True,
                    )
                    stop_event.set()
            queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers)
    return sorted(results, key=lambda item: item["index"])


def main():
    args = parse_args()
    global API_URL, API_KEY
    if args.api_url:
        API_URL = args.api_url
    elif args.base_url:
        API_URL = endpoint_from_base_url(args.base_url)
    API_KEY = args.api_key
    base_url = args.base_url.rstrip("/") if args.base_url else base_url_from_endpoint(API_URL)
    if args.concurrency < 1:
        raise ValueError("--concurrency must be >= 1")
    if not API_KEY:
        raise ValueError("--api-key is required, or set LENS_API_KEY / PROJECT4_API_KEY")
    image_urls = build_image_urls(args.limit)
    output_json, output_csv = output_paths_for_args(args)
    print_config(base_url, image_urls, args, output_json, output_csv)
    run_preflight()
    started = time.perf_counter()
    results = asyncio.run(run_batch(image_urls, args.concurrency, output_json, output_csv))
    wall_clock_seconds = time.perf_counter() - started

    write_outputs(results, output_json, output_csv)
    print_summary(results, wall_clock_seconds, output_json, output_csv)


if __name__ == "__main__":
    main()
