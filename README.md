<p align="center">
  <img src="assets/banner.svg" alt="Be_Ghost — ultra-lightweight stealth browser" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-22d3ee.svg"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-7c3aed.svg"></a>
  <img alt="Tests: 54 passing" src="https://img.shields.io/badge/tests-54%20passing-22c55e.svg">
  <img alt="Lite mode: ~20 MB RAM" src="https://img.shields.io/badge/lite%20mode-~20%20MB%20RAM-bae6fd.svg">
</p>

# Be_Ghost

Hybrid stealth browser. Two engines in one API:

| Mode | What runs | RAM | Disk | Use it for |
|---|---|---|---|---|
| `lite` | curl_cffi (Chrome JA3) + selectolax + QuickJS | ~20 MB | ~5 MB | APIs, static HTML, blogs, news, search results, batch scraping |
| `full` | Playwright + Chromium with stealth patches | ~150 MB | ~280 MB | SPAs, JS-rendered sites, Cloudflare challenges, sites needing canvas |
| `auto` (default) | tries `lite` first, escalates to `full` when the response signals an SPA / captcha / error | dynamic | dynamic | everything |

`mode="auto"` is what you want. Be_Ghost does the right thing per URL.

## Install

```bash
# everything (lite + full)
pip install -e ".[full]"
playwright install chromium

# minimum for lite-only — no Chromium download needed
pip install -e ".[lite]"
```

Extras:
- `[lite]` — `curl_cffi` + `selectolax` + `quickjs` (no Chromium)
- `[http]` — just `curl_cffi`
- `[parse]` — just `selectolax`
- `[mcp]` — MCP server entrypoint
- `[full]` — all of the above

## API tour

### Hybrid mode (the default)

```python
from be_ghost import BeGhost

with BeGhost(mode="auto") as ghost:        # mode="auto" is the default
    r1 = ghost.get("https://example.com")  # served by lite — no Chromium spawned
    r2 = ghost.get("https://twitter.com")  # auto-escalates to Chromium
```

Force a mode when you want to:

```python
BeGhost(mode="lite")  # never spawn Chromium. Fail fast on SPAs.
BeGhost(mode="full")  # always Chromium. Most compatible.
ghost.get(url, force="lite")  # one-shot override
```

Direct lite usage when you don't want the router overhead:

```python
from be_ghost import LiteBrowser

with LiteBrowser() as ghost:
    with ghost.session("https://example.com") as page:
        print(page.title())
        page.goto("/about")  # navigates within the same session
```

### One-shot fetch (HTTP-style)

```python
from be_ghost import BeGhost

with BeGhost() as ghost:
    r = ghost.get("https://example.com")
    print(r.status, r.final_url, r.elapsed_ms)
    print(r.html[:200])
    print(r.json())            # if body is JSON
    print(r.text_only())       # readable text (selectolax)
    print(r.select_text("h1")) # CSS extract
    print(r.links())           # all <a href>
    print(r.captcha)           # CaptchaInfo (cloudflare/hcaptcha/...)
```

### Async + concurrent batch

```python
import asyncio
from be_ghost import AsyncBeGhost

async def main():
    async with AsyncBeGhost() as ghost:
        results = await ghost.get_many(urls, concurrency=5)

asyncio.run(main())
```

### Production toolkit (cache + rate limit + pool + stats)

```python
from be_ghost import BeGhost, DiskCache, RateLimiter

cache = DiskCache(ttl=3600)
rl = RateLimiter(default_rps=2.0, per_domain={"api.fast.com": 10.0})

with BeGhost(cache=cache, rate_limit=rl, pool_size=5) as ghost:
    ghost.enable_logging("ghost.log")            # JSON-line per request
    r = ghost.get(url)
    print(ghost.stats())                          # total/lite/full/cache_hit/captcha/error
```

### Sitemap discovery + page metadata

```python
urls = ghost.sitemap("https://example.com", max_urls=10_000)
md = ghost.get(urls[0]).metadata()                # title, description, og, jsonld, canonical
```

CLI: `be_ghost sitemap example.com`

### Downloads / GraphQL / WebSocket / Cookies

```python
ghost.download(url, "big.zip", on_progress=lambda d, t: print(d, t))    # resumable, JA3-spoofed
ghost.graphql("https://api.com/graphql", "query { ... }", variables={...})
with ghost.ws("wss://stream.example.com") as ws:
    ws.send("hi"); print(ws.recv())
ghost.cookies.set("session", "abc", domain=".example.com")
```

### Cookie consent auto-accept

