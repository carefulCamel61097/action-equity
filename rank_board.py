"""
Action Equity -- Rank all hands on a specific board (optimised)
================================================================
Given a flop, turn, or river, ranks all possible starting hands.

River:  Just evaluate + sort by hand strength. Instant (~40ms).
Turn:   For each river card, compute river ranking to get percentiles,
        then compute action equity from those percentiles. Fast (~seconds).
Flop:   For each turn+river completion, same approach. (~minutes).

Usage:
    py rank_board.py Qh Jc 3s 2d 7h            # river
    py rank_board.py Qh Jc 3s 2d               # turn
    py rank_board.py Qh Jc 3s                  # flop
    py rank_board.py --short-deck 9h 8s 7d      # short deck flop
    py rank_board.py Qh Jc 3s --save results    # save to results.csv
"""

import sys
import csv
import time
from itertools import combinations
from collections import defaultdict

from treys import Card
from evaluator import StandardEvaluator, ShortDeckEvaluator
from simulation import parse_cards, pretty, hand_percentile, potential_value


def canonical_label(c1, c2, ranks_str):
    """Map two card ints to canonical 169-hand label."""
    r1 = Card.get_rank_int(c1)
    r2 = Card.get_rank_int(c2)
    s1 = Card.get_suit_int(c1)
    s2 = Card.get_suit_int(c2)

    n = len(ranks_str)
    ri1 = (n - 1) - (r1 - (13 - n))
    ri2 = (n - 1) - (r2 - (13 - n))

    if ri1 > ri2:
        ri1, ri2 = ri2, ri1

    high = ranks_str[ri1]
    low = ranks_str[ri2]

    if ri1 == ri2:
        return f"{high}{low}"
    elif s1 == s2:
        return f"{high}{low}s"
    else:
        return f"{high}{low}o"


# ── River: pure hand strength ────────────────────────────────────────────────

def rank_river(board_cards, evaluator):
    """Rank all hands on a complete board by hand strength. No AE needed."""
    full_deck = evaluator.get_deck()
    remaining = [c for c in full_deck if c not in set(board_cards)]
    all_hands = list(combinations(remaining, 2))

    # Evaluate every hand once
    hand_ranks = {}
    for h in all_hands:
        hand_ranks[h] = evaluator.evaluate(list(h), board_cards)

    # Sort: lower rank = stronger
    sorted_hands = sorted(all_hands, key=lambda h: hand_ranks[h])

    # Assign percentiles
    n = len(sorted_hands)
    hand_pct = {}
    for i, h in enumerate(sorted_hands):
        hand_pct[h] = (i + 1) / n  # 1/n = best, 1.0 = worst

    return hand_ranks, hand_pct, sorted_hands


# ── Turn: AE from river percentiles ─────────────────────────────────────────

def rank_turn(board_cards, evaluator):
    """For each possible river card, compute river ranking, then AE."""
    full_deck = evaluator.get_deck()
    board_set = set(board_cards)
    remaining = [c for c in full_deck if c not in board_set]
    max_rank = evaluator.MAX_RANK

    # All possible hero hands (from cards not on board)
    all_hands = list(combinations(remaining, 2))

    # Accumulators per hand
    stats = defaultdict(lambda: {
        "wins": 0, "ties": 0, "losses": 0,
        "weighted_ev": 0.0, "total_weight": 0.0,
    })

    # For each possible river card
    river_cards = remaining  # any card not on the 4-card board
    n_rivers = len(river_cards)

    for r_idx, river in enumerate(river_cards):
        full_board = board_cards + [river]

        # Get all hands that don't use the river card
        board_full_set = board_set | {river}
        avail = [c for c in full_deck if c not in board_full_set]
        hands_this_river = list(combinations(avail, 2))

        # Pre-compute all ranks on this complete board
        hand_ranks = {}
        for h in hands_this_river:
            hand_ranks[h] = evaluator.evaluate(list(h), full_board)

        # Sort to get percentiles on this river
        sorted_hands = sorted(hands_this_river, key=lambda h: hand_ranks[h])
        n = len(sorted_hands)
        hand_pct = {}
        for i, h in enumerate(sorted_hands):
            hand_pct[h] = (i + 1) / n

        # Compare each hero vs all non-overlapping opponents
        for hero in hands_this_river:
            hero_set = set(hero)
            p_rank = hand_ranks[hero]
            p_pct = hand_pct[hero]
            p_val = 1.0 / p_pct

            s = stats[hero]
            for opp in hands_this_river:
                if opp[0] in hero_set or opp[1] in hero_set:
                    continue

                o_rank = hand_ranks[opp]
                o_pct = hand_pct[opp]
                o_val = 1.0 / o_pct
                stake = min(p_val, o_val)

                s["total_weight"] += stake

                if p_rank < o_rank:
                    s["wins"] += 1
                    s["weighted_ev"] += stake
                elif p_rank == o_rank:
                    s["ties"] += 1
                else:
                    s["losses"] += 1
                    s["weighted_ev"] -= stake

    return stats, all_hands


