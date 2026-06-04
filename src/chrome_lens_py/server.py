import os
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Response

from .exact_matches import GoogleLensExactMatchesClient

DEFAULT_CURL_PATH = Path("experiments/firefox_exact_match.curl")
logger = logging.getLogger(__name__)

app = FastAPI(title="Project 4 Google Lens Exact Matches")


def get_curl_path() -> Path:
    return Path(os.environ.get("FIREFOX_LENS_CURL", str(DEFAULT_CURL_PATH)))


def get_profile_dir():
    value = os.environ.get("LENS_PLAYWRIGHT_PROFILE_DIR")
    return Path(value) if value else None


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


@app.get("/google-lens")
async def google_lens(imageUrl: str = Query(..., min_length=1)):
    curl_path = get_curl_path()
    if not curl_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Firefox cURL template not found at {curl_path}",
        )

    try:
        client = GoogleLensExactMatchesClient.from_firefox_curl(
            curl_path,
            timeout=env_float("LENS_HTTP_TIMEOUT", 60.0),
            browser_timeout=env_float("LENS_BROWSER_TIMEOUT", 45.0),
            headless=env_bool("LENS_PLAYWRIGHT_HEADLESS", True),
            profile_dir=get_profile_dir(),
        )
        result = await client.fetch_exact_matches_with_fallback(imageUrl)
    except httpx.HTTPStatusError as error:
        logger.warning("Google Lens upstream HTTP error: %s", error)
        raise HTTPException(
            status_code=502,
            detail=f"Upstream request failed with HTTP {error.response.status_code}",
        ) from error
    except Exception as error:
        logger.warning("Google Lens API failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail="Google Lens fallback did not produce valid result HTML",
        ) from error

    return Response(
        content=result.html,
        media_type="text/html; charset=utf-8",
        headers={"X-Google-Lens-Source": result.source},
    )
