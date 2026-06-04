# Project 4 Exact Match POC

## Goal

Prove whether the existing `experiments/reverse.py` Google Lens web-upload flow can take the challenge image URL and save the raw Google Lens Exact Matches HTML by changing the redirected Google Search URL to `udm=48`.

Challenge image:

```text
https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS9m4zOb/$_57.JPG
```

## Current `experiments/reverse.py` flow

`experiments/reverse.py` is a direct HTTP prototype, not Playwright/Selenium/browser automation.

Current flow:

1. Reads a local image file from disk.
2. Builds multipart form data with field:
   - `encoded_image`
3. Sends `POST https://lens.google.com/v3/upload`.
4. Uses browser-like navigation headers:
   - Chrome User-Agent
   - `Sec-Ch-Ua`
   - `Sec-Fetch-*`
   - `Origin: https://www.google.com`
   - `Referer: https://www.google.com/`
5. Sends upload params:
   - `hl`
   - `re=av`
   - `vpw`
   - `vph`
   - `ep=gsbubb`
   - `st`
6. Uses one `httpx.AsyncClient` with cookies, redirects, limits, timeout, HTTP/2, and TLS verification.
7. Follows the upload redirect to a Google Search/Lens URL.
8. Extracts `vsrid` and `lsessionid` from the redirected URL.
9. Calls `GET https://lens.google.com/qfmetadata` using `vsrid` and `lsessionid`.
10. Parses the XSSI-prefixed metadata response for OCR text/coordinates.

It does not currently:

- accept an image URL directly;
- construct `udm=48`;
- fetch raw Exact Matches HTML;
- save a Google Search result body.

## POC script added

Added:

```text
experiments/exact_match_poc.py
```

The script keeps the reverse.py-style direct HTTP approach but changes the experiment to:

1. Download the challenge image URL with `httpx`.
2. POST the downloaded bytes to `https://lens.google.com/v3/upload`.
3. Stop at the upload `303 See Other` redirect instead of following it into a possible 403.
4. Extract:
   - `vsrid`
   - `lsessionid`
   - also preserves the redirected URL containing `gsessionid`
5. Construct an Exact Matches URL by replacing `udm=26` with `udm=48`.
6. Fetch that URL using the same `httpx.AsyncClient`, cookies, and navigation-style headers.
7. Save the returned body to:

```text
exact_match_test.html
```

## Commands run

First run failed because this environment did not have HTTP/2 support installed for `httpx`:

```bash
python3 experiments/exact_match_poc.py
```

Error:

```text
ImportError: Using http2=True, but the 'h2' package is not installed.
```

Installed the missing dependency:

```bash
python3 -m pip install 'h2>=4,<5'
```

Then ran:

```bash
python3 experiments/exact_match_poc.py
```

## Run output summary

Image download:

```text
GET challenge image: HTTP/2 200 OK
```

Upload request URL:

```text
https://lens.google.com/v3/upload?hl=en&re=av&vpw=1903&vph=953&ep=gsbubb&st=1780518804346
```

Upload response status:

```text
303 See Other
```

Redirect location / final Lens Search URL:

```text
https://www.google.com/search?vsrid=CLiKidr_jtrXORACGAEiJDBmYmI5ODU1LTkxODEtNDQ5ZC05MmMzLTU2NmU2YmEzMWZlYjJ7IgJ1ZygBQnMKLmxmZS1kdW1teTphNTI5NzIwYy1hYjIzLTRmMDUtODg3NS0wNjk3MmZhNDQ1ODASQQo_L2Jucy91Zy9ib3JnL3VnL2Jucy9sZW5zLWZyb250ZW5kLWFwaS9wcm9kLmxlbnMtZnJvbnRlbmQtYXBpLzcyONSn8bb165QD&vsint=CAIqDAoCCAcSAggKGAEgATohChYNAAAAPxUAAAA_HQAAgD8lAACAPzABEFAYUCUAAIA_&udm=26&lns_mode=un&source=lns.web.gsbubb&vsdim=80,80&gsessionid=sBTO9GiGM6gOQcuEzFGkHxygsSoCNEUEoRSOcMFRFqGiLSyEQKkrtw&lsessionid=vr-mfTqBIE71OKzfMfMu_uAGwJExRSk8yG1dj4zWS_gqswX78WBzbw&lns_surface=26&lns_vfs=e&qsubts=1780518804346&biw=1903&bih=953&hl=en
```

