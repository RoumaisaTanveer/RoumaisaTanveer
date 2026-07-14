#!/usr/bin/env python3
"""
Pulls real GitHub stats for a user and regenerates assets/commit-tower.svg —
a looping, self-drawing tree animation (roots -> trunk -> branches ->
canopy -> blossoms -> caption).

Visual style: a clean, grid-aligned GitHub-contribution-graph aesthetic.
The tree is built entirely out of fixed-size, axis-aligned, rounded
squares snapped to a consistent grid (no rotation, no scatter/jitter in
position) — the same visual language as GitHub's own contribution heatmap
and profile-stats widgets. Green shades (GitHub's contribution palette)
cover the canopy; a muted brown palette covers the woody parts (trunk,
branches, roots). Size and density scale with real repo/star/follower
counts for the given user.

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

# GitHub Dark Mode contribution-graph greens, darkest -> brightest.
GREEN_SHADES = ["#0e4429", "#006d32", "#26a641", "#39d353"]
# Muted bark palette, darkest -> lightest. No neon/oversaturated tones.
BROWN_SHADES = ["#4a2f1a", "#6b4423", "#8c5a2b", "#a56b34"]
BLOSSOM_COLOR = "#f778ba"
BG_COLOR = "#161b22"

# --- grid constants: everything snaps to this pitch, GitHub-cell style ---
BLOCK_SIZE = 10
BLOCK_GAP = 2
PITCH = BLOCK_SIZE + BLOCK_GAP
CORNER_R = 2


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


def pick_shade(intensity, palette, jitter_span=1):
    """intensity: 0.0-1.0, biases which shade a cell gets, with a small
    jitter so a healthy mix of dark/mid/bright cells shows up, the way a
    real GitHub contribution heatmap mixes all four levels together."""
    base = round(intensity * (len(palette) - 1))
    jitter = random.randint(-jitter_span, jitter_span)
    idx = max(0, min(len(palette) - 1, base + jitter))
    return palette[idx]


def _block(cx, cy, size=BLOCK_SIZE):
    """A small rounded, axis-aligned GitHub-style square block, centered
    at (cx, cy). No rotation — every square stays perfectly horizontal."""
    half = size / 2
    x = cx - half
    y = cy - half
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" rx="{CORNER_R}"'


def fade(a1, a2, hold_end=0.9):
    return f'0;0;1;1;0" keyTimes="0;{a1:.3f};{a2:.3f};{hold_end:.3f};1'


def emit_block(parts, cx, cy, shade, a_start, a_end, size=BLOCK_SIZE):
    blk = _block(cx, cy, size)
    parts.append(f"""
  {blk} fill="{shade}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_end)}" dur="8s" repeatCount="indefinite"/>
  </rect>""")


def generate_svg(stats):
    random.seed(f"{stats['repos']}-{stats['stars']}-{stats['followers']}")

    svg_width = 380
    svg_height = 420
    center_x = svg_width / 2
    ground_y = 350

    intensity = min(1.0, stats["stars"] / max(stats["repos"], 1) / 4)
    # density scales canopy row/col reach with real stats (denser tree = more activity)
    density = 0.7 + 0.3 * min(1.0, stats["repos"] / 40)
    num_blossoms = max(3, min(14, stats["followers"] // 4 or 3))

    caption = f"{stats['repos']} repos · {stats['stars']} stars · {stats['followers']} followers"

    parts = []

    # --- seed: a single block where the tree starts ---
    emit_block(parts, center_x, ground_y, BROWN_SHADES[3], 0.02, 0.04)

    # --- roots: a short grid-aligned row spreading from the trunk base ---
    root_start, root_end = 0.05, 0.10
    root_cols = [-2, -1, 1, 2]
    for i, c in enumerate(root_cols):
        rx_pos = center_x + c * PITCH
        ry_pos = ground_y - PITCH * 0.35 if c in (-1, 1) else ground_y - PITCH * 0.1
        shade = pick_shade(0.3 + abs(c) * 0.15, BROWN_SHADES)
        a_start = root_start + (abs(c) / max(root_cols)) * (root_end - root_start) * 0.3
        emit_block(parts, rx_pos, ry_pos, shade, a_start, a_start + 0.012, size=BLOCK_SIZE * 0.8)

    # --- trunk: stepped, grid-aligned column stack, tapering upward, with a
    # slight natural lean (integer column sway, still perfectly grid-locked) ---
    trunk_rows = 9
    trunk_top_y = ground_y - trunk_rows * PITCH
    trunk_start, trunk_end = 0.10, 0.24
    sway = 0
    sway_by_row = {}
    for row_i in range(trunk_rows):
        if row_i > 1 and random.random() < 0.4:
            sway += random.choice([-1, 1])
            sway = max(-2, min(2, sway))
        sway_by_row[row_i] = sway
    for row_i in range(trunk_rows):
        frac = row_i / (trunk_rows - 1)  # 0 = bottom (ground), 1 = top
        y = ground_y - frac * (ground_y - trunk_top_y)
        cols = 3 if frac < 0.3 else (2 if frac < 0.7 else 1)
        row_time = trunk_start + (1 - frac) * (trunk_end - trunk_start)
        row_sway = sway_by_row[row_i]
        for c in range(-(cols // 2), cols // 2 + 1) if cols % 2 == 1 else range(cols):
            base_c = c if cols % 2 == 1 else (c - (cols - 1) / 2)
            x = center_x + (base_c + row_sway) * PITCH
            shade = pick_shade(0.3 + frac * 0.3, BROWN_SHADES)
            emit_block(parts, x, y, shade, row_time, row_time + 0.012)
    trunk_top_sway = sway_by_row[trunk_rows - 1]
    apex_x_col = trunk_top_sway  # column (in grid units) the canopy sits above

    # --- canopy: several overlapping rounded lobes (a real tree crown is a
    # cluster of foliage clumps, not one perfect blob) on a fixed grid ---
    lobes = [
        # (dx_cols, dy_rows, rx_cols, ry_rows) — offsets from the trunk apex
        (0, -4.5, 4.4, 3.1),     # top lobe
        (-4.4, -1.2, 4.3, 3.2),  # left lobe
        (4.4, -1.2, 4.3, 3.2),   # right lobe
        (-2.3, 2.0, 3.7, 2.7),   # lower-left lobe
        (2.3, 2.0, 3.7, 2.7),    # lower-right lobe
        (0, -1.0, 4.2, 3.2),     # core lobe, fills the gaps between the others
    ]
    lobes = [(dx * density, dy * density, rx * density, ry * density) for dx, dy, rx, ry in lobes]

    min_col = min(dx - rx for dx, dy, rx, ry in lobes)
    max_col = max(dx + rx for dx, dy, rx, ry in lobes)
    min_row = min(dy - ry for dx, dy, rx, ry in lobes)
    max_row = max(dy + ry for dx, dy, rx, ry in lobes)

    def in_canopy(col, row):
        best = None
        for dx, dy, rx, ry in lobes:
            d2 = ((col - dx) / rx) ** 2 + ((row - dy) / ry) ** 2
            if d2 <= 1.0 and (best is None or d2 < best):
                best = d2
        return best  # None if outside every lobe, else smallest normalized dist^2

    branch_start, branch_end = 0.24, 0.32
    canopy_start, canopy_end = 0.32, 0.66

    canopy_cells = []  # (col, row, x, y, dist2)
    for row in range(math.floor(min_row), math.ceil(max_row) + 1):
        for col in range(math.floor(min_col), math.ceil(max_col) + 1):
            d2 = in_canopy(col, row)
            if d2 is not None:
                x = center_x + col * PITCH
                y = trunk_top_y + row * PITCH
                canopy_cells.append((col, row, x, y, d2))

    row_span = max(1, math.ceil(max_row) - math.floor(min_row))
    blossom_candidates = []
    for col, row, x, y, d2 in canopy_cells:
        cell_intensity = max(0.0, min(1.0, intensity + 0.4 * (1 - d2) - 0.1))
        shade = pick_shade(cell_intensity, GREEN_SHADES)
        row_frac = 1 - ((row - math.floor(min_row)) / row_span)  # bottom rows fill first
        col_frac = (col - math.floor(min_col)) / max(1, math.ceil(max_col) - math.floor(min_col))
        a_start = canopy_start + row_frac * (canopy_end - canopy_start) * 0.9
        a_start += col_frac * (canopy_end - canopy_start) * 0.06
        emit_block(parts, x, y, shade, a_start, a_start + 0.012)
        blossom_candidates.append((x, y))

    # --- branches: a handful of grid-stepped diagonal chains (Bresenham
    # staircases, so every block stays axis-aligned) reaching from the trunk
    # apex up into each foliage lobe, with a couple of tips poking a little
    # past the leaves the way real bare branch tips do ---
    def grid_line(c0, r0, c1, r1):
        pts = []
        dc, dr = abs(c1 - c0), -abs(r1 - r0)
        sc = 1 if c0 < c1 else -1
        sr = 1 if r0 < r1 else -1
        err = dc + dr
        c, r = c0, r0
        while True:
            pts.append((c, r))
            if c == c1 and r == r1:
                break
            e2 = 2 * err
            if e2 >= dr:
                err += dr
                c += sc
            if e2 <= dc:
                err += dc
                r += sr
        return pts

    branch_targets = lobes[:-1]  # every lobe except the central filler
    for bi, (dx, dy, rx, ry) in enumerate(branch_targets):
        target_col, target_row = round(dx), round(dy)
        path = grid_line(apex_x_col, 0, target_col, target_row)
        n = len(path)
        for i, (c, r) in enumerate(path):
            # skip cells already deep inside the lobe union - the branch only
            # needs to be visible up to where the foliage takes over
            if in_canopy(c, r) is not None and i > n * 0.4:
                continue
            x = center_x + c * PITCH
            y = trunk_top_y + r * PITCH
            shade = pick_shade(0.3 + (i / max(1, n - 1)) * 0.3, BROWN_SHADES)
            t_frac = i / max(1, n - 1)
            a_start = branch_start + t_frac * (branch_end - branch_start)
            emit_block(parts, x, y, shade, a_start, a_start + 0.012, size=BLOCK_SIZE * 0.85)
        # a short exposed twig tip poking just past the lobe edge
        ext_c = target_col + (round((target_col - apex_x_col) * 0.18) or (1 if target_col >= apex_x_col else -1))
        ext_r = target_row - 1
        if in_canopy(ext_c, ext_r) is None:
            x = center_x + ext_c * PITCH
            y = trunk_top_y + ext_r * PITCH
            shade = pick_shade(0.55, BROWN_SHADES)
            emit_block(parts, x, y, shade, branch_end - 0.01, branch_end, size=BLOCK_SIZE * 0.7)

    # --- blossoms: a handful of pink accent blocks popping in after the canopy fills ---
    blossom_start, blossom_end = 0.68, 0.80
    if blossom_candidates:
        chosen = random.sample(blossom_candidates, k=min(num_blossoms, len(blossom_candidates)))
        for i, (bx, by) in enumerate(chosen):
            frac = i / max(1, len(chosen) - 1)
            a_start = blossom_start + frac * (blossom_end - blossom_start)
            a_mid = a_start + 0.015
            a_end = a_start + 0.04
            blk = _block(bx, by)
            parts.append(f"""
  {blk} fill="{BLOSSOM_COLOR}" opacity="0">
    <animate attributeName="opacity" values="{fade(a_start, a_end)}" dur="8s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="scale"
      values="0.4;0.4;1.3;1;1;1" keyTimes="0;{a_start:.3f};{a_mid:.3f};{a_end:.3f};0.9;1"
      dur="8s" repeatCount="indefinite" additive="sum"/>
  </rect>""")

    caption_appear = blossom_end + 0.03

    svg = f"""<svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">
  <!-- auto-generated: live GitHub stats for {USERNAME} -->
  <rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="{BG_COLOR}"/>
  <line x1="20" y1="{ground_y:.1f}" x2="{svg_width - 20}" y2="{ground_y:.1f}" stroke="#30363d" stroke-width="2"/>
{"".join(parts)}

  <text x="{center_x:.1f}" y="{svg_height - 15}" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="#8b949e" opacity="0">
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
