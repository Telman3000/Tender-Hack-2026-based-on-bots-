from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

ENDINGS = {
    "", "а", "я", "ы", "и", "е", "у", "ю", "о", "ь", "й",
    "ом", "ем", "ой", "ей", "ам", "ям", "ах", "ях", "ов", "ев", "ую", "юю",
    "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ых", "их", "ым", "им",
    "ого", "его", "ому", "ему", "ыми", "ими", "ами", "ями",
}
STOP = {
    "для", "без", "при", "или", "из", "на", "под", "над", "с", "со", "в", "во",
    "и", "к", "по", "от", "до", "не", "нет", "а", "о", "об", "у", "за",
}
NEGATIONS = {"без", "нет", "не"}
FLAG_WORDS = ("наличи", "возможност", "режим", "функци")

_WORD = re.compile(r"[a-zа-я0-9]+")


def words(s: str | None) -> list[str]:
    return _WORD.findall((s or "").lower().replace("ё", "е"))


@lru_cache(maxsize=1)
def analyzer() -> pymorphy3.MorphAnalyzer:
    return pymorphy3.MorphAnalyzer()


def known_word(word: str) -> bool:
    return analyzer().word_is_known(word.lower())


def genitive_noun(word: str) -> bool:
    tag = analyzer().parse(word.lower())[0].tag
    return "NOUN" in tag and "gent" in tag


def adjective(word: str) -> bool:
    return "ADJF" in analyzer().parse(word.lower())[0].tag


def same_lemma(a: str, b: str) -> bool:
    return analyzer().parse(a)[0].normal_form == analyzer().parse(b)[0].normal_form


def _common(a: str, b: str) -> int:
    n = min(len(a), len(b))
    k = 0
    while k < n and a[k] == b[k]:
        k += 1
    return k


def inflection(a: str, b: str) -> bool:
    return any(a[k:] in ENDINGS and b[k:] in ENDINGS for k in range(_common(a, b), 2, -1))


def same_stem(a: str, b: str) -> bool:
    if a == b or inflection(a, b):
        return True
    n = min(len(a), len(b))
    return n >= 4 and _common(a, b) >= max(4, n - 2)


def flag_answer(text_words: list[str], name: str) -> tuple[str, list[int]] | None:
    parts = [w for w in words(name) if w not in STOP and not w.startswith(FLAG_WORDS) and not w.isdigit()]
    if not parts:
        return None
    pos = []
    for p in parts:
        i = next((k for k, t in enumerate(text_words) if same_stem(p, t)), -1)
        if i < 0:
            return None
        pos.append(i)
    if max(pos) - min(pos) > len(parts):
        return None
    neg = [i - 1 for i in pos if i > 0 and text_words[i - 1] in NEGATIONS]
    if neg:
        return "Нет", sorted(set(pos + neg))
    return "Да", sorted(pos)
