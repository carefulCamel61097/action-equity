"""
Action Equity -- Full Hand Rankings (Stratified Sampling)
==========================================================
For each hero hand, enumerates all distinct opponent equivalence classes
(based on suit-pattern relative to hero) and runs equal board iterations
per class. This eliminates opponent sampling bias entirely.

Supports standard (52-card) and short deck (6+).

Usage:
    py rank_all_hands.py                          # standard, 50k per hand
    py rank_all_hands.py --short-deck             # short deck, 50k per hand
    py rank_all_hands.py --short-deck 100000      # custom iterations per hand
    py rank_all_hands.py 50000 results            # save to results.csv/.txt
    py rank_all_hands.py --short-deck 50000 rankings_short_deck
"""

import sys
import csv
import time
import random
from itertools import combinations

from treys import Card
from evaluator import StandardEvaluator, ShortDeckEvaluator
from simulation import hand_percentile, potential_value


def canonical_hands(ranks_str: str) -> list[tuple[str, list[int]]]:
    """Return (label, [card1, card2]) for all distinct starting hands."""
    hands = []
    for i, r1 in enumerate(ranks_str):
        for j, r2 in enumerate(ranks_str):
            if i < j:
                label = f"{r1}{r2}s"
                cards = [Card.new(f"{r1}s"), Card.new(f"{r2}s")]
            elif i == j:
                label = f"{r1}{r2}"
                cards = [Card.new(f"{r1}s"), Card.new(f"{r2}h")]
            else:
                label = f"{r2}{r1}o"
                cards = [Card.new(f"{r1}s"), Card.new(f"{r2}d")]
            hands.append((label, cards))
    return hands


# ── Opponent equivalence classes ─────────────────────────────────────────────

def compute_opponent_classes(hero_hand, deck):
    """Group all possible opponent hands into equivalence classes.

    Two opponent hands are equivalent if they differ only by a permutation
    of suits that are interchangeable from the hero's perspective.

    For a suited hero (e.g. AsKs):
        - Hero's suit is special; the other 3 suits are interchangeable.

    For an offsuit/pair hero (e.g. AsKd or AsAh):
        - Both hero suits are special; the other 2 suits are interchangeable.

    Returns list of (representative_hand, multiplicity) tuples.
    """
    hero_suits = [Card.get_suit_int(c) for c in hero_hand]
    hero_suited = (hero_suits[0] == hero_suits[1])

    remaining = [c for c in deck if c not in hero_hand]

    if hero_suited:
        hs = hero_suits[0]

        def suit_cat(card):
            return "H" if Card.get_suit_int(card) == hs else "O"
    else:
        def suit_cat(card):
            s = Card.get_suit_int(card)
            if s == hero_suits[0]:
                return "H1"
            if s == hero_suits[1]:
                return "H2"
            return "O"

    classes = {}
    for c1, c2 in combinations(remaining, 2):
        r1 = Card.get_rank_int(c1)
        r2 = Card.get_rank_int(c2)
        s1 = suit_cat(c1)
        s2 = suit_cat(c2)

        # Sort by (rank, suit_cat) for canonical ordering
        if (r1, s1) > (r2, s2):
            r1, r2 = r2, r1
            s1, s2 = s2, s1
            c1, c2 = c2, c1

        # For two "O" cards, distinguish same vs different actual suit
        if s1 == "O" and s2 == "O":
            same = Card.get_suit_int(c1) == Card.get_suit_int(c2)
            key = (r1, r2, "OO_s" if same else "OO_d")
        else:
            key = (r1, r2, s1, s2)

        if key not in classes:
            classes[key] = [c1, c2, 0]
        classes[key][2] += 1

    return [(entry[:2], entry[2]) for entry in classes.values()]


# ── Stratified simulation ────────────────────────────────────────────────────

