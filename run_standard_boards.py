"""
Standard Deck Board Rankings — All Streets
============================================
Computes rankings for all standard 52-card boards in stages:

  Stage 1: All river rankings (~2-3 hrs on Pi)
            Just hand strength, no simulation needed.
            C(52,5) = 2,598,960 boards (~134K canonical)

  Stage 2: All turn rankings (estimated ~5-6 days on Pi)
            For each turn, run out every river card, use river ranking
            to get percentiles, compute AE.
            C(52,4) = 270,725 boards (~16K canonical)

  Stage 3: All flop rankings (estimated 1-2 weeks on Pi)
            For each flop, run out every turn+river, use river ranking.
            C(52,3) = 22,100 boards (~1,833 canonical)

Usage:
    python3 run_standard_boards.py              # run all stages
    python3 run_standard_boards.py --stage 1    # run specific stage
    python3 run_standard_boards.py --stage 2    # turns only (needs stage 1 pkl)
    python3 run_standard_boards.py --stage 3    # flops only (needs stage 1 pkl)

Output:
    std_stage1_rivers.pkl    — cached river data
    std_stage2_turns.pkl     — cached turn rankings
    std_stage3_flops.pkl     — cached flop rankings
    std_results_rivers.csv   — overall river ranking
    std_results_turns.csv    — overall turn ranking
    std_results_flops.csv    — overall flop ranking
"""

import sys
import os
import csv
import time
import pickle
from itertools import combinations
from collections import defaultdict

from treys import Card, Deck
from evaluator import StandardEvaluator

# ── Initialise ───────────────────────────────────────────────────────────────

print("Initialising standard evaluator ...")
evaluator = StandardEvaluator()
DECK = evaluator.get_deck()
RANKS_STR = evaluator.RANKS
MAX_RANK = evaluator.MAX_RANK

TREYS_SUITS = sorted(set(Card.get_suit_int(c) for c in DECK))


# ── Canonicalisation helpers ─────────────────────────────────────────────────

def card_rs(c):
    """Return (rank_int, suit_int) for a treys card."""
    return Card.get_rank_int(c), Card.get_suit_int(c)


def canonicalize_board(board_cards):
    """Canonicalize board by remapping suits in order of first appearance."""
    rs = [card_rs(c) for c in board_cards]
    rs.sort()

    suit_map = {}
    next_s = 0
    for r, s in rs:
        if s not in suit_map:
            suit_map[s] = next_s
            next_s += 1
    for s in TREYS_SUITS:
        if s not in suit_map:
            suit_map[s] = next_s
            next_s += 1

    canon = tuple(sorted((r, suit_map[s]) for r, s in rs))
    return canon, suit_map


def hand_key(c1, c2, suit_map):
    """Map a concrete hand to a canonical key using the board's suit_map."""
    r1, s1 = card_rs(c1)
    r2, s2 = card_rs(c2)
    return tuple(sorted([(r1, suit_map[s1]), (r2, suit_map[s2])]))


def canonical_label_169(c1, c2):
    """Map two card ints to the standard 169-hand label."""
    r1 = Card.get_rank_int(c1)
    r2 = Card.get_rank_int(c2)
    s1 = Card.get_suit_int(c1)
    s2 = Card.get_suit_int(c2)

    n = len(RANKS_STR)
    ri1 = (n - 1) - r1
    ri2 = (n - 1) - r2

    if ri1 > ri2:
        ri1, ri2 = ri2, ri1

    high = RANKS_STR[ri1]
    low = RANKS_STR[ri2]

    if ri1 == ri2:
        return f"{high}{low}"
    elif s1 == s2:
        return f"{high}{low}s"
    else:
        return f"{high}{low}o"


# ── Core: compute ranking on a complete (5-card) board ───────────────────────

