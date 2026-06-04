# Chrome Lens API for Python

**English** | [Русский](/README_RU.md)

[![PyPI version](https://badge.fury.io/py/chrome-lens-py.svg)](https://badge.fury.io/py/chrome-lens-py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/chrome-lens-py.svg)](https://pypi.org/project/chrome-lens-py)
[![Downloads](https://static.pepy.tech/badge/chrome-lens-py)](https://pepy.tech/project/chrome-lens-py)

> [!IMPORTANT]
> **Major Rewrite (Version 3.1.0+)**
> This library has been completely rewritten from the ground up. It now uses a modern asynchronous architecture (`async`/`await`) and communicates directly with Google's Protobuf endpoint for significantly improved reliability and performance.
>
> **Please update your projects accordingly. All API calls are now `async`.**
>

> [!Warning]
> Also, please note that the library has been completely rewritten, and I could have missed something, or not spelled it out. If you notice an error, please let me know in Issues

This project provides a powerful, asynchronous Python library and command-line tool for interacting with Google Lens. It allows you to perform advanced Optical Character Recognition (OCR), get segmented text blocks (e.g., for comics), translate text, and get precise word coordinates.

## Project 4: Exact Matches HTML API

This fork also includes a Project 4 proof-of-concept API:

```text
GET /google-lens?imageUrl={image_url}
```

Current public Cloudflare Tunnel endpoint for review:

```text
https://gaming-felt-raymond-yea.trycloudflare.com/google-lens?imageUrl={image_url}
```

Required request header:

```text
X-API-KEY: <key>
```

The Cloudflare quick tunnel must stay running during review; this URL is not a permanent hosted deployment.

The endpoint returns raw Google Lens / Google Search Exact Matches HTML. The stable default path uses Playwright Firefox with a warmed persistent profile, one reusable browser context, and one shared page guarded by an `asyncio.Lock`. The reverse-engineered direct HTTP flow was researched but is disabled by default because Google returns a JavaScript retry shell in this environment.

The disabled direct HTTP research flow is:

1. Download the input image URL.
2. Upload bytes to `https://lens.google.com/v3/upload`.
3. Read the Google Search redirect containing Lens session IDs.
4. Set `udm=48` for Exact Matches.
5. Fetch the resulting Google Search document.

Direct HTTP can be re-enabled for future debugging with `LENS_USE_DIRECT_HTTP=1`. When enabled, Google can return its JavaScript retry shell (`/httpservice/retry/enablejs`, `knitsail`, `SG_SS`, `enablejs`). When that happens, the API treats the body as invalid and falls back to Playwright Firefox so the browser can execute Google's retry step and return `page.content()`.

If Firefox receives a Google captcha / unusual-traffic page, the API returns `502` instead of returning that block page as a successful Exact Matches response.

Run the API:

```bash
pip install -r requirements.txt
python3 -m playwright install firefox
uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

First-time warmup for the reliable Firefox path:

```bash
export LENS_PLAYWRIGHT_HEADLESS=0
export LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile
export LENS_API_KEY=change-me
PYTHONPATH=src uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

Then call the API once. A visible Firefox window should open. If Google asks for consent or a captcha, complete it manually in that window. The browser state is kept in `./browser_profile`, so retrying the API can reuse the warmed profile.
The first request may wait until `LENS_BROWSER_TIMEOUT` while you complete the prompt.
After the first successful request, the FastAPI process keeps the warmed Firefox context/page open and reuses it for later requests. Requests remain effectively concurrency `1` because the shared page is protected by a lock.

Successful local warmup flow:

1. Start the server with `LENS_PLAYWRIGHT_HEADLESS=0` and `LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile`.
2. Call the API once.
3. Solve Google consent/captcha in the visible Firefox window if shown.
4. Rerun `python3 experiments/test_api_local.py`.

Expected successful test markers:

```text
status: 200
source: playwright_firefox
direct_attempt: skipped
valid_exact_match_html: true
contains_exact_matches: true
contains_ebay: true
contains_etsy: true
```

Google's normal result HTML can contain inert retry/enablejs strings inside scripts. Those are only treated as invalid when the page lacks real Exact Matches/result markers.

The response includes:

```text
X-Google-Lens-Source: playwright_firefox
X-Google-Lens-Direct-Attempt: skipped
```

API key authentication is required. Configure:

```bash
export LENS_API_KEY=change-me
```

Every request must include:

```text
X-API-KEY: change-me
```

Missing `X-API-KEY` returns `401`; a wrong key returns `403`.

If direct HTTP is explicitly enabled and succeeds before the browser fallback, the source can be:

```text
X-Google-Lens-Source: direct_http
X-Google-Lens-Direct-Attempt: performed
```

When browser fallback is used, the source header should be:

```text
X-Google-Lens-Source: playwright_firefox
X-Google-Lens-Direct-Attempt: skipped
```

Local validation:

```bash
python3 experiments/test_api_local.py
```

Do not commit copied Firefox cURL files or Google cookies. `experiments/firefox_exact_match.curl` is ignored locally and should remain a private debugging artifact.

## Final Submission Quick Start

Setup:

```bash
cd /Users/moisesphilo/Documents/codex/project4/repos/chrome-lens-py
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
python3 -m playwright install firefox
```

Warm up the persistent Firefox profile:

```bash
export LENS_PLAYWRIGHT_HEADLESS=0
export LENS_PLAYWRIGHT_PROFILE_DIR=./browser_profile
export LENS_BROWSER_TIMEOUT=180
export LENS_USE_DIRECT_HTTP=0
export LENS_API_KEY=change-me
PYTHONPATH=src uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

Call the endpoint once. If Google shows consent or captcha in the visible Firefox window, solve it manually. Then rerun the local test.

Run server:

```bash
PYTHONPATH=src uvicorn chrome_lens_py.server:app --host 127.0.0.1 --port 8000
```

Test endpoint:

```bash
curl -i \
  -H "X-API-KEY: $LENS_API_KEY" \
  "http://127.0.0.1:8000/google-lens?imageUrl=https%3A%2F%2Fi.ebayimg.com%2F00%2Fs%2FMTYwMFgxNjAw%2Fz%2FBVcAAOSwS9m4zOb%2F%24_57.JPG" \
  -o api_test.html
```

Public tunnel example:

```bash
curl -i \
  -H "X-API-KEY: $LENS_API_KEY" \
  "https://gaming-felt-raymond-yea.trycloudflare.com/google-lens?imageUrl=https%3A%2F%2Fi.ebayimg.com%2F00%2Fs%2FMTYwMFgxNjAw%2Fz%2FBVcAAOSwS9m4zOb%2F%24_57.JPG" \
  -o api_test.html
```

Authentication checks:

```bash
# Missing key -> 401
curl -i "http://127.0.0.1:8000/google-lens?imageUrl=https%3A%2F%2Fi.ebayimg.com%2F00%2Fs%2FMTYwMFgxNjAw%2Fz%2FBVcAAOSwS9m4zOb%2F%24_57.JPG"

# Wrong key -> 403
curl -i \
  -H "X-API-KEY: wrong" \
  "http://127.0.0.1:8000/google-lens?imageUrl=https%3A%2F%2Fi.ebayimg.com%2F00%2Fs%2FMTYwMFgxNjAw%2Fz%2FBVcAAOSwS9m4zOb%2F%24_57.JPG"
```

Quick local smoke test:

```bash
LENS_API_KEY=change-me python3 experiments/test_api_local.py
```

Expected source header when fallback is used:

```text
X-Google-Lens-Source: playwright_firefox
X-Google-Lens-Direct-Attempt: skipped
```

Known limitation: this local setup depends on a persistent Firefox profile. Google may require a one-time manual consent/captcha warmup in the visible browser before automated requests succeed.

Recommended local concurrency: `1`. This is the only stable tested mode. The server reuses one warmed browser page and serializes requests through a lock.

Concurrency 2 was tested with one persistent Firefox profile and produced 0% success due to browser/profile contention. Do not run multiple concurrent requests against one profile.

External public 300-request test path: Dark Mac on external connection -> Cloudflare Tunnel -> Pink Mac server -> Google Lens. Results: 300 total, 297 valid pages, 290 valid pages with results, 7 no-match pages, 3 true failures, 3 captcha pages, 99.0% success rate, 5.242s average latency, 7.132s p95 latency, 48.158s max latency, and 682.6 estimated requests/hour.

Interpretation: the public tunnel path is validated from a separate machine. Latency and error rate are within challenge requirements, with captcha/unusual-traffic risk as the main remaining limitation.

Latest 1000-style run: attempted 1000 sequential requests and stopped early at 686 because captcha/unusual traffic appeared 4 times. Results were 680 valid pages, 667 valid pages with results, 13 no-match pages, 6 true failures, 99.1% success rate, 2.298s average latency, 2.377s p95 latency, and an estimated 1556.9 requests/hour.

Latest reusable-page local benchmark before the longer run: 100/100 valid pages, average latency around 1.7s.

Interpretation: the API met the challenge's 300+ valid HTML threshold before early stop and exceeded latency requirements. Google captcha/unusual-traffic risk remains the main scaling limitation, so recommended max concurrency remains `1` for this local single-profile setup.

## 🚀 Quick Start for Windows Users

If you don't want to install Python, you can download the standalone **lens_scan-windows-amd64.exe** from the [Releases](https://github.com/bropines/chrome-lens-py/releases) section.

> [!WARNING]
> **Antivirus False Positives**: Some antivirus software (like Windows Defender) might flag the compiled `.exe` as a threat (e.g., `Trojan:Win32/Wacatac.H!ml`). This is a **false positive** common with Nuitka/PyInstaller binaries. The tool is open-source; you can inspect the code and build it yourself if you have concerns.

### 📸 Automated ShareX Setup
If you use **ShareX**, you can fully automate the setup with one command:
```bash
# Using the installed package:
lens_scan --setup-sharex

# Or using the standalone .exe:
lens_scan-windows-amd64.exe --setup-sharex
```
This will automatically configure a hotkey (**Ctrl + O**) and the necessary actions to use Google Lens OCR.

---

## ✨ Key Features

-   **Modern Backend**: Utilizes Google's official Protobuf endpoint (`v1/crupload`) for robust and accurate results.
-   **Asynchronous & Safe**: Built with `asyncio` and `httpx`. Includes a built-in semaphore to prevent API abuse and IP bans from excessive concurrent requests.
-   **Powerful OCR & Segmentation**:
    -   Extract text from images as a single string.
    -   Get text segmented into logical blocks (paragraphs, dialog bubbles) with their own coordinates.
    -   Get individual text lines with their own precise geometry.
-   **Built-in Translation**: Instantly translate recognized text into any supported language.
-   **Versatile Image Sources**: Process images from a **file path**, **URL**, **bytes**, **PIL Image** object, or **NumPy array**.
-   **Text Overlay**: Automatically generate and save images with the translated text rendered over them(works poorly, alas, no time to do better).
-   **Feature-Rich CLI**: A simple yet powerful command-line interface (`lens_scan`) for quick use.
-   **Proxy Support**: Full support for HTTP, HTTPS, and SOCKS proxies.
-   **Clipboard Integration**: Instantly copy OCR or translation results to your clipboard with the `--sharex` flag.
-   **Flexible Configuration**: Manage settings via a `config.json` file, CLI arguments, or environment variables.

## 🚀 Installation

You can install the package using `pip`:

```bash
pip install chrome-lens-py
```

To enable clipboard functionality (the `--sharex` flag), install the library with the `[clipboard]` extra:

```bash
pip install "chrome-lens-py[clipboard]"
```

Or, install the latest version directly from GitHub:
```bash
pip install git+https://github.com/bropines/chrome-lens-py.git
```

## 🚀 Usage

<details>
  <summary><b>🛠️ CLI Usage (`lens_scan`)</b></summary>

  The command-line tool provides quick access to the library's features directly from your terminal.

  ```bash
  lens_scan <image_source> [ocr_lang] [options]
  ```

  -   **`<image_source>`**: Path to a local image file or an image URL.
  -   **`[ocr_lang]`** (optional): BCP 47 language code for OCR (e.g., 'en', 'ja'). If omitted, the API will attempt to auto-detect the language.

  #### **Options**

| Flag | Alias | Description |
| :--- | :--- | :--- |
| `--translate <lang>` | `-t` | **Translate** the OCR text to the target language code (e.g., `en`, `ru`). |
| `--translate-from <lang>` | | Specify the source language for translation (otherwise auto-detected). |
| `--translate-out <path>` | `-to` | **Save** the image with the translated text overlaid to the specified file path. |
| `--output-blocks` | `-b` | **Output OCR text as segmented blocks** (useful for comics). Incompatible with `--get-coords` and `--output-lines`.|
| `--output-lines` | `-ol` | **Output OCR text as individual lines** with their geometry. Incompatible with `--output-blocks` and `--get-coords`.|
| `--get-coords` | | Output recognized words and their coordinates in JSON format. Incompatible with `--output-blocks` and `--output-lines`. |
| `--sharex` | `-sx` | **Copy** the result (translation or OCR) to the clipboard. |
| `--ocr-single-line` | | Join all recognized OCR text into a single line, removing line breaks. |
| `--config-file <path>`| | Path to a custom JSON configuration file. |
| `--update-config` | | Update the default config file with settings from the current command. |
| `--font <path>` | | Path to a `.ttf` font file for the text overlay. |
| `--font-size <size>` | | Font size for the text overlay (default: 20). |
| `--proxy <url>` | | Proxy server URL (e.g., `socks5://127.0.0.1:9050`). |
| `--logging-level <lvl>`| `-l` | Set logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `--help` | `-h` | Show this help message and exit. |

  #### **Examples**

  **1. Basic OCR and Translation**
  
  Auto-detects the source language on the image and translates it to English. This is the most common use case.
  ```bash
  lens_scan "path/to/your/image.png" -t en
  ```

  ---
  
  **2. Get Segmented Text Blocks (for Comics/Manga)**

  Ideal for images with multiple, separate text boxes. This command outputs each recognized text block individually, making it perfect for translating comics or complex documents.
  ```bash
  lens_scan "path/to/manga.jpg" ja -b
  ```
  - `-b` is the alias for `--output-blocks`.

  ---
  
  **3. Get Individual Text Lines**
  
  Outputs each recognized line of text along with its geometry.
  ```bash
  lens_scan "path/to/document.png" --output-lines
  ```
  - `-ol` is the alias for `--output-lines`.

  ---

  **4. Get Coordinates of All Individual Words**
  
  Outputs a detailed JSON array containing every single recognized word and its precise geometric data (center, size, angle). Useful for programmatic analysis or custom overlays.
  ```bash
  lens_scan "path/to/diagram.png" --get-coords
  ```
  
  ---

  **5. Translate, Save Overlay, and Copy to Clipboard**
  
  A power-user workflow. This command will:
  1. OCR a Japanese image.
  2. Translate it to Russian.
  3. Save a new image named `translated_manga.png` with the Russian text rendered on it.
  4. Copy the final translation to your clipboard.
  ```bash
  lens_scan "path/to/manga.jpg" ja -t ru -to "translated_manga.png" -sx
  ```

  ---

  **6. Process an Image from a URL as a Single Line**

  Fetches an image directly from a URL and joins all recognized text into one continuous line, removing any line breaks.
  ```bash
  lens_scan "https://i.imgur.com/VPd1y6b.png" en --ocr-single-line
  ```

  ---

  **7. Use a SOCKS5 Proxy**
  
  All requests to the Google API will be routed through the specified proxy server, which is useful for privacy or bypassing region restrictions.
  ```bash
  lens_scan "image.png" --proxy "socks5://127.0.0.1:9050"
  ```

</details>

<details>
  <summary><b>👨‍💻 Programmatic API Usage (`LensAPI`)</b></summary>
  
  > [!IMPORTANT]
  > The `LensAPI` is fully **asynchronous**. All data retrieval methods must be called with `await` from within an `async` function.

  #### **Basic Example (Full Text)**
  
  ```python
  import asyncio
  from chrome_lens_py import LensAPI

  async def main():
      # Initialize the API. You can pass a proxy, region, etc. here.
      # By default, an API key is not required.
      api = LensAPI()

      image_source = "path/to/your/image.png" # Or a URL, PIL Image, NumPy array

      try:
          # Process the image and get a single string of text
          result = await api.process_image(
              image_path=image_source,
              ocr_language="ja",
              target_translation_language="en"
          )

          print("--- OCR Text ---")
          print(result.get("ocr_text"))

          print("\n--- Translated Text ---")
          print(result.get("translated_text"))
          
      except Exception as e:
          print(f"An error occurred: {e}")

  if __name__ == "__main__":
      asyncio.run(main())
  ```
  
  #### **Working with Different Image Sources**

  The `process_image` method seamlessly handles various input types.

  ```python
  from PIL import Image
  import numpy as np

  # ... inside an async function ...
  
  # From a URL
  result_url = await api.process_image("https://i.imgur.com/VPd1y6b.png")

  # From a PIL Image object
  with Image.open("path/to/image.png") as img:
      result_pil = await api.process_image(img)

  # From a NumPy array (e.g., loaded via OpenCV)
  with Image.open("path/to/image.png") as img:
      numpy_array = np.array(img)
      result_numpy = await api.process_image(numpy_array)
  ```

  #### **Getting Segmented Text Blocks**

  To get text segmented into logical blocks (like dialog bubbles in a comic), use the `output_format='blocks'` parameter.

  ```python
  import asyncio
  from chrome_lens_py import LensAPI

  async def process_comics():
      api = LensAPI()
      image_source = "path/to/manga.jpg"
      
      result = await api.process_image(
          image_path=image_source,
          output_format='blocks' # Get segmented blocks instead of a single string
      )

      # The result now contains a 'text_blocks' key
      text_blocks = result.get("text_blocks", [])
      print(f"Found {len(text_blocks)} text blocks.")

      for i, block in enumerate(text_blocks):
          print(f"\n--- Block #{i+1} ---")
          print(block['text'])
          # block also contains 'lines' and 'geometry' keys
  
  asyncio.run(process_comics())
  ```

  #### **Getting Individual Lines and their Geometry**

  To get each recognized line of text as a separate item, use the `output_format='lines'` parameter.

  ```python
  import asyncio
  from chrome_lens_py import LensAPI

  async def process_document_lines():
      api = LensAPI()
      image_source = "path/to/document.png"
      
      result = await api.process_image(
          image_path=image_source,
          output_format='lines' # Get individual lines with their geometry
      )

      # The result now contains a 'line_blocks' key
      line_blocks = result.get("line_blocks", [])
      print(f"Found {len(line_blocks)} lines.")

      for i, line in enumerate(line_blocks):
          print(f"\n--- Line #{i+1} ---")
          print(f"Text: {line['text']}")
          print(f"Geometry: {line['geometry']}")
  
  asyncio.run(process_document_lines())
  ```

  #### **Getting Fully Detailed Text Structures**

To get a complete, nested structure of paragraphs, lines, and words with geometry at each level, use `output_format='detailed'`.

```python
import asyncio
from chrome_lens_py import LensAPI

async def process_with_details():
    api = LensAPI()
    image_source = "path/to/document.png"
    
    result = await api.process_image(
        image_path=image_source,
        output_format='detailed' # Get the fully nested structure
    )

    # The result now contains a 'detailed_blocks' key
    detailed_blocks = result.get("detailed_blocks", [])
    print(f"Found {len(detailed_blocks)} detailed blocks.")

    for i, block in enumerate(detailed_blocks):
        print(f"\n--- Block #{i+1} ---")
        print(f"  Geometry: {block['geometry']}")
        for j, line in enumerate(block['lines']):
            print(f"    --- Line #{j+1}: '{line['text']}' ---")
            for k, word in enumerate(line['words']):
                 print(f"      - Word: '{word['text']}', Geometry: {word['geometry']}")

asyncio.run(process_with_details())
```


  #### **`LensAPI` Constructor**

  ```python
  api = LensAPI(
      api_key: str = "YOUR_API_KEY_OR_DEFAULT",
      client_region: Optional[str] = None,
      client_time_zone: Optional[str] = None,
      proxy: Optional[str] = None,
      timeout: int = 60,
      font_path: Optional[str] = None,
      font_size: Optional[int] = None,
      max_concurrent: int = 5
  )
  ```
  
  #### **`process_image` Method**
  
  ```python
  result: dict = await api.process_image(
      image_path: Any,
      ocr_language: Optional[str] = None,
      target_translation_language: Optional[str] = None,
      source_translation_language: Optional[str] = None,
      output_overlay_path: Optional[str] = None,
      ocr_preserve_line_breaks: bool = True,
      output_format: Literal['full_text', 'blocks', 'lines', 'detailed'] = 'full_text'
  )
  ```
  -   **`output_format`**: Controls the structure of the OCR output. `'full_text'` (default) returns a single string in `ocr_text`. `'blocks'` returns a list in `text_blocks`. `'lines'` returns a list in `line_blocks`. `'detailed'` returns a fully nested structure in `detailed_blocks`.
  -   **`ocr_preserve_line_breaks`**: If `False` and `output_format` is `'full_text'`, joins all OCR text into a single line.

  **The returned `result` dictionary contains:**
  - `ocr_text` (Optional[str]): The full recognized text (if `output_format='full_text'`).
  - `text_blocks` (Optional[List[dict]]): A list of segmented text blocks (if `output_format='blocks'`). Each block is a dict with `text`, `lines`, and `geometry`.
  - `line_blocks` (Optional[List[dict]]): A list of individual text lines (if `output_format='lines'`). Each block is a dict with `text` and `geometry`.
  - `translated_text` (Optional[str]): The translated text, if requested.
  - `word_data` (List[dict]): A list of dictionaries for every recognized word with its geometry.
  - `detailed_blocks` (Optional[List[dict]]): A list of fully structured text blocks (if `output_format='detailed'`). Each block contains lines, which in turn contain words, with geometry at every level.
  - `raw_response_objects`: The "raw" Protobuf response object for further analysis.

</details>

<details>
  <summary><b>⚙️ Configuration</b></summary>
  
  Settings are loaded with the following priority: **CLI Arguments > `config.json` File > Library Defaults**.
  
  #### **`config.json`**
  
  A `config.json` file can be placed in your system's default config directory to set persistent options.
  -   **Linux**: `~/.config/chrome-lens-py/config.json`
  -   **macOS**: `~/Library/Application Support/chrome-lens-py/config.json`
  -   **Windows**: `C:\Users\<user>\.config\chrome-lens-py\config.json`

  ##### **Example `config.json`**
  ```json
  {
    "api_key": "OPTIONAL! If you don't know what this is, I don't recommend setting it here.",
    "proxy": "socks5://127.0.0.1:9050",
    "client_region": "DE",
    "client_time_zone": "Europe/Berlin",
    "timeout": 90,
    "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "ocr_preserve_line_breaks": true
  }
  ```

</details>

## Sharex Integration
Check [sharex.md](docs/sharex.md) for more information on how to use this library with ShareX.

## ❤️ Support & Acknowledgments

-   **OWOCR**: Greatly inspired by and based on [OWOCR](https://github.com/AuroraWright/owocr). Thank you to them for their research into Protobuf and OCR implementation.
-   **Chrome Lens OCR**: For the original implementation and ideas that formed the basis of this library. The update with SHAREX support was originally tested and added by me to [chrome-lens-ocr](https://github.com/dimdenGD/chrome-lens-ocr), thanks for the initial implementation and ideas.
-   **AI Collaboration**: A significant portion of the v3.0 code, including the architectural refactor, asynchronous implementation, and Protobuf integration, was developed in collaboration with an advanced AI assistant.
-   **GOOGLE**: For the convenient and high-quality Lens technology.
-   **Support the Author**: If you find this library useful, you can support the author - **[Boosty](https://boosty.to/pinus)**

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=bropines/chrome-lens-py&type=Date)](https://www.star-history.com/#bropines/chrome-lens-py&Date)

### Disclaimer

This project is intended for educational and experimental purposes only. Use of Google's services must comply with their Terms of Service. The author is not responsible for any misuse of this software.
