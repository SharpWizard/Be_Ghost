"""Self-test against public bot-detection pages.

Runs Be_Ghost against the standard detector pages and parses each one's own
result text into a pass/fail score. Use it to verify stealth changes actually
help instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    url: str
    passed: int
    failed: int
    notes: list[str]
    score: float  # 0..1

    def __str__(self) -> str:
        bar = "█" * int(self.score * 20) + "░" * (20 - int(self.score * 20))
        return f"  {self.name:<26} {bar} {self.score*100:5.1f}%  ({self.passed} ok / {self.failed} fail)"


# Each entry: (name, url, parser-callback returning (passed, failed, notes))

def _parse_sannysoft(html: str) -> tuple[int, int, list[str]]:
    # sannysoft uses class="passed" / class="failed" on each row.
    passed = len(re.findall(r'class="passed"', html))
    failed = len(re.findall(r'class="failed"', html))
    notes: list[str] = []
    for m in re.finditer(r'<td>(.*?)</td>\s*<td class="failed">', html, re.S):
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if text:
            notes.append(text[:60])
    return passed, failed, notes[:8]


def _parse_areyouheadless(html: str) -> tuple[int, int, list[str]]:
    if re.search(r"You are not Chrome headless", html, re.I) or \
       re.search(r"not\s*headless", html, re.I):
        return 1, 0, []
    if re.search(r"You are Chrome headless", html, re.I) or \
       re.search(r"\bheadless\b", html, re.I):
        return 0, 1, ["page reports: headless detected"]
    return 0, 0, ["could not parse result"]


def _parse_creepjs(html: str) -> tuple[int, int, list[str]]:
    # creepjs renders client-side; we can only confirm load + look for a trust score.
    m = re.search(r"trust score[^0-9]*([0-9]+)", html, re.I)
    if m:
        score = int(m.group(1))
        return (1, 0, [f"trust score: {score}"]) if score >= 50 else (0, 1, [f"trust score: {score}"])
    return 0, 0, ["client-side render — open in --show to see results"]


SUITE = [
    ("sannysoft", "https://bot.sannysoft.com/", _parse_sannysoft),
    ("areyouheadless", "https://arh.antoinevastel.com/bots/areyouheadless", _parse_areyouheadless),
    ("creepjs (limited)", "https://abrahamjuliot.github.io/creepjs/", _parse_creepjs),
]


def run(ghost) -> list[CheckResult]:
    """Run the full suite against a started BeGhost instance."""
    results: list[CheckResult] = []
    for name, url, parser in SUITE:
        try:
            r = ghost.get(url, wait_until="networkidle")
            p, f, notes = parser(r.html)
        except Exception as e:
            results.append(CheckResult(name, url, 0, 1, [f"fetch error: {e}"], 0.0))
            continue
        total = p + f
        score = (p / total) if total else 0.0
        results.append(CheckResult(name, url, p, f, notes, score))
    return results


def report(results: list[CheckResult]) -> str:
    lines = ["", "Be_Ghost detection self-test", "=" * 60]
    for r in results:
        lines.append(str(r))
        for n in r.notes:
            lines.append(f"      · {n}")
    overall = sum(r.score for r in results) / max(1, len(results))
    bar = "█" * int(overall * 30) + "░" * (30 - int(overall * 30))
    lines += ["-" * 60, f"  OVERALL                    {bar} {overall*100:5.1f}%", ""]
    return "\n".join(lines)
