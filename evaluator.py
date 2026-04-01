"""
Poker Hand Evaluators
=====================
Common interface for standard (52-card) and short deck (36-card, 6+) evaluation.

Both evaluators expose:
    evaluate(hand, board) -> int    (lower = better)
    get_deck()            -> list   (treys card ints)
    MAX_RANK              -> int    (worst possible rank)
    RANKS                 -> str    (rank characters, high to low)
"""

from itertools import combinations
from treys import Card, Evaluator as TreysEvaluator, Deck


class StandardEvaluator:
    """Standard 52-card poker hand evaluator (wraps treys)."""

    RANKS = "AKQJT98765432"
    MAX_RANK = 7462

    def __init__(self):
        self._eval = TreysEvaluator()

    def evaluate(self, hand, board):
        return self._eval.evaluate(list(hand), list(board))

    def get_deck(self):
        return Deck.GetFullDeck()


class ShortDeckEvaluator:
    """Short deck (6+) poker hand evaluator.

    Differences from standard:
      - 36-card deck (6 through A)
      - Flush beats Full House
      - A-6-7-8-9 is the low straight (wheel)
    """

    RANKS = "AKQJT9876"

    def __init__(self):
        self._eval = TreysEvaluator()
        print("  Initialising short deck evaluator ...", end=" ", flush=True)
        worst = 0
        for combo in combinations(self.get_deck(), 5):
            rank = self._evaluate5(list(combo))
            if rank > worst:
                worst = rank
        self.MAX_RANK = worst
        print(f"done  (MAX_RANK = {worst})")

    def get_deck(self):
        deck = []
        for rank in "6789TJQKA":
            for suit in "shdc":
                deck.append(Card.new(f"{rank}{suit}"))
        return deck

    # ── Internal helpers ─────────────────────────────────────────────────

    def _remap_rank(self, treys_rank):
        """Swap flush and full house categories in the rank space."""
        rc = self._eval.get_rank_class(treys_rank)
        if rc == 3:          # Full House (167-322) -> after Flush
            return treys_rank + 1277
        elif rc == 4:        # Flush (323-1599) -> before Full House
            return treys_rank - 156
        return treys_rank

    def _evaluate5(self, five_cards):
        """Evaluate a single 5-card hand under short deck rules."""
        rank_ints = [Card.get_rank_int(c) for c in five_cards]

        # A-6-7-8-9 wheel (treys rank ints: A=12, 9=7, 8=6, 7=5, 6=4)
        if set(rank_ints) == {12, 4, 5, 6, 7}:
            suit_ints = [Card.get_suit_int(c) for c in five_cards]
            if len(set(suit_ints)) == 1:
                return 10    # worst straight flush
            return 1609      # worst straight

        std_rank = self._eval.evaluate(five_cards, [])
        return self._remap_rank(std_rank)

    # ── Public interface ─────────────────────────────────────────────────

    def evaluate(self, hand, board):
        """Evaluate best 5-card hand from hand (2) + board (3-5)."""
        all_cards = list(hand) + list(board)
        n = len(all_cards)

        if n == 5:
            return self._evaluate5(all_cards)

        # --- Hybrid approach for 6-7 cards ---

        # 1) Standard treys eval + remap
        std_rank = self._eval.evaluate(list(hand), list(board))
        best = self._remap_rank(std_rank)

        # 2) Check for A-6-7-8-9 wheel straight / straight flush
        rank_ints = [Card.get_rank_int(c) for c in all_cards]
        if all(r in rank_ints for r in (12, 4, 5, 6, 7)):
            suit_groups = {}
            for c in all_cards:
                s = Card.get_suit_int(c)
                suit_groups.setdefault(s, set()).add(Card.get_rank_int(c))

            wheel = 1609     # straight
            for s, ranks in suit_groups.items():
                if {12, 4, 5, 6, 7}.issubset(ranks):
                    wheel = 10   # straight flush
                    break
            best = min(best, wheel)

        # 3) If treys picked full house, check if a flush is available
        #    (flush beats full house in short deck)
        std_class = self._eval.get_rank_class(std_rank)
        if std_class == 3:   # Full House
            suit_counts = {}
            for c in all_cards:
                s = Card.get_suit_int(c)
                suit_counts[s] = suit_counts.get(s, 0) + 1

            for s, count in suit_counts.items():
                if count >= 5:
                    suit_cards = [c for c in all_cards
                                  if Card.get_suit_int(c) == s]
                    for combo in combinations(suit_cards, 5):
                        r = self._eval.evaluate(list(combo), [])
                        best = min(best, self._remap_rank(r))
                    break

        return best
