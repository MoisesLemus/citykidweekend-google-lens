# Project 4 Firefox Replay

## Corrected finding

`experiments/replay_firefox_curl.py` now validates the saved response by lowercasing the entire HTML before searching. It checks:

- `exact matches`
- `ebay`
- `etsy`
- `master pieces`
- `www.ebay.com/itm`
- negative markers: `403`, `captcha`, `knitsail`, `sg_ss`

It also parses result links from `<a href="...">...</a>` attributes, unwraps Google `/url?q=...` redirects, and prints the first 10 matched result titles and URLs.

## Current replay result

Command:

```bash
python3 experiments/replay_firefox_curl.py
```

Current saved cURL artifact:

```text
experiments/firefox_exact_match.curl
```

Current output summary:

```json
{
  "status_code": 200,
  "validation": {
    "contains_exact_matches": false,
    "contains_ebay": false,
    "contains_etsy": false,
    "contains_master_pieces": false,
    "contains_ebay_item_url": false,
    "contains_403": false,
    "contains_captcha": false,
    "contains_knitsail": true,
    "contains_sg_ss": true,
    "body_bytes": 91092,
    "saved_to": "firefox_replay_exact_match.html"
  },
  "first_10_matched_results": []
}
```

With the current saved cURL/session, replay still returns a Google Search JavaScript retry shell, not the real Exact Matches result page. The corrected validator is in place; when the saved/replayed HTML is the real Exact Matches page, the same script will report the eBay/Etsy/Master Pieces markers and print matched result links.

## Firefox request shape

The Firefox cURL request is a direct document request to:

```text
https://www.google.com/search?...udm=48...
```

Important URL parameters present:

- `udm=48`
- `vsrid` repeated twice
- `vsint`
- `gsessionid`
- `lsessionid`
- `lns_surface=26`
- `source=lns.web.gsbubu`
- `biw=839`
- `bih=754`
- `dpr=1.82`
- `sca_esv`
- `sxsrf`
- `ved`

Important request headers present:

- Firefox `User-Agent`
- `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`
- `Accept-Language: en-US,en;q=0.9`
- `Referer: https://www.google.com/`
- `Upgrade-Insecure-Requests: 1`
- `Sec-Fetch-Dest: document`
- `Sec-Fetch-Mode: navigate`
- `Sec-Fetch-Site: same-origin`
- `Sec-Fetch-User: ?1`

Cookie names present, without sensitive values:

- `AEC`
- `APISID`
- `DV`
- `HSID`
- `NID`
- `OTZ`
- `SAPISID`
- `SEARCH_SAMESITE`
- `SID`
- `SIDCC`
- `SSID`
- `__Secure-1PAPISID`
- `__Secure-1PSID`
- `__Secure-1PSIDCC`
- `__Secure-1PSIDTS`
- `__Secure-3PAPISID`
- `__Secure-3PSID`
- `__Secure-3PSIDCC`
- `__Secure-3PSIDTS`
- `__Secure-BUCKET`
- `__Secure-STRP`

## API work added

Added:

```text
src/chrome_lens_py/exact_matches.py
src/chrome_lens_py/server.py
experiments/test_api_local.py
```

The reusable client now uses two attempts.

Attempt #1, direct HTTP:

1. Load headers/cookies from `experiments/firefox_exact_match.curl`.
2. Download the input `imageUrl`.
3. Upload bytes to `https://lens.google.com/v3/upload`.
4. Read the Google Search redirect.
5. Replace/set `udm=48`.
6. Fetch that Exact Matches URL with the same Firefox-style header/cookie template.
7. Return the raw HTML body.

If that HTML contains any retry marker, it is treated as invalid:

- `/httpservice/retry/enablejs`
- `knitsail`
- `SG_SS`
- `enablejs`

Attempt #2, Playwright Firefox:

1. Launch a fresh Firefox browser context.
2. Open `https://www.google.com/` to establish normal browser state.
3. Navigate to the generated `udm=48` Exact Matches URL.
4. Let Google Search execute any JavaScript retry/challenge step.
5. Wait until the page contains `Exact matches` or a result domain such as `ebay` / `etsy`.
6. Return `page.content()`.

If `LENS_PLAYWRIGHT_PROFILE_DIR` is set, the fallback uses Playwright's persistent Firefox context instead:

```bash
export LENS_PLAYWRIGHT_HEADLESS=0
export LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile
PYTHONPATH=src uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

This opens a visible Firefox window and stores browser state under `./browser_profile`. Complete any Google consent/captcha prompt manually during the first warmup request, then rerun the API test.
The first request may stay open until `LENS_BROWSER_TIMEOUT` while the visible browser waits on that prompt.

After solving the captcha manually, local validation is expected to return:

```text
status: 200
source: playwright_firefox
valid_exact_match_html: true
contains_exact_matches: true
contains_ebay: true
contains_etsy: true
```

Retry/enablejs strings can still appear inside valid Google result HTML. They are invalid only when the page lacks real Exact Matches/result markers or contains a clear captcha/unusual-traffic page.

Failed fallback attempts save:

```text
debug_playwright_final.html
debug_playwright_final.png
```

The FastAPI route is:

```text
GET /google-lens?imageUrl={image_url}
```

Server entry point:

```bash
uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

Required browser install:

```bash
python3 -m playwright install firefox
```

Optional cURL template override:

```bash
FIREFOX_LENS_CURL=/path/to/firefox_exact_match.curl uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

The API response includes a source header:

```text
X-Google-Lens-Source: direct_http
X-Google-Lens-Source: playwright_firefox
```

When browser fallback is used, the source header should be `X-Google-Lens-Source: playwright_firefox`.

Dependencies added:

```text
fastapi
uvicorn
playwright
```

## Remaining gap

The direct HTTP reverse-engineered flow is still useful because it creates the Lens upload/session redirect and the `udm=48` Exact Matches URL. It is blocked as a final fetch mechanism whenever Google returns the JavaScript retry shell. Firefox browser fallback is now used for reliability because it can execute the retry step that `httpx` cannot.

Copied Firefox cURL files contain sensitive cookies and must stay local. `experiments/firefox_exact_match.curl` is ignored and should not be committed.

## Commands run

```bash
python3 experiments/replay_firefox_curl.py
PYTHONPYCACHEPREFIX=/tmp/chrome_lens_py_pycache python3 -m py_compile experiments/replay_firefox_curl.py src/chrome_lens_py/exact_matches.py src/chrome_lens_py/server.py
```

Local API validation command:

```bash
python3 experiments/test_api_local.py
```

Validation observed on fresh test servers:

- Port `8001`, headless Playwright: fallback ran and returned `X-Google-Lens-Source: playwright_firefox`, but Google returned a captcha page.
- Port `8003`, headed Playwright with `lens.google.com/uploadbyurl`: one run reached a large Google results page containing `Exact matches`, `eBay`, and `Etsy`, but the raw HTML still contained retry markers, so it failed the strict validator.
- Port `8004`, stricter invalid-page handling: API returned `502` instead of leaking retry/captcha HTML as a successful response.
- Persistent headed profile warmup using `LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile`: Firefox opened and persisted state. One warmup run reached real Exact Matches HTML with eBay/Etsy/Master Pieces links; later validation ended on a Google captcha page and correctly returned `502`. The latest failed state is saved in `debug_playwright_final.html` and `debug_playwright_final.png`.

The compile check passed. The running server must be restarted after these changes so it can load the Playwright fallback code. Playwright Firefox is installed locally in this environment.
