"""In-memory catalog cache, loaded once at engine start (keeps /api/analyze fast)."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.morph import STOP, inflection, same_stem
from app.units import UNITS, canon_unit

_BOUND = re.compile(r"\s+(?:до|от)$")
_LETTERS = re.compile(r"[a-zа-я]+")
_PACKAGE = ("упаков", "короб", "тара", "брутто", "транспорт")
_SAME_NAME = {"масса": "вес", "вес": "масса"}
MIN_SAMPLES = 15


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9\s\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> frozenset[str]:
    return frozenset(t for t in norm(s).split() if len(t) > 2)


@dataclass
class CharSpec:
    name: str
    required: bool = False
    enums: list[str] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)
    ranges: list[tuple[float | None, float | None, str | None, str | None]] = field(
        default_factory=list
    )
    unit: str | None = None

    @property
    def is_numeric(self) -> bool:
        return bool(self.numbers or self.ranges)

    @property
    def is_flag(self) -> bool:
        return bool(self.enums) and {norm(e) for e in self.enums} <= {"да", "нет"}

    def allowed_enums(self) -> list[str] | None:
        return list(dict.fromkeys(self.enums))[:50] if self.enums else None

    def bounds(self) -> tuple[float | None, float | None]:
        lows = [r[0] for r in self.ranges] + self.numbers
        highs = [r[1] for r in self.ranges] + self.numbers
        lo = None if (not lows or any(x is None for x in lows)) else min(lows)
        hi = None if (not highs or any(x is None for x in highs)) else max(highs)
        return lo, hi


@dataclass
class KtruEntry:
    code: str
    name: str
    okpd2: str | None
    domain: str | None
    name_norm: str
    toks: frozenset[str]
    specs: dict[str, CharSpec]  # lower(name) -> spec

    @property
    def required(self) -> list[str]:
        return [s.name for s in self.specs.values() if s.required]

    def material_specs(self) -> list[CharSpec]:
        return [sp for k, sp in self.specs.items() if "материал" in k and sp.enums and not sp.is_flag]

    def materials(self) -> CharSpec | None:
        specs = self.material_specs()
        if not specs:
            return None
        return CharSpec(name="Материал", enums=list(dict.fromkeys(v for sp in specs for v in sp.enums)))


@dataclass
class HeadSamples:
    words: dict[str, set[int]] = field(default_factory=dict)
    chars: dict[str, list[tuple[int, str, float, str]]] = field(default_factory=dict)
    by_word: dict[str, set[int]] = field(default_factory=dict)

    def rows_with(self, word: str) -> set[int]:
        if word not in self.by_word:
            self.by_word[word] = set().union(*(ids for w, ids in self.words.items() if same_stem(word, w)))
        return self.by_word[word]


class Catalog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.entries: list[KtruEntry] = []
        self.by_code: dict[str, KtruEntry] = {}
        self.by_domain: dict[str | None, list[int]] = {}
        self.portal_names: dict[str | None, list[str]] = {}
        self.portal_freq: dict[tuple[str | None, str], int] = {}
        self.ste_names: dict[str | None, list[str]] = {}
        self.ste_chars: dict[str, list[tuple[str, str]]] = {}
        self._load(conn)

    def _load(self, conn: sqlite3.Connection) -> None:
        specs: dict[str, dict[str, CharSpec]] = {}
        has_values = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ktru_char_values'"
        ).fetchone()
        if has_values:
            for r in conn.execute(
                "SELECT code, char_name, required, kind, value, vmin, vmax, min_op, max_op, unit "
                "FROM ktru_char_values"
            ):
                d = specs.setdefault(r["code"], {})
                key = r["char_name"].lower()
                sp = d.get(key)
                if sp is None:
                    sp = d[key] = CharSpec(name=r["char_name"], required=bool(r["required"]))
                if r["unit"] and not sp.unit:
                    sp.unit = r["unit"]
                kind = r["kind"]
                if kind == "enum" and r["value"]:
                    sp.enums.append(r["value"])
                elif kind == "number" and r["vmin"] is not None:
                    sp.numbers.append(r["vmin"])
                elif kind == "range":
                    sp.ranges.append((r["vmin"], r["vmax"], r["min_op"], r["max_op"]))

        rows = conn.execute(
            "SELECT code, name, okpd2, domain, required_json, chars_json FROM ktru ORDER BY code"
        ).fetchall()
        for row in rows:
            sp = specs.get(row["code"])
            if sp is None:  # old index without values: names only
                sp = {}
                try:
                    for it in json.loads(row["chars_json"] or "[]"):
                        name = it if isinstance(it, str) else it.get("name")
                        req = isinstance(it, dict) and it.get("required")
                        if name:
                            sp[name.lower()] = CharSpec(name=name, required=bool(req))
                except Exception:
                    pass
            e = KtruEntry(
                code=row["code"], name=row["name"], okpd2=row["okpd2"], domain=row["domain"],
                name_norm=norm(row["name"]), toks=tokens(row["name"]), specs=sp,
            )
            idx = len(self.entries)
            self.entries.append(e)
            self.by_code[e.code] = e
            self.by_domain.setdefault(e.domain, []).append(idx)
            self.by_domain.setdefault(None, []).append(idx)

        for r in conn.execute(
            "SELECT domain, char_name, COUNT(*) AS n FROM portal_chars "
            "WHERE char_name IS NOT NULL GROUP BY domain, char_name"
        ):
            self.portal_freq[(r["domain"], r["char_name"])] = r["n"]
        for (dom, name), _n in sorted(self.portal_freq.items(), key=lambda x: -x[1]):
            self.portal_names.setdefault(dom, []).append(name)
            self.portal_names.setdefault(None, []).append(name)
        for r in conn.execute("SELECT domain, name_norm, chars_raw FROM portal_ste"):
            if r["name_norm"]:
                self.ste_names.setdefault(r["domain"], []).append(r["name_norm"])
                if r["chars_raw"]:
                    head = r["name_norm"].split()[0]
                    self.ste_chars.setdefault(head, []).append((r["name_norm"], r["chars_raw"]))

    # -------- lookups --------
    def pool(self, domain: str | None) -> list[int]:
        return self.by_domain.get(domain) or self.by_domain.get(None, [])

    @staticmethod
    def find_spec(entry: KtruEntry, name: str) -> CharSpec | None:
        key = name.lower().strip()
        if key in entry.specs:
            return entry.specs[key]
        if not entry.specs:
            return None
        # "Высота" -> "Высота столешницы", typo-tolerant
        best = None
        for k, sp in entry.specs.items():
            if k.startswith(key + " ") or k.split(",")[0] == key:
                return sp
        # whole-word containment: «размер» -> «Российский размер», «длина» -> «Длина губок»
        nk = norm(key)
        if nk:
            hits = [sp for k, sp in entry.specs.items() if f" {nk} " in f" {norm(k)} "
                    and not (sp.enums and {norm(e) for e in sp.enums} <= {"да", "нет"})]
            if hits:
                return sorted(hits, key=lambda sp: (len(sp.name), sp.name))[0]
        m = process.extractOne(key, list(entry.specs.keys()), scorer=fuzz.ratio, score_cutoff=88)
        if m:
            best = entry.specs[m[0]]
        return best

    # -------- vectorised views (lazy, cached) --------
    def names_for(self, pool: list[int]) -> tuple[list[str], list[frozenset[str]]]:
        key = id(pool)
        hit = getattr(self, "_names_cache", {}).get(key)
        if hit is None:
            hit = ([self.entries[i].name_norm for i in pool], [self.entries[i].toks for i in pool])
            self.__dict__.setdefault("_names_cache", {})[key] = hit
        return hit

    def vocab(self, domain: str | None) -> set[str]:
        cache = self.__dict__.setdefault("_vocab", {})
        if domain not in cache:
            v: set[str] = set()
            for i in self.pool(domain):
                v.update(self.entries[i].name_norm.split())
            for n in self.ste_names.get(domain, [])[:30000]:
                v.update(n.split())
            cache[domain] = {w for w in v if len(w) >= 3}
        return cache[domain]

    def head_samples(self, head: str) -> HeadSamples:
        cache = self.__dict__.setdefault("_head_samples", {})
        hs = cache.get(head)
        if hs is None:
            hs = HeadSamples()
            rows = [it for h, items in self.ste_chars.items() if h == head or inflection(h, head) for it in items]
            units: dict[str, str | None] = {}
            names: dict[str, str] = {}
            for i, (name, raw) in enumerate(rows):
                for w in name.split():
                    hs.words.setdefault(w, set()).add(i)
                for part in raw.split("|"):
                    rest, _, unit = part.strip().rpartition(" ")
                    if unit not in units:
                        cu = canon_unit(unit)
                        units[unit] = cu if cu in UNITS else None
                    cu = units[unit]
                    if cu is None:
                        continue
                    label, _, num = rest.rpartition(" ")
                    try:
                        x = float(num.replace(",", "."))
                    except ValueError:
                        continue
                    if x <= 0 or not label:
                        continue
                    if label not in names:
                        names[label] = _BOUND.sub("", norm(label))
                    dim, factor = UNITS[cu]
                    hs.chars.setdefault(names[label], []).append((i, dim, x * factor, cu))
            cache[head] = hs
        return hs

    def typical(self, query: list[str], name: str) -> tuple[float, float, str, int] | None:
        if not query:
            return None
        key = norm(name)
        cache = self.__dict__.setdefault("_typical", {})
        if (tuple(query), key) in cache:
            return cache[(tuple(query), key)]
        hs = self.head_samples(query[0])
        exact = {key, _SAME_NAME.get(key, key)}
        stems = [w for w in key.split() if w not in STOP]
        loose = [c for c in hs.chars if c not in exact and stems and len(c.split()) <= len(stems) + 1
                 and not any(w.startswith(_PACKAGE) for w in c.split())
                 and all(any(same_stem(s, w) for w in c.split()) for s in stems)]
        result = None
        hits = [hs.rows_with(q) for q in query[1:]]
        for k in range(len(hits), -1, -1):
            rows = set.intersection(*hits[:k]) if k else None
            found = [s for c in exact for s in hs.chars.get(c, ()) if rows is None or s[0] in rows]
            if len(found) < MIN_SAMPLES:
                found += [s for c in loose for s in hs.chars[c] if rows is None or s[0] in rows]
            if not found:
                continue
            dim = Counter(s[1] for s in found).most_common(1)[0][0]
            xs = sorted(s[2] for s in found if s[1] == dim)
            if len(xs) >= MIN_SAMPLES:
                unit = Counter(s[3] for s in found if s[1] == dim).most_common(1)[0][0]
                result = (xs[int(len(xs) * 0.05)], xs[max(0, int(len(xs) * 0.95) - 1)], unit, len(xs))
                break
        cache[(tuple(query), key)] = result
        return result

    def word_freq(self) -> Counter:
        freq = self.__dict__.get("_freq")
        if freq is None:
            freq = Counter()
            for e in self.entries:
                freq.update(_LETTERS.findall(e.name_norm))
                for sp in e.specs.values():
                    freq.update(_LETTERS.findall(norm(sp.name)))
                    for v in sp.enums:
                        freq.update(_LETTERS.findall(norm(v)))
            for (_dom, name), n in self.portal_freq.items():
                for w in _LETTERS.findall(norm(name)):
                    freq[w] += n
            for names in self.ste_names.values():
                for n in names:
                    freq.update(_LETTERS.findall(n))
            self._freq = freq
        return freq

    def vocab_list(self, domain: str | None) -> list[str]:
        cache = self.__dict__.setdefault("_vocab_l", {})
        if domain not in cache:
            cache[domain] = sorted(self.vocab(domain))
        return cache[domain]

    def okpd_for(self, pool: list[int]):
        import numpy as np

        cache = self.__dict__.setdefault("_okpd", {})
        key = id(pool)
        if key not in cache:
            cache[key] = np.array([self.entries[i].okpd2 or "" for i in pool], dtype=str)
        return cache[key]

    def qualifier_mask(self, pool: list[int], stem: str):
        import numpy as np

        cache = self.__dict__.setdefault("_qual", {})
        key = (id(pool), stem)
        if key not in cache:
            cache[key] = np.array(
                [any((w == stem[1:]) if stem.startswith("=") else w.startswith(stem)
                     for w in self.entries[i].name_norm.split()[1:]) for i in pool],
                dtype=float,
            )
        return cache[key]

    def known_form(self, word: str, domain: str | None) -> bool:
        """Word is an inflection of a vocabulary word (same stem, ending differs by <= 3 chars)."""
        cache = self.__dict__.setdefault("_stems", {})
        if domain not in cache:
            st: set[str] = set()
            for w in self.vocab(domain):
                if len(w) >= 5:
                    st.add(w[: max(4, len(w) - 3)])
            cache[domain] = st
        st = cache[domain]
        for cut in range(max(4, len(word) - 3), len(word) + 1):
            if word[:cut] in st:
                return True
        return False
