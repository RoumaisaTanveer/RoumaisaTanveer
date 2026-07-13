#!/usr/bin/env python3
"""
Pulls real GitHub stats for a user and regenerates assets/commit-tower.svg —
a looping, self-drawing tree animation (roots -> trunk -> primary branches ->
secondary twigs -> layered canopy -> leaf scatter -> accent blocks -> caption).
The tree keeps an organic silhouette (curved roots/trunk/branches), but it is
built ENTIRELY out of small rounded GitHub-style square blocks — no strokes
or filled paths anywhere on the tree itself. Green shades (GitHub's own
contribution-graph palette) cover the canopy; a warm brown palette covers
every woody part (trunk, branches, twigs, roots). Size and density scale
with real repo/star/follower counts for the given user.

Run manually:
    GITHUB_TOKEN=xxxx GITHUB_USERNAME=RoumaisaTanveer python scripts/generate_tower.py

In CI (GitHub Actions), GITHUB_TOKEN is provided automatically.
"""

import os
import sys
import math
import random
import urllib.request
import json

USERNAME = os.environ.get("GITHUB_USERNAME", "RoumaisaTanveer")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "commit-tower.svg")

API = "https://api.github.com"

# GitHub Dark Mode contribution-graph greens, darkest -> brightest. No neon/oversaturated tones.
GREEN_SHADES = ["#0e4429", "#006d32", "#26a641", "#39d353"]
# Muted bark palette, darkest -> lightest. No neon/oversaturated tones.
BROWN_SHADES = ["#4a2f1a", "#6b4423", "#8c5a2b", "#a56b34"]
BLOSSOM_COLOR = "#f778ba"
BG_COLOR = "#161b22"


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


def pick_shade(intensity, palette):
    """intensity: 0.0-1.0, biases which shade a cell gets, with wide jitter so
    the full range of tones — dark, mid, bright — shows up clearly, the way
    a real GitHub contribution heatmap mixes all four levels together."""
    base = round(intensity * (len(palette) - 1))
    jitter = random.choice([-2, -1, -1, 0, 0, 0, 1, 1, 2])
    idx = max(0, min(len(palette) - 1, base + jitter))
    return palette[idx]


def pick_leaf_shade(intensity):
    """Leaf-specific shade pick: the four GitHub greens with wide spread."""
    return pick_shade(intensity, GREEN_SHADES)


def pick_wood_shade(intensity):
    """Bark-specific shade pick: the muted brown palette with wide spread."""
    return pick_shade(intensity, BROWN_SHADES)


def _scatter_point(cx, cy, radius, squash=0.75):
    """Random point inside an ellipse (radius x, radius*squash y) centered at cx,cy."""
    r = radius * (random.random() ** 0.5)
    theta = random.uniform(0, 2 * math.pi)
    return cx + r * math.cos(theta), cy + r * math.sin(theta) * squash


def _block(cx, cy, size, angle_deg=0.0):
    """A small rounded GitHub-style square block, centered at (cx, cy) and
    optionally rotated so chains along curves still read as organic."""
    half = size / 2
    x = cx - half
    y = cy - half
    rx = 2
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" rx="{rx:.1f}" '
        f'transform="rotate({angle_deg:.0f} {cx:.1f} {cy:.1f})"'
    )


