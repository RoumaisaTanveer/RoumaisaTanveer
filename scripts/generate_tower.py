#!/usr/bin/env python3
"""
Pulls real GitHub stats for a user and regenerates assets/commit-tower.svg —
a tower/tree built out of small commit-style squares (GitHub contribution-graph
green shades), stacked layer by layer, sized by real repo/star/follower counts.

Run manually:
    GITHUB_TOKEN=xxxx GITHUB_USERNAME=RoumaisaTanveer python scripts/generate_tower.py

In CI (GitHub Actions), GITHUB_TOKEN is provided automatically.
"""

import os
import sys
import random
import urllib.request
import json

USERNAME = os.environ.get("GITHUB_USERNAME", "RoumaisaTanveer")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "commit-tower.svg")

API = "https://api.github.com"

# GitHub's own contribution-graph green shades (dark theme), darkest -> brightest
GREEN_SHADES = ["#0e4429", "#006d32", "#26a641", "#39d353"]
BROWN_SHADES = ["#3b2412", "#5a3a1e", "#7a4f26", "#96652f"]


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

    return {"repos": public_repos, "followers": followers, "stars": total_stars}


def pick_shade(intensity, palette=GREEN_SHADES):
    """intensity: 0.0-1.0, biases which shade a cell gets, with jitter for texture."""
    base = round(intensity * (len(palette) - 1))
    jitter = random.choice([-1, 0, 0, 1])
    idx = max(0, min(len(palette) - 1, base + jitter))
    return palette[idx]