```python
with BeGhost(auto_accept_consent=True) as ghost:
    with ghost.session("https://eu-site.com") as page:
        # OneTrust/Cookiebot/Didomi/etc. banner is clicked away automatically
        ...
```

Recognizes 8 major consent providers + a generic "Accept all" / "I agree" text fallback.

### Smart waiters

```python
from be_ghost.waiters import wait_for_text, wait_for_predicate, wait_for_quiet_network

wait_for_text(page, "Order confirmed")
wait_for_predicate(page, "document.querySelectorAll('article').length >= 10")
wait_for_quiet_network(page, idle_ms=500)   # ignores GA/Sentry/etc.
```

### Extraction templates

```python
data = r.extract({
    "title": "h1",
    "price": (".price", "float"),         # type-coerced
    "images": ("img.gallery", "src", "all"),
    "tags": ("ul.tags > li", "text", "all"),
    "url": "@request",
})
```

### Auto-debug on error

```python
with BeGhost(debug_dir="./debug") as ghost:
    ghost.get(url)   # if it raises, screenshot + HTML + log are saved
```

### HTML diff

```python
r1, r2 = ghost.get(url), ghost.get(url)
d = r1.diff(r2)              # HtmlDiff: added/removed lines, changed text chars
print(d.unified)             # full unified-diff string
```

### CDP helpers

```python
from be_ghost.cdp import set_geolocation, throttle_network, clear_service_workers

with ghost.session() as page:
    set_geolocation(page, lat=40.7128, lon=-74.0060)
    throttle_network(page, download_kbps=1500, latency_ms=40)
    clear_service_workers(page, "https://example.com")
```

### HTTP/3 + parallel downloads

```python
from be_ghost import LiteBrowser
LiteBrowser(http_version="h3")              # QUIC/HTTP3
ghost.download(url, "big.zip", parallel=8)  # 8-chunk multi-range
```

### Mobile profiles

`profile="iphone_safari"` (iPhone Safari 17) and `profile="android_chrome"` (Pixel 8 Chrome) ship alongside the desktop ones — many sites serve simpler HTML to mobile UAs.

### JA3-spoofed HTTP fallback

When you don't need JS, skip the browser:

```python
ghost.get("https://api.example.com/json", auto_http=True)
```

Tries a `curl_cffi` request that mimics Chrome's TLS handshake. Falls back to the browser only if the HTTP attempt fails or returns a challenge page. ~100x cheaper than launching a page.

### Interactive session with human-like input

```python
with ghost.session("https://example.com/login", human=True) as page:
    page.fill_form({
        "input[name=user]": "alice",
        "input[name=pw]": "secret",
    }, submit="button[type=submit]", typo_rate=0.04)
    page.scroll(total=1500)
```

Bezier mouse curves, randomized typing cadence, optional typos.

### Persistent storage (cookies + localStorage)

```python
with BeGhost(storage_state="state.json") as ghost:
    # state.json auto-loads on start, auto-saves on close
    ...
```

### Proxy rotation pool

```python
from be_ghost import ProxyPool

pool = ProxyPool(["http://...", "http://..."], max_failures=3, cooldown_seconds=300)
with BeGhost(proxy_pool=pool) as ghost:
    r = ghost.get(url)   # picks a live proxy, marks failures, rotates per request
pool.health_check()      # explicit health probe (requires curl_cffi)
```

### Pagination

```python
for r in ghost.paginate(url, next_selector="a.next", max_pages=10):
    print(len(r.html))
```

### Capture (screenshot, PDF, MHTML, trace, HAR)

```python
ghost.get(url, screenshot="out.png", pdf="out.pdf", mhtml="out.mhtml")

with BeGhost(trace="run.zip") as ghost:           # debug with: playwright show-trace run.zip
    ghost.get(url)

with BeGhost(har_record="cap.har") as ghost:      # record once
    ghost.get(url)

with BeGhost(har_replay="cap.har") as ghost:      # replay offline (zero network)
    ghost.get(url)
```

### Resource budget

```python
BeGhost(max_bytes=5 * 1024 * 1024)   # abort if response total > 5 MB
```

### Retry + captcha handling

```python
ghost.get(url, retries=3, retry_on_captcha=True)
```

Exponential backoff with jitter. Re-fetches when a Cloudflare / hCaptcha / DataDome / etc. page is detected.

## CLI