# ── Flop: AE from turn+river completions ─────────────────────────────────────

def rank_flop(board_cards, evaluator):
    """For each possible turn+river, compute river ranking, then AE."""
    full_deck = evaluator.get_deck()
    board_set = set(board_cards)
    remaining = [c for c in full_deck if c not in board_set]

    all_hands = list(combinations(remaining, 2))

    stats = defaultdict(lambda: {
        "wins": 0, "ties": 0, "losses": 0,
        "weighted_ev": 0.0, "total_weight": 0.0,
    })

    # All possible turn+river completions
    completions = list(combinations(remaining, 2))
    total_comp = len(completions)

    t0 = time.time()
    for c_idx, (turn_c, river_c) in enumerate(completions, 1):
        full_board = board_cards + [turn_c, river_c]
        board_full_set = board_set | {turn_c, river_c}
        avail = [c for c in full_deck if c not in board_full_set]
        hands_this = list(combinations(avail, 2))

        # Pre-compute ranks
        hand_ranks = {}
        for h in hands_this:
            hand_ranks[h] = evaluator.evaluate(list(h), full_board)

        # Percentiles
        sorted_hands = sorted(hands_this, key=lambda h: hand_ranks[h])
        n = len(sorted_hands)
        hand_pct = {}
        for i, h in enumerate(sorted_hands):
            hand_pct[h] = (i + 1) / n

        # Compare
        for hero in hands_this:
            hero_set = set(hero)
            p_rank = hand_ranks[hero]
            p_pct = hand_pct[hero]
            p_val = 1.0 / p_pct

            s = stats[hero]
            for opp in hands_this:
                if opp[0] in hero_set or opp[1] in hero_set:
                    continue

                o_rank = hand_ranks[opp]
                o_pct = hand_pct[opp]
                o_val = 1.0 / o_pct
                stake = min(p_val, o_val)

                s["total_weight"] += stake

                if p_rank < o_rank:
                    s["wins"] += 1
                    s["weighted_ev"] += stake
                elif p_rank == o_rank:
                    s["ties"] += 1
                else:
                    s["losses"] += 1
                    s["weighted_ev"] -= stake

        if c_idx % max(1, total_comp // 20) == 0 or c_idx == total_comp:
            elapsed = time.time() - t0
            rate = c_idx / elapsed
            eta = (total_comp - c_idx) / rate if rate else 0
            print(f"  [{c_idx:>6,}/{total_comp:,}]  "
                  f"elapsed {elapsed:5.1f}s  ETA {eta:5.1f}s", flush=True)

    return stats, all_hands


# ── Output ───────────────────────────────────────────────────────────────────

def print_ranking(board_cards, evaluator, stats_or_sorted, is_river, save_base):
    """Group by canonical label, average, print and optionally save."""
    ranks_str = evaluator.RANKS

    if is_river:
        # stats_or_sorted is (hand_ranks, hand_pct, sorted_hands)
        hand_ranks, hand_pct, sorted_hands = stats_or_sorted
        # Group by canonical label
        grouped = defaultdict(lambda: {"rank_sum": 0, "pct_sum": 0.0, "count": 0})
        for h in sorted_hands:
            label = canonical_label(h[0], h[1], ranks_str)
            g = grouped[label]
            g["rank_sum"] += hand_ranks[h]
            g["pct_sum"] += hand_pct[h]
            g["count"] += 1

        results = []
        for label, g in grouped.items():
            results.append({
                "hand": label,
                "avg_rank": g["rank_sum"] / g["count"],
                "avg_pct": g["pct_sum"] / g["count"],
                "combos": g["count"],
            })

        results.sort(key=lambda x: x["avg_rank"])

        n_hands = len(results)
        print(f"\n  {n_hands} distinct hands on board {pretty(board_cards)}")
        print(f"  (River: ranked by hand strength, no AE needed)\n")

        header = f"{'#':>4}  {'Hand':<5} {'Combos':>6} {'Avg Pct':>8}"
        print(header)
        print("-" * len(header))

        for i, entry in enumerate(results, 1):
            print(f"{i:>4}  {entry['hand']:<5} {entry['combos']:>6} "
                  f"{entry['avg_pct']:>7.2%}")

        if save_base:
            csv_path = save_base + ".csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["rank", "hand", "combos", "avg_percentile"])
                for i, entry in enumerate(results, 1):
                    writer.writerow([i, entry["hand"], entry["combos"],
                                     f"{entry['avg_pct']:.6f}"])
            print(f"\nResults saved to {csv_path}")

    else:
        # stats_or_sorted is (stats dict, all_hands list)
        stats, all_hands = stats_or_sorted

        grouped = defaultdict(lambda: {
            "raw_eq_sum": 0.0, "norm_ae_sum": 0.0, "count": 0,
        })

        for h in all_hands:
            if h not in stats:
                continue
            s = stats[h]
            total = s["wins"] + s["ties"] + s["losses"]
            if total == 0:
                continue
            raw_eq = (s["wins"] + s["ties"] * 0.5) / total
            norm_ae = s["weighted_ev"] / s["total_weight"] if s["total_weight"] else 0

            label = canonical_label(h[0], h[1], ranks_str)
            g = grouped[label]
            g["raw_eq_sum"] += raw_eq
            g["norm_ae_sum"] += norm_ae
            g["count"] += 1

        results = []
        for label, g in grouped.items():
            n = g["count"]
            results.append({
                "hand": label,
                "raw_equity": g["raw_eq_sum"] / n,
                "norm_ae": g["norm_ae_sum"] / n,
                "combos": n,
            })

        by_raw = sorted(results, key=lambda x: x["raw_equity"], reverse=True)
        by_ae = sorted(results, key=lambda x: x["norm_ae"], reverse=True)
        raw_rank = {r["hand"]: i + 1 for i, r in enumerate(by_raw)}

        n_hands = len(results)
        print(f"\n  {n_hands} distinct hands on board {pretty(board_cards)}\n")

        header = (f"{'#':>4}  {'Hand':<5} {'Combos':>6} {'Raw Eq':>7} {'Raw #':>5}  "
                  f"{'AE Norm':>8} {'AE #':>5}  {'Diff':>5}")
        print(header)
        print("-" * len(header))

        for i, entry in enumerate(by_ae, 1):
            h = entry["hand"]
            rr = raw_rank[h]
            diff = rr - i
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            print(f"{i:>4}  {h:<5} {entry['combos']:>6} {entry['raw_equity']:>7.2%} {rr:>5}  "
                  f"{entry['norm_ae']:>+8.4f} {i:>5}  {diff_str:>5}")

        if save_base:
            csv_path = save_base + ".csv"
            ae_rank = {r["hand"]: i + 1 for i, r in enumerate(by_ae)}
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["hand", "combos", "raw_equity", "raw_rank",
                                 "action_equity_norm", "action_equity_rank", "rank_diff"])
                for i, entry in enumerate(by_ae, 1):
                    h = entry["hand"]
                    rr = raw_rank[h]
                    writer.writerow([h, entry["combos"],
                                     f"{entry['raw_equity']:.6f}", rr,
                                     f"{entry['norm_ae']:.6f}", i, rr - i])
            print(f"\nResults saved to {csv_path}")


