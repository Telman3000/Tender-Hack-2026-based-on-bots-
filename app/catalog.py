"""In-memory catalog cache, loaded once at engine start (keeps /api/analyze fast)."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process


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


class Catalog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.entries: list[KtruEntry] = []
        self.by_code: dict[str, KtruEntry] = {}
        self.by_domain: dict[str | None, list[int]] = {}
        self.portal_names: dict[str | None, list[str]] = {}
        self.portal_freq: dict[tuple[str | None, str], int] = {}
        self.ste_names: dict[str | None, list[str]] = {}
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
        for r in conn.execute("SELECT domain, name_norm FROM portal_ste"):
            if r["name_norm"]:
                self.ste_names.setdefault(r["domain"], []).append(r["name_norm"])

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
