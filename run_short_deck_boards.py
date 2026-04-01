"""
Short Deck Board Rankings — All Streets
==========================================
Computes rankings for all short deck boards in stages:

  Stage 1: All river rankings (~10-15 min)
            Just hand strength, no simulation needed.

  Stage 2: All turn rankings (hours)
            For each turn, run out every river card, use river ranking
            to get percentiles, compute AE.
            Saves results for use in Stage 3b.

  Stage 3a: All flop rankings — full method (hours)
            For each flop, run out every turn+river, same as Stage 2.

  Stage 3b: All flop rankings — approx method (minutes)
            For each flop, run out only the turn card, use pre-computed
            turn rankings (from Stage 2) for percentiles.
            Much faster but approximate.

Usage:
    python3 run_short_deck_boards.py              # run all stages
    python3 run_short_deck_boards.py --stage 1    # run specific stage
    python3 run_short_deck_boards.py --stage 3b   # approx flops only

Output:
    sd_stage1_rivers.pkl    — cached river data
    sd_stage2_turns.pkl     — cached turn rankings (used by stage 3b)
    sd_results_rivers.csv   — overall river ranking
    sd_results_turns.csv    — overall turn ranking
    sd_results_flops.csv    — overall flop ranking (full)
    sd_results_flops_approx.csv — overall flop ranking (approx)
"""

import sys
import os
import csv
import time
import pickle
from itertools import combinations
from collections import defaultdict

from treys import Card
from evaluator import ShortDeckEvaluator

# ── Initialise ───────────────────────────────────────────────────────────────

print("Initialising short deck evaluator ...")
evaluator = ShortDeckEvaluator()
DECK = evaluator.get_deck()
RANKS_STR = evaluator.RANKS
MAX_RANK = evaluator.MAX_RANK

TREYS_SUITS = sorted(set(Card.get_suit_int(c) for c in DECK))


# ── Canonicalisation helpers ─────────────────────────────────────────────────

def card_rs(c):
    """Return (rank_int, suit_int) for a treys card."""
    return Card.get_rank_int(c), Card.get_suit_int(c)


def canonicalize_board(board_cards):
    """Canonicalize board by remapping suits in order of first appearance.

    Returns (canonical_board_tuple, suit_map).
    suit_map maps every original suit to a canonical suit (0,1,2,3).
    Unseen suits are assigned in natural order after seen ones.
    """
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
    """Map two card ints to the standard 169-hand label (e.g. AKs, TT, 72o)."""
    r1 = Card.get_rank_int(c1)
    r2 = Card.get_rank_int(c2)
    s1 = Card.get_suit_int(c1)
    s2 = Card.get_suit_int(c2)

    n = len(RANKS_STR)
    ri1 = (n - 1) - (r1 - (13 - n))
    ri2 = (n - 1) - (r2 - (13 - n))

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
    """Evaluate all hands on a complete board, return {hand_key: rank_position}.

    rank_position: 1 = best, N = worst (based on hand strength).
    Returns dict in canonical suit space of this board.
    """
    _, suit_map = canonicalize_board(board_cards)
    board_set = set(board_cards)
    remaining = [c for c in DECK if c not in board_set]
    hands = list(combinations(remaining, 2))

    # Evaluate all hands
    evals = []
    for h in hands:
        rank = evaluator.evaluate(list(h), board_cards)
        hk = hand_key(h[0], h[1], suit_map)
        evals.append((rank, hk))

    # Sort by rank (lower = better in treys)
    evals.sort(key=lambda x: x[0])

    # Assign percentiles: 1/N = best, N/N = worst
    n = len(evals)
    ranking = {}
    for i, (rank, hk) in enumerate(evals):
        ranking[hk] = (i + 1) / n

    return ranking


# ── Core: compute AE on a turn board using river rankings ────────────────────

def compute_turn_ae(board_4, river_cache):
    """Compute action equity for all hands on a 4-card board.

    For each possible river card, looks up the river ranking to get
    percentiles, then computes AE.

    Returns {hand_key: (raw_equity, norm_ae)} in canonical suit space.
    """
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

        # Get river ranking (cached)
        canon_river, river_suit_map = canonicalize_board(full_board)
        if canon_river not in river_cache:
            river_cache[canon_river] = compute_river_ranking(full_board)
        river_ranking = river_cache[canon_river]

        # All hands on this complete board
        avail = [c for c in DECK if c not in full_board_set]
        hands = list(combinations(avail, 2))

        # Look up percentiles for all hands
        hand_pcts = {}
        for h in hands:
            hk_river = hand_key(h[0], h[1], river_suit_map)
            hk_turn = hand_key(h[0], h[1], suit_map)
            hand_pcts[h] = (river_ranking[hk_river], hk_turn)

        # Compare all hand pairs
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

    # Compute final metrics
    result = {}
    for hk, s in stats.items():
        total = s["wins"] + s["ties"] + s["losses"]
        if total == 0:
            continue
        raw_eq = (s["wins"] + s["ties"] * 0.5) / total
        norm_ae = s["weighted_ev"] / s["total_weight"] if s["total_weight"] else 0
        result[hk] = (raw_eq, norm_ae)

    return result


