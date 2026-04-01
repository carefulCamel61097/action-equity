"""
Street-by-Street Action Equity Simulation
============================================
Models pot growth and early folding across streets (flop, turn, river).

Key idea: at each street, if the percentile gap between the two hands is
large enough, the weaker hand folds -- ending the hand early with a small
pot.  Pots grow each street by a factor determined by the bet size.

Parameters:
    --bet-flop   Bet size as fraction of pot on flop  (default: 0.33)
    --bet-turn   Bet size as fraction of pot on turn  (default: 0.66)
    --bet-river  Bet size as fraction of pot on river (default: 0.75)
    --fold-gap   Percentile gap threshold for folding (default: 0.50)
                 If abs(P_hero - P_opp) > fold_gap, weaker hand folds.

Pot growth: if bet size is B (fraction of pot), the pot grows by
factor (1 + 2*B) each street when both players continue.
  - B=0.33 -> x1.66
  - B=0.66 -> x2.32
  - B=0.75 -> x2.50

Usage:
    py simulation_streets.py As Kd
    py simulation_streets.py --short-deck As Kd
    py simulation_streets.py As Kd --bet-flop 0.25 --fold-gap 0.40
"""

import sys
import random

from treys import Card
from evaluator import StandardEvaluator, ShortDeckEvaluator
from simulation import parse_cards, pretty, hand_percentile, potential_value


def run_street_simulation(
    player_hand: list[int],
    evaluator,
    board_cards: list[int] | None = None,
    iterations: int = 50_000,
    bet_flop: float = 0.33,
    bet_turn: float = 0.66,
    bet_river: float = 0.75,
    fold_gap: float = 0.50,
) -> dict:
    """Street-by-street simulation with pot scaling and early folding.

    At each street:
      1. Evaluate both hands on the current board
      2. If percentile gap > fold_gap, weaker hand folds (hand ends)
      3. Otherwise, pot grows by (1 + 2*bet_size) and we continue

    The EV won/lost is stake * pot_multiplier, where:
      - stake = min(V_hero, V_opp) as before
      - pot_multiplier reflects how many streets were played
    """
    if board_cards is None:
        board_cards = []

    known = set(player_hand + board_cards)
    cards_needed = 5 - len(board_cards)
    available = [c for c in evaluator.get_deck() if c not in known]
    max_rank = evaluator.MAX_RANK

    # Street config: (n_board_cards_at_street, bet_size)
    # Only include streets that haven't been dealt yet
    streets = []
    if len(board_cards) <= 2:
        streets.append(("flop", 3, bet_flop))
    if len(board_cards) <= 3:
        streets.append(("turn", 4, bet_turn))
    if len(board_cards) <= 4:
        streets.append(("river", 5, bet_river))

    raw_wins = 0
    raw_ties = 0
    weighted_ev = 0.0
    total_weight = 0.0
    fold_counts = {"flop": 0, "turn": 0, "river": 0, "showdown": 0}

    for _ in range(iterations):
        drawn = random.sample(available, cards_needed + 2)
        full_board = board_cards + drawn[:cards_needed]
        opp_hand = drawn[cards_needed:cards_needed + 2]

        pot_mult = 1.0
        folded = False

        for street_name, n_cards, bet_size in streets:
            current_board = full_board[:n_cards]

            p_rank = evaluator.evaluate(player_hand, current_board)
            o_rank = evaluator.evaluate(opp_hand, current_board)

            p_pct = hand_percentile(p_rank, max_rank)
            o_pct = hand_percentile(o_rank, max_rank)

            gap = abs(p_pct - o_pct)

            if gap > fold_gap:
                # Weaker hand folds -- hand ends here
                p_val = potential_value(p_pct)
                o_val = potential_value(o_pct)
                stake = min(p_val, o_val) * pot_mult

                total_weight += stake
                fold_counts[street_name] += 1

                if p_rank < o_rank:  # hero wins
                    raw_wins += 1
                    weighted_ev += stake
                else:                # hero loses (opponent had better hand but hero folds)
                    weighted_ev -= stake

                folded = True
                break

            # Both continue -- pot grows
            pot_mult *= (1 + 2 * bet_size)

        if not folded:
            # Showdown on river
            p_rank = evaluator.evaluate(player_hand, full_board)
            o_rank = evaluator.evaluate(opp_hand, full_board)

            p_pct = hand_percentile(p_rank, max_rank)
            o_pct = hand_percentile(o_rank, max_rank)
            p_val = potential_value(p_pct)
            o_val = potential_value(o_pct)
            stake = min(p_val, o_val) * pot_mult

            total_weight += stake
            fold_counts["showdown"] += 1

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
        "fold_counts": fold_counts,
        "bet_sizes": {"flop": bet_flop, "turn": bet_turn, "river": bet_river},
        "fold_gap": fold_gap,
    }


