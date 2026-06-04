import os
import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response

from .exact_matches import (
    BrowserSessionManager,
    GoogleLensExactMatchesClient,
    LensExactMatchesError,
    is_retry_shell,
)

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


def browser_kwargs(headers=None):
    return {
        "headers": headers,
        "browser_timeout": env_float("LENS_BROWSER_TIMEOUT", 45.0),
        "headless": env_bool("LENS_PLAYWRIGHT_HEADLESS", True),
        "profile_dir": get_profile_dir(),
    }


def get_browser_manager(headers=None) -> BrowserSessionManager:
    manager = getattr(app.state, "browser_manager", None)
    if manager is None:
        manager = BrowserSessionManager(**browser_kwargs(headers=headers))
        app.state.browser_manager = manager
    return manager


@app.on_event("startup")
async def startup():
    app.state.browser_manager = None


@app.on_event("shutdown")
async def shutdown():
    manager = getattr(app.state, "browser_manager", None)
    if manager:
        await manager.close()


@app.get("/google-lens")
async def google_lens(
    imageUrl: str = Query(..., min_length=1),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
):
    expected_api_key = os.environ.get("LENS_API_KEY")
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="LENS_API_KEY is not configured")
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-KEY header")
    if x_api_key != expected_api_key:
        raise HTTPException(status_code=403, detail="Invalid X-API-KEY header")

    use_direct_http = env_bool("LENS_USE_DIRECT_HTTP", False)
    logger.warning("direct_http_enabled=%s", use_direct_http)

    try:
        direct_client_kwargs = {
            "timeout": env_float("LENS_HTTP_TIMEOUT", 60.0),
            "browser_timeout": env_float("LENS_BROWSER_TIMEOUT", 45.0),
            "headless": env_bool("LENS_PLAYWRIGHT_HEADLESS", True),
            "profile_dir": get_profile_dir(),
        }
        if use_direct_http:
            logger.warning("direct_attempt=performed")
            curl_path = get_curl_path()
            if not curl_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail=f"Firefox cURL template not found at {curl_path}",
                )
            client = GoogleLensExactMatchesClient.from_firefox_curl(
                curl_path, **direct_client_kwargs
            )
            direct_result = await client.fetch_exact_matches(imageUrl)
            if not is_retry_shell(direct_result.html):
                result = direct_result
            else:
                manager = get_browser_manager(headers=client.headers)
                result = await manager.fetch_exact_matches(imageUrl, direct_result)
        else:
            logger.warning("direct_attempt=skipped")
            manager = get_browser_manager()
            result = await manager.fetch_exact_matches(imageUrl)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as error:
        logger.warning("Google Lens upstream HTTP error: %s", error)
        raise HTTPException(
            status_code=502,
            detail={
                "reason": "browser_navigation_failed",
                "message": f"Upstream request failed with HTTP {error.response.status_code}",
            },
        ) from error
    except LensExactMatchesError as error:
        logger.warning("Google Lens API failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail={"reason": error.reason, "message": str(error)},
        ) from error
    except Exception as error:
        logger.warning("Google Lens API failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail={
                "reason": "validation_failed",
                "message": "Google Lens fallback did not produce valid result HTML",
            },
        ) from error

    return Response(
        content=result.html,
        media_type="text/html; charset=utf-8",
        headers={
            "X-Google-Lens-Source": result.source,
            "X-Google-Lens-Direct-Attempt": result.direct_attempt,
        },
    )
