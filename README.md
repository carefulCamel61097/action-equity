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

### Example: JTs vs small pocket pairs in Short Deck

A surprising result: in our VS Range simulation, **JTs actually loses money against small pocket pairs** like 66 and 77. This seems wrong -- JTs is one of the most popular hands in Short Deck, and small pairs are considered weak. What's going on?

The issue is the free showdown. In our simulation, 66 gets to see all five board cards without paying anything. On most boards, 66 ends up with just a low pair -- bottom percentile, tiny pot, and JTs wins almost nothing. But on the ~12% of boards where 66 hits a set or better, it's suddenly a monster hand with a huge potential value, and JTs pays dearly.

The math works out: 66 loses many micro-pots (stake near 1) but wins a few massive pots (stake near 10+). The weighted sum favors 66.

In real poker, this doesn't happen. To see the flop, 66 has to call a raise. On the ~88% of flops where 66 misses, it faces a bet and folds. It never gets to realize those micro-wins. The cost of calling pre-flop and folding post-flop far outweighs the occasional set-mining payoff at these stack depths.

This is the clearest example of Action Equity's limitation: **hands that are weak most of the time but occasionally very strong are overvalued**, because our model doesn't charge them for the many streets of betting they'd need to survive to reach showdown.

### Future work: fold model

A natural extension would simulate folding at each street. If the percentile gap between hero and opponent exceeds a threshold, the weaker hand folds and the stronger hand wins the current pot. The pot grows at each street based on bet sizing (e.g. 33% pot on flop, 66% on turn, 75% on river). This would penalize hands like small pocket pairs that need to survive multiple streets to realize their equity.

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
| All river rankings | 2,598,960 | ~134,459 | In progress |
| All turn rankings | 270,725 | ~16,432 | In progress |
| All flop rankings | 22,100 | ~1,833 | In progress |

### Preflop Rankings

Preflop rankings use stratified opponent sampling with 1 million iterations per hand, ensuring every opponent class is equally represented.

## Interactive Tools

The **[interactive tools page](https://carefulcamel61097.github.io/action-equity/)** lets you:

- **Look up rankings** on any short deck board (preflop, flop, turn, or river)
- **View all suit combinations** separately -- see how Jc Tc (flush draw) differs from Js Ts (off-board suits) on the same board
- **Explore ranges** by percentile with a visual 9x9 hand grid
- **Simulate your hand** against opponent ranges to calculate Action Equity, with exhaustive mode for boards with 3+ cards

## Technical Details

### Suit Frequency Group Canonicalization

Boards are canonicalized by grouping suits by their frequency on the board. Suits that appear the same number of times are interchangeable -- for example, on a board with two clubs and no spades or hearts, Js Ts and Jh Th are strategically identical (both off-board suited), but Jc Tc is different (flush draw). This reduces the number of unique hand combinations per board by ~42% compared to naive canonicalization, while preserving all strategically meaningful distinctions.

### Chunked Data Storage

Board ranking data is split into chunks by the two lowest card ranks on the board (e.g., all boards with 6 and 7 as the two lowest ranks go into `sd_rivers_67.json`). This keeps individual files small (max ~4 MB compressed) while allowing the web app to load only the data it needs.

### Stratified Opponent Sampling (Preflop)

For preflop rankings, opponents are grouped into equivalence classes based on suit relationship to the hero's hand. Each class is sampled equally, weighted by multiplicity. This eliminates the suited/offsuit bias in naive Monte Carlo.

## Running the Simulations

Requires Python 3 and the `treys` library (`pip install treys`).

```bash
# Preflop rankings (both standard and short deck, ~overnight on Pi)
python3 run_all_rankings.py

# Short deck board rankings (all stages, ~14 hours on Pi)
python3 run_short_deck_boards.py

# Standard deck board rankings (memory-efficient, no inter-stage dependencies)
python3 run_standard_boards.py --stage 1    # rivers (~3 hrs)
python3 run_standard_boards.py --stage 2    # turns (~days)
python3 run_standard_boards.py --stage 3    # flops (~weeks)
```

## Project Structure

```
docs/                       GitHub Pages site
  index.html                Interactive tools
  data/                     Chunked JSON data for the site
    sd_rivers_*.json        Short deck river rankings (36 chunks)
    sd_turns_*.json         Short deck turn rankings (45 chunks)
    sd_flops_*.json         Short deck flop rankings (45 chunks)
    sd_preflop.json         Short deck preflop ranking
    std_preflop.json        Standard preflop ranking

results/                    Pre-computed ranking data
  rankings.csv              Standard preflop (raw + action equity)
  rankings_short_deck.csv   Short deck preflop
  sd_results_*.csv          Short deck board rankings (aggregated)
  *.pkl                     Per-board caches (gitignored, regenerable)

archive/                    Unused/experimental results

evaluator.py                Standard + Short Deck hand evaluators
simulation.py               Single hand equity calculator
simulation_streets.py       Street-by-street pot model simulation
simulation_vs_range.py      Hand vs opponent range simulation
rank_all_hands.py           Preflop ranking with stratified sampling
rank_board.py               Single board ranking
run_short_deck_boards.py    All short deck board rankings (4 stages)
run_standard_boards.py      All standard board rankings (3 stages, memory-efficient)
run_all_rankings.py         Preflop ranking batch script
convert_to_json.py          Pickle to chunked JSON converter
```
