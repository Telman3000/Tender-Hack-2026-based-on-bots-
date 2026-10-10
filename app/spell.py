from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from rapidfuzz import process
from rapidfuzz.distance import OSA

from app.morph import inflection, known_word

EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
LAYOUT = str.maketrans(EN, RU)

LATIN_OK = {
    "mm", "cm", "kg", "ml", "kw", "w", "v", "a", "l", "s", "m", "xl", "xxl",
    "led", "usb", "pvc", "abs", "mdf", "lcd", "rgb", "eva", "pu", "pp", "sds",
}

TOKEN = re.compile(r"[A-Za-z][A-Za-z\[\];'`]*(?:[,.][A-Za-z\[\];'`]+)*|[А-Яа-яЁё]+")
GLUED = re.compile(r"[A-Za-zА-Яа-яЁё0-9]")


@dataclass
class Fix:
    kind: str
    src: str
    dst: str


def _same_case(src: str, dst: str) -> str:
    if len(src) > 1 and src.isupper():
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


class Speller:
    def __init__(self, freq: Counter, min_count: int = 2) -> None:
        self.freq = {w: n for w, n in freq.items() if n >= min_count and len(w) >= 3 and w.isalpha()}
        self.by_letter: dict[str, list[str]] = {}
        for w in self.freq:
            self.by_letter.setdefault(w[0], []).append(w)

    def known(self, word: str) -> bool:
        return word in self.freq

    def suggest(self, word: str) -> str | None:
        limit = 1 if len(word) <= 5 else 2
        found = process.extract(word, self.by_letter.get(word[0], []), scorer=OSA.distance,
                                score_cutoff=limit, limit=25)
        best = None
        for cand, dist, _ in found:
            if cand == word or abs(len(cand) - len(word)) > limit or inflection(cand, word):
                continue
            rank = (dist, -self.freq[cand])
            if best is None or rank < best[0]:
                best = (rank, cand)
        return best[1] if best else None

    def _latin(self, token: str) -> Fix | None:
        low = token.lower()
        if low in LATIN_OK or (len(token) > 1 and token.isupper()):
            return None
        ru = low.translate(LAYOUT).replace("ё", "е")
        return Fix("layout", token, _same_case(token, ru)) if self.known(ru) else None

    def _cyrillic(self, token: str, first: bool) -> Fix | None:
        low = token.lower().replace("ё", "е")
        if len(low) < 4 or (token.isupper() and len(token) <= 6) or (token[:1].isupper() and not first):
            return None
        if known_word(low):
            return None
        if self.known(low):
            if len(low) < 6 or self.freq[low] >= 10:
                return None
            cand = self.suggest(low)
            if not cand or self.freq[cand] < 20 * self.freq[low]:
                return None
        else:
            cand = self.suggest(low)
        return Fix("typo", token, _same_case(token, cand)) if cand else None

    def fix(self, text: str) -> tuple[str, list[Fix]]:
        fixes: list[Fix] = []

        def repl(m: re.Match) -> str:
            token = m.group(0)
            s, e = m.start(), m.end()
            if len(token) > 40 or (s and GLUED.match(text[s - 1])) or (e < len(text) and GLUED.match(text[e])):
                return token
            if "a" <= token[0].lower() <= "z":
                f = self._latin(token)
            else:
                f = self._cyrillic(token, not TOKEN.search(text, 0, s))
            if f is None:
                return token
            fixes.append(f)
            return f.dst

        return TOKEN.sub(repl, text), fixes
