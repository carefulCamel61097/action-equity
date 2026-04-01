"""
Action Equity Poker Simulation
================================
Quantifies hand strength by weighting wins according to a realistic pot-size
model rather than raw equity.  Supports standard (52-card) and short deck (6+).

Usage:
    py simulation.py As Kd                  # standard deck
    py simulation.py --short-deck As Kd     # short deck (6+)
    py simulation.py As Kd Qh Jc 2s        # with board cards
"""

import sys
import random
from itertools import combinations
from treys import Card, Deck

from evaluator import StandardEvaluator, ShortDeckEvaluator


# ── Action-weight helpers ────────────────────────────────────────────────────

def hand_percentile(rank: int, max_rank: int) -> float:
    """P in (0, 1].  Lower P = stronger hand."""
    return rank / max_rank


def potential_value(percentile: float) -> float:
    """V = 1 / P -- the action weight."""
    return 1.0 / percentile


# ── Parsing helpers ──────────────────────────────────────────────────────────

def parse_cards(tokens: list[str]) -> list[int]:
    """Convert human-readable card strings (e.g. 'As', 'Kd') to treys ints."""
    cards = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        t = t[0].upper() + t[1].lower()
        cards.append(Card.new(t))
    return cards


def pretty(cards: list[int]) -> str:
    return " ".join(Card.int_to_str(c) for c in cards)


# ── Core simulation ─────────────────────────────────────────────────────────

def run_exact(
    player_hand: list[int],
    evaluator,
    board_cards: list[int],
) -> dict:
    """Exact enumeration when board cards are partially or fully known.

    Enumerates all possible (remaining board cards + opponent hands).
    Use this when board_cards has 3-5 cards for exact results with no noise.
    """
    known = set(player_hand + board_cards)
    cards_needed = 5 - len(board_cards)
    available = [c for c in evaluator.get_deck() if c not in known]
    max_rank = evaluator.MAX_RANK

    raw_wins = 0
    raw_ties = 0
    raw_total = 0
    weighted_ev = 0.0
    total_weight = 0.0

    # Enumerate remaining board cards (0, 1, or 2 cards)
    if cards_needed == 0:
        board_combos = [()]
    else:
        board_combos = list(combinations(available, cards_needed))

    for board_fill in board_combos:
        full_board = board_cards + list(board_fill)
        remaining = [c for c in available if c not in board_fill]

        p_rank = evaluator.evaluate(player_hand, full_board)
        p_pct = hand_percentile(p_rank, max_rank)
        p_val = potential_value(p_pct)

        for opp in combinations(remaining, 2):
            o_rank = evaluator.evaluate(list(opp), full_board)
            o_pct = hand_percentile(o_rank, max_rank)
            o_val = potential_value(o_pct)
            stake = min(p_val, o_val)

            total_weight += stake
            raw_total += 1

            if p_rank < o_rank:
                raw_wins += 1
                weighted_ev += stake
            elif p_rank == o_rank:
                raw_ties += 1
            else:
                weighted_ev -= stake

    raw_equity = (raw_wins + raw_ties * 0.5) / raw_total if raw_total else 0
    normalised_ev = weighted_ev / total_weight if total_weight else 0.0

    return {
        "player_hand": pretty(player_hand),
        "board": pretty(board_cards),
        "iterations": raw_total,
        "exact": True,
        "raw_equity": raw_equity,
        "weighted_ev": weighted_ev,
        "normalised_ev": normalised_ev,
        "wins": raw_wins,
        "ties": raw_ties,
        "losses": raw_total - raw_wins - raw_ties,
    }


def run_simulation(
    player_hand: list[int],
    evaluator,
    board_cards: list[int] | None = None,
    iterations: int = 50_000,
) -> dict:
    """Monte Carlo simulation for preflop or when exact is too expensive."""
    if board_cards is None:
        board_cards = []

    known = set(player_hand + board_cards)
    cards_needed = 5 - len(board_cards)
    available = [c for c in evaluator.get_deck() if c not in known]

    raw_wins = 0
    raw_ties = 0
    weighted_ev = 0.0
    total_weight = 0.0

    max_rank = evaluator.MAX_RANK

    for _ in range(iterations):
        drawn = random.sample(available, cards_needed + 2)
        sim_board = board_cards + drawn[:cards_needed]
        opp_hand = drawn[cards_needed:cards_needed + 2]

        p_rank = evaluator.evaluate(player_hand, sim_board)
        o_rank = evaluator.evaluate(opp_hand, sim_board)

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
        "exact": False,
        "raw_equity": raw_equity,
        "weighted_ev": weighted_ev,
        "normalised_ev": normalised_ev,
        "wins": raw_wins,
        "ties": raw_ties,
        "losses": iterations - raw_wins - raw_ties,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def print_results(r: dict, variant: str) -> None:
    mode = "EXACT" if r.get("exact") else "Monte Carlo"
    print()
    print("=" * 50)
    print(f"  Variant:    {variant}")
    print(f"  Mode:       {mode}")
    print(f"  Hand:       {r['player_hand']}")
    print(f"  Board:      {r['board']}")
    print(f"  Matchups:   {r['iterations']:,}")
    print("-" * 50)
    print(f"  Wins / Ties / Losses:  {r['wins']:,} / {r['ties']:,} / {r['losses']:,}")
    print(f"  Raw Equity:            {r['raw_equity']:.2%}")
    print(f"  Action-Weighted EV:    {r['weighted_ev']:+,.2f}")
    print(f"  Normalised AW Equity:  {r['normalised_ev']:+.4f}")
    print("=" * 50)
    print()


def main() -> None:
    args = sys.argv[1:]

    short_deck = False
    if "--short-deck" in args:
        short_deck = True
        args.remove("--short-deck")

    if not args:
        raw = input("Enter your hand (e.g. As Kd) and optional board cards: ")
        args = raw.split()

    if len(args) < 2:
        print("Please provide at least 2 cards for your hand.")
        sys.exit(1)

    cards = parse_cards(args)
    player_hand = cards[:2]
    board_cards = cards[2:]

    if len(board_cards) > 5:
        print("Board can have at most 5 cards.")
        sys.exit(1)

    if short_deck:
        evaluator = ShortDeckEvaluator()
        variant = "Short Deck (6+)"
    else:
        evaluator = StandardEvaluator()
        variant = "Standard"

    if board_cards:
        print(f"\nExact enumeration: {pretty(player_hand)} on {pretty(board_cards)} ({variant}) ...")
        results = run_exact(player_hand, evaluator, board_cards)
    else:
        print(f"\nSimulating {pretty(player_hand)} vs random opponent ({variant}) ...")
        results = run_simulation(player_hand, evaluator, board_cards)
    print_results(results, variant)


if __name__ == "__main__":
    main()