def compute_river_ranking(board_cards):
    """Evaluate all hands on a complete board, return {hand_key: percentile}."""
    _, suit_map = canonicalize_board(board_cards)
    board_set = set(board_cards)
    remaining = [c for c in DECK if c not in board_set]
    hands = list(combinations(remaining, 2))

    evals = []
    for h in hands:
        rank = evaluator.evaluate(list(h), board_cards)
        hk = hand_key(h[0], h[1], suit_map)
        evals.append((rank, hk))

    evals.sort(key=lambda x: x[0])

    n = len(evals)
    ranking = {}
    for i, (rank, hk) in enumerate(evals):
        ranking[hk] = (i + 1) / n

    return ranking


# ── Core: compute AE on a turn board using river rankings ────────────────────

def compute_turn_ae(board_4, river_cache):
    """Compute action equity for all hands on a 4-card board."""
    _, suit_map = canonicalize_board(board_4)
    board_set = set(board_4)
    remaining = [c for c in DECK if c not in board_set]

    stats = defaultdict(lambda: {
        "wins": 0, "ties": 0, "losses": 0,
        "weighted_ev": 0.0, "total_weight": 0.0,
    })

    for river_card in remaining:
        full_board = board_4 + [river_card]
        full_board_set = board_set | {river_card}

        canon_river, river_suit_map = canonicalize_board(full_board)
        if canon_river not in river_cache:
            river_cache[canon_river] = compute_river_ranking(full_board)
        river_ranking = river_cache[canon_river]

        avail = [c for c in DECK if c not in full_board_set]
        hands = list(combinations(avail, 2))

        hand_pcts = {}
        for h in hands:
            hk_river = hand_key(h[0], h[1], river_suit_map)
            hk_turn = hand_key(h[0], h[1], suit_map)
            hand_pcts[h] = (river_ranking[hk_river], hk_turn)

        for hero in hands:
            hero_pct, hero_tk = hand_pcts[hero]
            hero_val = 1.0 / hero_pct
            hero_set = set(hero)

            s = stats[hero_tk]
            for opp in hands:
                if opp[0] in hero_set or opp[1] in hero_set:
                    continue

                opp_pct, _ = hand_pcts[opp]
                opp_val = 1.0 / opp_pct
                stake = min(hero_val, opp_val)

                s["total_weight"] += stake

                if hero_pct < opp_pct:
                    s["wins"] += 1
                    s["weighted_ev"] += stake
                elif hero_pct == opp_pct:
                    s["ties"] += 1
                else:
                    s["losses"] += 1
                    s["weighted_ev"] -= stake

    result = {}
    for hk, s in stats.items():
        total = s["wins"] + s["ties"] + s["losses"]
        if total == 0:
            continue
        raw_eq = (s["wins"] + s["ties"] * 0.5) / total
        norm_ae = s["weighted_ev"] / s["total_weight"] if s["total_weight"] else 0
        result[hk] = (raw_eq, norm_ae)

    return result


# ── Aggregate and save ───────────────────────────────────────────────────────