# ── Core: compute AE on a flop using turn rankings (approx) ─────────────────

def compute_flop_ae_approx(board_3, turn_rankings):
    """Compute AE for all hands on a 3-card flop using pre-computed turn rankings.

    Instead of running out to the river, runs out only to the turn and
    uses pre-computed turn AE percentiles.
    """
    _, suit_map = canonicalize_board(board_3)
    board_set = set(board_3)
    remaining = [c for c in DECK if c not in board_set]

    stats = defaultdict(lambda: {
        "wins": 0, "ties": 0, "losses": 0,
        "weighted_ev": 0.0, "total_weight": 0.0,
    })

    for turn_card in remaining:
        board_4 = board_3 + [turn_card]
        board_4_set = board_set | {turn_card}

        # Look up turn ranking
        canon_turn, turn_suit_map = canonicalize_board(board_4)
        if canon_turn not in turn_rankings:
            continue  # shouldn't happen

        turn_ranking = turn_rankings[canon_turn]

        # All hands on this 4-card board
        avail = [c for c in DECK if c not in board_4_set]
        hands = list(combinations(avail, 2))

        # Look up AE percentiles from turn ranking
        # First: get all AE values and rank them to get percentiles
        hand_ae_vals = {}
        for h in hands:
            hk_turn = hand_key(h[0], h[1], turn_suit_map)
            if hk_turn in turn_ranking:
                _, norm_ae = turn_ranking[hk_turn]
                hand_ae_vals[h] = norm_ae

        # Rank by AE to get percentiles (higher AE = better = lower percentile)
        sorted_hands = sorted(hand_ae_vals.keys(),
                              key=lambda h: hand_ae_vals[h], reverse=True)
        n = len(sorted_hands)
        hand_pcts = {}
        for i, h in enumerate(sorted_hands):
            hand_pcts[h] = (i + 1) / n

        # Compare all hand pairs using turn-derived percentiles
        for hero in sorted_hands:
            hero_pct = hand_pcts[hero]
            hero_val = 1.0 / hero_pct
            hero_set = set(hero)
            hero_tk = hand_key(hero[0], hero[1], suit_map)

            s = stats[hero_tk]
            for opp in sorted_hands:
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


# ── Core: compute AE on a flop running out to river (full) ──────────────────

def compute_flop_ae_full(board_3, river_cache):
    """Compute AE for all hands on a 3-card flop by running out to the river.

    Same approach as turns but with C(33,2)=528 board completions.
    """
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

        # Get river ranking (cached)
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


# ── Aggregate and save ───────────────────────────────────────────────────────