def run_stratified_simulation(hands, evaluator, iterations_per_hand):
    """Run stratified simulation: equal board samples per opponent class."""
    max_rank = evaluator.MAX_RANK
    full_deck = evaluator.get_deck()
    total_hands = len(hands)
    results = []

    t0 = time.time()

    for idx, (label, player_hand) in enumerate(hands, 1):
        classes = compute_opponent_classes(player_hand, full_deck)
        n_classes = len(classes)
        boards_per_class = max(1, iterations_per_hand // n_classes)

        weighted_wins = 0.0
        weighted_ties = 0.0
        weighted_ev = 0.0
        total_weight = 0.0
        total_samples = 0

        for opp_rep, multiplicity in classes:
            known = set(player_hand + opp_rep)
            available = [c for c in full_deck if c not in known]

            for _ in range(boards_per_class):
                board = random.sample(available, 5)

                p_rank = evaluator.evaluate(player_hand, board)
                o_rank = evaluator.evaluate(opp_rep, board)

                p_pct = hand_percentile(p_rank, max_rank)
                o_pct = hand_percentile(o_rank, max_rank)
                stake = min(potential_value(p_pct), potential_value(o_pct))

                w = multiplicity
                total_weight += stake * w

                if p_rank < o_rank:
                    weighted_wins += w
                    weighted_ev += stake * w
                elif p_rank == o_rank:
                    weighted_ties += w
                else:
                    weighted_ev -= stake * w

                total_samples += w

        raw_eq = (weighted_wins + weighted_ties * 0.5) / total_samples
        norm_ae = weighted_ev / total_weight if total_weight else 0

        actual_iters = n_classes * boards_per_class
        results.append({
            "hand": label,
            "raw_equity": raw_eq,
            "norm_ae": norm_ae,
            "action_ev": weighted_ev,
            "samples": actual_iters,
            "n_classes": n_classes,
        })

        if idx % 10 == 0 or idx == total_hands:
            elapsed = time.time() - t0
            rate = idx / elapsed
            eta = (total_hands - idx) / rate if rate else 0
            print(f"  [{idx:>3}/{total_hands}]  {label:<5}  "
                  f"({n_classes} classes x {boards_per_class} boards)  "
                  f"elapsed {elapsed:5.1f}s  ETA {eta:5.1f}s", flush=True)

    return results


# ── Output ───────────────────────────────────────────────────────────────────

def print_and_save(results, csv_path, variant_name):
    """Sort, print comparison table, and optionally save CSV."""
    by_raw = sorted(results, key=lambda x: x["raw_equity"], reverse=True)
    by_ae = sorted(results, key=lambda x: x["norm_ae"], reverse=True)
    raw_rank = {r["hand"]: i + 1 for i, r in enumerate(by_raw)}
    ae_rank = {r["hand"]: i + 1 for i, r in enumerate(by_ae)}

    total = len(results)
    print(f"\n  {variant_name} -- {total} distinct hands (stratified sampling)\n")

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

    if csv_path:
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["hand", "samples", "opp_classes", "raw_equity",
                             "raw_rank", "action_equity_norm",
                             "action_equity_rank", "rank_diff"])
            for entry in by_ae:
                h = entry["hand"]
                writer.writerow([h, entry["samples"], entry["n_classes"],
                                 f"{entry['raw_equity']:.4f}", raw_rank[h],
                                 f"{entry['norm_ae']:.4f}", ae_rank[h],
                                 raw_rank[h] - ae_rank[h]])
        print(f"\nResults saved to {csv_path}")

    return by_raw, by_ae


def generate_rankings_txt(by_raw, by_ae, iters, variant_name, txt_path):
    """Write side-by-side rankings to a text file."""
    lines = []
    lines.append(f"Hand Rankings: Raw Equity vs Action Equity ({variant_name})")
    lines.append("=" * 60)
    lines.append(f"Based on ~{iters:,} iterations per hand (stratified sampling)")
    lines.append("")
    lines.append("")
    lines.append("  RAW EQUITY RANKING          ACTION EQUITY RANKING")
    lines.append("  --------------------        ---------------------")
    lines.append(f"{'#':>4}  {'Hand':<5} {'Equity':>7}      "
                 f"{'#':>4}  {'Hand':<5} {'AE Norm':>8}")
    lines.append(f"{'':->4}  {'':->5} {'':->7}      "
                 f"{'':->4}  {'':->5} {'':->8}")

    for i in range(len(by_ae)):
        rh = by_raw[i]
        ah = by_ae[i]
        re = rh["raw_equity"] * 100
        ae = ah["norm_ae"]
        lines.append(f"{i+1:>4}  {rh['hand']:<5} {re:>6.2f}%      "
                     f"{i+1:>4}  {ah['hand']:<5} {ae:>+8.4f}")

    with open(txt_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Rankings saved to {txt_path}")


def main() -> None:
    args = sys.argv[1:]

    short_deck = False
    if "--short-deck" in args:
        short_deck = True
        args.remove("--short-deck")

    iterations = 50_000
    csv_path = None
    txt_path = None

    if len(args) > 0:
        iterations = int(args[0])
    if len(args) > 1:
        base = args[1]
        csv_path = base + ".csv"
        txt_path = base + ".txt"

    if short_deck:
        evaluator = ShortDeckEvaluator()
        variant = "Short Deck (6+)"
        if csv_path is None:
            csv_path = "rankings_short_deck.csv"
        if txt_path is None:
            txt_path = "rankings_short_deck.txt"
    else:
        evaluator = StandardEvaluator()
        variant = "Standard"
        if csv_path is None:
            csv_path = "rankings.csv"
        if txt_path is None:
            txt_path = "rankings.txt"

    hands = canonical_hands(evaluator.RANKS)
    n_hands = len(hands)

    print(f"\nStratified simulation: ~{iterations:,} iterations per hand x "
          f"{n_hands} hands  ({variant})\n")

    t0 = time.time()
    results = run_stratified_simulation(hands, evaluator, iterations)
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    by_raw, by_ae = print_and_save(results, csv_path, variant)
    generate_rankings_txt(by_raw, by_ae, iterations, variant, txt_path)


if __name__ == "__main__":
    main()
