# Final Submission Notes

## Endpoint Implemented

Implemented:

```text
GET /google-lens?imageUrl={image_url}
```

Current public Cloudflare Tunnel API URL:

```text
https://gaming-felt-raymond-yea.trycloudflare.com/google-lens?imageUrl={image_url}
```

Required request header:

```text
X-API-KEY: <key>
```

The Cloudflare quick tunnel must stay running during review.

The endpoint returns raw Google Lens / Google Search Exact Matches HTML.

Server entry point:

```bash
PYTHONPATH=src uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

## Direct HTTP Reverse-Engineered Attempt

The direct HTTP path was reverse-engineered and is kept for research/debug behind `LENS_USE_DIRECT_HTTP=1`:

1. Download the supplied image URL.
2. Upload image bytes to `https://lens.google.com/v3/upload`.
3. Read the Google Search redirect containing Lens session IDs.
4. Replace/set `udm=48` for Exact Matches.
5. Fetch the resulting Google Search HTML with `httpx`.

The direct fetch reliably creates a Lens/Search session URL, but Google returns a JavaScript retry shell for the final document request in the current environment. It is disabled by default to avoid extra latency and noisy failures.

## v3/upload and udm=48 Findings

Confirmed findings:

- `https://lens.google.com/v3/upload` accepts multipart image upload under `encoded_image`.
- The upload response redirects to Google Search.
- The redirect URL contains values such as `vsrid`, `gsessionid`, and `lsessionid`.
- Exact Matches is selected by setting `udm=48`.
- Direct `httpx` can receive HTTP 200 while still getting a retry/enablejs shell instead of real results.

## Fallback Strategy

The primary stable path uses Playwright Firefox:

- Fresh browser context by default.
- Persistent headed Firefox profile when `LENS_PLAYWRIGHT_PROFILE_DIR` is set.
- Recommended local config:

```bash
export LENS_PLAYWRIGHT_HEADLESS=0
export LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile
export LENS_BROWSER_TIMEOUT=180
export LENS_USE_DIRECT_HTTP=0
```

The browser path opens Google/Lens in Firefox, lets Google execute required JavaScript, navigates to the Exact Matches URL, and returns `page.content()` only when the page contains:

- `Exact matches`
- at least one result marker: `ebay`, `etsy`, `www.ebay.com/itm`, or `Master Pieces`
- no clear captcha/unusual-traffic page

When browser fallback is used, successful responses include:

```text
X-Google-Lens-Source: playwright_firefox
X-Google-Lens-Direct-Attempt: skipped
```

Failed fallback attempts save:

```text
debug_playwright_final.html
debug_playwright_final.png
```

## Local Test Result

After manually solving Google captcha in the persistent headed Firefox profile, the local smoke test passed:

```bash
python3 experiments/test_api_local.py
```

Observed successful markers:

```text
status: 200
source: playwright_firefox
direct_attempt: skipped
valid_exact_match_html: true
contains_exact_matches: true
contains_ebay: true
contains_etsy: true
```

The raw Google result HTML can still contain inert retry/enablejs strings inside scripts. Validation treats those as invalid only when real result markers are missing or a captcha/block page is present.

## Stress Test Result

Latest 1000-style sequential run:

```text
attempted_target: 1000
stopped_early_at: 686
stop_reason: captcha/unusual traffic appeared 4 times
valid_pages: 680
valid_pages_with_results: 667
no_match_pages: 13
true_failures: 6
captcha_pages: 4
success_rate: 99.1%
average_latency: 2.298s
p95_latency: 2.377s
requests_per_hour_estimate: 1556.9
```

The API met the challenge's 300+ valid HTML threshold before early stop and exceeded latency requirements. Google captcha/unusual-traffic risk remains the main scaling limitation.

Latest reusable-page local benchmark before the longer run: 100/100 valid pages, average latency around 1.7s.

## Limitations

- Persistent browser profile may require manual Google consent/captcha warmup.
- Keep concurrency at `1` for this local single-profile setup. This is the only stable tested mode.
- Max recommended concurrency for review traffic is `1`.
- Cloudflare quick tunnel must remain running during review; the public URL is tunnel-backed, not permanent hosting.
- Concurrency 2 with one persistent profile caused 0% success due to browser/profile contention.
- Current 1000-style run estimated 1556.9 requests/hour before captcha early stop.
- Do not claim full 1000-request reliability yet. The latest run stopped at 686 after 4 captcha/unusual-traffic pages.
- Do not commit copied Firefox cURL files, cookies, debug captures, or browser profile data.
- This is a reverse-engineered proof of concept and depends on Google UI/backend behavior that can change.
