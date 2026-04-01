"""Convert pickle caches and CSV rankings to compact JSON for web app."""

import pickle
import json
import csv
import gzip
import os
from collections import defaultdict
from pathlib import Path

BASE = Path(r"c:/Users/Thabi/Documents/Recreating/Poker - VSRandomAdv")
RESULTS = BASE / "results"
OUT = BASE / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)

RANK_MAP = {12: 'A', 11: 'K', 10: 'Q', 9: 'J', 8: 'T', 7: '9', 6: '8', 5: '7', 4: '6',
            3: '5', 2: '4', 1: '3', 0: '2'}


def hand_label(hand_key):
    (r1, s1), (r2, s2) = hand_key
    if r1 < r2:
        r1, s1, r2, s2 = r2, s2, r1, s1
    c1 = RANK_MAP[r1]
    c2 = RANK_MAP[r2]
    if r1 == r2:
        return f"{c1}{c2}"
    elif s1 == s2:
        return f"{c1}{c2}s"
    else:
        return f"{c1}{c2}o"


def board_key_str(board_tuple):
    return "|".join(f"{r},{s}" for r, s in board_tuple)


def convert_board_data(pkl_name, out_name, data_type="river"):
    print(f"Loading {pkl_name} ...")
    with open(RESULTS / pkl_name, "rb") as f:
        data = pickle.load(f)
    print(f"  {len(data)} boards loaded.")

    result = {}
    for board_tuple, hands in data.items():
        agg = defaultdict(lambda: [0.0, 0])
        for hk, val in hands.items():
            label = hand_label(hk)
            if data_type == "river":
                agg[label][0] += val
            else:
                agg[label][0] += val[1]  # norm_ae
            agg[label][1] += 1

        ranking = []
        for label, (s, c) in agg.items():
            ranking.append([label, round(s / c, 4), c])

        if data_type == "river":
            ranking.sort(key=lambda x: x[1])  # ascending percentile
        else:
            ranking.sort(key=lambda x: x[1], reverse=True)  # descending AE

        result[board_key_str(board_tuple)] = ranking

    out_path = OUT / out_name
    with open(out_path, "w") as f:
        json.dump(result, f, separators=(",", ":"))
    raw_size = os.path.getsize(out_path)
    with open(out_path, "rb") as f:
        gz_size = len(gzip.compress(f.read()))
    print(f"  Wrote {out_name}: {raw_size/1e6:.1f} MB raw, {gz_size/1e6:.1f} MB gzip")
    return out_path


def convert_preflop(csv_name, out_name):
    csv_path = RESULTS / csv_name
    print(f"Loading {csv_path.name} ...")
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append([
                row["hand"],
                round(float(row["action_equity_norm"]), 4),
                int(row["action_equity_rank"]),
                round(float(row["raw_equity"]), 4),
                int(row["raw_rank"]),
            ])
    rows.sort(key=lambda x: x[2])

    out_path = OUT / out_name
    with open(out_path, "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    print(f"  Wrote {out_name} ({len(rows)} hands)")
    return out_path


if __name__ == "__main__":
    convert_board_data("sd_stage1_rivers.pkl", "sd_rivers.json", "river")
    convert_board_data("sd_stage2_turns.pkl", "sd_turns.json", "turn")
    convert_preflop("rankings_short_deck.csv", "sd_preflop.json")
    convert_preflop("rankings.csv", "std_preflop.json")
    print("\nDone.")
