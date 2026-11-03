"""Solo playtest ("Test" page): shuffle, opening hand by the game's rules, mulligan, draw, prize cards – and exact
opening-hand probabilities (hypergeometric) for groups of cards in the deck. No rules engine: you play both sides of
nothing, the program only deals.

Rules per game: games.<game>.playtest = {"hand": 7, "mulligan": "london" | "basic" | "bottom_any" | None, "prizes": 6,
"draw_first": False, "inkwell": False}; games.<game>.playtest_groups() names the groups (e.g. "Basic Pokémon",
"Lands"). bottom_any (Lorcana): once before the first turn any number of cards face down on the bottom, draw as many,
shuffle. inkwell (Lorcana): a zone for face-down cards (ink)."""
import math
import random


# ---------- probabilities ----------
def p_at_least(deck, hits, seen, k=1):
    """Exact chance to see at least k of `hits` cards among `seen` cards drawn from a deck of `deck` (hypergeometric)."""
    if hits <= 0 or seen <= 0 or deck <= 0:
        return 0.0 if k > 0 else 1.0
    seen = min(seen, deck)
    total = math.comb(deck, seen)
    miss = sum(math.comb(hits, i) * math.comb(deck - hits, seen - i) for i in range(0, min(k, hits + 1))
               if seen - i <= deck - hits)
    return max(0.0, min(1.0, 1 - miss / total))


def seen_by_turn(rules, turn):
    """Cards seen by your turn `turn` (1 = first turn): opening hand + one draw per turn – the first turn without a draw
    unless the game draws on it (Pokémon)."""
    return rules.get("hand", 7) + max(0, turn - 1) + (1 if rules.get("draw_first") else 0)


def chances(n, k, rules, turns=(2, 3)):
    """[chance in the opening hand, by turn 2, by turn 3 …] for k cards of a deck of n."""
    return [p_at_least(n, k, rules.get("hand", 7))] + [p_at_least(n, k, seen_by_turn(rules, t)) for t in turns]


def group_stats(cards, rules, groups, turns=(2, 3)):
    """cards: the library as card rows (one per copy); groups: [(name, predicate)].
    -> [{"name", "count", "p": [opening hand, by turn 2, 3 …]}] – groups that occur in the deck."""
    n = len(cards)
    out = []
    for name, test in groups:
        k = sum(1 for r in cards if test(r))
        if k:
            out.append({"name": name, "count": k, "p": chances(n, k, rules, turns)})
    return out


