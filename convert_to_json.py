"""Convert pickle caches and CSV rankings to compact JSON for web app.

Uses suit frequency group canonicalization: suits with the same board
frequency are interchangeable. This collapses equivalent hand combos
(e.g., JsTs = JhTh on a board with no spades or hearts) while keeping
strategically different combos separate (e.g., JcTc flush draw).

Output is chunked by the two lowest ranks on the board for manageable
file sizes.
"""

import pickle
import json
import csv
import gzip
import os
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(r"c:/Users/Thabi/Documents/Recreating/Poker - VSRandomAdv")
RESULTS = BASE / "results"
OUT = BASE / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)

RANK_INT_TO_CHAR = {12:'A',11:'K',10:'Q',9:'J',8:'T',7:'9',6:'8',5:'7',4:'6',
                    3:'5',2:'4',1:'3',0:'2'}


# ── Suit frequency group canonicalization ────────────────────────────────

def suit_group_map(board_rs):
    """Build suit -> group_id mapping based on suit frequency on board.

    Suits with the same frequency get the same group_id.
    Groups are numbered by descending frequency.
    """
    suit_freq = Counter()
    for r, s in board_rs:
        suit_freq[s] += 1
    freq_to_suits = defaultdict(list)
    for s in range(4):  # canonical suits 0-3
        freq_to_suits[suit_freq.get(s, 0)].append(s)
    group_map = {}
    gid = 0
    for freq in sorted(freq_to_suits.keys(), reverse=True):
        for s in sorted(freq_to_suits[freq]):
            group_map[s] = gid
        gid += 1
    return group_map


def recanon_hand_key(hk, gmap):
    """Re-canonicalize a hand_key using suit frequency groups.

    Returns a canonical key that encodes:
    - Each card's rank
    - Which suit group each card belongs to
    - Whether the two cards share a suit (within the same group)

    Two hands with the same key are strategically equivalent on this board.
    """
    (r1, s1), (r2, s2) = hk
    g1, g2 = gmap[s1], gmap[s2]
    if g1 == g2:
        # Same group: distinguish same-suit vs different-suit
        local = 0 if s1 == s2 else 1
        return tuple(sorted([(r1, g1, 0), (r2, g2, local)]))
    else:
        # Different groups: fully identified by group
        return tuple(sorted([(r1, g1, 0), (r2, g2, 0)]))


# ── Human-readable hand key labels ──────────────────────────────────────

def hand_key_label(grouped_key, n_groups):
    """Convert a grouped canonical key to a human-readable label.

    Returns (rank_label, suit_desc) e.g. ('JT', 'suited-clubs') or ('JT', 'offsuit').
    For the JSON we encode as a compact string.
    """
    (r1, g1, l1), (r2, g2, l2) = grouped_key
    # Sort by rank descending
    if r1 < r2:
        r1, g1, l1, r2, g2, l2 = r2, g2, l2, r1, g1, l1

    c1 = RANK_INT_TO_CHAR[r1]
    c2 = RANK_INT_TO_CHAR[r2]

    if r1 == r2:
        # Pair
        if g1 == g2 and l1 == l2:
            # Same suit — impossible for a pair (can't have two of same rank+suit)
            # Actually l1==l2==0 means same suit within group, but pairs can't be same suit
            # This means both in the same group, same local = both in same group-suit slot
            # For pairs this means: both cards in the same specific suit group slot
            # Wait — pairs always have different suits. Let me think...
            # For a pair, s1 != s2 always. So if g1==g2, l1=0,l2=1 (different suits in same group)
            # If g1!=g2, l1=0,l2=0 (different groups)
            pass
        # Pairs: encode which groups
        return f"{c1}{c2}:{g1}{g2}"
    else:
        if g1 == g2:
            if l1 == l2:
                # Same suit within group
                return f"{c1}{c2}s:{g1}"
            else:
                # Different suits in same group (offsuit within group)
                return f"{c1}{c2}x:{g1}"
        else:
            # Different groups (offsuit across groups)
            return f"{c1}{c2}o:{g1}{g2}"


# ── Board key and chunk key ──────────────────────────────────────────────