def main():
    args = sys.argv[1:]

    short_deck = False
    if "--short-deck" in args:
        short_deck = True
        args.remove("--short-deck")

    save_base = None
    if "--save" in args:
        idx = args.index("--save")
        save_base = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if len(args) < 3 or len(args) > 5:
        print("Provide 3-5 board cards.")
        sys.exit(1)

    board_cards = parse_cards(args)

    if short_deck:
        evaluator = ShortDeckEvaluator()
        variant = "Short Deck (6+)"
    else:
        evaluator = StandardEvaluator()
        variant = "Standard"

    n_board = len(board_cards)
    print(f"\nRanking all hands on board ({variant}):\n")

    t0 = time.time()

    if n_board == 5:
        result = rank_river(board_cards, evaluator)
        elapsed = time.time() - t0
        print(f"  Done in {elapsed*1000:.0f}ms")
        print_ranking(board_cards, evaluator, result, is_river=True, save_base=save_base)
    elif n_board == 4:
        stats, all_hands = rank_turn(board_cards, evaluator)
        elapsed = time.time() - t0
        print(f"  Done in {elapsed:.1f}s")
        print_ranking(board_cards, evaluator, (stats, all_hands), is_river=False, save_base=save_base)
    elif n_board == 3:
        stats, all_hands = rank_flop(board_cards, evaluator)
        elapsed = time.time() - t0
        print(f"  Done in {elapsed:.1f}s ({elapsed/60:.1f} min)")
        print_ranking(board_cards, evaluator, (stats, all_hands), is_river=False, save_base=save_base)
    else:
        print("Provide 3-5 board cards.")
        sys.exit(1)


if __name__ == "__main__":
    main()
