#!/usr/bin/env python3
"""
Pulls real GitHub stats for a user and regenerates assets/commit-tower.svg
so the animated "tower" always reflects current repos / stars / followers.

Run manually:
    GITHUB_TOKEN=xxxx GITHUB_USERNAME=RoumaisaTanveer python scripts/generate_tower.py

In CI (GitHub Actions), GITHUB_TOKEN is provided automatically.
"""

import os
import sys
import urllib.request
import json

USERNAME = os.environ.get("GITHUB_USERNAME", "RoumaisaTanveer")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "commit-tower.svg")

API = "https://api.github.com"


def gh_get(path):
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("User-Agent", "tower-stats-script")
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def fetch_stats(username):
    user = gh_get(f"/users/{username}")
    repos = []
    page = 1
    while True:
        batch = gh_get(f"/users/{username}/repos?per_page=100&page={page}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    public_repos = user.get("public_repos", len(repos))
    followers = user.get("followers", 0)
    total_stars = sum(r.get("stargazers_count", 0) for r in repos)

    return {
        "repos": public_repos,
        "followers": followers,
        "stars": total_stars,
    }


# Colors cycle for however many blocks we draw (1-6 blocks, scaled from repo count)
BLOCK_COLORS = ["#3fb950", "#58a6ff", "#f0883e", "#a371f7", "#f778ba", "#ffd33d"]


def build_block(index, y, color, appear_start, appear_end, fade_start, x=95, w=70, h=34):
    window_x = x + 10 if index % 2 == 0 else x + 45
    window_y = y + 10
    return f"""
  <g>
    <animateTransform attributeName="transform" type="translate"
      values="0,20;0,20;0,0;0,0;0,0" keyTimes="0;{appear_start:.2f};{appear_end:.2f};{fade_start:.2f};1" dur="8s" repeatCount="indefinite"/>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{color}" opacity="0">
      <animate attributeName="opacity" values="0;0;0.9;0.9;0" keyTimes="0;{appear_start:.2f};{appear_end:.2f};{fade_start:.2f};1" dur="8s" repeatCount="indefinite"/>
    </rect>
    <rect x="{window_x}" y="{window_y}" width="10" height="10" fill="#0d1117" opacity="0">
      <animate attributeName="opacity" values="0;0;0.9;0.9;0" keyTimes="0;{appear_start:.2f};{appear_end:.2f};{fade_start:.2f};1" dur="8s" repeatCount="indefinite"/>
    </rect>
  </g>"""


def generate_svg(stats):
    num_blocks = max(1, min(6, round(stats["repos"] / 5) or 1))
    block_h = 34
    ground_y = 300
    blocks_svg = []
    step = 0.10
    start = 0.10
    last_end = start
    for i in range(num_blocks):
        y = ground_y - block_h - (i * block_h)
        appear_start = start + i * step
        appear_end = appear_start + 0.03
        fade_start = 0.9
        last_end = appear_end
        blocks_svg.append(
            build_block(i, y, BLOCK_COLORS[i % len(BLOCK_COLORS)], appear_start, appear_end, fade_start)
        )

    flag_y_top = ground_y - block_h - (num_blocks * block_h)
    flag_appear = last_end + 0.10
    flag_bounce_mid = flag_appear + 0.02
    flag_bounce_end = flag_appear + 0.06

    caption = f"{stats['repos']} repos · {stats['stars']} stars · {stats['followers']} followers"

    svg = f"""<svg width="260" height="340" viewBox="0 0 260 340" xmlns="http://www.w3.org/2000/svg">
  <!-- auto-generated: live GitHub stats for {USERNAME} -->
  <line x1="20" y1="300" x2="240" y2="300" stroke="#30363d" stroke-width="2"/>

  <circle cx="130" cy="297" r="4" fill="#3fb950">
    <animate attributeName="opacity" values="0;0;1;1;1;0" keyTimes="0;0.02;0.05;0.9;0.92;1" dur="8s" repeatCount="indefinite"/>
  </circle>
{"".join(blocks_svg)}

  <g opacity="0">
    <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;{flag_appear:.2f};{flag_bounce_end:.2f};0.9;1" dur="8s" repeatCount="indefinite"/>
    <line x1="130" y1="{flag_y_top}" x2="130" y2="{flag_y_top - 41}" stroke="#8b949e" stroke-width="2"/>
    <path d="M 130,{flag_y_top - 41} L 148,{flag_y_top - 33} L 130,{flag_y_top - 25} Z" fill="#f85149">
      <animateTransform attributeName="transform" type="scale"
        values="0.6;0.6;1.15;1;1;1" keyTimes="0;{flag_appear:.2f};{flag_bounce_mid:.2f};{flag_bounce_end:.2f};0.9;1"
        dur="8s" repeatCount="indefinite"/>
    </path>
  </g>

  <text x="130" y="322" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="#8b949e" opacity="0">
    {caption}
    <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;{flag_bounce_end:.2f};{min(flag_bounce_end+0.06,0.88):.2f};0.9;1" dur="8s" repeatCount="indefinite"/>
  </text>
</svg>
"""
    return svg


def main():
    try:
        stats = fetch_stats(USERNAME)
    except Exception as e:
        print(f"Failed to fetch GitHub stats: {e}", file=sys.stderr)
        sys.exit(1)

    svg = generate_svg(stats)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(svg)

    print(f"Updated {OUT_PATH} with stats: {stats}")


if __name__ == "__main__":
    main()