# ---------- the table ----------
class Goldfish:
    """One solo game. cards: rows (one per copy) of the library; extra: Extra Deck (Yu-Gi-Oh!), not shuffled in.
    Zones: library, hand, play, discard, prizes (face down) – plus the cards put back with a London mulligan.
    Games with a Leader: it starts in play, its Life value goes face down into "prizes" (Life), DON!! is a counter."""

    def __init__(self, cards, rules, extra=(), basic=lambda r: True, rng=None, leader=None):
        self.all, self.rules, self.extra, self.leader = list(cards), dict(rules), list(extra), leader
        self.basic = basic
        self.rng = rng or random.Random()
        self.new_game()

    def new_game(self):
        self.library = list(self.all)
        self.rng.shuffle(self.library)
        self.hand, self.play, self.discard, self.prizes = [], [], [], []
        self.active, self.bench = [], []   # Pokémon: Active Pokémon (1) and Bench (rules["bench"] places)
        self.inkwell = []                  # Lorcana: face-down cards (ink)
        self.mulligans, self.to_bottom, self.revealed = 0, 0, []
        self.choosing, self.aside, self.swapped = False, [], 0   # Lorcana mulligan: picking cards for the bottom
        self.turn = 1
        if self.leader is not None:
            self.play = [self.leader]
        self.don = 1 if self.rules.get("don") else 0   # 1 DON!! on the first turn, then 2 per turn
        self._deal()

    def _deal(self):
        rules = self.rules
        self.hand = self._take(rules.get("hand", 7))
        if rules.get("mulligan") == "basic":   # Pokémon: no Basic Pokémon -> show, shuffle back, redraw (counted)
            while not any(self.basic(r) for r in self.hand) and any(self.basic(r) for r in self.library + self.hand):
                self.mulligans += 1
                self.revealed = list(self.hand)
                self.library += self.hand
                self.rng.shuffle(self.library)
                self.hand = self._take(rules.get("hand", 7))
        if rules.get("prizes"):
            self.prizes = self._take(rules["prizes"])
        if rules.get("life") == "leader" and self.leader is not None:   # Life = the Leader's value
            self.prizes = self._take(int(self.leader.get("loyalty") or 0))
        if rules.get("draw_first"):
            self.draw()

    def _take(self, n):
        got, self.library = self.library[:n], self.library[n:]
        return got

    def mulligan(self):
        """Magic London mulligan: hand back, shuffle, draw the full hand again – then put one card per mulligan on the
        bottom (put_back). Lorcana (bottom_any): the first call starts picking (clicked hand cards are set aside), the
        second finishes – as many cards drawn as were set aside, those go under the library, then shuffle. Once, before
        the first turn. Other games: nothing."""
        if self.rules.get("mulligan") == "bottom_any":
            if self.choosing:
                self.choosing = False
                self.swapped = len(self.aside)
                self.hand += self._take(self.swapped)
                self.library += self.aside
                self.aside = []
                self.rng.shuffle(self.library)
                self.mulligans = 1
            elif self.can_mulligan():
                self.choosing = True
            return
        if self.rules.get("mulligan") == "once":   # once, all cards back (Life too), new hand and Life
            if self.can_mulligan():
                self.library += self.hand + self.prizes
                self.rng.shuffle(self.library)
                self.hand, self.prizes = [], []
                self.mulligans = 1
                self.hand = self._take(self.rules.get("hand", 5))
                if self.rules.get("life") == "leader" and self.leader is not None:
                    self.prizes = self._take(int(self.leader.get("loyalty") or 0))
            return
        if self.rules.get("mulligan") != "london":
            return
        self.library += self.hand
        self.rng.shuffle(self.library)
        self.hand = self._take(self.rules.get("hand", 7))
        self.mulligans += 1
        self.to_bottom = self.mulligans

    def can_mulligan(self):
        m = self.rules.get("mulligan")
        if m == "bottom_any":   # once, before the first turn (or while picking: to finish)
            return self.choosing or (not self.mulligans and self.turn == 1)
        if m == "once":
            return not self.mulligans and self.turn == 1
        return m == "london"

    def put_back(self, i):
        """London mulligan: card i of the hand to the bottom of the library. Lorcana: set it aside while picking."""
        if self.choosing and 0 <= i < len(self.hand):
            self.aside.append(self.hand.pop(i))
            return
        if self.to_bottom > 0 and 0 <= i < len(self.hand):
            self.library.append(self.hand.pop(i))
            self.to_bottom -= 1

    def draw(self):
        if self.library:
            self.hand.append(self.library.pop(0))

    def next_turn(self):
        self.turn += 1
        self.draw()
        if self.rules.get("don"):
            self.don = min(self.rules["don"], self.don + 2)

    def take_prize(self, i=0):
        if 0 <= i < len(self.prizes):
            self.hand.append(self.prizes.pop(i))

    ZONES = ("hand", "play", "discard", "active", "bench", "inkwell")

    def room(self, zone):
        """Free places in a zone (Active: 1, Bench: rules["bench"]) – None = unlimited."""
        if zone == "active":
            return 1 - len(self.active)
        if zone == "bench":
            return self.rules.get("bench", 5) - len(self.bench)
        return None

    def move(self, zone_from, i, zone_to):
        """Move card i between hand / play / discard / active / bench (drag on the table). A full Active spot or
        Bench takes nothing – no other rules."""
        if zone_from not in self.ZONES or zone_to not in self.ZONES:
            return False
        src, dst = getattr(self, zone_from), getattr(self, zone_to)
        if not 0 <= i < len(src) or src is dst or (self.room(zone_to) is not None and self.room(zone_to) <= 0):
            return False
        dst.append(src.pop(i))
        return True
