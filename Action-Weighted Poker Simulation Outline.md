# Action-Weighted Poker Simulation — Original Outline

This document is the original project outline that motivated the Action Equity system.

## Objective

To quantify hand strength in Poker by weighting wins according to a "Realistic Pot Size" model.

## The Problem

Standard simulations calculate Raw Equity: Wins / Total Iterations. This is flawed because it assumes you win the same amount of money whether your opponent has a strong-but-second-best hand or total "trash."

## The "Action-Weighted" Logic

This simulation introduces a "Potential Value" (V) derived from the hand's percentile rank (P):

**The Percentile:** P = Hands Stronger Than Mine / Total Possible Hands.

**The Weight:** V = 1/P.

**The Result:** For every matchup, the EV added or subtracted is min(V_Player, V_Opponent).

This effectively models the "implied action" of a hand. A win against a weak hand (P near 1) contributes very little to the final score, while a win against a strong hand (P near 0.1) contributes significantly.

## What Was Built

Starting from this outline, the following was implemented:

1. **Evaluators** for standard (52-card) and short deck (36-card, 6+) poker
2. **Preflop rankings** for both variants using stratified opponent sampling (1M iterations per hand)
3. **Exhaustive board rankings** for all short deck boards: rivers (25,746 canonical), turns (4,191), and flops (609)
4. **Standard deck board rankings** in progress: rivers, turns, and flops
5. **Suit frequency group canonicalization** to collapse equivalent suit combinations while preserving strategic differences
6. **Interactive web tools** for looking up rankings on any board and simulating hands against opponent ranges

## The Missing Piece: The "Bluffing" Gap

While this solves the Pot Size Problem, it does not account for Fold Equity or Bluffing.

**The Issue:** In the simulation, hands always go to the "showdown."

**The Reality:** A weak hand with a "strong story" (aggressive betting) can force a better hand to fold before the river. Conversely, a weak hand that would normally fold in real play gets a free ride to showdown in our simulation.

**Planned Extension:** A fold model based on percentile gap thresholds at each street. If the difference in percentile between hero and opponent exceeds a threshold, the weaker hand folds and the stronger hand wins the current pot. The pot grows at each street based on configurable bet sizing (e.g. 33% pot on flop, 66% on turn, 75% on river). An early version of this exists in `simulation_streets.py`.
