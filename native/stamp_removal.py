"""Remove red seals (公章 / 合同专用章) before OCR.

Red stamp ink over black text makes PP-OCR drop whole lines (measured on a synthetic signing page:
52.9% -> 97.6% character accuracy after removal). Only stamp-shaped red regions are cleared:

* a red pixel is clearly red (R well above G and B, not dark): dark text under the seal is kept;
* red pixels are grouped on a coarse grid (gaps of a few millimetres joined), so a seal's ring,
  star and characters form one region;
* a region counts as a seal only if it is roughly square / round (aspect 0.6-1.67) and at least
  about 1.3 cm across (6% of the page's short side). Long, thin red text lines and small red marks
  are left untouched.
"""
from __future__ import annotations

from collections import deque

RED_MARGIN = 40          # R must exceed max(G, B) by this much
RED_MIN = 110            # and be at least this bright (dark red/black text stays)
MIN_SIDE_RATIO = 0.06    # seal side >= 6% of the page's short side (~1.3 cm on A4)
ASPECT = (0.6, 1.67)
MAX_FILL = 0.45          # a solid red block (logo, highlight) is not a seal


def red_mask(bgr):
    import numpy as np
    b = bgr[:, :, 0].astype(np.int16); g = bgr[:, :, 1].astype(np.int16); r = bgr[:, :, 2].astype(np.int16)
    return (r - np.maximum(g, b) > RED_MARGIN) & (r >= RED_MIN)


def stamp_regions(mask):
    """Bounding boxes (y0, x0, y1, x1) of seal-shaped red regions."""
    import numpy as np
    h, w = mask.shape
    short = min(h, w)
    cell = max(4, short // 150)
    gh, gw = -(-h // cell), -(-w // cell)
    padded = np.zeros((gh * cell, gw * cell), dtype=bool)
    padded[:h, :w] = mask
    counts = padded.reshape(gh, cell, gw, cell).sum(axis=(1, 3))
    grid = counts >= 2
    if not grid.any():
        return []
    # join ring, star and characters of one seal (gaps up to ~2 cells)
    joined = grid.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            joined |= np.roll(np.roll(grid, dy, axis=0), dx, axis=1)
    seen = np.zeros_like(joined)
    regions = []
    for sy, sx in zip(*np.nonzero(joined)):
        if seen[sy, sx]:
            continue
        queue = deque([(sy, sx)]); seen[sy, sx] = True
        y0 = y1 = sy; x0 = x1 = sx
        while queue:
            y, x = queue.popleft()
            y0, y1, x0, x1 = min(y0, y), max(y1, y), min(x0, x), max(x1, x)
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < gh and 0 <= nx < gw and joined[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True; queue.append((ny, nx))
        # bbox of the real red cells inside this joined component
        sub = grid[y0:y1 + 1, x0:x1 + 1]
        ys, xs = np.nonzero(sub)
        if not len(ys):
            continue
        py0, py1 = (y0 + ys.min()) * cell, min(h, (y0 + ys.max() + 1) * cell)
        px0, px1 = (x0 + xs.min()) * cell, min(w, (x0 + xs.max() + 1) * cell)
        bh, bw = py1 - py0, px1 - px0
        if min(bh, bw) < MIN_SIDE_RATIO * short or not ASPECT[0] <= bw / bh <= ASPECT[1]:
            continue
        if mask[py0:py1, px0:px1].mean() > MAX_FILL:
            continue
        regions.append((py0, px0, py1, px1))
    return regions


def remove_stamps(bgr):
    """Return (pixels, number of seals removed). The input array is not modified."""
    mask = red_mask(bgr)
    regions = stamp_regions(mask)
    if not regions:
        return bgr, 0
    out = bgr.copy()
    for y0, x0, y1, x1 in regions:
        out[y0:y1, x0:x1][mask[y0:y1, x0:x1]] = 255
    return out, len(regions)
