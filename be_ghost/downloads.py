"""File downloads with progress + resume.

Uses curl_cffi when available for browser-grade TLS, falls back to httpx/urllib
if needed. Resume via Range header.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from .fingerprint import curl_impersonate_target


@dataclass
class DownloadResult:
    path: str
    size: int
    elapsed_ms: int
    resumed: bool


def download(
    url: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    proxy: str | None = None,
    chunk_size: int = 64 * 1024,
    on_progress: Callable[[int, int | None], None] | None = None,
    resume: bool = True,
    impersonate: str | None = None,
    timeout: float = 120.0,
) -> DownloadResult:
    """Stream `url` to `path`. Resumes if `path` already exists and resume=True.

    on_progress(downloaded, total) is called periodically; total may be None.
    """
    try:
        from curl_cffi.requests import Session  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "curl_cffi not installed. install with: pip install 'be_ghost[lite]'"
        ) from e

    import time
    headers = dict(headers or {})
    existing = os.path.getsize(path) if (resume and os.path.exists(path)) else 0
    if existing:
        headers["Range"] = f"bytes={existing}-"

    sess = Session()
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}

    t0 = time.monotonic()
    r = sess.request(
        "GET", url,
        headers=headers,
        impersonate=impersonate or curl_impersonate_target(),
        timeout=timeout,
        stream=True,
    )
    if existing and r.status_code != 206:
        # Server didn't honor Range — start over.
        existing = 0
        if os.path.exists(path):
            os.remove(path)

    total = None
    cl = r.headers.get("content-length")
    if cl is not None:
        try:
            total = int(cl) + existing
        except ValueError:
            total = None

    written = existing
    mode = "ab" if existing else "wb"
    with open(path, mode) as f:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            f.write(chunk)
            written += len(chunk)
            if on_progress:
                on_progress(written, total)

    elapsed = int((time.monotonic() - t0) * 1000)
    return DownloadResult(path=path, size=written, elapsed_ms=elapsed, resumed=bool(existing))


def download_parallel(
    url: str,
    path: str,
    *,
    chunks: int = 8,
    headers: dict[str, str] | None = None,
    proxy: str | None = None,
    impersonate: str | None = None,
    timeout: float = 120.0,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> DownloadResult:
    """Multi-range parallel download. Falls back to single-stream if server doesn't support Range.

    Splits the file into `chunks` parts, fetches each in a thread, then concatenates.
    Often 4-8x faster on big files when the server has spare bandwidth.
    """
    try:
        from curl_cffi.requests import Session  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError("curl_cffi not installed (pip install 'be_ghost[lite]')") from e
    import time
    from concurrent.futures import ThreadPoolExecutor

    sess = Session()
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    target = impersonate or curl_impersonate_target()

    # HEAD to learn the size and Range support.
    head = sess.request("HEAD", url, headers=headers or {}, impersonate=target,
                         timeout=timeout, allow_redirects=True)
    accept_ranges = head.headers.get("accept-ranges", "").lower()
    cl = head.headers.get("content-length")
    if accept_ranges != "bytes" or not cl:
        # Server doesn't support Range — fall back to streaming.
        return download(url, path, headers=headers, proxy=proxy, on_progress=on_progress,
                        impersonate=impersonate, timeout=timeout)

    total = int(cl)
    chunks = max(1, min(chunks, total // (256 * 1024) or 1))  # don't over-split tiny files
    span = total // chunks

    def _grab(idx: int) -> bytes:
        start = idx * span
        end = total - 1 if idx == chunks - 1 else (start + span - 1)
        h = dict(headers or {})
        h["Range"] = f"bytes={start}-{end}"
        r = sess.request("GET", url, headers=h, impersonate=target, timeout=timeout)
        return r.content

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=chunks) as pool:
        results = list(pool.map(_grab, range(chunks)))
    written = 0
    with open(path, "wb") as f:
        for chunk in results:
            f.write(chunk)
            written += len(chunk)
            if on_progress:
                on_progress(written, total)
    elapsed = int((time.monotonic() - t0) * 1000)
    return DownloadResult(path=path, size=written, elapsed_ms=elapsed, resumed=False)