def aggregate_to_169(all_boards_iter, compute_fn, street_name, cache_arg=None):
    """Run computation over all boards, aggregate by 169-hand labels."""
    overall = defaultdict(lambda: {"raw_eq_sum": 0.0, "norm_ae_sum": 0.0, "count": 0})
    computed_cache = {}
    total = len(all_boards_iter)

    t0 = time.time()
    boards_computed = 0

    for b_idx, board in enumerate(all_boards_iter, 1):
        canon, suit_map = canonicalize_board(board)

        if canon not in computed_cache:
            if cache_arg is not None:
                ae_data = compute_fn(board, cache_arg)
            else:
                ae_data = compute_fn(board)
            computed_cache[canon] = ae_data
            boards_computed += 1

        ae_data = computed_cache[canon]

        board_set = set(board)
        remaining = [c for c in DECK if c not in board_set]
        for h in combinations(remaining, 2):
            hk = hand_key(h[0], h[1], suit_map)
            if hk in ae_data:
                raw_eq, norm_ae = ae_data[hk]
                label = canonical_label_169(h[0], h[1])
                g = overall[label]
                g["raw_eq_sum"] += raw_eq
                g["norm_ae_sum"] += norm_ae
                g["count"] += 1

        if b_idx % max(1, total // 100) == 0 or b_idx == total:
            elapsed = time.time() - t0
            rate = b_idx / elapsed
            eta = (total - b_idx) / rate if rate else 0
            print(f"  [{b_idx:>9,}/{total:,}] ({boards_computed} unique)  "
                  f"elapsed {elapsed/60:6.1f}min  ETA {eta/60:6.1f}min", flush=True)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s ({elapsed/60:.1f} min / {elapsed/3600:.1f} hrs)")
    print(f"  Boards: {total:,} total, {boards_computed} unique (canonical)")

    return overall, computed_cache


def save_ranking_csv(overall, csv_path):
    """Sort, print, and save overall ranking to CSV."""
    results = []
    for label, g in overall.items():
        n = g["count"]
        results.append({
            "hand": label,
            "raw_equity": g["raw_eq_sum"] / n,
            "norm_ae": g["norm_ae_sum"] / n,
            "count": n,
        })

    by_raw = sorted(results, key=lambda x: x["raw_equity"], reverse=True)
    by_ae = sorted(results, key=lambda x: x["norm_ae"], reverse=True)
    raw_rank = {r["hand"]: i + 1 for i, r in enumerate(by_raw)}

    n_hands = len(results)
    print(f"\n  {n_hands} distinct hands\n")

    header = (f"{'#':>4}  {'Hand':<5} {'Raw Eq':>7} {'Raw #':>5}  "
              f"{'AE Norm':>8} {'AE #':>5}  {'Diff':>5}")
    print(header)
    print("-" * len(header))

    for i, entry in enumerate(by_ae, 1):
        h = entry["hand"]
        rr = raw_rank[h]
        diff = rr - i
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        print(f"{i:>4}  {h:<5} {entry['raw_equity']:>7.2%} {rr:>5}  "
              f"{entry['norm_ae']:>+8.4f} {i:>5}  {diff_str:>5}")

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hand", "count", "raw_equity", "raw_rank",
                         "action_equity_norm", "action_equity_rank", "rank_diff"])
        ae_rank = {r["hand"]: i + 1 for i, r in enumerate(by_ae)}
        for i, entry in enumerate(by_ae, 1):
            h = entry["hand"]
            rr = raw_rank[h]
            writer.writerow([h, entry["count"],
                             f"{entry['raw_equity']:.6f}", rr,
                             f"{entry['norm_ae']:.6f}", i, rr - i])
    print(f"\n  Saved to {csv_path}")


# ── River ranking (simple: just hand strength) ───────────────────────────────