def aggregate_to_169(all_boards_iter, compute_fn, street_name, cache_arg=None):
    """Run computation over all boards, aggregate by 169-hand labels.

    all_boards_iter: list of board card lists
    compute_fn: function(board, cache) -> {hand_key: (raw_eq, norm_ae)}
    """
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

        # Map hands back through this board's suit_map
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

        if b_idx % max(1, total // 20) == 0 or b_idx == total:
            elapsed = time.time() - t0
            rate = b_idx / elapsed
            eta = (total - b_idx) / rate if rate else 0
            print(f"  [{b_idx:>7,}/{total:,}] ({boards_computed} unique)  "
                  f"elapsed {elapsed:5.1f}s  ETA {eta:5.1f}s", flush=True)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")
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
    """For rivers, ranking is just hand strength. No AE computation."""
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

        if b_idx % max(1, total // 20) == 0 or b_idx == total:
            elapsed = time.time() - t0
            rate = b_idx / elapsed
            eta = (total - b_idx) / rate if rate else 0
            print(f"  [{b_idx:>7,}/{total:,}] ({boards_computed} unique)  "
                  f"elapsed {elapsed:5.1f}s  ETA {eta:5.1f}s", flush=True)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Boards: {total:,} total, {boards_computed} unique (canonical)")

    # For rivers, we rank by average percentile (lower = better)
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

    header = f"{'#':>4}  {'Hand':<5} {'Avg Pct':>8}"
    print(header)
    print("-" * len(header))
    for i, entry in enumerate(results, 1):
        print(f"{i:>4}  {entry['hand']:<5} {entry['avg_pct']:>7.2%}")

    return computed_cache


# ── Stage runners ────────────────────────────────────────────────────────────

def run_stage_1():
    """Stage 1: All river rankings."""
    print("\n" + "=" * 60)
    print("  STAGE 1: All Short Deck River Rankings")
    print("=" * 60 + "\n")

    t0 = time.time()
    river_cache = aggregate_rivers()

    # Save cache for later stages
    pkl_path = "sd_stage1_rivers.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(river_cache, f)
    print(f"  River cache saved to {pkl_path} ({len(river_cache)} canonical boards)")

    elapsed = time.time() - t0
    print(f"\n  Stage 1 total: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    return river_cache


def run_stage_2(river_cache=None):
    """Stage 2: All turn rankings."""
    print("\n" + "=" * 60)
    print("  STAGE 2: All Short Deck Turn Rankings")
    print("=" * 60 + "\n")

    # Load river cache if not provided
    if river_cache is None:
        pkl_path = "sd_stage1_rivers.pkl"
        print(f"  Loading river cache from {pkl_path} ...")
        with open(pkl_path, "rb") as f:
            river_cache = pickle.load(f)
        print(f"  Loaded {len(river_cache)} canonical river boards\n")

    all_boards = [list(b) for b in combinations(DECK, 4)]
    total = len(all_boards)
    print(f"  Total 4-card boards: {total:,}\n")

    t0 = time.time()

    # Compute turn AE for all boards, aggregate by 169 labels
    overall, turn_cache = aggregate_to_169(
        all_boards, compute_turn_ae, "turn", cache_arg=river_cache
    )

    save_ranking_csv(overall, "sd_results_turns.csv")

    # Save turn cache for stage 3b
    pkl_path = "sd_stage2_turns.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(turn_cache, f)
    print(f"  Turn cache saved to {pkl_path} ({len(turn_cache)} canonical boards)")

    elapsed = time.time() - t0
    print(f"\n  Stage 2 total: {elapsed:.1f}s ({elapsed/60:.1f} min / {elapsed/3600:.1f} hrs)")
    return turn_cache


def run_stage_3a(river_cache=None):
    """Stage 3a: All flop rankings (full method — run out to river)."""
    print("\n" + "=" * 60)
    print("  STAGE 3a: All Short Deck Flop Rankings (Full Method)")
    print("=" * 60 + "\n")

    if river_cache is None:
        pkl_path = "sd_stage1_rivers.pkl"
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

    save_ranking_csv(overall, "sd_results_flops.csv")

    # Save flop cache for web app
    flop_pkl = "sd_stage3_flops.pkl"
    with open(flop_pkl, "wb") as f:
        pickle.dump(flop_cache, f)
    print(f"  Flop cache saved to {flop_pkl} ({len(flop_cache)} canonical boards)")

    elapsed = time.time() - t0
    print(f"\n  Stage 3a total: {elapsed:.1f}s ({elapsed/60:.1f} min / {elapsed/3600:.1f} hrs)")


def run_stage_3b(turn_cache=None):
    """Stage 3b: All flop rankings (approx method — run out to turn only)."""
    print("\n" + "=" * 60)
    print("  STAGE 3b: All Short Deck Flop Rankings (Approx Method)")
    print("=" * 60 + "\n")

    if turn_cache is None:
        pkl_path = "sd_stage2_turns.pkl"
        print(f"  Loading turn cache from {pkl_path} ...")
        with open(pkl_path, "rb") as f:
            turn_cache = pickle.load(f)
        print(f"  Loaded {len(turn_cache)} canonical turn boards\n")

    all_boards = [list(b) for b in combinations(DECK, 3)]
    total = len(all_boards)
    print(f"  Total 3-card flops: {total:,}\n")

    t0 = time.time()

    overall, _ = aggregate_to_169(
        all_boards, compute_flop_ae_approx, "flop_approx", cache_arg=turn_cache
    )

    save_ranking_csv(overall, "sd_results_flops_approx.csv")

    elapsed = time.time() - t0
    print(f"\n  Stage 3b total: {elapsed:.1f}s ({elapsed/60:.1f} min / {elapsed/3600:.1f} hrs)")


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

    if stage is None or stage == "3a":
        run_stage_3a(river_cache)

    if stage is None or stage == "3b":
        run_stage_3b(turn_cache)

    total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  All done in {total:.0f}s ({total/60:.0f} min / {total/3600:.1f} hrs)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
