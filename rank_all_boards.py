"""
Action Equity -- Rank all hands across all possible boards
============================================================
Exhaustively evaluates every possible board and ranks all hands.

For rivers: fully exact (board complete, enumerate opponents only).
For turns/flops: uses run_exact which enumerates remaining board + opponents.

Usage:
    py rank_all_boards.py --river                    # all rivers (standard)
    py rank_all_boards.py --turn                     # all turns
    py rank_all_boards.py --flop                     # all flops
    py rank_all_boards.py --river --short-deck       # short deck
    py rank_all_boards.py --river --save results_dir # save CSV
"""

import sys
import os
import csv
import time
from itertools import combinations
from collections import defaultdict

from treys import Card
from evaluator import StandardEvaluator, ShortDeckEvaluator
from simulation import hand_percentile, potential_value, pretty, run_exact


def canonical_label(c1, c2, ranks_str):
    """Map two cards to canonical 169-hand label."""
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


def rank_all_rivers_exact(evaluator, save_dir=None):
    """Optimised: for each complete river board, evaluate all hands vs all opponents."""
    full_deck = evaluator.get_deck()
    ranks_str = evaluator.RANKS
    max_rank = evaluator.MAX_RANK

    all_boards = list(combinations(full_deck, 5))
    total_boards = len(all_boards)

    print(f"  Total river boards: {total_boards:,}\n")

    overall = defaultdict(lambda: {
        "raw_eq_sum": 0.0, "norm_ae_sum": 0.0, "count": 0,
    })

    t0 = time.time()

    for b_idx, board in enumerate(all_boards, 1):
        board_list = list(board)
        board_set = set(board_list)
        remaining = [c for c in full_deck if c not in board_set]

        hand_combos = list(combinations(remaining, 2))

        # Pre-compute rank for every possible hand on this board
        hand_ranks = {}
        for h in hand_combos:
            hand_ranks[h] = evaluator.evaluate(list(h), board_list)

        # For each hand, compare against all non-overlapping opponents
        for hand in hand_combos:
            p_rank = hand_ranks[hand]
            p_pct = hand_percentile(p_rank, max_rank)
            p_val = potential_value(p_pct)
            hand_set = set(hand)

            wins = 0
            ties = 0
            total = 0
            weighted_ev = 0.0
            total_weight = 0.0

            for opp in hand_combos:
                if opp[0] in hand_set or opp[1] in hand_set:
                    continue

                o_rank = hand_ranks[opp]
                o_pct = hand_percentile(o_rank, max_rank)
                o_val = potential_value(o_pct)
                stake = min(p_val, o_val)

                total_weight += stake
                total += 1

                if p_rank < o_rank:
                    wins += 1
                    weighted_ev += stake
                elif p_rank == o_rank:
                    ties += 1
                else:
                    weighted_ev -= stake

            raw_eq = (wins + ties * 0.5) / total if total else 0
            norm_ae = weighted_ev / total_weight if total_weight else 0

            label = canonical_label(hand[0], hand[1], ranks_str)
            g = overall[label]
            g["raw_eq_sum"] += raw_eq
            g["norm_ae_sum"] += norm_ae
            g["count"] += 1

        if b_idx % max(1, total_boards // 20) == 0 or b_idx == total_boards:
            elapsed = time.time() - t0
            rate = b_idx / elapsed
            eta = (total_boards - b_idx) / rate if rate else 0
            print(f"  [{b_idx:>8,}/{total_boards:,}]  "
                  f"elapsed {elapsed:5.1f}s  ETA {eta:5.1f}s", flush=True)

    return overall, time.time() - t0


def rank_all_partial_boards(n_board, evaluator, save_dir=None):
    """For turns/flops: enumerate all partial boards, use run_exact per hand."""
    full_deck = evaluator.get_deck()
    ranks_str = evaluator.RANKS

    all_boards = list(combinations(full_deck, n_board))
    total_boards = len(all_boards)
    street = {3: "flop", 4: "turn"}[n_board]

    print(f"  Total {street} boards: {total_boards:,}\n")

    overall = defaultdict(lambda: {
        "raw_eq_sum": 0.0, "norm_ae_sum": 0.0, "count": 0,
    })

    t0 = time.time()

    for b_idx, board in enumerate(all_boards, 1):
        board_list = list(board)
        board_set = set(board_list)
        remaining = [c for c in full_deck if c not in board_set]

        for hand in combinations(remaining, 2):
            hand_list = list(hand)
            r = run_exact(hand_list, evaluator, board_list)

            label = canonical_label(hand[0], hand[1], ranks_str)
            g = overall[label]
            g["raw_eq_sum"] += r["raw_equity"]
            g["norm_ae_sum"] += r["normalised_ev"]
            g["count"] += 1

        if b_idx % max(1, total_boards // 20) == 0 or b_idx == total_boards:
            elapsed = time.time() - t0
            rate = b_idx / elapsed
            eta = (total_boards - b_idx) / rate if rate else 0
            print(f"  [{b_idx:>8,}/{total_boards:,}]  "
                  f"elapsed {elapsed:5.1f}s  ETA {eta:5.1f}s", flush=True)

    return overall, time.time() - t0


def print_and_save_results(overall, street, total_boards, evaluator, save_dir):
    """Average, rank, print and save results."""
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
    print(f"\n  {n_hands} distinct hands, averaged across {total_boards:,} {street}s\n")

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

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        csv_path = os.path.join(save_dir, f"rankings_all_{street}s.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["hand", "count", "raw_equity", "raw_rank",
                             "action_equity_norm", "action_equity_rank", "rank_diff"])
            for i, entry in enumerate(by_ae, 1):
                h = entry["hand"]
                rr = raw_rank[h]
                writer.writerow([h, entry["count"],
                                 f"{entry['raw_equity']:.6f}", rr,
                                 f"{entry['norm_ae']:.6f}", i, rr - i])
        print(f"\nResults saved to {csv_path}")


def main():
    args = sys.argv[1:]

    short_deck = "--short-deck" in args
    if short_deck:
        args.remove("--short-deck")

    save_dir = None
    if "--save" in args:
        idx = args.index("--save")
        save_dir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    street = None
    for s in ("--river", "--turn", "--flop"):
        if s in args:
            street = s[2:]
            args.remove(s)

    if not street:
        print("Specify a street: --river, --turn, or --flop")
        sys.exit(1)

    if short_deck:
        evaluator = ShortDeckEvaluator()
        variant = "Short Deck (6+)"
    else:
        evaluator = StandardEvaluator()
        variant = "Standard"

    n_board = {"river": 5, "turn": 4, "flop": 3}[street]
    n_deck = len(evaluator.get_deck())
    total_boards = 1
    for i in range(n_board):
        total_boards = total_boards * (n_deck - i) // (i + 1)

    print(f"\nExhaustive ranking across all {street}s ({variant}):\n")

    if street == "river":
        overall, elapsed = rank_all_rivers_exact(evaluator, save_dir)
    else:
        overall, elapsed = rank_all_partial_boards(n_board, evaluator, save_dir)

    print(f"\n  Completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print_and_save_results(overall, street, total_boards, evaluator, save_dir)


if __name__ == "__main__":
    main()