Extracted IDs:

```text
vsrid=CLiKidr_jtrXORACGAEiJDBmYmI5ODU1LTkxODEtNDQ5ZC05MmMzLTU2NmU2YmEzMWZlYjJ7IgJ1ZygBQnMKLmxmZS1kdW1teTphNTI5NzIwYy1hYjIzLTRmMDUtODg3NS0wNjk3MmZhNDQ1ODASQQo_L2Jucy91Zy9ib3JnL3VnL2Jucy9sZW5zLWZyb250ZW5kLWFwaS9wcm9kLmxlbnMtZnJvbnRlbmQtYXBpLzcyONSn8bb165QD
lsessionid=vr-mfTqBIE71OKzfMfMu_uAGwJExRSk8yG1dj4zWS_gqswX78WBzbw
gsessionid=sBTO9GiGM6gOQcuEzFGkHxygsSoCNEUEoRSOcMFRFqGiLSyEQKkrtw
```

Constructed `udm=48` URL:

```text
https://www.google.com/search?vsrid=CLiKidr_jtrXORACGAEiJDBmYmI5ODU1LTkxODEtNDQ5ZC05MmMzLTU2NmU2YmEzMWZlYjJ7IgJ1ZygBQnMKLmxmZS1kdW1teTphNTI5NzIwYy1hYjIzLTRmMDUtODg3NS0wNjk3MmZhNDQ1ODASQQo_L2Jucy91Zy9ib3JnL3VnL2Jucy9sZW5zLWZyb250ZW5kLWFwaS9wcm9kLmxlbnMtZnJvbnRlbmQtYXBpLzcyONSn8bb165QD&vsint=CAIqDAoCCAcSAggKGAEgATohChYNAAAAPxUAAAA_HQAAgD8lAACAPzABEFAYUCUAAIA_&udm=48&lns_mode=un&source=lns.web.gsbubb&vsdim=80%2C80&gsessionid=sBTO9GiGM6gOQcuEzFGkHxygsSoCNEUEoRSOcMFRFqGiLSyEQKkrtw&lsessionid=vr-mfTqBIE71OKzfMfMu_uAGwJExRSk8yG1dj4zWS_gqswX78WBzbw&lns_surface=26&lns_vfs=e&qsubts=1780518804346&biw=1903&bih=953&hl=en
```

Exact Matches fetch:

```text
HTTP/2 200 OK
```

Saved:

```text
exact_match_test.html
```

File size:

```text
89K
```

## Validation results

The script checked the saved body for requested markers:

```text
contains "Exact matches": false
contains "eBay": false
contains "Etsy": false
contains "403": false
contains "captcha": false
body_bytes: 90799
```

Additional inspection:

```text
title: Google Search
contains "Google Search": true
contains "Our systems have detected": false
```

The saved page contains a Google Search JavaScript challenge/retry shell. It includes terms such as:

```text
knitsail
SG_SS
If you're having trouble accessing Google Search, please click here
```

So this is not the final Exact Matches result HTML yet.

## Important finding

The useful part is now proven:

- `lens.google.com/v3/upload` accepts the challenge image URL bytes.
- The upload returns a Google Search redirect URL.
- That redirect URL already contains:
  - `vsrid`
  - `gsessionid`
  - `lsessionid`
  - `udm=26`
- Replacing `udm=26` with `udm=48` produces an HTTP 200 response.

The blocker is that the HTTP 200 response is a Google Search JavaScript challenge/retry shell, not the raw Exact Matches result page. It is not a simple 403 and not an obvious captcha page, but it likely requires browser-executed Search challenge state/cookies such as `SG_SS`.

## Current status

This POC does not yet prove that one image URL can become one saved Exact Matches HTML file containing real eBay/Etsy match results.

It does prove the correct upstream Lens upload/session redirect path and gets us to a `udm=48` Google Search URL with all three important session IDs.

## Recommended next step

Use Firefox manual testing as a recorder, not as production:

1. Capture the successful Firefox request for the `udm=48` page.
2. Compare it against this POC request:
   - cookies, especially Search challenge cookies;
   - headers;
   - redirect chain;
   - `sei`, `ved`, `sca_esv`, and other Search params;
   - whether Firefox first executes a challenge/retry URL before the real result page.
3. Reproduce the missing cookie/header/request step in `httpx`.
4. Only after `exact_match_test.html` contains real Exact Matches HTML should we build the `/google-lens?imageUrl=...` API.