def generate_svg(stats):
    # deterministic look for same stats
    random.seed(f"{stats['repos']}-{stats['stars']}-{stats['followers']}")

    # basic cell geometry
    cell = 18
    gap = 4
    pitch = cell + gap

    # trunk: fixed narrow brown base
    TRUNK_COLUMNS = 2
    TRUNK_ROWS = 4

    # canopy tiers (tree / tower silhouette: wide -> narrow)
    CANOPY_TIERS = [7, 5, 3, 1]

    # ---- map stats to geometry ----
    # total canopy rows depends on repos (min 8, max 24)
    canopy_rows_total = max(8, min(24, round(stats["repos"] / 2) or 8))

    # intensity of green depends on stars per repo
    intensity = min(1.0, stats["stars"] / max(stats["repos"], 1) / 4)

    num_tiers = len(CANOPY_TIERS)
    base_rows_per_tier = canopy_rows_total // num_tiers
    remainder = canopy_rows_total - base_rows_per_tier * num_tiers
    rows_per_tier = [base_rows_per_tier + (1 if i < remainder else 0) for i in range(num_tiers)]
    rows_per_tier = [max(1, r) for r in rows_per_tier]
    canopy_rows_total = sum(rows_per_tier)

    total_rows = TRUNK_ROWS + canopy_rows_total
    widest_width = CANOPY_TIERS[0] * pitch - gap
    total_height = total_rows * pitch - gap

    # layout margins
    top_margin = 55        # room for fruit/tip above canopy
    bottom_margin = 45     # room for caption below ground

    ground_y = top_margin + total_height
    svg_height = ground_y + bottom_margin
    svg_width = max(260, widest_width + 40)
    center_x = svg_width / 2

    # build animation timing
    build_start, build_end = 0.05, 0.72
    row_step = (build_end - build_start) / total_rows

    cells_svg = []
    row_counter = 0  # bottom (0) upward

    # ---- trunk rows (brown, narrow) ----
    trunk_width = TRUNK_COLUMNS * pitch - gap
    trunk_x = center_x - trunk_width / 2
    for _ in range(TRUNK_ROWS):
        row_y = ground_y - (row_counter + 1) * pitch + gap
        appear_start = build_start + row_counter * row_step
        appear_end = appear_start + row_step * 0.5
        for c in range(TRUNK_COLUMNS):
            cell_x = trunk_x + c * pitch
            shade = pick_shade(random.uniform(0.2, 0.8), palette=BROWN_SHADES)
            cells_svg.append(f"""
  <rect x="{cell_x:.1f}" y="{row_y:.1f}" width="{cell}" height="{cell}" rx="3" fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="0;0;1;1;0"
             keyTimes="0;{appear_start:.3f};{appear_end:.3f};0.9;1"
             dur="8s" repeatCount="indefinite"/>
  </rect>""")
        row_counter += 1

    # ---- canopy tiers (green, tapering) ----
    for tier_idx, tier_cols in enumerate(CANOPY_TIERS):
        tier_width = tier_cols * pitch - gap
        tier_x = center_x - tier_width / 2
        for _ in range(rows_per_tier[tier_idx]):
            row_y = ground_y - (row_counter + 1) * pitch + gap
            appear_start = build_start + row_counter * row_step
            appear_end = appear_start + row_step * 0.5
            for c in range(tier_cols):
                cell_x = tier_x + c * pitch
                shade = pick_shade(intensity + random.uniform(-0.15, 0.15), palette=GREEN_SHADES)
                cells_svg.append(f"""
  <rect x="{cell_x:.1f}" y="{row_y:.1f}" width="{cell}" height="{cell}" rx="3" fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="0;0;1;1;0"
             keyTimes="0;{appear_start:.3f};{appear_end:.3f};0.9;1"
             dur="8s" repeatCount="indefinite"/>
  </rect>""")
            row_counter += 1

    # ---- fruit / tip animation ----
    fruit_appear = build_end + 0.03
    fruit_bounce_mid = fruit_appear + 0.02
    fruit_bounce_end = fruit_appear + 0.06
    caption_appear = fruit_bounce_end + 0.02
    fruit_y = top_margin - 12

    # caption: user + stats
    caption_line1 = f"{USERNAME}"
    caption_line2 = f"{stats['repos']} repos · {stats['stars']} stars · {stats['followers']} followers"

    svg = f"""<svg width="{svg_width:.0f}" height="{svg_height:.0f}"
     viewBox="0 0 {svg_width:.0f} {svg_height:.0f}" xmlns="http://www.w3.org/2000/svg">
  <!-- auto-generated: live GitHub stats for {USERNAME} -->

  <!-- ground line -->
  <line x1="20" y1="{ground_y:.1f}" x2="{svg_width - 20:.1f}" y2="{ground_y:.1f}"
        stroke="#30363d" stroke-width="2"/>

  <!-- ground node -->
  <circle cx="{center_x:.1f}" cy="{ground_y + 3:.1f}" r="4" fill="#96652f">
    <animate attributeName="opacity" values="0;0;1;1;1;0"
             keyTimes="0;0.02;0.04;0.9;0.92;1"
             dur="8s" repeatCount="indefinite"/>
  </circle>
{"".join(cells_svg)}

  <!-- fruit / top marker -->
  <circle cx="{center_x:.1f}" cy="{fruit_y:.1f}" r="7" fill="#f85149" opacity="0">
    <animate attributeName="opacity" values="0;0;1;1;0"
             keyTimes="0;{fruit_appear:.3f};{fruit_bounce_end:.3f};0.9;1"
             dur="8s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="scale"
      values="0.6;0.6;1.2;1;1;1"
      keyTimes="0;{fruit_appear:.3f};{fruit_bounce_mid:.3f};{fruit_bounce_end:.3f};0.9;1"
      dur="8s" repeatCount="indefinite"/>
  </circle>

  <!-- caption: line 1 (username) -->
  <text x="{center_x:.1f}" y="{svg_height - 28:.0f}" text-anchor="middle"
        font-family="Consolas, monospace" font-size="11" fill="#8b949e" opacity="0">
    {caption_line1}
    <animate attributeName="opacity" values="0;0;1;1;0"
             keyTimes="0;{caption_appear:.3f};{min(caption_appear + 0.06, 0.88):.3f};0.9;1"
             dur="8s" repeatCount="indefinite"/>
  </text>

  <!-- caption: line 2 (stats) -->
  <text x="{center_x:.1f}" y="{svg_height - 14:.0f}" text-anchor="middle"
        font-family="Consolas, monospace" font-size="11" fill="#8b949e" opacity="0">
    {caption_line2}
    <animate attributeName="opacity" values="0;0;1;1;0"
             keyTimes="0;{caption_appear:.3f};{min(caption_appear + 0.08, 0.88):.3f};0.9;1"
             dur="8s" repeatCount="indefinite"/>
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
