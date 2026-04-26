"""Run Be_Ghost against common bot-detection test pages.

Note: lite=False here because some detectors load CSS/fonts to fingerprint.
"""

from be_ghost import BeGhost

TARGETS = [
    "https://bot.sannysoft.com/",
    "https://abrahamjuliot.github.io/creepjs/",
    "https://arh.antoinevastel.com/bots/areyouheadless",
]


def main():
    with BeGhost(stealth=True, lite=False, headless=True) as ghost:
        print("profile:", ghost.profile["name"])
        for url in TARGETS:
            r = ghost.get(url, wait_until="networkidle")
            print(f"{r.status}  {r.elapsed_ms:>5}ms  {len(r.html):>7}b  {url}")


if __name__ == "__main__":
    main()