def board_key_str(board_tuple):
    return "|".join(f"{r},{s}" for r, s in board_tuple)


def chunk_key(board_tuple):
    """Get chunk identifier from two lowest ranks on board."""
    ranks_sorted = sorted(set(r for r, s in board_tuple))
    lo1 = RANK_INT_TO_CHAR[ranks_sorted[0]].lower()
    lo2 = RANK_INT_TO_CHAR[ranks_sorted[1]].lower() if len(ranks_sorted) > 1 else lo1
    return f"{lo1}{lo2}"


# ── Convert board data with per-combo grouped keys ──────────────────────

def convert_board_data_chunked(pkl_name, prefix, data_type="river"):
    print(f"\nLoading {pkl_name} ...")
    with open(RESULTS / pkl_name, "rb") as f:
        data = pickle.load(f)
    print(f"  {len(data)} boards loaded.")

    # Group boards into chunks
    chunks = defaultdict(dict)
    total_keys = 0
    total_grouped = 0

    for board_tuple, hands in data.items():
        board_rs = list(board_tuple)
        gmap = suit_group_map(board_rs)
        n_groups = max(gmap.values()) + 1

        # Re-canonicalize hand keys and aggregate values for identical grouped keys
        grouped = defaultdict(lambda: [0.0, 0])
        for hk, val in hands.items():
            gk = recanon_hand_key(hk, gmap)
            label = hand_key_label(gk, n_groups)
            if data_type == "river":
                grouped[label][0] += val
            else:
                grouped[label][0] += val[1]  # norm_ae
            grouped[label][1] += 1

        # Build sorted ranking
        ranking = []
        for label, (s, c) in grouped.items():
            ranking.append([label, round(s / c, 4), c])

        if data_type == "river":
            ranking.sort(key=lambda x: x[1])  # ascending percentile
        else:
            ranking.sort(key=lambda x: x[1], reverse=True)  # descending AE

        ck = chunk_key(board_tuple)
        chunks[ck][board_key_str(board_tuple)] = ranking

        total_keys += len(hands)
        total_grouped += len(grouped)

    print(f"  Hand keys: {total_keys:,} -> {total_grouped:,} grouped ({100*(1-total_grouped/total_keys):.1f}% reduction)")

    # Write chunks
    total_raw = 0
    total_gz = 0
    files = []

    for ck in sorted(chunks):
        chunk_data = chunks[ck]
        fname = f"{prefix}_{ck}.json"
        out_path = OUT / fname
        with open(out_path, "w") as f:
            json.dump(chunk_data, f, separators=(",", ":"))
        raw = os.path.getsize(out_path)
        with open(out_path, "rb") as f:
            gz = len(gzip.compress(f.read()))
        total_raw += raw
        total_gz += gz
        files.append(fname)
        print(f"    {fname:<25} {len(chunk_data):>5} boards  {raw/1e6:>6.1f} MB raw  {gz/1e6:>5.1f} MB gz")

    print(f"  Total: {len(chunks)} chunks, {total_raw/1e6:.1f} MB raw, {total_gz/1e6:.1f} MB gzip")

    # Write chunk index (which chunks exist)
    index_path = OUT / f"{prefix}_index.json"
    with open(index_path, "w") as f:
        json.dump(sorted(chunks.keys()), f, separators=(",", ":"))

    return files


def convert_preflop(csv_name, out_name):
    csv_path = RESULTS / csv_name
    print(f"\nLoading {csv_path.name} ...")
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


if __name__ == "__main__":
    import sys
    only = sys.argv[1] if len(sys.argv) > 1 else None

    if not only or only == "rivers":
        convert_board_data_chunked("sd_stage1_rivers.pkl", "sd_rivers", "river")
    if not only or only == "turns":
        convert_board_data_chunked("sd_stage2_turns.pkl", "sd_turns", "turn")
    if not only or only == "flops":
        convert_board_data_chunked("sd_stage3_flops.pkl", "sd_flops", "turn")  # same format as turns
    if not only or only == "preflop":
        convert_preflop("rankings_short_deck.csv", "sd_preflop.json")
        convert_preflop("rankings.csv", "std_preflop.json")
    print("\nDone.")
