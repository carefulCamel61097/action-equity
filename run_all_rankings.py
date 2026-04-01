"""
Run all rankings overnight (Stratified Sampling)
===================================================
Generates both Standard and Short Deck rankings with 1,000,000 iterations
per hand using stratified opponent sampling for stable results.

Standard:   169 hands x ~1M iterations (367-757 opponent classes each)
Short Deck:  81 hands x ~1M iterations (165-345 opponent classes each)

Output files:
    rankings.txt / rankings.csv                       (Standard)
    rankings_short_deck.txt / rankings_short_deck.csv (Short Deck 6+)

Usage:
    python3 run_all_rankings.py
"""

from rank_all_hands import (
    canonical_hands, run_stratified_simulation,
    print_and_save, generate_rankings_txt,
)
from evaluator import StandardEvaluator, ShortDeckEvaluator
import time

ITERATIONS = 1_000_000


def run_variant(evaluator, variant_name, csv_path, txt_path):
    hands = canonical_hands(evaluator.RANKS)
    n = len(hands)

    print(f"\n{'=' * 60}")
    print(f"  {variant_name}")
    print(f"  ~{ITERATIONS:,} iterations x {n} hands (stratified)")
    print(f"{'=' * 60}\n")

    t0 = time.time()
    results = run_stratified_simulation(hands, evaluator, ITERATIONS)
    elapsed = time.time() - t0

    print(f"\nDone in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    by_raw, by_ae = print_and_save(results, csv_path, variant_name)
    generate_rankings_txt(by_raw, by_ae, ITERATIONS, variant_name, txt_path)


def main():
    t_start = time.time()

    run_variant(
        StandardEvaluator(),
        "Standard",
        "rankings.csv",
        "rankings.txt",
    )

    run_variant(
        ShortDeckEvaluator(),
        "Short Deck (6+)",
        "rankings_short_deck.csv",
        "rankings_short_deck.txt",
    )

    total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  All done in {total:.0f}s ({total/60:.0f} min / {total/3600:.1f} hrs)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
