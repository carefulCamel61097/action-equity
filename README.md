# Action Equity - A Better Way to Rank Poker Hands

Traditional poker equity calculations treat all wins equally: beating pocket aces counts the same as beating 7-2 offsuit. But in real poker, **the amount you win depends on the strength of your opponent's hand**. A strong opponent will put more money in the pot before showdown, while a weak opponent will fold early or contribute very little.

**Action Equity** solves this by weighting each outcome by a realistic pot size model. The result is a ranking system that better reflects how much money hands actually make at the table.

## The Idea

In a standard equity simulation, every win adds the same to your score:

> Raw Equity = Wins / Total Hands

This is useful but limited. Consider: **AKo** wins against random hands more often than **JTs**, but when JTs hits a straight or flush, it tends to win a *large pot* against strong hands that also connected with the board. AKo often wins *small pots* because opponents fold weak hands.

Action Equity captures this by asking: **when you win, how much do you win?**

## The Formula

For any two hands being compared on a given board:

1. **Percentile** -- rank each hand among all possible hands on this board. P = rank / total_hands (lower P = stronger hand).

2. **Potential Value** -- V = 1/P. A hand at the 10th percentile has V = 10, meaning it's worth 10x the baseline. A median hand has V = 2.

3. **Stake** -- the amount at risk is min(V_hero, V_opponent). The weaker hand determines the pot size, because a rational player won't put more money in than their hand is worth.

4. **Outcome** -- if hero wins, they gain the stake. If hero loses, they lose the stake.

The final Action Equity is the weighted sum of all outcomes divided by total weight. Positive = profitable, negative = unprofitable.

### Why min(V_hero, V_opponent)?

This models the natural dynamics of poker betting:
- When you have a monster hand (V = 20) vs a weak hand (V = 1.5), you only win 1.5 -- the weak hand won't pay you off
- When two strong hands collide (V = 15 vs V = 12), the pot is large (stake = 12) -- both players are confident and betting
- This is essentially modeling the [principle of fast play](https://en.wikipedia.org/wiki/Fast_play_(poker)) vs slow play dynamics

## What Changes in the Rankings?

Compared to raw equity rankings, Action Equity produces some notable shifts:

| Effect | Why |
|--------|-----|
| **Suited connectors rise** (JTs, QJs, T9s) | When they hit flushes/straights, they win big pots against other strong hands |
| **Low pocket pairs drop** (22-66) | They win many small pots but rarely win large ones unless they hit a set |
| **Offsuit big cards drop** (AKo, AQo) | They win often but against weak opposition; strong opponents frequently have them dominated |
| **Suited aces hold steady** | Nut flush potential means they win the biggest pots when they connect |

## Limitations

**Action Equity does not model bluffing or folding.** Every hand goes to showdown. In real poker:
- Weak hands can win by bluffing strong hands off the pot
- Strong hands can lose value when opponents fold to their bets
- Position, bet sizing, and board texture all affect whether hands see a showdown

This means Action Equity is most accurate for evaluating **showdown value** -- how much a hand makes when it gets to the river. It undervalues hands with good bluffing potential and overvalues hands that are hard to play deceptively.

## What We Computed

All computations are **exhaustive** -- no Monte Carlo sampling. We enumerate every possible board and opponent combination.

### Short Deck (6+ Hold'em)

Short Deck uses a 36-card deck (6 through A), where flushes beat full houses and A-6-7-8-9 is the low straight.

| Data | Boards | Canonical | Time (Pi 5) |
|------|--------|-----------|-------------|
| **All river rankings** | 376,992 | 25,746 | 13 min |
| **All turn rankings** | 58,905 | 4,191 | 234 min |
| **All flop rankings** | 7,140 | 609 | 539 min |

Every possible short deck board has been ranked. For any flop, turn, or river you can look up the exact Action Equity ranking of all 81 starting hands.

### Standard Hold'em (52 cards)

| Data | Boards | Canonical | Status |
|------|--------|-----------|--------|
| **Preflop ranking** | n/a | 169 hands | Done (1M iterations, stratified sampling) |
| **All river rankings** | 2,598,960 | ~134,459 | Ready to run |
| **All turn rankings** | 270,725 | ~16,432 | Ready to run |
| **All flop rankings** | 22,100 | ~1,833 | Ready to run |

### Preflop Rankings

Preflop rankings use stratified opponent sampling with 1 million iterations per hand, ensuring every opponent class is equally represented.

## Tools

The [interactive tools page](https://carefulCamel61097.github.io/action-equity/) lets you:

- **Look up rankings** on any short deck board (preflop, turn, or river)
- **Explore ranges** by percentile with a visual hand grid
- **Compare your hand** against opponent ranges to see win rates

## Technical Details

### Isomorphic Board Canonicalization

To avoid redundant computation, we canonicalize boards by remapping suits in order of first appearance. For example, As Kh Qd and Ah Ks Qc are strategically identical -- only the suit *pattern* matters (three different suits), not which specific suits. This reduces the number of boards to compute by ~15x.

### Stratified Opponent Sampling (Preflop)

For preflop rankings, opponents are grouped into equivalence classes based on their suit relationship to the hero's hand. Each class is sampled equally, weighted by its multiplicity. This eliminates the suited/offsuit sampling bias that plagues naive Monte Carlo approaches.

## Running the Simulations

Requires Python 3 and the `treys` library (`pip install treys`).

```bash
# Preflop rankings (both standard and short deck, ~overnight on Pi)
python3 run_all_rankings.py

# Short deck board rankings (all stages, ~14 hours on Pi)
python3 run_short_deck_boards.py

# Standard deck board rankings (rivers ~3hrs, turns ~days, flops ~weeks)
python3 run_standard_boards.py --stage 1    # rivers only
python3 run_standard_boards.py               # all stages
```

## Project Structure

```
results/                    # Pre-computed ranking data
  rankings.csv              # Standard preflop (raw + action equity)
  rankings_short_deck.csv   # Short deck preflop
  sd_results_rivers.csv     # Short deck river rankings (aggregated)
  sd_results_turns.csv      # Short deck turn rankings (aggregated)
  sd_results_flops.csv      # Short deck flop rankings (aggregated)
  sd_stage1_rivers.pkl      # Per-board river cache (for lookups)
  sd_stage2_turns.pkl       # Per-board turn cache

docs/                       # GitHub Pages site
  index.html                # Interactive tools
  data/                     # JSON data for the site

evaluator.py                # Standard + Short Deck hand evaluators
simulation.py               # Single hand equity calculator
rank_all_hands.py           # Preflop ranking with stratified sampling
rank_board.py               # Single board ranking
run_short_deck_boards.py    # All short deck board rankings
run_standard_boards.py      # All standard board rankings
run_all_rankings.py         # Preflop ranking batch script
```