def aggregate_rivers():
    """For rivers, ranking is just hand strength."""
    all_boards = list(combinations(DECK, 5))
    total = len(all_boards)
    computed_cache = {}

    overall = defaultdict(lambda: {"pct_sum": 0.0, "count": 0})
    t0 = time.time()
    boards_computed = 0

    for b_idx, board in enumerate(all_boards, 1):
        board_list = list(board)
        canon, suit_map = canonicalize_board(board_list)

        if canon not in computed_cache:
            computed_cache[canon] = compute_river_ranking(board_list)
            boards_computed += 1

        ranking = computed_cache[canon]

        board_set = set(board)
        remaining = [c for c in DECK if c not in board_set]
        for h in combinations(remaining, 2):
            hk = hand_key(h[0], h[1], suit_map)
            pct = ranking[hk]
            label = canonical_label_169(h[0], h[1])
            g = overall[label]
            g["pct_sum"] += pct
            g["count"] += 1

        if b_idx % max(1, total // 100) == 0 or b_idx == total:
            elapsed = time.time() - t0
            rate = b_idx / elapsed
            eta = (total - b_idx) / rate if rate else 0
            print(f"  [{b_idx:>9,}/{total:,}] ({boards_computed} unique)  "
                  f"elapsed {elapsed/60:6.1f}min  ETA {eta/60:6.1f}min", flush=True)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s ({elapsed/60:.1f} min / {elapsed/3600:.1f} hrs)")
    print(f"  Boards: {total:,} total, {boards_computed} unique (canonical)")

    results = []
    for label, g in overall.items():
        results.append({
            "hand": label,
            "avg_pct": g["pct_sum"] / g["count"],
            "count": g["count"],
        })

    results.sort(key=lambda x: x["avg_pct"])
    n_hands = len(results)
    print(f"\n  {n_hands} distinct hands (ranked by avg hand strength)\n")

    header = f"{'#':>4}  {'Hand':<5} {'Avg Pct':>8}  {'Count':>9}"
    print(header)
    print("-" * len(header))
    for i, entry in enumerate(results, 1):
        print(f"{i:>4}  {entry['hand']:<5} {entry['avg_pct']:>7.2%}  {entry['count']:>9,}")

    # Save river CSV
    csv_path = "std_results_rivers.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hand", "count", "avg_percentile", "rank"])
        for i, entry in enumerate(results, 1):
            writer.writerow([entry["hand"], entry["count"],
                             f"{entry['avg_pct']:.6f}", i])
    print(f"\n  Saved to {csv_path}")

    return computed_cache


# ── Stage runners ────────────────────────────────────────────────────────────

def run_stage_1():
    """Stage 1: All river rankings."""
    print("\n" + "=" * 60)
    print("  STAGE 1: All Standard Deck River Rankings")
    print("  C(52,5) = 2,598,960 boards")
    print("=" * 60 + "\n")

    t0 = time.time()
    river_cache = aggregate_rivers()

    pkl_path = "std_stage1_rivers.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(river_cache, f)
    print(f"  River cache saved to {pkl_path} ({len(river_cache)} canonical boards)")

    elapsed = time.time() - t0
    print(f"\n  Stage 1 total: {elapsed:.1f}s ({elapsed/60:.1f} min / {elapsed/3600:.1f} hrs)")
    return river_cache


def run_stage_2(river_cache=None):
    """Stage 2: All turn rankings."""
    print("\n" + "=" * 60)
    print("  STAGE 2: All Standard Deck Turn Rankings")
    print("  C(52,4) = 270,725 boards (~16K canonical)")
    print("  WARNING: This will take several days!")
    print("=" * 60 + "\n")

    if river_cache is None:
        pkl_path = "std_stage1_rivers.pkl"
        print(f"  Loading river cache from {pkl_path} ...")
        with open(pkl_path, "rb") as f:
            river_cache = pickle.load(f)
        print(f"  Loaded {len(river_cache)} canonical river boards\n")

    all_boards = [list(b) for b in combinations(DECK, 4)]
    total = len(all_boards)
    print(f"  Total 4-card boards: {total:,}\n")

    t0 = time.time()

    overall, turn_cache = aggregate_to_169(
        all_boards, compute_turn_ae, "turn", cache_arg=river_cache
    )

    save_ranking_csv(overall, "std_results_turns.csv")

    pkl_path = "std_stage2_turns.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(turn_cache, f)
    print(f"  Turn cache saved to {pkl_path} ({len(turn_cache)} canonical boards)")

    elapsed = time.time() - t0
    print(f"\n  Stage 2 total: {elapsed:.1f}s ({elapsed/60:.1f} min / "
          f"{elapsed/3600:.1f} hrs / {elapsed/86400:.1f} days)")
    return turn_cache