def _bezier_point(p0, c, p1, t):
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t ** 2 * p1[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t ** 2 * p1[1]
    dx = 2 * (1 - t) * (c[0] - p0[0]) + 2 * t * (p1[0] - c[0])
    dy = 2 * (1 - t) * (c[1] - p0[1]) + 2 * t * (p1[1] - c[1])
    angle = math.degrees(math.atan2(dy, dx))
    return x, y, angle


def emit_chain(parts, fade, p0, c, p1, n, size_start, size_end, palette,
                intensity_bias, start, end, jitter=1.2):
    """Places n blocks along a quadratic bezier curve, tapering in size,
    each fading in in sequence from base (t=0) to tip (t=1) within
    [start, end] — a 'drawn in' effect made of blocks instead of a stroke."""
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0
        x, y, angle = _bezier_point(p0, c, p1, t)
        # small perpendicular jitter for an organic, non-mechanical line
        perp = math.radians(angle + 90)
        off = random.uniform(-jitter, jitter)
        x += math.cos(perp) * off
        y += math.sin(perp) * off
        size = size_start + (size_end - size_start) * t
        shade = pick_wood_shade(intensity_bias + random.uniform(-0.15, 0.15))
        a_start = start + t * (end - start)
        a_end = a_start + 0.012
        blk = _block(x, y, size, angle + random.uniform(-8, 8))
        parts.append(f"""
  {blk} fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_end)}" dur="8s" repeatCount="indefinite"/>
  </rect>""")


def generate_svg(stats):
    random.seed(f"{stats['repos']}-{stats['stars']}-{stats['followers']}")

    SCALE = 1.3
    svg_width = 320 * SCALE
    svg_height = 360 * SCALE
    center_x = svg_width / 2
    ground_y = 292 * SCALE

    intensity = min(1.0, stats["stars"] / max(stats["repos"], 1) / 4)
    num_leaves = max(120, min(340, stats["repos"] * 7))
    num_blossoms = max(4, min(16, stats["followers"] // 3 or 4))

    caption = f"{stats['repos']} repos · {stats['stars']} stars · {stats['followers']} followers"

    parts = []

    def fade(a1, a2, hold_end=0.9):
        return f'0;0;1;1;0" keyTimes="0;{a1:.3f};{a2:.3f};{hold_end:.3f};1'

    # --- seed: a single block where the tree starts ---
    seed_blk = _block(center_x, ground_y + 2 * SCALE, 7 * SCALE)
    parts.append(f"""
  {seed_blk} fill="{BROWN_SHADES[3]}">
    <animate attributeName="opacity" values="0;0;1;1;1;0" keyTimes="0;0.02;0.04;0.9;0.92;1" dur="8s" repeatCount="indefinite"/>
  </rect>""")

    # --- roots: block chains along gently curved paths from the trunk base ---
    root_appear = 0.05
    root_defs = [
        (-14, -30, -6), (14, 30, -4), (-9, -14, 6), (9, 16, 8), (0, 0, -18),
    ]
    for i, (dx, sway, updrift) in enumerate(root_defs):
        dx, sway, updrift = dx * SCALE, sway * SCALE, updrift * SCALE
        p0 = (center_x + dx, ground_y - 4 * SCALE)
        c = (center_x + dx + sway * 0.5, ground_y + 4 * SCALE + updrift * 0.3)
        p1 = (center_x + dx + sway, ground_y + 9 * SCALE)
        r_start = root_appear + i * 0.005
        r_end = root_appear + 0.07 + i * 0.005
        emit_chain(parts, fade, p0, c, p1, n=5, size_start=6.5 * SCALE, size_end=3.5 * SCALE,
                   palette=BROWN_SHADES, intensity_bias=0.25 + i * 0.05,
                   start=r_start, end=r_end, jitter=1.0 * SCALE)

    # --- trunk: stacked rows of blocks filling a tapered outline ---
    trunk_top_y = 182 * SCALE
    trunk_appear_start, trunk_appear_end = 0.07, 0.19
    base_half = 13 * SCALE
    top_half = 6 * SCALE
    row_pitch = 9.5 * SCALE
    n_rows = max(4, int((ground_y - trunk_top_y) / row_pitch))
    for row_i in range(n_rows):
        frac = row_i / max(1, n_rows - 1)  # 0 = bottom (ground), 1 = top
        y = ground_y - frac * (ground_y - trunk_top_y)
        half_w = base_half + (top_half - base_half) * frac
        n_cols = max(2, round((half_w * 2) / row_pitch))
        # bottom row appears first (grows upward)
        row_start = trunk_appear_start + (1 - frac) * (trunk_appear_end - trunk_appear_start) * 0.85
        for col_i in range(n_cols):
            cfrac = (col_i / max(1, n_cols - 1)) - 0.5 if n_cols > 1 else 0
            x = center_x + cfrac * half_w * 2
            x += random.uniform(-1.2, 1.2) * SCALE
            yy = y + random.uniform(-1.2, 1.2) * SCALE
            size = row_pitch * 0.98
            shade = pick_wood_shade(0.35 + abs(cfrac) * 0.4)
            a_start = row_start + random.uniform(0, 0.01)
            a_end = a_start + 0.012
            blk = _block(x, yy, size, random.uniform(-6, 6))
            parts.append(f"""
  {blk} fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_end)}" dur="8s" repeatCount="indefinite"/>
  </rect>""")

    # --- primary branches: block chains drawn from the top of the trunk ---
    branch_defs = [
        # (end_x, end_y, control_x, control_y, begin, end)
        (center_x - 88 * SCALE, 112 * SCALE, center_x - 32 * SCALE, 148 * SCALE, 0.19, 0.29),
        (center_x + 88 * SCALE, 116 * SCALE, center_x + 34 * SCALE, 150 * SCALE, 0.21, 0.31),
        (center_x, 88 * SCALE, center_x + 4 * SCALE, 136 * SCALE, 0.23, 0.32),
        (center_x - 52 * SCALE, 142 * SCALE, center_x - 20 * SCALE, 162 * SCALE, 0.25, 0.33),
        (center_x + 52 * SCALE, 146 * SCALE, center_x + 20 * SCALE, 164 * SCALE, 0.26, 0.34),
    ]
    cluster_centers = []  # (x, y, ready_at)
    branch_ends = []  # (x, y, dir_x, dir_y, ready_at) for spawning secondary twigs
    trunk_top_point = (center_x, trunk_top_y + 6 * SCALE)
    for ex, ey, cx2, cy2, b_start, b_end in branch_defs:
        emit_chain(parts, fade, trunk_top_point, (cx2, cy2), (ex, ey), n=7,
                   size_start=8 * SCALE, size_end=4 * SCALE, palette=BROWN_SHADES,
                   intensity_bias=0.4, start=b_start, end=b_end, jitter=1.4 * SCALE)
        cluster_centers.append((ex, ey, b_end))
        dirx, diry = ex - cx2, ey - cy2
        norm = math.hypot(dirx, diry) or 1
        branch_ends.append((ex, ey, dirx / norm, diry / norm, b_end))

    # a center canopy cluster too, sitting just above the trunk
    cluster_centers.append((center_x, 154 * SCALE, 0.34))

    # --- secondary twigs: 2 short block chains sprouting from each branch tip ---
    twig_dur = 0.05
    for bx, by, dirx, diry, ready_at in branch_ends:
        perp_x, perp_y = -diry, dirx
        for side in (-1, 1):
            spread = random.uniform(16, 26) * SCALE
            length = random.uniform(20, 30) * SCALE
            tex = bx + dirx * length * 0.5 + perp_x * side * spread * 0.5
            tey = by + diry * length * 0.5 + perp_y * side * spread * 0.5
            twig_end_x = bx + dirx * length + perp_x * side * spread
            twig_end_y = by + diry * length + perp_y * side * spread
            t_start = ready_at + 0.005
            t_end = t_start + twig_dur
            emit_chain(parts, fade, (bx, by), (tex, tey), (twig_end_x, twig_end_y),
                       n=4, size_start=5 * SCALE, size_end=3 * SCALE, palette=BROWN_SHADES,
                       intensity_bias=0.6, start=t_start, end=t_end, jitter=1.0 * SCALE)
            cluster_centers.append((twig_end_x, twig_end_y, t_end))

    # --- fine twig blocks fanning inside each cluster, for texture under the leaves ---
    for cx3, cy3, ready_at in cluster_centers:
        fan_start = ready_at + 0.02
        for _ in range(3):
            ang = random.uniform(0, 2 * math.pi)
            length = random.uniform(8, 18) * SCALE
            for j, tfrac in enumerate((0.5, 1.0)):
                fx = cx3 + math.cos(ang) * length * tfrac
                fy = cy3 + math.sin(ang) * length * 0.7 * tfrac
                shade = pick_wood_shade(0.5)
                size = (4 - j * 1) * SCALE
                a_start = fan_start + tfrac * 0.02
                blk = _block(fx, fy, size, math.degrees(ang))
                parts.append(f"""
  {blk} fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_start + 0.015)}" dur="8s" repeatCount="indefinite"/>
  </rect>""")

    # --- leaf scatter: prominent rounded square blocks, shaded like GitHub cells ---
    leaf_fill_start, leaf_fill_end = 0.36, 0.72
    leaves_per_cluster = max(4, num_leaves // len(cluster_centers))
    leaf_i = 0
    total_planned_leaves = leaves_per_cluster * len(cluster_centers)
    for cx3, cy3, ready_at in cluster_centers:
        radius = (26 if ready_at < 0.34 else 15) * SCALE
        for _ in range(leaves_per_cluster):
            lx, ly = _scatter_point(cx3, cy3, radius=radius)
            # wide jitter so all four GitHub greens show up clearly, not a muddy average
            shade = pick_leaf_shade(intensity + random.uniform(-0.3, 0.3))
            frac = leaf_i / max(1, total_planned_leaves - 1)
            a_start = max(ready_at, leaf_fill_start + frac * (leaf_fill_end - leaf_fill_start))
            a_end = a_start + 0.015
            size = random.uniform(5.5, 8.5) * SCALE
            angle = random.uniform(-20, 20)
            blk = _block(lx, ly, size, angle)
            parts.append(f"""
  {blk} fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_end)}" dur="8s" repeatCount="indefinite"/>
  </rect>""")
            leaf_i += 1

    # --- accent blocks: a handful of pink blocks, popping in after the leaves settle ---
    blossom_start, blossom_end = 0.74, 0.84
    for i in range(num_blossoms):
        cx3, cy3, _ = random.choice(cluster_centers)
        bx, by = _scatter_point(cx3, cy3, radius=26 * SCALE)
        frac = i / max(1, num_blossoms - 1)
        a_start = blossom_start + frac * (blossom_end - blossom_start)
        a_mid = a_start + 0.015
        a_end = a_start + 0.04
        size = random.uniform(6.5, 8.5) * SCALE
        angle = random.uniform(-20, 20)
        blk = _block(bx, by, size, angle)
        parts.append(f"""
  {blk} fill="{BLOSSOM_COLOR}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_end)}" dur="8s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="scale"
      values="0.4;0.4;1.3;1;1;1" keyTimes="0;{a_start:.3f};{a_mid:.3f};{a_end:.3f};0.9;1"
      dur="8s" repeatCount="indefinite" additive="sum"/>
  </rect>""")

    caption_appear = blossom_end + 0.03

    svg = f"""<svg width="{svg_width:.0f}" height="{svg_height:.0f}" viewBox="0 0 {svg_width:.0f} {svg_height:.0f}" xmlns="http://www.w3.org/2000/svg">
  <!-- auto-generated: live GitHub stats for {USERNAME} -->
  <rect x="0" y="0" width="{svg_width:.0f}" height="{svg_height:.0f}" fill="{BG_COLOR}"/>
  <line x1="{20 * SCALE:.1f}" y1="{ground_y:.1f}" x2="{svg_width - 20 * SCALE:.1f}" y2="{ground_y:.1f}" stroke="#30363d" stroke-width="2"/>
{"".join(parts)}

  <text x="{center_x:.1f}" y="{svg_height - 15:.1f}" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="#8b949e" opacity="0">
    {caption}
    <animate attributeName="opacity" values="{fade(caption_appear, caption_appear + 0.05)}" dur="8s" repeatCount="indefinite"/>
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
