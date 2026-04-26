"""GraphQL helper. Posts a query/mutation through the lite client (or full)."""

from __future__ import annotations

from typing import Any

from .browser import Response


def query(
    ghost,
    url: str,
    query_str: str,
    variables: dict | None = None,
    operation_name: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    force: str | None = "lite",
) -> dict:
    """Send a GraphQL request. Returns the parsed JSON body.

    Raises if the server returns non-200 or invalid JSON.
    """
    payload: dict[str, Any] = {"query": query_str}
    if variables is not None:
        payload["variables"] = variables
    if operation_name:
        payload["operationName"] = operation_name

    h = {"content-type": "application/json", "accept": "application/json"}
    if headers:
        h.update(headers)

    r = _post_json(ghost, url, payload, headers=h, force=force)
    if not (200 <= r.status < 300):
        raise RuntimeError(f"graphql {r.status} for {url}: {r.html[:200]}")
    return r.json()


def _post_json(ghost, url: str, payload: dict, *, headers: dict[str, str], force: str | None) -> Response:
    """Internal POST helper. Uses the lite client directly when available."""
    # Prefer lite path — GraphQL is HTTP-only.
    try:
        from .lite.client import LiteClient, available
        if available() and (force == "lite" or force is None):
            client = LiteClient(profile=ghost.profile_name, proxy=ghost.proxy,
                                timeout=ghost.timeout_ms / 1000.0)
            try:
                http = client.post(url, json=payload, headers=headers)
                return Response(
                    url=url, status=http.status, headers=http.headers,
                    html=http.text, cookies=http.cookies,
                    final_url=http.final_url, elapsed_ms=http.elapsed_ms,
                )
            finally:
                client.close()
    except ImportError:
        pass

    # Fall back: use a Playwright APIRequestContext from the full browser.
    if not ghost._browser:
        ghost.start()
    api = ghost._browser.new_context().request  # quick API context
    try:
        resp = api.post(url, headers=headers, data=payload)
        return Response(
            url=url, status=resp.status, headers=dict(resp.headers),
            html=resp.text(), cookies=[], final_url=resp.url, elapsed_ms=0,
        )
    finally:
        try:
            api.dispose()
        except Exception:
            pass