def compute_flop_ae_full(board_3, river_cache):
    """Compute AE for all hands on a 3-card flop by running out to the river."""
    _, suit_map = canonicalize_board(board_3)
    board_set = set(board_3)
    remaining = [c for c in DECK if c not in board_set]

    stats = defaultdict(lambda: {
        "wins": 0, "ties": 0, "losses": 0,
        "weighted_ev": 0.0, "total_weight": 0.0,
    })

    completions = list(combinations(remaining, 2))

    for turn_c, river_c in completions:
        full_board = board_3 + [turn_c, river_c]
        full_board_set = board_set | {turn_c, river_c}

        canon_river, river_suit_map = canonicalize_board(full_board)
        if canon_river not in river_cache:
            river_cache[canon_river] = compute_river_ranking(full_board)
        river_ranking = river_cache[canon_river]

        avail = [c for c in DECK if c not in full_board_set]
        hands = list(combinations(avail, 2))

        hand_pcts = {}
        for h in hands:
            hk_river = hand_key(h[0], h[1], river_suit_map)
            hand_pcts[h] = river_ranking[hk_river]

        for hero in hands:
            hero_pct = hand_pcts[hero]
            hero_val = 1.0 / hero_pct
            hero_set = set(hero)
            hero_tk = hand_key(hero[0], hero[1], suit_map)

            s = stats[hero_tk]
            for opp in hands:
                if opp[0] in hero_set or opp[1] in hero_set:
                    continue

                opp_pct = hand_pcts[opp]
                opp_val = 1.0 / opp_pct
                stake = min(hero_val, opp_val)

                s["total_weight"] += stake

                if hero_pct < opp_pct:
                    s["wins"] += 1
                    s["weighted_ev"] += stake
                elif hero_pct == opp_pct:
                    s["ties"] += 1
                else:
                    s["losses"] += 1
                    s["weighted_ev"] -= stake

    result = {}
    for hk, s in stats.items():
        total = s["wins"] + s["ties"] + s["losses"]
        if total == 0:
            continue
        raw_eq = (s["wins"] + s["ties"] * 0.5) / total
        norm_ae = s["weighted_ev"] / s["total_weight"] if s["total_weight"] else 0
        result[hk] = (raw_eq, norm_ae)

    return result


def run_stage_3(river_cache=None):
    """Stage 3: All flop rankings (full method — run out to river)."""
    print("\n" + "=" * 60)
    print("  STAGE 3: All Standard Deck Flop Rankings (Full Method)")
    print("  C(52,3) = 22,100 boards (~1,833 canonical)")
    print("  WARNING: This may take 1-2 weeks!")
    print("=" * 60 + "\n")

    if river_cache is None:
        pkl_path = "std_stage1_rivers.pkl"
        print(f"  Loading river cache from {pkl_path} ...")
        with open(pkl_path, "rb") as f:
            river_cache = pickle.load(f)
        print(f"  Loaded {len(river_cache)} canonical river boards\n")

    all_boards = [list(b) for b in combinations(DECK, 3)]
    total = len(all_boards)
    print(f"  Total 3-card flops: {total:,}\n")

    t0 = time.time()

    overall, flop_cache = aggregate_to_169(
        all_boards, compute_flop_ae_full, "flop", cache_arg=river_cache
    )

    save_ranking_csv(overall, "std_results_flops.csv")

    flop_pkl_path = "std_stage3_flops.pkl"
    with open(flop_pkl_path, "wb") as f:
        pickle.dump(flop_cache, f)
    print(f"  Flop cache saved to {flop_pkl_path} ({len(flop_cache)} canonical boards)")

    elapsed = time.time() - t0
    print(f"\n  Stage 3 total: {elapsed:.1f}s ({elapsed/60:.1f} min / "
          f"{elapsed/3600:.1f} hrs / {elapsed/86400:.1f} days)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    stage = None
    if "--stage" in args:
        idx = args.index("--stage")
        stage = args[idx + 1]

    t_start = time.time()

    if stage is None or stage == "1":
        river_cache = run_stage_1()
    else:
        river_cache = None

    if stage is None or stage == "2":
        turn_cache = run_stage_2(river_cache)
    else:
        turn_cache = None

    if stage is None or stage == "3":
        run_stage_3(river_cache)

    total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  All done in {total:.0f}s ({total/60:.0f} min / {total/3600:.1f} hrs)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
