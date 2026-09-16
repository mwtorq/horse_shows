"""
HSO <-> SHR class-name matching with synonym expansion and Entry corroboration.

Used by rebuild_merged_show_hso_first.py to map SHR judge cards onto HSO results.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SYNONYM_PHRASES: Tuple[Tuple[str, str], ...] = (
    ("OPEN BREED", "OTAB"),
    ("WALK TROT CANTER", "WTC"),
    ("WALK TROT JOG", "WTJ"),
    ("WALK TROT", "WT"),
    ("14 AND OVER", "14 OVER"),
    ("14 OVER", "14/OVER"),
    ("HACKNEY ROADSTER PONY", "ROAD PONY"),
    ("SECTION", "SEC"),
)


def normalize_class_name(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.strip().upper()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " AND ").replace("/", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for long, short in SYNONYM_PHRASES:
        text = text.replace(long, short)
    # Expand short tokens back so WT matches WALK TROT after both sides normalize
    replacements = {
        "OTAB": "OPEN BREED",
        "WTC": "WALK TROT CANTER",
        "WTJ": "WALK TROT JOG",
        "WT": "WALK TROT",
    }
    tokens = []
    for tok in text.split():
        tokens.extend(replacements.get(tok, tok).split())
    stop = {
        "THE", "A", "AN", "AND", "OF", "AT", "TO", "FOR",
        "ASB", "AHA", "USEF", "UPHA", "AHHS", "AMHA",
        "OPEN", "MONARCH", "CHAMPIONSHIP", "CHAMP", "CLASS",
        "HORSE", "PONY", "SECTION", "SEC", "DIVISION", "DIV",
    }
    # Keep age/section tokens; drop only filler
    keep_always = {
        "WALK", "TROT", "CANTER", "JOG", "ACADEMY", "EQUITATION",
        "SHOWMANSHIP", "BREED", "ELITE", "SINGLE", "BIT", "MODEL",
        "RANCH", "RIDING", "CARRIAGE", "TURNOUT", "PATTERN",
        "HUNT", "WESTERN", "OVER", "UNDER", "SADDLE", "ROADSTER",
        "HACKNEY", "DRIVING", "PLEASURE", "MASTERS", "AMATEUR",
    }
    out = []
    for t in tokens:
        if t in stop and t not in keep_always and not re.search(r"\d", t):
            continue
        out.append(t)
    return " ".join(out)


def class_name_similarity(a: Optional[str], b: Optional[str]) -> float:
    na, nb = normalize_class_name(a), normalize_class_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return seq
    inter = ta & tb
    jaccard = len(inter) / len(ta | tb)
    containment = len(inter) / min(len(ta), len(tb))
    return max(seq, 0.5 * seq + 0.5 * jaccard, containment * 0.95)


def extract_age_tokens(name: Optional[str]) -> set:
    text = (name or "").upper()
    ages = set(re.findall(r"\b\d{1,2}\s*[-/]\s*\d{1,2}\b", text))
    ages |= set(re.findall(r"\b\d{1,2}\s*(?:AND\s+)?OVER\b", text))
    ages |= set(re.findall(r"\b\d{1,2}\s*/\s*OVER\b", text))
    ages |= set(re.findall(r"\b\d{1,2}\s*&\s*UNDER\b", text))
    # normalize
    return {re.sub(r"\s+", " ", a.replace("&", "AND").replace("/", " ")) for a in ages}


def ages_compatible(a: Optional[str], b: Optional[str]) -> bool:
    aa, bb = extract_age_tokens(a), extract_age_tokens(b)
    if not aa or not bb:
        return True
    return bool(aa & bb)


@dataclass
class ClassSide:
    class_id: Optional[int]
    class_name: str
    class_num: Optional[str] = None
    entries_count: Optional[int] = None
    entry_numbers: Optional[set] = None


@dataclass
class ClassMatch:
    shr: ClassSide
    hso: ClassSide
    score: float
    entry_overlap: int
    reason: str


def match_classes(
    shr_classes: Sequence[ClassSide],
    hso_classes: Sequence[ClassSide],
    min_score: float = 0.72,
    prefer_entry_overlap: bool = True,
) -> Tuple[List[ClassMatch], List[ClassSide], List[ClassSide]]:
    """
    One-to-one match. Prefer candidates with Entry overlap and compatible ages.
    """
    matches: List[ClassMatch] = []
    used_hso = set()
    used_shr = set()

    candidates: List[Tuple[float, int, int, int, str]] = []
    for i, shr in enumerate(shr_classes):
        for j, hso in enumerate(hso_classes):
            if not ages_compatible(shr.class_name, hso.class_name):
                continue
            score = class_name_similarity(shr.class_name, hso.class_name)
            if score < min_score:
                continue
            sa = shr.entry_numbers or set()
            ha = hso.entry_numbers or set()
            overlap = len(sa & ha) if sa and ha else 0
            # Boost when Entries counts are close
            entries_bonus = 0.0
            if (
                shr.entries_count is not None
                and hso.entries_count is not None
                and shr.entries_count > 0
                and hso.entries_count > 0
            ):
                ratio = min(shr.entries_count, hso.entries_count) / max(
                    shr.entries_count, hso.entries_count
                )
                if ratio >= 0.8:
                    entries_bonus = 0.05
            # Require corroboration when score is soft
            if score < 0.88 and prefer_entry_overlap and sa and ha and overlap == 0:
                continue
            if score < 0.80 and overlap == 0 and entries_bonus == 0:
                continue
            adj = min(1.0, score + (0.08 if overlap else 0) + entries_bonus)
            reason = f"score={score:.3f};overlap={overlap};entries_bonus={entries_bonus:.2f}"
            candidates.append((adj, overlap, i, j, reason))

    # Sort by adjusted score, then overlap
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for adj, overlap, i, j, reason in candidates:
        if i in used_shr or j in used_hso:
            continue
        used_shr.add(i)
        used_hso.add(j)
        matches.append(
            ClassMatch(
                shr=shr_classes[i],
                hso=hso_classes[j],
                score=adj,
                entry_overlap=overlap,
                reason=reason,
            )
        )

    unmatched_shr = [c for i, c in enumerate(shr_classes) if i not in used_shr]
    unmatched_hso = [c for i, c in enumerate(hso_classes) if i not in used_hso]
    return matches, unmatched_shr, unmatched_hso


def write_match_report(
    path: str,
    matches: Iterable[ClassMatch],
    unmatched_shr: Iterable[ClassSide],
    unmatched_hso: Iterable[ClassSide],
) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "status",
                "shr_class_id",
                "shr_class_name",
                "shr_entries",
                "hso_class_id",
                "hso_class",
                "hso_class_name",
                "hso_entries",
                "score",
                "entry_overlap",
                "reason",
            ]
        )
        for m in matches:
            w.writerow(
                [
                    "MATCH",
                    m.shr.class_id,
                    m.shr.class_name,
                    m.shr.entries_count,
                    m.hso.class_id,
                    m.hso.class_num,
                    m.hso.class_name,
                    m.hso.entries_count,
                    f"{m.score:.4f}",
                    m.entry_overlap,
                    m.reason,
                ]
            )
        for s in unmatched_shr:
            w.writerow(
                ["UNMATCHED_SHR", s.class_id, s.class_name, s.entries_count, "", "", "", "", "", "", ""]
            )
        for h in unmatched_hso:
            w.writerow(
                [
                    "UNMATCHED_HSO",
                    "",
                    "",
                    "",
                    h.class_id,
                    h.class_num,
                    h.class_name,
                    h.entries_count,
                    "",
                    "",
                    "",
                ]
            )