def print_results(r: dict, variant: str) -> None:
    fc = r["fold_counts"]
    bs = r["bet_sizes"]
    total = r["iterations"]

    print()
    print("=" * 55)
    print(f"  Variant:    {variant}")
    print(f"  Hand:       {r['player_hand']}")
    print(f"  Board:      {r['board']}")
    print(f"  Iterations: {r['iterations']:,}")
    print(f"  Bet sizes:  flop={bs['flop']:.0%}  turn={bs['turn']:.0%}  river={bs['river']:.0%}")
    print(f"  Fold gap:   {r['fold_gap']:.0%}")
    print("-" * 55)
    print(f"  Wins / Ties / Losses:  {r['wins']:,} / {r['ties']:,} / {r['losses']:,}")
    print(f"  Raw Equity:            {r['raw_equity']:.2%}")
    print(f"  Street-Weighted EV:    {r['weighted_ev']:+,.2f}")
    print(f"  Normalised SW Equity:  {r['normalised_ev']:+.4f}")
    print("-" * 55)
    print(f"  Hand endings:")
    print(f"    Fold on flop:    {fc['flop']:>7,}  ({fc['flop']/total:>6.1%})")
    print(f"    Fold on turn:    {fc['turn']:>7,}  ({fc['turn']/total:>6.1%})")
    print(f"    Fold on river:   {fc['river']:>7,}  ({fc['river']/total:>6.1%})")
    print(f"    Showdown:        {fc['showdown']:>7,}  ({fc['showdown']/total:>6.1%})")
    print("=" * 55)
    print()


def main() -> None:
    args = sys.argv[1:]

    short_deck = False
    if "--short-deck" in args:
        short_deck = True
        args.remove("--short-deck")

    # Parse optional parameters
    bet_flop = 0.33
    bet_turn = 0.66
    bet_river = 0.75
    fold_gap = 0.50

    param_flags = {
        "--bet-flop": "bet_flop",
        "--bet-turn": "bet_turn",
        "--bet-river": "bet_river",
        "--fold-gap": "fold_gap",
    }
    clean_args = []
    i = 0
    while i < len(args):
        if args[i] in param_flags:
            locals()[param_flags[args[i]]] = float(args[i + 1])
            if args[i] == "--bet-flop":
                bet_flop = float(args[i + 1])
            elif args[i] == "--bet-turn":
                bet_turn = float(args[i + 1])
            elif args[i] == "--bet-river":
                bet_river = float(args[i + 1])
            elif args[i] == "--fold-gap":
                fold_gap = float(args[i + 1])
            i += 2
        else:
            clean_args.append(args[i])
            i += 1

    if not clean_args:
        raw = input("Enter your hand (e.g. As Kd) and optional board cards: ")
        clean_args = raw.split()

    if len(clean_args) < 2:
        print("Please provide at least 2 cards for your hand.")
        sys.exit(1)

    cards = parse_cards(clean_args)
    player_hand = cards[:2]
    board_cards = cards[2:]

    if short_deck:
        evaluator = ShortDeckEvaluator()
        variant = "Short Deck (6+)"
    else:
        evaluator = StandardEvaluator()
        variant = "Standard"

    print(f"\nStreet simulation: {pretty(player_hand)} ({variant}) ...")
    results = run_street_simulation(
        player_hand, evaluator, board_cards,
        bet_flop=bet_flop, bet_turn=bet_turn, bet_river=bet_river,
        fold_gap=fold_gap,
    )
    print_results(results, variant)


if __name__ == "__main__":
    main()
