"""UI texture atlas: high-frequency add/remove churn test.

A slot-based atlas (1024x1024, 64px cells + 4px gutters) is filled with
procedural sprites, then stressed with 200 churn cycles. Each cycle removes
a random 10% of sprites and inserts new random-size sprites, preferring
recently freed slots. Verified invariants after every stage:

  * survivor_uv_moves: surviving sprites never change UVs (stable seams);
  * gutter_bleed_px:   gutter pixels always keep the sentinel color
                       (no sprite bleeds into its neighbour);
  * max_sprite_pixel_error: re-rendered sprite content matches the atlas
                       bit-exactly (no corruption by later inserts);
  * utilization:       sprite_pixel_fill / reserved_fill tracked per stage.

Writes artifacts/ui_atlas.png and artifacts/atlas_report.json.
"""
import json
import os

import numpy as np
from PIL import Image

ATLAS_SIZE = 1024
CELL = 64
GUTTER = 4
PITCH = CELL + GUTTER
GRID = ATLAS_SIZE // PITCH          # 15 x 15 slots
CHURN_CYCLES = 200
INITIAL_SPRITES = 167
RNG_SEED = 20261120
SENTINEL = np.array([255, 0, 220], dtype=np.uint8)
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "artifacts")


def sprite_pixels(sprite_id, w, h):
    """Deterministic sprite content: id-tinted gradient plus 1px border."""
    rng = np.random.default_rng(sprite_id * 7919 + 13)
    base = rng.integers(40, 220, size=3)
    xx = np.linspace(0, 1, w)[None, :, None]
    yy = np.linspace(0, 1, h)[:, None, None]
    img = np.clip(base * (0.5 + 0.5 * xx) + 60 * yy, 0, 255)
    img = np.broadcast_to(img, (h, w, 3)).copy()
    img[0, :] = 255 - base
    img[-1, :] = 255 - base
    img[:, 0] = 255 - base
    img[:, -1] = 255 - base
    return img.astype(np.uint8)


class Atlas:
    def __init__(self):
        self.img = np.tile(SENTINEL, (ATLAS_SIZE, ATLAS_SIZE, 1))
        self.free = [(r, c) for r in range(GRID) for c in range(GRID)]
        self.reused = []
        self.sprites = {}             # id -> dict(slot, w, h, uv)
        self.free_slot_reuses = 0

    def _slot_origin(self, slot):
        r, c = slot
        return r * PITCH + GUTTER // 2, c * PITCH + GUTTER // 2

    def add(self, sprite_id, w, h):
        assert w <= CELL and h <= CELL
        if self.reused:
            slot = self.reused.pop()
            self.free_slot_reuses += 1
        else:
            slot = self.free.pop(0)
        y0, x0 = self._slot_origin(slot)
        self.img[y0:y0 + h, x0:x0 + w] = sprite_pixels(sprite_id, w, h)
        self.sprites[sprite_id] = {
            "slot": slot, "w": w, "h": h,
            "uv": (x0 / ATLAS_SIZE, y0 / ATLAS_SIZE),
        }

    def remove(self, sprite_id):
        slot = self.sprites.pop(sprite_id)["slot"]
        y0, x0 = self._slot_origin(slot)
        self.img[y0:y0 + CELL, x0:x0 + CELL] = SENTINEL
        self.reused.append(slot)

    def utilization(self):
        sprite_px = sum(s["w"] * s["h"] for s in self.sprites.values())
        return {
            "sprite_pixel_fill": sprite_px / ATLAS_SIZE ** 2,
            "reserved_fill": (len(self.sprites) * CELL * CELL)
                             / ATLAS_SIZE ** 2,
            "sprite_count": len(self.sprites),
            "free_slot_count": len(self.free) + len(self.reused),
        }

    def gutter_bleed_px(self):
        """Count non-sentinel pixels in gutter rows/columns."""
        bleed = 0
        for r in range(GRID):
            for c in range(GRID):
                y0, x0 = self._slot_origin((r, c))
                top = self.img[y0 - GUTTER // 2:y0, x0:x0 + CELL]
                left = self.img[y0:y0 + CELL, x0 - GUTTER // 2:x0]
                bleed += int((top != SENTINEL).any(axis=-1).sum())
                bleed += int((left != SENTINEL).any(axis=-1).sum())
        return bleed

    def max_sprite_pixel_error(self):
        """Re-render every sprite and compare against the atlas content."""
        worst = 0
        for sprite_id, s in self.sprites.items():
            y0, x0 = self._slot_origin(s["slot"])
            actual = self.img[y0:y0 + s["h"], x0:x0 + s["w"]]
            expect = sprite_pixels(sprite_id, s["w"], s["h"])
            if actual.shape == expect.shape:
                worst = max(worst, int(np.abs(actual.astype(int)
                                              - expect.astype(int)).max()))
            else:
                worst = 255
        return worst


def run_churn():
    rng = np.random.default_rng(RNG_SEED)
    atlas = Atlas()
    next_id = [0]
    survivor_uv_moves = 0
    stages = []

    def add_sprite():
        sprite_id = next_id[0]
        next_id[0] += 1
        w = int(rng.integers(12, CELL + 1))
        h = int(rng.integers(12, CELL + 1))
        atlas.add(sprite_id, w, h)

    def snapshot(stage_name):
        stages.append({
            "stage": stage_name,
            "utilization": atlas.utilization(),
            "gutter_bleed_px": atlas.gutter_bleed_px(),
            "max_sprite_pixel_error": atlas.max_sprite_pixel_error(),
        })

    for _ in range(INITIAL_SPRITES):
        add_sprite()
    snapshot("initial_fill")

    for cycle in range(CHURN_CYCLES):
        ids = list(atlas.sprites.keys())
        before_uv = {i: atlas.sprites[i]["uv"] for i in ids}
        cut = max(1, len(ids) // 10)
        for victim in rng.choice(ids, size=cut, replace=False):
            atlas.remove(int(victim))
        for _ in range(cut):
            add_sprite()
        for i, uv in before_uv.items():
            if i in atlas.sprites and atlas.sprites[i]["uv"] != uv:
                survivor_uv_moves += 1
        if cycle % 50 == 0 or cycle == CHURN_CYCLES - 1:
            snapshot("churn_cycle_%d" % cycle)

    report = {
        "atlas_size": ATLAS_SIZE,
        "cell": CELL,
        "gutter": GUTTER,
        "churn_cycles": CHURN_CYCLES,
        "survivor_uv_moves": survivor_uv_moves,
        "free_slot_reuses": atlas.free_slot_reuses,
        "final": atlas.utilization(),
        "stages": stages,
    }
    os.makedirs(ARTIFACTS, exist_ok=True)
    Image.fromarray(atlas.img).save(os.path.join(ARTIFACTS, "ui_atlas.png"))
    with open(os.path.join(ARTIFACTS, "atlas_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "stages"},
                     indent=2))
    print("stage gutter_bleed / pixel_error:",
          [(s["stage"], s["gutter_bleed_px"], s["max_sprite_pixel_error"])
           for s in stages])


if __name__ == "__main__":
    run_churn()