```bash
be_ghost https://example.com -o info             # status, profile, captcha, timing
be_ghost https://api.x.com/data -o json          # parse JSON
be_ghost https://example.com -o text             # readable text
be_ghost https://example.com -o links            # all hrefs
be_ghost https://example.com --screenshot p.png --pdf p.pdf --mhtml p.mhtml
be_ghost https://example.com --auto-http         # try HTTP first
be_ghost https://example.com --storage state.json
be_ghost https://example.com --proxy http://user:pass@host:8080
be_ghost https://example.com --trace run.zip --har-record cap.har
be_ghost --detect                                # full self-test against detector pages

# concurrent batch
be_ghost batch urls.txt --concurrency 10 --out-dir pages/
echo -e "https://a.com\nhttps://b.com" | be_ghost batch -

be_ghost --list-profiles
```

## Config file

Drop `be_ghost.toml` in your project root or `~/.be_ghost.toml`:

```toml
[defaults]
profile = "win11_chrome"
lite = true
proxy = "http://user:pass@host:8080"

[storage]
state = "state.json"
```

## MCP server (Claude / LLM clients)

```bash
pip install "be_ghost[mcp]"
be_ghost_mcp                   # stdio MCP server
```

Exposes tools: `fetch`, `screenshot`, `extract`, `submit_form`. Add to `claude_desktop_config.json`:

```json
{ "mcpServers": { "be_ghost": { "command": "be_ghost_mcp" } } }
```

## pytest

```python
def test_homepage(ghost):
    r = ghost.get("https://example.com")
    assert r.ok
    assert "Example" in r.html

@pytest.mark.asyncio
async def test_api(async_ghost):
    r = await async_ghost.get("https://api.example.com/data")
    assert r.ok
```

Session-scoped — one browser for the whole suite.

## Self-test

```bash
be_ghost --detect
```

Runs sannysoft + areyouheadless + creepjs and prints a pass/fail score per detector plus an overall percentage. CI fails if overall < 70%.

## Stealth coverage

Injected before any page script:
- `navigator.webdriver` → `undefined`
- `navigator.plugins` / `mimeTypes` populated like real Chrome
- `navigator.permissions.query` returns sane values for `notifications`
- WebGL `UNMASKED_VENDOR_WEBGL` / `RENDERER` spoofed to match the OS profile
- Canvas `toDataURL` / `getImageData` get deterministic per-session noise
- AudioContext frequency data noised
- `navigator.languages`, `hardwareConcurrency`, `deviceMemory`, `platform` aligned with the profile
- `window.chrome.runtime` / `chrome.app` stubbed
- `Function.prototype.toString` patched so overridden funcs still report `[native code]`
- iframe `contentWindow.navigator.webdriver` cleared on access
- `Error.prototype.toString` strips `playwright`/`puppeteer` stack frames

Plus at the network layer:
- Sec-CH-UA + full Client Hints aligned with profile
- TLS/JA3 fingerprint spoofing via `auto_http` (curl_cffi)
- WebRTC IP leak prevention via Chromium flag

## Profiles

`win11_chrome`, `win10_chrome`, `mac_chrome`, `linux_chrome` (Chrome 132). Each is internally consistent (UA matches platform, GL vendor matches OS, Sec-CH-UA matches UA). `profile=None` randomizes per session.

## All `BeGhost` options

| arg | default | what |
|---|---|---|
| `stealth` | `True` | inject anti-fingerprint patches |
| `lite` | `True` | block image/font/css/media |
| `headless` | `True` | hide window |
| `profile` | random | named profile |
| `proxy` | `None` | single proxy URL |
| `proxy_pool` | `None` | `ProxyPool` instance (overrides `proxy`) |
| `block_resources` | `{image,media,font,stylesheet}` | override blocked types |
| `extra_args` | `[]` | additional Chromium flags |
| `timeout_ms` | `30000` | default page timeout |
| `storage_state` | `None` | persistent cookie/localStorage path |
| `auto_save_storage` | `True` | save storage_state on context close |
| `trace` | `None` | path to trace.zip |
| `har_record` | `None` | record traffic to .har |
| `har_replay` | `None` | serve from recorded .har |
| `max_bytes` | `None` | abort context if response total exceeds N |
| `max_seconds` | `None` | per-page timeout override |
| `client_hints` | profile default | Sec-CH-UA override dict |

## Docker

```bash
docker build -t be_ghost .
docker run --rm be_ghost https://example.com -o info
```

## Honest limits

- **TLS**: solved for HTTP-only paths via `auto_http=True`. The browser path still uses Chromium's TLS — same handshake as a real Chrome, so this is fine.
- **IP reputation**: nothing in this library helps if your IP is on a block list. Use a residential proxy pool.
- **Behavioral**: bot detectors that fingerprint mouse/keyboard timing benefit from `human=True`, but no library defeats this fully if you're moving at machine speed.
- **lite=True breaks layout-heavy sites**: drop to `lite=False` for those.
