# 3. Project Outline: Action-Weighted Poker Simulation

**Objective:** To quantify hand strength in Poker by weighting wins according to a "Realistic Pot Size" model.

## Introduction

Standard simulations calculate Raw Equity: $\frac{Wins}{Total Iterations}$. This is flawed because it assumes you win the same amount of money whether your opponent has a strong-but-second-best hand or total "trash."

## The "Action-Weighted" Logic

This simulation introduces a "Potential Value" ($V$) derived from the hand's percentile rank ($P$):

**The Percentile:** $P = \frac{\text{Hands Stronger Than Mine}}{\text{Total Possible Hands}}$.

**The Weight:** $V = 1/P$.

**The Result:** For every iteration, the EV added or subtracted is $\min(V_{Player}, V_{Opponent})$.

This effectively models the "implied action" of a hand. A win against a weak hand ($P \approx 1$) contributes very little to the final score, while a win against a strong hand ($P \approx 0.1$) contributes significantly.

## The Missing Piece: The "Bluffing" Gap

While this solves the Pot Size Problem, it does not account for Fold Equity or Bluffing.

**The Issue:** In your simulation, hands always go to the "showdown."

**The Reality:** A weak hand with a "strong story" (aggressive betting) can force a better hand to fold before the river.

**Future Addition:** To "fix" this, the next version of this tool could incorporate a "Fold Probability" based on the texture of the board (e.g., if a 3-flush appears on the turn, how likely is the opponent to fold their pair?).
