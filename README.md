# Action Equity

**[Try the interactive tools](https://carefulcamel61097.github.io/action-equity/)** -- look up hand rankings on any board, explore ranges, and simulate hands against opponent ranges.

## The Problem with Raw Equity

Standard poker equity calculations treat all wins equally. Whether you beat pocket aces or 7-2 offsuit, your equity goes up by the same amount. But in real poker, **the size of the pot depends on both players' hand strength**.

When you hold a strong hand and your opponent has trash, they fold early or put very little money in. When two strong hands collide, the pot grows large. A hand that wins many small pots and loses a few big ones may have high raw equity but actually *loses money* at the table.

Raw Equity = Wins / Total Hands. Useful, but it misses this fundamental dynamic.

## Action Equity: A Better Model

Action Equity solves this by weighting each outcome by a realistic pot size. Instead of asking "how often do I win?", it asks **"how much do I win?"**

For any two hands being compared on a given board:

1. **Percentile** -- rank each hand among all possible hands. P = rank / total_hands (lower P = stronger).

2. **Potential Value** -- V = 1/P. A hand at the 10th percentile has V = 10. A median hand has V = 2.

3. **Stake** -- the pot size is min(V_hero, V_opponent). The weaker hand caps the pot, because a rational player won't over-invest with a weak holding.

4. **Outcome** -- hero gains or loses the stake based on who wins.

### Why min(V_hero, V_opponent)?

This models natural poker dynamics:
- **Monster vs trash** (V=20 vs V=1.5): hero only wins 1.5 -- the weak hand won't pay off
- **Monster vs strong** (V=15 vs V=12): large pot (stake=12) -- both players are confident
- **Medium vs medium** (V=3 vs V=2.5): moderate pot -- both have something but neither is committed

## Limitations

**Action Equity does not model bluffing or folding.** Every hand goes to showdown. In real poker:
- Weak hands can win by bluffing better hands off the pot
- Strong hands can lose value when opponents fold to their bets
- Position, bet sizing, and board texture all influence the action

Action Equity measures **showdown value** -- how much a hand makes when it gets to the river. It undervalues bluffing hands and overvalues hands that are hard to play deceptively.

## What Changes in the Rankings?

### Standard Hold'em (52 cards)

| Hand | Raw Equity Rank | Action Equity Rank | Shift | Why |
|------|:-:|:-:|:-:|-----|
| AKo | #12 | #7 | +5 | When it connects, opponents often have second-best hands that pay off |
| 99 | #6 | #11 | -5 | Wins many small pots but rarely wins big unless it flops a set |
| 88 | #7 | #21 | -14 | Same story, even worse -- strong raw equity but small average pot |
| KQo | #23 | #16 | +7 | Good board coverage; makes strong top pairs that get paid |
| A6s | #32 | #29 | +3 | Nut flush potential captures big pots when it hits |

The pattern: **pocket pairs 99-22 drop significantly** because they win many tiny pots (opponents fold or have nothing). **Broadway hands and suited connectors rise** because when they connect, they make strong hands that other strong hands pay off.

### Short Deck (6+ Hold'em, 36 cards)

Short Deck amplifies these effects because the deck is denser -- more players connect with the board.

| Hand | Raw Equity Rank | Action Equity Rank | Shift | Why |
|------|:-:|:-:|:-:|-----|
| TT | #5 | #20 | -15 | The biggest drop: in a denser deck, overpairs get cracked more and underpairs never pay |
| AKo | #8 | #5 | +3 | Even stronger in short deck: high cards dominate the smaller rank space |
| QJs | #15 | #18 | -3 | Less room for straight draws to be unique; more shared outs |
| JTs | #19 | #24 | -5 | Similar effect: connected hands lose some edge in a denser deck |
| KQo | #17 | #11 | +6 | Top pair hands gain -- more opponents connect with the board and pay off |

In short deck, **TT drops 15 spots** -- the most dramatic shift in either format. With only 36 cards, the gap between having an overpair and being dominated is much smaller.

## What We Computed

All board-level computations are **exhaustive** -- no Monte Carlo sampling. We enumerate every possible board and opponent combination.

### Short Deck (6+ Hold'em)

| Data | Total Boards | Canonical | Time (Pi 5) |
|------|-----:|------:|------:|
| All river rankings | 376,992 | 25,746 | 13 min |
| All turn rankings | 58,905 | 4,191 | 234 min |
| All flop rankings | 7,140 | 609 | 539 min |

Every possible short deck board has been ranked. For any flop, turn, or river you can look up the exact Action Equity ranking of all 81 starting hands.

### Standard Hold'em (52 cards)

| Data | Total Boards | Canonical | Status |
|------|-----:|------:|------|
| Preflop ranking | -- | 169 hands | Done (1M iterations, stratified) |
| All river rankings | 2,598,960 | ~134,459 | Ready to run |
| All turn rankings | 270,725 | ~16,432 | Ready to run |
| All flop rankings | 22,100 | ~1,833 | Ready to run |

### Preflop Rankings

Preflop rankings use stratified opponent sampling with 1 million iterations per hand, ensuring every opponent class is equally represented.

## Interactive Tools

The **[interactive tools page](https://carefulcamel61097.github.io/action-equity/)** lets you:

- **Look up rankings** on any board (preflop, flop, turn, or river) for both standard and short deck
- **Explore ranges** by percentile with a visual 9x9 / 13x13 hand grid
- **Simulate your hand** against opponent ranges to calculate Action Equity in real time

## Technical Details

### Isomorphic Board Canonicalization

We canonicalize boards by remapping suits in order of first appearance. As Kh Qd and Ah Ks Qc are strategically identical -- only the suit *pattern* matters. This reduces computation by ~15x.

### Stratified Opponent Sampling (Preflop)

For preflop rankings, opponents are grouped into equivalence classes based on suit relationship to the hero's hand. Each class is sampled equally, weighted by multiplicity. This eliminates the suited/offsuit bias in naive Monte Carlo.

## Running the Simulations

Requires Python 3 and the `treys` library (`pip install treys`).

```bash
# Preflop rankings (both standard and short deck)
python3 run_all_rankings.py

# Short deck board rankings (all stages, ~14 hours on Pi)
python3 run_short_deck_boards.py

# Standard deck board rankings
python3 run_standard_boards.py --stage 1    # rivers (~3 hrs)
python3 run_standard_boards.py --stage 2    # turns (~days)
python3 run_standard_boards.py --stage 3    # flops (~weeks)
```

## Project Structure

```
docs/                       GitHub Pages site
  index.html                Interactive tools
  data/                     JSON data for the site

results/                    Pre-computed ranking data
  rankings.csv              Standard preflop (raw + action equity)
  rankings_short_deck.csv   Short deck preflop
  sd_results_*.csv          Short deck board rankings (aggregated)
  sd_stage*.pkl             Per-board caches (gitignored, regenerable)

evaluator.py                Standard + Short Deck hand evaluators
simulation.py               Single hand equity calculator
rank_all_hands.py           Preflop ranking with stratified sampling
rank_board.py               Single board ranking
run_short_deck_boards.py    All short deck board rankings
run_standard_boards.py      All standard board rankings
```
