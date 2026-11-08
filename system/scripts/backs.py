"""Pairs back sides with their fronts (loose photos with writing on the back).

Workflow: photograph the front, then IMMEDIATELY the back. Time alone is not enough (people
photograph everything a few seconds apart), so a back side is recognized by its content:
  - almost the whole snapshot is plain paper (≥ 80 % of the area close to the paper tone,
    low brightness spread) — writing or a stamp, no picture
  - it is the only photo on its snapshot (a crop from an album page can never be a back side,
    so newspaper clippings on pages are not mistaken for backs)
and it is paired with the photo on the snapshot taken right before it (setting "back_max_gap",
default 60 s; 0 = ignore time and rely on order only — e.g. for scanners). The order comes from
the "time_source" setting (camera time, file date or file name).
Calibrated on real prints: back side 95 % paper; closest real photo 57 %. Cases in between
are reported as uncertain.

  system/.venv/bin/python system/scripts/backs.py <album>
  → system/work/<album>/backs_proposal.json. Only pairs confirmed in backs.json
    ({"IMG_0012_1": "IMG_0011_1"}) are used in the album — Claude writes it after checking.
"""
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BACK_PAPER, BACK_SPREAD = 0.80, 20        # certainly a back side
UNSURE_PAPER, UNSURE_SPREAD = 0.65, 35    # report for checking


def measure(path):
    """Share of the area close to the paper tone, and brightness spread (blurred gray, 400 px)."""
    g = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (400, max(1, int(400 * g.shape[0] / g.shape[1]))), interpolation=cv2.INTER_AREA)
    b = cv2.GaussianBlur(g, (0, 0), 3).astype(int)
    return float(np.mean(np.abs(b - np.median(b)) < 20)), float(b.std())


def kind(paper, spread):
    if paper >= BACK_PAPER and spread <= BACK_SPREAD:
        return "back"
    if paper >= UNSURE_PAPER and spread <= UNSURE_SPREAD:
        return "unsure"
    return "photo"


def propose(name):
    d = common.album_dir(name)
    by_snapshot = {}
    for p in sorted(glob.glob(os.path.join(d, "crops", "*.jpg"))):
        j = os.path.splitext(os.path.basename(p))[0]
        by_snapshot.setdefault(j.rsplit("_", 1)[0], []).append(j)
    order = common.shooting_order(by_snapshot)
    max_gap = int(common.load_config()["back_max_gap"])
    found, pairs, unsure = {}, {}, []
    for i, s in enumerate(order):
        for j in by_snapshot[s]:
            paper, spread = measure(os.path.join(d, "crops", f"{j}.jpg"))
            k = kind(paper, spread) if len(by_snapshot[s]) == 1 else "photo"
            found[j] = dict(kind=k, paper=round(paper, 2), spread=round(spread, 1))
            if k == "photo":
                continue
            front, reason = None, None
            if i == 0:
                reason = "first snapshot, nothing before it"
            else:
                prev = order[i - 1]
                t1, t0 = common.capture_time(s), common.capture_time(prev)
                gap = (t1 - t0).total_seconds() if t1 and t0 else None
                candidates = [c for c in by_snapshot[prev] if found.get(c, {}).get("kind") != "back"]
                if max_gap and gap is not None and gap > max_gap:
                    reason = f"previous snapshot taken {gap:.0f} s earlier"
                elif len(candidates) != 1:
                    reason = f"previous snapshot has {len(candidates)} photos"
                front = candidates[0] if candidates else None
            if k == "back" and not reason:
                pairs[j] = front
            else:
                unsure.append(dict(id=j, proposed_front=front, reason=reason or "unsure content (could be a pale photo)", **found[j]))
    result = dict(backs=pairs, unsure=unsure, note="For checking. Only pairs written to backs.json are used.")
    with open(os.path.join(d, "backs_proposal.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


if __name__ == "__main__":
    r = propose(sys.argv[1])
    print(f"Back sides found: {len(r['backs'])}")
    for b, f in r["backs"].items():
        print(f"  {b} → front {f}")
    print(f"To check: {len(r['unsure'])}")
    for u in r["unsure"]:
        print(f"  {u['id']} (paper {u['paper']}, spread {u['spread']}) → {u['proposed_front']}: {u['reason']}")
