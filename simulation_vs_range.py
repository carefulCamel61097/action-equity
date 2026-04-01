"""
Action Equity -- Simulate vs a percentile range of opponents
===============================================================
Instead of random opponents, filter opponents to a specific percentile
range based on the preflop Action Equity ranking.

The 0th-10th percentile = the top 10% of hands.
Convention: lower percentile = stronger hand (matches the P formula).

Usage:
    py simulation_vs_range.py As Kd 0 10             # vs top 10%
    py simulation_vs_range.py As Kd 0 50             # vs top 50%
    py simulation_vs_range.py As Kd 50 100            # vs bottom 50%
    py simulation_vs_range.py --short-deck As Kd 0 20 # short deck vs top 20%
    py simulation_vs_range.py As Kd 0 10 --ranking rankings.csv  # custom ranking
"""

import sys
import csv
import random

from treys import Card
from evaluator import StandardEvaluator, ShortDeckEvaluator
from simulation import parse_cards, pretty, hand_percentile, potential_value


SUITS = "shdc"


def load_ranking(csv_path: str) -> list[dict]:
    """Load ranking CSV and return sorted by action equity (best first)."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    return sorted(rows, key=lambda r: float(r["action_equity_norm"]), reverse=True)


def expand_hand_label(label: str) -> list[list[int]]:
    """Expand a canonical hand label (e.g. AKs, AKo, AA) to all concrete combos."""
    if len(label) == 2:
        # Pair: e.g. AA
        r = label[0]
        combos = []
        for i, s1 in enumerate(SUITS):
            for s2 in SUITS[i + 1:]:
                combos.append([Card.new(f"{r}{s1}"), Card.new(f"{r}{s2}")])
        return combos
    elif label.endswith("s"):
        # Suited: e.g. AKs
        r1, r2 = label[0], label[1]
        combos = []
        for s in SUITS:
            combos.append([Card.new(f"{r1}{s}"), Card.new(f"{r2}{s}")])
        return combos
    else:
        # Offsuit: e.g. AKo
        r1, r2 = label[0], label[1]
        combos = []
        for s1 in SUITS:
            for s2 in SUITS:
                if s1 != s2:
                    combos.append([Card.new(f"{r1}{s1}"), Card.new(f"{r2}{s2}")])
        return combos


def get_range_hands(ranking: list[dict], pct_low: float, pct_high: float) -> list[list[int]]:
    """Get all concrete hand combos within a percentile range.

    pct_low=0, pct_high=10 means the top 10% of hands.
    """
    n = len(ranking)
    idx_start = int(pct_low / 100 * n)
    idx_end = int(pct_high / 100 * n)

    hands_in_range = []
    labels_in_range = []
    for i in range(idx_start, min(idx_end, n)):
        label = ranking[i]["hand"]
        labels_in_range.append(label)
        hands_in_range.extend(expand_hand_label(label))

    return hands_in_range, labels_in_range


def run_vs_range(
    player_hand: list[int],
    evaluator,
    range_hands: list[list[int]],
    board_cards: list[int] | None = None,
    iterations: int = 50_000,
) -> dict:
    """Simulate player hand vs opponents drawn from a specific range."""
    if board_cards is None:
        board_cards = []

    known_hero = set(player_hand + board_cards)
    cards_needed = 5 - len(board_cards)
    full_deck = evaluator.get_deck()
    max_rank = evaluator.MAX_RANK

    # Filter range hands that don't overlap with hero
    valid_opps = [h for h in range_hands
                  if h[0] not in known_hero and h[1] not in known_hero]

    if not valid_opps:
        print("No valid opponent hands in range (all overlap with hero).")
        return None

    raw_wins = 0
    raw_ties = 0
    weighted_ev = 0.0
    total_weight = 0.0

    for _ in range(iterations):
        opp = random.choice(valid_opps)
        known = known_hero | set(opp)
        available = [c for c in full_deck if c not in known]

        board_fill = random.sample(available, cards_needed)
        sim_board = board_cards + board_fill

        p_rank = evaluator.evaluate(player_hand, sim_board)
        o_rank = evaluator.evaluate(list(opp), sim_board)

        p_pct = hand_percentile(p_rank, max_rank)
        o_pct = hand_percentile(o_rank, max_rank)
        stake = min(potential_value(p_pct), potential_value(o_pct))

        total_weight += stake

        if p_rank < o_rank:
            raw_wins += 1
            weighted_ev += stake
        elif p_rank == o_rank:
            raw_ties += 1
        else:
            weighted_ev -= stake

    raw_equity = (raw_wins + raw_ties * 0.5) / iterations
    normalised_ev = weighted_ev / total_weight if total_weight else 0.0

    return {
        "player_hand": pretty(player_hand),
        "board": pretty(board_cards) if board_cards else "(none)",
        "iterations": iterations,
        "raw_equity": raw_equity,
        "weighted_ev": weighted_ev,
        "normalised_ev": normalised_ev,
        "wins": raw_wins,
        "ties": raw_ties,
        "losses": iterations - raw_wins - raw_ties,
        "n_valid_opps": len(valid_opps),
    }


def print_results(r: dict, variant: str, pct_low: float, pct_high: float,
                   labels: list[str]) -> None:
    print()
    print("=" * 55)
    print(f"  Variant:    {variant}")
    print(f"  Hand:       {r['player_hand']}")
    print(f"  Board:      {r['board']}")
    print(f"  Vs range:   {pct_low:.0f}th - {pct_high:.0f}th percentile")
    print(f"  Range hands: {', '.join(labels[:10])}"
          + (f" ... +{len(labels)-10} more" if len(labels) > 10 else ""))
    print(f"  Valid opps:  {r['n_valid_opps']} combos")
    print(f"  Iterations:  {r['iterations']:,}")
    print("-" * 55)
    print(f"  Wins / Ties / Losses:  {r['wins']:,} / {r['ties']:,} / {r['losses']:,}")
    print(f"  Raw Equity:            {r['raw_equity']:.2%}")
    print(f"  Action-Weighted EV:    {r['weighted_ev']:+,.2f}")
    print(f"  Normalised AW Equity:  {r['normalised_ev']:+.4f}")
    print("=" * 55)
    print()


def main() -> None:
    args = sys.argv[1:]

    short_deck = False
    if "--short-deck" in args:
        short_deck = True
        args.remove("--short-deck")

    ranking_path = None
    if "--ranking" in args:
        idx = args.index("--ranking")
        ranking_path = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if len(args) < 4:
        print("Usage: py simulation_vs_range.py [--short-deck] <card1> <card2> <pct_low> <pct_high>")
        print("  e.g. py simulation_vs_range.py As Kd 0 10")
        sys.exit(1)

    pct_low = float(args[-2])
    pct_high = float(args[-1])
    card_args = args[:-2]

    cards = parse_cards(card_args)
    player_hand = cards[:2]
    board_cards = cards[2:]

    if short_deck:
        evaluator = ShortDeckEvaluator()
        variant = "Short Deck (6+)"
        if ranking_path is None:
            ranking_path = "rankings_short_deck.csv"
    else:
        evaluator = StandardEvaluator()
        variant = "Standard"
        if ranking_path is None:
            ranking_path = "rankings.csv"

    print(f"\nLoading ranking from {ranking_path} ...")
    ranking = load_ranking(ranking_path)
    range_hands, labels = get_range_hands(ranking, pct_low, pct_high)

    print(f"Range: {pct_low:.0f}th-{pct_high:.0f}th percentile = "
          f"{len(labels)} hand types, {len(range_hands)} combos")

    results = run_vs_range(player_hand, evaluator, range_hands, board_cards)
    if results:
        print_results(results, variant, pct_low, pct_high, labels)


if __name__ == "__main__":
    main()
