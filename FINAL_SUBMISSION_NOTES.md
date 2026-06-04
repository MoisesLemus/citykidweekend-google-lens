# Final Submission Notes

## Endpoint Implemented

Implemented:

```text
GET /google-lens?imageUrl={image_url}
```

The endpoint returns raw Google Lens / Google Search Exact Matches HTML.

Server entry point:

```bash
PYTHONPATH=src uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

## Direct HTTP Reverse-Engineered Attempt

The direct HTTP path is kept as attempt #1:

1. Download the supplied image URL.
2. Upload image bytes to `https://lens.google.com/v3/upload`.
3. Read the Google Search redirect containing Lens session IDs.
4. Replace/set `udm=48` for Exact Matches.
5. Fetch the resulting Google Search HTML with `httpx`.

The direct fetch reliably creates a Lens/Search session URL, but Google often returns a JavaScript retry shell for the final document request.

## v3/upload and udm=48 Findings

Confirmed findings:

- `https://lens.google.com/v3/upload` accepts multipart image upload under `encoded_image`.
- The upload response redirects to Google Search.
- The redirect URL contains values such as `vsrid`, `gsessionid`, and `lsessionid`.
- Exact Matches is selected by setting `udm=48`.
- Direct `httpx` can receive HTTP 200 while still getting a retry/enablejs shell instead of real results.

## Fallback Strategy

Attempt #2 uses Playwright Firefox:

- Fresh browser context by default.
- Persistent headed Firefox profile when `LENS_PLAYWRIGHT_PROFILE_DIR` is set.
- Recommended local config:

```bash
export LENS_PLAYWRIGHT_HEADLESS=0
export LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile
export LENS_BROWSER_TIMEOUT=180
```

The fallback opens Google/Lens in Firefox, lets Google execute required JavaScript, navigates to the Exact Matches URL, and returns `page.content()` only when the page contains:

- `Exact matches`
- at least one result marker: `ebay`, `etsy`, `www.ebay.com/itm`, or `Master Pieces`
- no clear captcha/unusual-traffic page

When browser fallback is used, successful responses include:

```text
X-Google-Lens-Source: playwright_firefox
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
valid_exact_match_html: true
contains_exact_matches: true
contains_ebay: true
contains_etsy: true
```

The raw Google result HTML can still contain inert retry/enablejs strings inside scripts. Validation treats those as invalid only when real result markers are missing or a captcha/block page is present.

## Limitations

- Persistent browser profile may require manual Google consent/captcha warmup.
- Keep concurrency at `1` for this local setup. The fallback shares one persistent Firefox profile and Google challenge/rate behavior is sensitive.
- Do not commit copied Firefox cURL files, cookies, debug captures, or browser profile data.
- This is a reverse-engineered proof of concept and depends on Google UI/backend behavior that can change.
