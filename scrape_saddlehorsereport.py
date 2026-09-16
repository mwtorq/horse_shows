"""
Scrape show results, horse pedigree, judges, and judge cards from
saddlehorsereport.com into HorseShows.sResults.

Auth: reCAPTCHA v3 rejects headless login, so login uses headed
undetected-chromedriver, then cookies transfer into a headless Selenium session
for scraping.

Every fetched page is archived under saddlehorsereport/{year}/{kind}/ as
debug_shr_*.html plus a matching *_raw.txt, where kind is horse, judges,
results, or other (same pattern as jrtca_results debug_trialvault_*.html).

Credentials: SHR_EMAIL / SHR_PASSWORD (from scripts/Save-SaddleHorseReportCredential.ps1
via ResultsAutomation DPAPI), or interactive getpass.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import socket
import time
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import pyodbc
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

BASE_URL = "https://www.saddlehorsereport.com"
RESULTS_URL = f"{BASE_URL}/results"
JUDGES_URL = f"{BASE_URL}/judges"
LOGIN_URL = f"{BASE_URL}/login?return=results"
RECAPTCHA_SITE_KEY = "6LdFNZ4sAAAAAN2gyWb4TWuTv08iBnABNMvC04Al"
COOKIE_PATH = os.path.join(
    os.environ.get("RESULTS_AUTOMATION_HOME", r"C:\Users\mw\ResultsAutomation"),
    "saddlehorsereport_cookies.json",
)
# Persistent profile improves reCAPTCHA v3 trust across retries.
UC_PROFILE_DIR = os.path.join(
    os.environ.get("RESULTS_AUTOMATION_HOME", r"C:\Users\mw\ResultsAutomation"),
    "chrome_profiles",
    "saddlehorsereport_uc",
)
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
# Year/{kind} under saddlehorsereport/, same idea as jrtca_results/{year}/debug_*.html
SHR_ARCHIVE_ROOT = os.path.join(REPO_ROOT, "saddlehorsereport")
FUZZY_SHOW_THRESHOLD = 0.82  # legacy; show matching uses SHOW_NAME_MATCH_MIN
FUZZY_CLASS_THRESHOLD = 0.86
SHOW_NAME_MATCH_MIN = 0.78
# When date ranges overlap AND state codes agree, allow a looser name gate
# (e.g. Monarch National Championship vs Monarch Show Series Championship).
SHOW_NAME_MATCH_MIN_CONFIRMED = 0.55
CHROME_MAJOR = 152

# HSO stores StateProv as abbreviation; SHR uses full names. Always compare codes.
_US_CA_STATE_CODES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
    "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
    "ALBERTA": "AB", "BRITISH COLUMBIA": "BC", "MANITOBA": "MB", "NEW BRUNSWICK": "NB",
    "NEWFOUNDLAND AND LABRADOR": "NL", "NEWFOUNDLAND": "NL", "NORTHWEST TERRITORIES": "NT",
    "NOVA SCOTIA": "NS", "NUNAVUT": "NU", "ONTARIO": "ON", "PRINCE EDWARD ISLAND": "PE",
    "QUEBEC": "QC", "SASKATCHEWAN": "SK", "YUKON": "YT",
}
_VALID_STATE_ABBREVS = set(_US_CA_STATE_CODES.values())
# page_kind -> archive subdirectory under the year folder
SHR_ARCHIVE_KIND_DIRS = {
    "horse": "horse",
    "judges": "judges",
    "judgesyear": "judges",
    "results": "results",
    "yearlist": "results",
    "resultshome": "results",
}


def print_with_timestamp(message: str, end: str = "\n") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", end=end, flush=True)


def sanitize_filename(name: str, max_len: int = 50) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    safe = safe.replace(" ", "_").replace("&", "and").replace("'", "")
    safe = re.sub(r"_+", "_", safe).strip("_")
    return (safe[:max_len] or "unknown")


def build_shr_raw_text(html_content: str, source_url: str, label: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    page_text = soup.get_text(separator="\n", strip=False)
    cleaned = re.sub(r"\n{3,}", "\n\n", page_text)
    cleaned = re.sub(r" +", " ", cleaned)
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    header = [
        f"Source URL: {source_url}",
        f"Label: {label}",
        f"Captured: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    return "\n".join(header + lines)


def save_shr_page(
    html_content: str,
    year: Optional[int],
    page_kind: str,
    label: str,
    source_url: str,
    sid: Optional[str] = None,
    extra_id: Optional[str] = None,
) -> str:
    """
    Save full HTML and stripped text under saddlehorsereport/{year}/{kind}/,
    mirroring jrtca_results/{year}/debug_trialvault_*.html (+ _raw.txt).
    kind is horse, judges, results, or other.
    """
    kind_dir_name = SHR_ARCHIVE_KIND_DIRS.get((page_kind or "").lower(), "other")
    out_dir = os.path.join(SHR_ARCHIVE_ROOT, str(year or "unknown"), kind_dir_name)
    os.makedirs(out_dir, exist_ok=True)
    parts = ["debug_shr", page_kind, sanitize_filename(label)]
    if sid:
        parts.append(f"sid{sid}")
    if extra_id:
        parts.append(sanitize_filename(str(extra_id), 40))
    base = "_".join(parts)
    html_path = os.path.join(out_dir, f"{base}.html")
    raw_path = os.path.join(out_dir, f"{base}_raw.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(build_shr_raw_text(html_content, source_url, label))
    print_with_timestamp(f"  Saved HTML {html_path}")
    return html_path


def save_driver_page(
    driver,
    year: Optional[int],
    page_kind: str,
    label: str,
    sid: Optional[str] = None,
    extra_id: Optional[str] = None,
) -> str:
    return save_shr_page(
        driver.page_source,
        year,
        page_kind,
        label,
        driver.current_url,
        sid=sid,
        extra_id=extra_id,
    )


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.strip().upper()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def normalize_show_name(value: Optional[str]) -> str:
    """Normalize show names for HSOâ†”SHR fuzzy compare."""
    if not value:
        return ""
    text = value.strip().upper()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Drop leading year tokens: "2024 MONARCH SHOW SERIES..."
    text = re.sub(r"^(?:19|20)\d{2}\s+", "", text)
    # Strip common trailing noise while leaving distinctive words
    for junk in ("HORSE SHOW", "HORSESHOW", " SHOW"):
        if text.endswith(junk) and len(text) > len(junk) + 2:
            text = text[: -len(junk)].strip()
    if text.endswith(" SHOW") and len(text) > 6:
        text = text[:-5].strip()
    # Drop low-signal filler tokens that differ across HSO/SHR branding
    stop = {
        "THE", "A", "AN", "AND", "OF", "AT", "HORSE", "SHOW", "SHOWS",
        "SERIES", "PRESENT", "PRESENTS",
    }
    tokens = [t for t in text.split() if t not in stop]
    return " ".join(tokens)


def token_set_similarity(a: str, b: str) -> float:
    """FuzzyWuzzy-style token_set_ratio without the dependency."""
    ta, tb = set((a or "").split()), set((b or "").split())
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    if not inter:
        return 0.0
    t0 = " ".join(sorted(inter))
    t1 = " ".join(sorted(ta))
    t2 = " ".join(sorted(tb))
    return max(
        SequenceMatcher(None, t0, t1).ratio(),
        SequenceMatcher(None, t0, t2).ratio(),
        SequenceMatcher(None, t1, t2).ratio(),
    )


def show_name_similarity(a: Optional[str], b: Optional[str]) -> float:
    na, nb = normalize_show_name(a), normalize_show_name(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    sort_a = " ".join(sorted(na.split()))
    sort_b = " ".join(sorted(nb.split()))
    token_sort = SequenceMatcher(None, sort_a, sort_b).ratio()
    return max(seq, token_sort, token_set_similarity(na, nb))


def normalize_state_code(value: Optional[str]) -> Optional[str]:
    """Map HSO abbr or SHR full name to a 2-letter US/CA code."""
    if not value:
        return None
    raw = value.strip().upper()
    raw = re.sub(r"[^\w\s]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return None
    if len(raw) == 2 and raw in _VALID_STATE_ABBREVS:
        return raw
    if raw in _US_CA_STATE_CODES:
        return _US_CA_STATE_CODES[raw]
    # Sometimes "Lexington, Virginia" or trailing state in location-like strings
    parts = raw.split()
    if len(parts) >= 2:
        joined = " ".join(parts[-2:])
        if joined in _US_CA_STATE_CODES:
            return _US_CA_STATE_CODES[joined]
        if parts[-1] in _US_CA_STATE_CODES:
            return _US_CA_STATE_CODES[parts[-1]]
        if len(parts[-1]) == 2 and parts[-1] in _VALID_STATE_ABBREVS:
            return parts[-1]
    return None


def _parse_one_date(token: str) -> Optional[date]:
    token = (token or "").strip()
    if not token:
        return None
    token = re.sub(r"\s+", " ", token)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def parse_show_date_range(
    show_date: Optional[str] = None,
    start_date: Any = None,
    end_date: Any = None,
) -> Optional[Tuple[date, date]]:
    """
    Parse SHR ('June 17-21, 2025') or HSO ('Jun 17, 2025 - Jun 21, 2025')
    or StartDate/EndDate columns into an inclusive (start, end) range.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    if isinstance(start_date, date) and isinstance(end_date, date):
        return (start_date, end_date) if start_date <= end_date else (end_date, start_date)
    if isinstance(start_date, date) and not end_date:
        return start_date, start_date

    text = (show_date or "").strip()
    if not text:
        return None
    # Normalize odd separators: "November 21-23. 2025"
    text = text.replace(".", ",")
    text = re.sub(r",+", ",", text)
    text = re.sub(r"\s+", " ", text).strip()

    # HSO style: "Jun 17, 2025 - Jun 21, 2025"
    if " - " in text or " â€“ " in text or " â€” " in text:
        parts = re.split(r"\s+[-â€“â€”]\s+", text, maxsplit=1)
        if len(parts) == 2:
            a, b = _parse_one_date(parts[0]), _parse_one_date(parts[1])
            if a and b:
                return (a, b) if a <= b else (b, a)

    # SHR cross-month: "July 30-August 2, 2025"
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s*[-â€“â€”]\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})$",
        text,
    )
    if m:
        a = _parse_one_date(f"{m.group(1)} {m.group(2)}, {m.group(5)}")
        b = _parse_one_date(f"{m.group(3)} {m.group(4)}, {m.group(5)}")
        if a and b:
            return (a, b) if a <= b else (b, a)

    # SHR same-month: "June 17-21, 2025" or "June 17, 2025"
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s*[-â€“â€”]\s*(\d{1,2}),?\s*(\d{4})$",
        text,
    )
    if m:
        month, d1, d2, year = m.group(1), m.group(2), m.group(3), m.group(4)
        a = _parse_one_date(f"{month} {d1}, {year}")
        b = _parse_one_date(f"{month} {d2}, {year}")
        if a and b:
            return (a, b) if a <= b else (b, a)

    single = _parse_one_date(text)
    if single:
        return single, single
    return None


def dates_overlap(a: Optional[Tuple[date, date]], b: Optional[Tuple[date, date]]) -> bool:
    if not a or not b:
        return False
    return a[0] <= b[1] and b[0] <= a[1]


def location_match_score(shr_loc: Optional[str], hso_loc: Optional[str]) -> float:
    """0..1 bonus signal: SHR city contained in HSO venue string, or fuzzy first segment."""
    city = (shr_loc or "").strip()
    venue = (hso_loc or "").strip()
    if not city or not venue:
        return 0.0
    if city.lower() in venue.lower():
        return 1.0
    first = venue.split(",")[0].strip()
    return similarity(city, first)


def _strip_trailing_state_token(text: str) -> str:
    """Drop a trailing US/CA state code/name from a venue string before name compare."""
    parts = (text or "").split()
    if not parts:
        return ""
    last = parts[-1]
    if (len(last) == 2 and last in _VALID_STATE_ABBREVS) or last in _US_CA_STATE_CODES:
        parts = parts[:-1]
    elif len(parts) >= 2:
        joined = " ".join(parts[-2:])
        if joined in _US_CA_STATE_CODES:
            parts = parts[:-2]
    return " ".join(parts)


def score_show_match(
    shr_name: str,
    shr_date: str,
    shr_location: str,
    shr_state: str,
    cand_name: str,
    cand_date: Optional[str],
    cand_location: Optional[str],
    cand_state: Optional[str],
    cand_start: Any = None,
    cand_end: Any = None,
) -> Optional[float]:
    """
    Composite score for SHR vs a ShowList candidate.
    Returns None if hard gates fail (name / state / date).

    Name can match either the HSO ShowName or the HSO ShowLocation â€” SHR often
    uses venue/fair names (e.g. "Kentucky State Fair") while HSO uses the
    official show title ("WORLDS CHAMPIONSHIP HORSE SHOW") and puts the fair
    name in ShowLocation.
    """
    name_vs_name = show_name_similarity(shr_name, cand_name)
    loc_as_name = _strip_trailing_state_token(normalize_show_name(cand_location or ""))
    # Re-join through normalize_show_name path: location already uppercased-ish
    name_vs_loc = show_name_similarity(shr_name, loc_as_name) if loc_as_name else 0.0
    # Also try raw location (handles "KENTUCKY STATE FAIR, KY")
    name_vs_loc = max(
        name_vs_loc,
        show_name_similarity(shr_name, cand_location or ""),
    )
    name_score = max(name_vs_name, name_vs_loc)
    matched_via_location = name_vs_loc >= name_vs_name and name_vs_loc >= SHOW_NAME_MATCH_MIN_CONFIRMED

    shr_code = normalize_state_code(shr_state)
    cand_code = normalize_state_code(cand_state)
    if shr_code and cand_code and shr_code != cand_code:
        return None
    state_score = 1.0 if (shr_code and cand_code and shr_code == cand_code) else 0.0

    shr_range = parse_show_date_range(shr_date)
    cand_range = parse_show_date_range(cand_date, cand_start, cand_end)
    if shr_range and cand_range and not dates_overlap(shr_range, cand_range):
        return None
    date_score = 1.0 if (shr_range and cand_range and dates_overlap(shr_range, cand_range)) else 0.0

    # Strong confirmation (same state + overlapping dates) allows looser names like
    # "Monarch National Championship" vs "Monarch Show Series Championship",
    # and venue-title swaps like "Kentucky State Fair" vs Worlds Championship.
    confirmed = bool(state_score and date_score)
    name_min = SHOW_NAME_MATCH_MIN_CONFIRMED if confirmed else SHOW_NAME_MATCH_MIN
    # Location-as-name matches require date+state confirmation (otherwise too loose)
    if matched_via_location and name_vs_loc > name_vs_name:
        if not confirmed:
            return None
        name_min = SHOW_NAME_MATCH_MIN_CONFIRMED
    if name_score < name_min:
        return None
    if confirmed:
        # Require at least one meaningful shared token (â‰¥5 chars) against the
        # field we actually matched (official name or HSO location).
        ta = set(normalize_show_name(shr_name).split())
        if matched_via_location and name_vs_loc >= name_vs_name:
            tb = set(normalize_show_name(cand_location or "").split())
        else:
            tb = set(normalize_show_name(cand_name).split())
        shared_strong = [t for t in (ta & tb) if len(t) >= 5]
        if not shared_strong:
            return None

    loc_score = location_match_score(shr_location, cand_location)
    # Boost when SHR title is clearly the HSO venue name
    if matched_via_location and name_vs_loc >= 0.9:
        loc_score = max(loc_score, name_vs_loc)
    return 0.70 * name_score + 0.15 * date_score + 0.10 * state_score + 0.05 * loc_score


def find_best_hso_show_match(
    conn,
    show_name: str,
    year: Optional[int],
    show_date: str,
    location: str,
    state: str,
    exclude_shr_id: Optional[str] = None,
) -> Optional[Tuple[int, float]]:
    """
    Find best HSO ShowList row (has ShowGUID) for an SHR show.
    Returns (ShowListID, score) or None.
    """
    cursor = conn.cursor()
    try:
        if year:
            cursor.execute(
                """
                SELECT ID, ShowName, ShowDate, ShowLocation, StateProv,
                       StartDate, EndDate, ShowGUID, SHRShowID
                FROM sResults.ShowList
                WHERE Year = ?
                  AND ShowGUID IS NOT NULL AND ShowGUID <> ''
                """,
                year,
            )
        else:
            cursor.execute(
                """
                SELECT ID, ShowName, ShowDate, ShowLocation, StateProv,
                       StartDate, EndDate, ShowGUID, SHRShowID
                FROM sResults.ShowList
                WHERE ShowGUID IS NOT NULL AND ShowGUID <> ''
                """
            )
        best_id, best_score = None, 0.0
        for row in cursor.fetchall():
            (
                sid,
                sname,
                sdate,
                sloc,
                sstate,
                start,
                end,
                _guid,
                existing_shr,
            ) = row
            existing_shr = (existing_shr or "").strip()
            # Skip HSO rows already linked to a different SHR show
            if existing_shr and str(existing_shr) != str(exclude_shr_id or ""):
                continue
            score = score_show_match(
                show_name,
                show_date,
                location,
                state,
                sname or "",
                sdate,
                sloc,
                sstate,
                start,
                end,
            )
            if score is not None and score > best_score:
                best_score, best_id = score, sid
        if best_id is not None:
            return best_id, best_score
        return None
    finally:
        cursor.close()


def extract_sid(url: str) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(urljoin(BASE_URL, url))
    qs = parse_qs(parsed.query)
    for key in ("sid", "cid"):
        if key in qs and qs[key]:
            return qs[key][0]
    return None


def absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)


def credentials_from_env_or_prompt() -> Tuple[str, str]:
    email = os.environ.get("SHR_EMAIL", "").strip()
    password = os.environ.get("SHR_PASSWORD", "")
    if email and password:
        print_with_timestamp(f"Using SHR credentials from environment ({email})")
        return email, password
    print_with_timestamp("SHR credentials not in environment; prompting")
    email = input("Saddle Horse Report email: ").strip()
    password = getpass.getpass("Saddle Horse Report password: ")
    if not email or not password:
        raise SystemExit("Email and password are required")
    return email, password


def get_db_connection():
    hostname = socket.gethostname().upper()
    use_windows_auth = hostname == "LDAHSAR"
    if use_windows_auth:
        print_with_timestamp(f"[INFO] Running on {hostname}, using Windows authentication")
        password = None
    else:
        password = getpass.getpass("Enter SQL Server password for sa user: ")
    drivers = [
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 18 for SQL Server",
        "SQL Server",
        "SQL Server Native Client 11.0",
    ]
    for driver in drivers:
        try:
            if use_windows_auth:
                conn_str = (
                    f"DRIVER={{{driver}}};SERVER=LDAHSAR\\SQLEXPRESS;"
                    "DATABASE=HorseShows;Trusted_Connection=yes;"
                )
            else:
                conn_str = (
                    f"DRIVER={{{driver}}};SERVER=LDAHSAR\\SQLEXPRESS;"
                    f"DATABASE=HorseShows;UID=sa;PWD={password};"
                )
            conn = pyodbc.connect(conn_str)
            print_with_timestamp(f"[OK] Connected via {driver}")
            return conn
        except Exception as e:
            if driver == drivers[-1]:
                raise
    raise RuntimeError("No ODBC driver worked")


def ensure_schema(conn) -> None:
    cursor = conn.cursor()
    statements = [
        """
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='ShowList' AND COLUMN_NAME='SHRShowID'
        )
        BEGIN
            ALTER TABLE sResults.ShowList ADD SHRShowID NVARCHAR(200) NULL;
        END
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes WHERE name='IX_ShowList_SHRShowID'
              AND object_id=OBJECT_ID('sResults.ShowList')
        )
        CREATE INDEX IX_ShowList_SHRShowID ON sResults.ShowList(SHRShowID);
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='Horse' AND COLUMN_NAME='BroodmareSire'
        )
        ALTER TABLE sResults.Horse ADD BroodmareSire NVARCHAR(200) NULL;
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='Horse' AND COLUMN_NAME='BreederID'
        )
        ALTER TABLE sResults.Horse ADD BreederID INT NULL;
        """,
        """
        IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name='FK_Horse_Breeder')
        ALTER TABLE sResults.Horse ADD CONSTRAINT FK_Horse_Breeder
            FOREIGN KEY (BreederID) REFERENCES sResults.Competitors(ID);
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='ShowJudge'
        )
        BEGIN
            CREATE TABLE sResults.ShowJudge (
                ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ShowListID INT NOT NULL,
                JudgeName NVARCHAR(500) NOT NULL,
                JudgeRole NVARCHAR(200) NULL,
                SortOrder INT NULL,
                CreatedDate DATETIME NOT NULL CONSTRAINT DF_ShowJudge_CreatedDate DEFAULT GETDATE(),
                UpdatedDate DATETIME NULL,
                CONSTRAINT FK_ShowJudge_ShowList FOREIGN KEY (ShowListID)
                    REFERENCES sResults.ShowList(ID)
            );
            CREATE INDEX IX_ShowJudge_ShowListID ON sResults.ShowJudge(ShowListID);
            CREATE UNIQUE INDEX UX_ShowJudge_Show_Name ON sResults.ShowJudge(ShowListID, JudgeName);
        END
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='ShowResults_JudgeCard'
        )
        BEGIN
            CREATE TABLE sResults.ShowResults_JudgeCard (
                ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ShowResultsID INT NOT NULL,
                ShowJudgeID INT NOT NULL,
                Entry NVARCHAR(50) NULL,
                Place INT NULL,
                CreatedDate DATETIME NOT NULL
                    CONSTRAINT DF_ShowResults_JudgeCard_CreatedDate DEFAULT GETDATE(),
                UpdatedDate DATETIME NULL,
                CONSTRAINT FK_JudgeCard_ShowResults FOREIGN KEY (ShowResultsID)
                    REFERENCES sResults.ShowResults(ID),
                CONSTRAINT FK_JudgeCard_ShowJudge FOREIGN KEY (ShowJudgeID)
                    REFERENCES sResults.ShowJudge(ID)
            );
            CREATE UNIQUE INDEX UX_JudgeCard_Result_Judge
                ON sResults.ShowResults_JudgeCard(ShowResultsID, ShowJudgeID);
            CREATE INDEX IX_JudgeCard_ShowJudgeID ON sResults.ShowResults_JudgeCard(ShowJudgeID);
            CREATE INDEX IX_JudgeCard_Entry ON sResults.ShowResults_JudgeCard(Entry);
        END
        """,
        """
        IF EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='ShowResults_JudgeCard'
        )
        AND NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='ShowResults_JudgeCard'
              AND COLUMN_NAME='Entry'
        )
        BEGIN
            ALTER TABLE sResults.ShowResults_JudgeCard ADD Entry NVARCHAR(50) NULL;
            -- Place Entry before Place for readability (logical order via view/docs;
            -- SQL Server appends physically; OK)
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_JudgeCard_Entry'
                  AND object_id = OBJECT_ID('sResults.ShowResults_JudgeCard')
            )
                CREATE INDEX IX_JudgeCard_Entry ON sResults.ShowResults_JudgeCard(Entry);
        END
        """,
    ]
    for sql in statements:
        cursor.execute(sql)
        conn.commit()
    cursor.close()
    print_with_timestamp("[OK] Schema ensured for SHR tables/columns")


def headed_login_cookies(email: str, password: str, attempts: int = 3) -> List[dict]:
    """Login with headed UC (required for reCAPTCHA) and return cookies."""
    last_err = "unknown"
    for attempt in range(1, attempts + 1):
        print_with_timestamp(
            f"Logging in via headed undetected-chromedriver (reCAPTCHA) attempt {attempt}/{attempts}..."
        )
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1400,1000")
        os.makedirs(UC_PROFILE_DIR, exist_ok=True)
        options.add_argument(f"--user-data-dir={UC_PROFILE_DIR}")
        driver = uc.Chrome(options=options, headless=False, version_main=CHROME_MAJOR)
        try:
            driver.get(LOGIN_URL)
            time.sleep(4 + attempt)
            # Light mouse activity helps reCAPTCHA v3 scoring.
            try:
                driver.execute_script(
                    "window.scrollBy(0, 120); "
                    "document.dispatchEvent(new MouseEvent('mousemove', "
                    "{clientX: 180, clientY: 220, bubbles: true}));"
                )
            except Exception:
                pass
            email_el = driver.find_element(By.ID, "plcBody_txtEmail")
            pwd_el = driver.find_element(By.ID, "plcBody_txtPassword")
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();",
                email_el,
            )
            time.sleep(0.5)
            try:
                email_el.click()
                email_el.clear()
                email_el.send_keys(email)
                time.sleep(0.35)
                pwd_el.click()
                pwd_el.clear()
                pwd_el.send_keys(password)
            except Exception:
                driver.execute_script(
                    """
                    arguments[0].value = arguments[2];
                    arguments[1].value = arguments[3];
                    arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
                    arguments[1].dispatchEvent(new Event('input', {bubbles:true}));
                    """,
                    email_el,
                    pwd_el,
                    email,
                    password,
                )
            # Prefer the page's own on-load grecaptcha token; refresh only if missing/stale.
            token = ""
            for _wait in range(20):
                token = driver.execute_script(
                    "var el=document.getElementById('g_recaptcha_response');"
                    "return el && el.value ? el.value : '';"
                ) or ""
                if len(token) > 20:
                    break
                time.sleep(0.5)
            if len(token) <= 20:
                token = driver.execute_async_script(
                    """
                    var siteKey = arguments[0];
                    var done = arguments[arguments.length - 1];
                    var finish = function (v) { try { done(v); } catch (e) {} };
                    if (typeof grecaptcha === 'undefined') {
                        finish('ERR:grecaptcha missing');
                        return;
                    }
                    grecaptcha.ready(function () {
                        grecaptcha.execute(siteKey, { action: 'forms' }).then(function (tok) {
                            var el = document.getElementById('g_recaptcha_response');
                            if (el) { el.value = tok; }
                            finish(tok);
                        }).catch(function (e) { finish('ERR:' + e); });
                    });
                    """,
                    RECAPTCHA_SITE_KEY,
                )
            if not token or str(token).startswith("ERR:") or len(str(token)) < 20:
                last_err = f"recaptcha token failed: {token!r}"
                print_with_timestamp(f"[WARNING] Login attempt {attempt} failed: {last_err}")
                time.sleep(30 * attempt)
                continue
            time.sleep(0.8)
            btn = driver.find_element(By.ID, "plcBody_btnLogin")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.4)
            # btnLogin is an <a href="javascript:WebForm_DoPostBack...">; navigate that path.
            try:
                href = btn.get_attribute("href") or ""
                if href.startswith("javascript:"):
                    driver.execute_script(href[len("javascript:") :])
                else:
                    btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(7)
            page = driver.page_source.lower()
            try:
                err = driver.find_element(By.ID, "error").text.strip()
            except Exception:
                err = ""
            if "you are not logged in" in page or "security check failed" in page or err:
                last_err = err or "still logged out"
                print_with_timestamp(f"[WARNING] Login attempt {attempt} failed: {last_err}")
                # Stop early on security-check lockouts so we don't deepen the ban.
                if "security check failed" in (err or page).lower() and attempt >= 2:
                    print_with_timestamp(
                        "[WARNING] reCAPTCHA lockout likely; aborting further attempts this run"
                    )
                    break
                time.sleep(45 * attempt)
                continue
            cookies = driver.get_cookies()
            os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
            with open(COOKIE_PATH, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print_with_timestamp(f"[OK] Logged in; saved {len(cookies)} cookies")
            return cookies
        finally:
            try:
                driver.quit()
            except Exception:
                pass
    raise SystemExit(f"Login failed after {attempts} attempts: {last_err}")

def setup_headless_with_cookies(cookies: List[dict]) -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=opts)
    driver.get(BASE_URL + "/")
    time.sleep(1)
    for c in cookies:
        cookie = {k: c[k] for k in ("name", "value", "path") if k in c}
        if "expiry" in c:
            cookie["expiry"] = int(c["expiry"])
        if "secure" in c:
            cookie["secure"] = c["secure"]
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
    driver.get(RESULTS_URL)
    time.sleep(2)
    if "you are not logged in" in driver.page_source.lower():
        raise SystemExit("Cookie session is not authenticated")
    print_with_timestamp("[OK] Headless session authenticated via cookies")
    return driver


def soup_of(driver) -> BeautifulSoup:
    return BeautifulSoup(driver.page_source, "html.parser")


def collect_result_years(driver) -> List[Tuple[int, str]]:
    driver.get(RESULTS_URL)
    time.sleep(1.5)
    save_driver_page(driver, datetime.now().year, "resultshome", "results_index")
    soup = soup_of(driver)
    years: Dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = absolute_url(a["href"])
        if re.fullmatch(r"\d{4}", text) and "year=" in href:
            years[int(text)] = href
    # oldest -> newest per user request for Other Years first, then explicit
    ordered = sorted(years.items(), key=lambda x: x[0])
    print_with_timestamp(f"[DEBUG] Result years: {[y for y, _ in ordered]}")
    return [(y, u) for y, u in ordered]


def collect_shows_for_year(driver, year: int, year_url: str) -> List[Dict[str, str]]:
    driver.get(year_url)
    time.sleep(1.5)
    save_driver_page(driver, year, "yearlist", f"results_year_{year}")
    soup = soup_of(driver)
    shows = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        sid = extract_sid(href)
        if not sid:
            continue
        name = a.get_text(" ", strip=True)
        if not name or name.lower() == "show results":
            continue
        # year list uses results?sid= ; judges list uses judges?cid=
        if "results?" not in href.replace("/results?", "results?") and "sid=" not in href:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        shows.append(
            {
                "name": name,
                "sid": sid,
                "url": absolute_url(f"results?sid={sid}"),
                "judges_url": absolute_url(f"judges?classbased=true&cid={sid}"),
                "year": str(year),
            }
        )
    # Prefer table ContentText links only â€” filter if we got nav noise
    shows = [s for s in shows if s["name"] and not re.fullmatch(r"\d{4}", s["name"])]
    print_with_timestamp(f"  Year {year}: {len(shows)} show(s)")
    return shows


def parse_show_meta(soup: BeautifulSoup) -> Dict[str, Any]:
    text = soup.get_text("\n", strip=True)
    info: Dict[str, Any] = {
        "show_name": "",
        "location": "",
        "state": "",
        "show_date": "",
        "year": None,
        "judges": [],
    }
    h1 = soup.find(["h1", "h2"])
    # Title often in page title: "Monarch ... Show Results |"
    title = soup.title.get_text(strip=True) if soup.title else ""
    m = re.match(r"(.+?)\s+Show Results", title)
    if m:
        info["show_name"] = m.group(1).strip()
    loc = re.search(r"Location:\s*(.+)", text)
    if loc:
        loc_line = loc.group(1).split("\n")[0].strip()
        info["location"] = loc_line
        if "," in loc_line:
            parts = [p.strip() for p in loc_line.split(",")]
            info["location"] = parts[0]
            info["state"] = parts[-1]
    date = re.search(r"Date:\s*(.+)", text)
    if date:
        info["show_date"] = date.group(1).split("\n")[0].strip()
        ym = re.search(r"(20\d{2}|19\d{2})", info["show_date"])
        if ym:
            info["year"] = int(ym.group(1))
    judges = re.search(r"Judge\(s\):\s*(.+)", text)
    if judges:
        chunk = judges.group(1).split("\n")[0]
        for i, name in enumerate(re.split(r",\s*", chunk)):
            name = name.strip()
            if name:
                info["judges"].append({"name": name, "role": None, "sort_order": i + 1})
    if not info["show_name"]:
        # first substantial heading in body
        for el in soup.find_all(["h1", "h2", "strong", "b"]):
            t = el.get_text(" ", strip=True)
            if t and "judge" not in t.lower() and len(t) > 3:
                info["show_name"] = t
                break
    return info


def _is_na_label(value: Optional[str]) -> bool:
    v = (value or "").strip().upper()
    return (not v) or v in {"N/A", "NA", "NONE", "-", "--"}


def _strip_eq_marker(name: str) -> str:
    return re.sub(r"\s*\(eq\)\s*$", "", name or "", flags=re.I).strip()


def normalize_shr_entry_identity(
    horse: str,
    rider: str,
    owner: str,
    class_name: Optional[str] = None,
    horse_url: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    SHR Academy/Equitation rows put the rider in the Horse column with Rider/Owner
    as literal 'n/a' (often still linked as ?horse=). Treat that as Rider, not Horse.
    """
    horse = (horse or "").strip()
    rider = (rider or "").strip()
    owner = (owner or "").strip()
    cname = (class_name or "").upper()
    looks_eq_class = any(
        tok in cname
        for tok in (
            "ACADEMY",
            "EQUITATION",
            "SHOWMANSHIP",
            "HORSEMANSHIP",
            "PATTERN",
        )
    )
    has_eq_marker = bool(re.search(r"\(eq\)\s*$", horse, re.I))
    if (
        horse
        and _is_na_label(rider)
        and (_is_na_label(owner) or looks_eq_class or has_eq_marker)
    ):
        return {
            "horse": "",
            "horse_url": None,
            "rider": _strip_eq_marker(horse),
            "owner": "" if _is_na_label(owner) else owner,
        }
    return {
        "horse": horse,
        "horse_url": horse_url,
        "rider": "" if _is_na_label(rider) else rider,
        "owner": "" if _is_na_label(owner) else owner,
    }


def parse_results_classes(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Parse the big results table: class banner rows + Pl/Horse/Rider/Owner rows."""
    classes: List[Dict[str, Any]] = []
    table = soup.find("table")
    if not table:
        return classes
    current: Optional[Dict[str, Any]] = None
    accepting_entries = False
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        texts = [c.get_text(" ", strip=True) for c in cells]
        if not texts:
            continue
        joined = " ".join(texts).strip()
        # Class header rows often span and include HPS Category
        if len(cells) == 1 or (len(cells) <= 2 and "HPS Category" in joined):
            class_name = texts[0]
            class_name = re.sub(r"\s*HPS Category.*$", "", class_name, flags=re.I).strip()
            if class_name and class_name.upper() not in ("PL", "HORSE", "RIDER", "OWNER"):
                # Ignore judge-name banner leftovers like "PL Tammie Conatser..."
                if class_name.upper().startswith("PL "):
                    current = None
                    accepting_entries = False
                    continue
                current = {"class_name": class_name, "class_number": None, "entries": []}
                classes.append(current)
                accepting_entries = False
            continue
        upper = [t.upper() for t in texts]
        # Official placing header â€” only then accept Horse/Rider/Owner rows
        if texts[:4] == ["Pl", "Horse", "Rider", "Owner"] or (
            len(texts) >= 4 and upper[0] == "PL" and "HORSE" in upper and "RIDER" in upper
        ):
            accepting_entries = bool(current)
            continue
        # Judge-card ranking header (PL | judges... | Final) â€” do not treat as entries
        if (
            len(texts) >= 3
            and upper[0] == "PL"
            and upper[-1] == "FINAL"
            and "HORSE" not in upper
        ):
            accepting_entries = False
            continue
        if not current or not accepting_entries:
            continue
        if not re.fullmatch(r"\d+", texts[0] or ""):
            continue
        if len(texts) < 2:
            continue
        # Horse name must not look like a bare entry number (judge-card bleed)
        horse = texts[1] if len(texts) > 1 else ""
        if re.fullmatch(r"\d+", horse or ""):
            continue
        place = texts[0]
        rider = texts[2] if len(texts) > 2 else ""
        owner = texts[3] if len(texts) > 3 else ""
        horse_url = None
        for a in tr.find_all("a", href=True):
            if "horse=" in a["href"]:
                horse_url = absolute_url(a["href"])
                if not horse:
                    horse = a.get_text(strip=True)
                break
        identity = normalize_shr_entry_identity(
            horse,
            rider,
            owner,
            class_name=current.get("class_name"),
            horse_url=horse_url,
        )
        if not identity["horse"] and not identity["rider"]:
            continue
        current["entries"].append(
            {
                "place": place,
                "entry": "",  # results pages have no entry #; judge cards do
                "horse": identity["horse"] or "",
                "horse_url": identity["horse_url"],
                "rider": identity["rider"] or "",
                "owner": identity["owner"] or "",
            }
        )
    # Drop class banners that never received a Pl/Horse/Rider/Owner block
    return [c for c in classes if c.get("entries")]


def parse_horse_detail(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    text = soup.get_text("\n", strip=True)
    labels = (
        "Current Owner",
        "Sire",
        "Dam",
        "Broodmare Sire",
        "Breeder",
        "Sex",
        "Foaling Date",
    )

    def value_for(label: str) -> Optional[str]:
        m = re.search(rf"{re.escape(label)}\s*:\s*(.*)", text, re.I)
        if not m:
            return None
        val = m.group(1).split("\n")[0].strip()
        # Truncate if the next label was jammed onto the same line.
        val = re.split(
            r"\s+(?:" + "|".join(re.escape(x) for x in labels) + r")\s*:",
            val,
            maxsplit=1,
            flags=re.I,
        )[0].strip()
        val = re.sub(r"\s*\(owner history\)\s*$", "", val, flags=re.I).strip()
        if not val or val.endswith(":") or val.lower() in {x.lower() for x in labels}:
            return None
        if re.fullmatch(r"20\d{2}", val):
            return None
        return val[:500]

    return {
        "owner": value_for("Current Owner"),
        "sire": value_for("Sire"),
        "dam": value_for("Dam"),
        "broodmare_sire": value_for("Broodmare Sire"),
        "breeder": value_for("Breeder"),
        "sex": value_for("Sex"),
        "dob": value_for("Foaling Date"),
    }


def parse_judge_card_classes(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Judge card pages nest many small ranking tables inside one large table.
    Walk top-level table rows (or leaf ranking tables) and collect:
      PL | JudgeA | JudgeB | ... | Final
      1  | 566    | 566    | ... | 566
    cell values are EntryNumbers for that place under each judge.
    """
    classes: List[Dict[str, Any]] = []
    last_class_name = ""

    def is_ranking_header(cells: List[str]) -> bool:
        if len(cells) < 3 or len(cells) > 12:
            return False
        if cells[0].upper() != "PL" or cells[-1].upper() != "FINAL":
            return False
        judges = cells[1:-1]
        return bool(judges) and all(j and not re.fullmatch(r"\d+", j) for j in judges)

    def consume_ranking(rows, header_idx: int, class_name: str) -> None:
        cells = [c.get_text(" ", strip=True) for c in rows[header_idx].find_all(["td", "th"])]
        judges = cells[1:-1]
        cards = []
        for tr in rows[header_idx + 1 :]:
            row_cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not row_cells:
                continue
            upper = [c.upper() for c in row_cells]
            if upper[:4] == ["PL", "HORSE", "RIDER", "OWNER"] or (
                upper[0] == "PL" and "HORSE" in upper
            ):
                break
            if is_ranking_header(row_cells):
                break
            if len(row_cells) == 1:
                break
            if not re.fullmatch(r"\d+", row_cells[0] or ""):
                continue
            place = int(row_cells[0])
            final_entry = row_cells[-1].strip() if len(row_cells) > len(judges) + 1 else ""
            if not re.fullmatch(r"\d+", final_entry or ""):
                final_entry = ""
            for j_idx, judge_name in enumerate(judges):
                if j_idx + 1 >= len(row_cells):
                    break
                entry = row_cells[j_idx + 1].strip()
                if not re.fullmatch(r"\d+", entry or ""):
                    continue
                cards.append(
                    {
                        "judge_name": judge_name,
                        "entry": entry,
                        # Official placing entry for ShowResults.Entry merge
                        "final": final_entry or entry,
                        "place": place,
                    }
                )
        if class_name and cards:
            classes.append({"class_name": class_name, "cards": cards})

    # Prefer the outermost large results table; fall back to all tables.
    top_tables = [t for t in soup.find_all("table") if not t.find_parent("table")]
    tables = top_tables or soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        i = 0
        while i < len(rows):
            cells = [c.get_text(" ", strip=True) for c in rows[i].find_all(["td", "th"])]
            if len(cells) == 1:
                name = re.sub(r"\s*HPS Category.*$", "", cells[0], flags=re.I).strip()
                if name and not name.upper().startswith("PL "):
                    last_class_name = name
                i += 1
                continue
            if is_ranking_header(cells):
                consume_ranking(rows, i, last_class_name)
                # advance past this block
                i += 1
                while i < len(rows):
                    nxt = [c.get_text(" ", strip=True) for c in rows[i].find_all(["td", "th"])]
                    if len(nxt) == 1 or is_ranking_header(nxt) or (
                        nxt and nxt[0].upper() == "PL" and "HORSE" in [x.upper() for x in nxt]
                    ):
                        break
                    if not nxt or not re.fullmatch(r"\d+", nxt[0] or ""):
                        i += 1
                        break
                    i += 1
                continue
            i += 1
    return classes


def get_or_create_competitor(conn, name: str, role: str) -> Optional[int]:
    """Map a person into Competitors. role is Rider, Owner, or Trainer."""
    if not name or not name.strip() or role not in ("Rider", "Owner", "Trainer"):
        return None
    name = name.strip()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT ID FROM sResults.Competitors
            WHERE Rider = ? OR Owner = ? OR Trainer = ?
            """,
            name,
            name,
            name,
        )
        row = cursor.fetchone()
        if row:
            competitor_id = row[0]
            cursor.execute(
                f"""
                UPDATE sResults.Competitors
                SET {role} = ?, UpdatedDate = GETDATE()
                WHERE ID = ? AND {role} IS NULL
                """,
                name,
                competitor_id,
            )
            conn.commit()
            return competitor_id
        values = {"Rider": None, "Owner": None, "Trainer": None}
        values[role] = name
        cursor.execute(
            """
            INSERT INTO sResults.Competitors (Rider, Owner, Trainer)
            OUTPUT INSERTED.ID VALUES (?, ?, ?)
            """,
            values["Rider"],
            values["Owner"],
            values["Trainer"],
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return new_id
    except Exception as e:
        print_with_timestamp(f"  [WARNING] Competitor ({role}) upsert failed: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()


def get_or_create_competitor_owner(conn, name: str) -> Optional[int]:
    """Breeders and owners are stored in Competitors.Owner."""
    return get_or_create_competitor(conn, name, "Owner")


def find_or_insert_show(
    conn,
    show_name: str,
    year: Optional[int],
    show_date: str,
    location: str,
    state: str,
    shr_id: str,
) -> int:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ID FROM sResults.ShowList WHERE SHRShowID = ?", shr_id)
        row = cursor.fetchone()
        if row:
            return row[0]

        match = find_best_hso_show_match(
            conn,
            show_name=show_name,
            year=year,
            show_date=show_date or "",
            location=location or "",
            state=state or "",
            exclude_shr_id=shr_id,
        )
        if match:
            best_id, best_score = match
            state_abbr = normalize_state_code(state)
            cursor.execute(
                """
                UPDATE sResults.ShowList
                SET SHRShowID = COALESCE(NULLIF(SHRShowID, ''), ?),
                    ShowLocation = COALESCE(NULLIF(ShowLocation, ''), ?),
                    ShowDate = COALESCE(NULLIF(ShowDate, ''), ?),
                    StateProv = COALESCE(NULLIF(StateProv, ''), ?),
                    UpdatedDate = GETDATE()
                WHERE ID = ?
                """,
                shr_id,
                location or None,
                show_date or None,
                state_abbr,  # abbreviation only; never write SHR full name onto HSO
                best_id,
            )
            conn.commit()
            print_with_timestamp(
                f"  Matched ShowList ID={best_id} score={best_score:.2f} "
                f"SHRShowID={shr_id} name='{show_name}'"
            )
            return best_id

        if not year:
            year = datetime.now().year
        # SHR-only insert: keep SHR's state text as provided (full name OK here)
        cursor.execute(
            """
            INSERT INTO sResults.ShowList
                (Year, ShowName, ShowDate, ShowLocation, StateProv, GoverningBody, SHRShowID)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            year,
            show_name[:500],
            show_date or None,
            location or None,
            state or None,
            "SHR",
            shr_id,
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        print_with_timestamp(f"  Inserted ShowList ID={new_id} '{show_name}'")
        return new_id
    finally:
        cursor.close()


def find_or_insert_class(conn, show_list_id: int, class_name: str) -> int:
    cursor = conn.cursor()
    try:
        class_name = (class_name or "").strip()
        cursor.execute(
            """
            SELECT ID FROM sResults.ShowClass
            WHERE ShowListID = ? AND ClassName = ?
            """,
            show_list_id,
            class_name[:500],
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor.execute(
            "SELECT ID, Class, ClassName FROM sResults.ShowClass WHERE ShowListID = ?",
            show_list_id,
        )
        best_id, best_score = None, 0.0
        for rid, _cnum, cname in cursor.fetchall():
            score = similarity(class_name, cname or "")
            if score > best_score:
                best_score, best_id = score, rid
        # Only fuzzy-match when names are nearly identical; prefer insert otherwise
        # so distinct SHR classes are not collapsed (which duplicates Place values).
        if best_id and best_score >= 0.97:
            return best_id
        cursor.execute(
            """
            INSERT INTO sResults.ShowClass (ShowListID, Class, ClassName, Entries, Placings)
            OUTPUT INSERTED.ID VALUES (?, '', ?, 0, 0)
            """,
            show_list_id,
            class_name[:500],
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        print_with_timestamp(f"    Inserted ShowClass ID={new_id} '{class_name}'")
        return new_id
    finally:
        cursor.close()


def get_or_create_horse_fill_nulls(conn, horse_name: str, details: Dict[str, Optional[str]]) -> Optional[int]:
    if not horse_name or not horse_name.strip():
        return None
    horse_name = horse_name.strip()
    cursor = conn.cursor()
    try:
        owner_id = get_or_create_competitor_owner(conn, details.get("owner") or "")
        breeder_id = get_or_create_competitor_owner(conn, details.get("breeder") or "")
        cursor.execute(
            """
            SELECT ID, OwnerID, Sire, Dam, BroodmareSire, BreederID, DOB, Sex
            FROM sResults.Horse WHERE HorseName = ?
            """,
            horse_name,
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                """
                INSERT INTO sResults.Horse
                    (HorseName, OwnerID, Sire, Dam, BroodmareSire, BreederID, DOB, Sex)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                horse_name,
                owner_id,
                details.get("sire"),
                details.get("dam"),
                details.get("broodmare_sire"),
                breeder_id,
                details.get("dob"),
                details.get("sex"),
            )
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
        horse_id, cur_owner, cur_sire, cur_dam, cur_bms, cur_breeder, cur_dob, cur_sex = row
        sets, params = [], []
        if owner_id and not cur_owner:
            sets.append("OwnerID = ?"); params.append(owner_id)
        if details.get("sire") and not cur_sire and details["sire"] not in ("Dam:", "Sire:"):
            sets.append("Sire = ?"); params.append(details["sire"])
        if details.get("dam") and not cur_dam and not details["dam"].endswith(":"):
            sets.append("Dam = ?"); params.append(details["dam"])
        if details.get("broodmare_sire") and not cur_bms and not re.fullmatch(r"20\d{2}", details["broodmare_sire"] or ""):
            sets.append("BroodmareSire = ?"); params.append(details["broodmare_sire"])
        if breeder_id and not cur_breeder:
            sets.append("BreederID = ?"); params.append(breeder_id)
        if details.get("dob") and not cur_dob:
            sets.append("DOB = ?"); params.append(details["dob"])
        if details.get("sex") and not cur_sex:
            sets.append("Sex = ?"); params.append(details["sex"])
        if sets:
            sets.append("UpdatedDate = GETDATE()")
            params.append(horse_id)
            cursor.execute(f"UPDATE sResults.Horse SET {', '.join(sets)} WHERE ID = ?", *params)
            conn.commit()
        return horse_id
    except Exception as e:
        print_with_timestamp(f"    [WARNING] Horse upsert failed for {horse_name}: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()


def get_or_create_show_result(
    conn,
    show_class_id: int,
    entry_number: Optional[str],
    place: Optional[int],
    horse_id: Optional[int],
    rider_id: Optional[int] = None,
) -> Optional[int]:
    """
    Upsert ShowResults without duplicating a placing.
    Prefer Entry, then Place+Horse, then merge place rows that only have one side filled.
    """
    cursor = conn.cursor()
    try:
        entry_number = (entry_number or "").strip() or None
        result_id = None

        if entry_number:
            cursor.execute(
                """
                SELECT ID FROM sResults.ShowResults
                WHERE ShowClassID = ? AND Entry = ?
                """,
                show_class_id,
                entry_number,
            )
            row = cursor.fetchone()
            if row:
                result_id = row[0]

        if result_id is None and place is not None and horse_id:
            cursor.execute(
                """
                SELECT ID FROM sResults.ShowResults
                WHERE ShowClassID = ? AND Place = ? AND HorseID = ?
                """,
                show_class_id,
                place,
                horse_id,
            )
            row = cursor.fetchone()
            if row:
                result_id = row[0]

        # Attach Entry onto an existing placing that already has a horse
        if result_id is None and place is not None and entry_number and not horse_id:
            cursor.execute(
                """
                SELECT ID FROM sResults.ShowResults
                WHERE ShowClassID = ? AND Place = ? AND HorseID IS NOT NULL
                  AND (Entry IS NULL OR Entry = '')
                """,
                show_class_id,
                place,
            )
            row = cursor.fetchone()
            if row:
                result_id = row[0]

        # Attach Horse/Rider onto an existing Entry placeholder for this place
        if result_id is None and place is not None and horse_id and not entry_number:
            cursor.execute(
                """
                SELECT ID FROM sResults.ShowResults
                WHERE ShowClassID = ? AND Place = ? AND HorseID IS NULL
                  AND Entry IS NOT NULL AND Entry <> ''
                """,
                show_class_id,
                place,
            )
            row = cursor.fetchone()
            if row:
                result_id = row[0]

        if result_id is None:
            cursor.execute(
                """
                INSERT INTO sResults.ShowResults
                    (ShowClassID, Place, Entry, HorseID, RiderID)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, ?)
                """,
                show_class_id,
                place,
                entry_number,
                horse_id,
                rider_id,
            )
            result_id = cursor.fetchone()[0]
            conn.commit()
            return result_id

        sets, params = [], []
        if entry_number:
            sets.append("Entry = COALESCE(NULLIF(Entry, ''), ?)")
            params.append(entry_number)
        if horse_id:
            sets.append("HorseID = COALESCE(HorseID, ?)")
            params.append(horse_id)
        if rider_id:
            sets.append("RiderID = COALESCE(RiderID, ?)")
            params.append(rider_id)
        if place is not None:
            sets.append("Place = COALESCE(Place, ?)")
            params.append(place)
        if sets:
            sets.append("UpdatedDate = GETDATE()")
            params.append(result_id)
            cursor.execute(
                f"UPDATE sResults.ShowResults SET {', '.join(sets)} WHERE ID = ?",
                *params,
            )
            conn.commit()
        return result_id
    except Exception as e:
        print_with_timestamp(f"      [WARNING] ShowResults upsert failed: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()


def upsert_judges(conn, show_list_id: int, judges: List[Dict[str, Any]]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    cursor = conn.cursor()
    try:
        for j in judges:
            name = (j.get("name") or "").strip()
            if not name:
                continue
            cursor.execute(
                "SELECT ID FROM sResults.ShowJudge WHERE ShowListID = ? AND JudgeName = ?",
                show_list_id,
                name,
            )
            row = cursor.fetchone()
            if row:
                mapping[name] = row[0]
                continue
            cursor.execute(
                """
                INSERT INTO sResults.ShowJudge (ShowListID, JudgeName, JudgeRole, SortOrder)
                OUTPUT INSERTED.ID VALUES (?, ?, ?, ?)
                """,
                show_list_id,
                name,
                j.get("role"),
                j.get("sort_order"),
            )
            mapping[name] = cursor.fetchone()[0]
            conn.commit()
    finally:
        cursor.close()
    return mapping


def upsert_judge_card(
    conn,
    show_results_id: int,
    show_judge_id: int,
    place: Optional[int],
    entry: Optional[str] = None,
) -> None:
    cursor = conn.cursor()
    try:
        entry_val = (entry or "").strip() or None
        cursor.execute(
            """
            SELECT ID, Entry, Place FROM sResults.ShowResults_JudgeCard
            WHERE ShowResultsID = ? AND ShowJudgeID = ?
            """,
            show_results_id,
            show_judge_id,
        )
        row = cursor.fetchone()
        if row:
            jc_id, cur_entry, cur_place = row
            sets, params = [], []
            if entry_val and (not cur_entry or str(cur_entry).strip() == ""):
                sets.append("Entry = ?")
                params.append(entry_val)
            elif entry_val and str(cur_entry).strip() != entry_val:
                sets.append("Entry = ?")
                params.append(entry_val)
            if place is not None and (cur_place is None or int(cur_place) != int(place)):
                sets.append("Place = ?")
                params.append(place)
            if sets:
                sets.append("UpdatedDate = GETDATE()")
                params.append(jc_id)
                cursor.execute(
                    f"UPDATE sResults.ShowResults_JudgeCard SET {', '.join(sets)} WHERE ID = ?",
                    *params,
                )
                conn.commit()
            return
        cursor.execute(
            """
            INSERT INTO sResults.ShowResults_JudgeCard
                (ShowResultsID, ShowJudgeID, Entry, Place)
            VALUES (?, ?, ?, ?)
            """,
            show_results_id,
            show_judge_id,
            entry_val,
            place,
        )
        conn.commit()
    except Exception as e:
        print_with_timestamp(f"      [WARNING] JudgeCard insert failed: {e}")
        conn.rollback()
    finally:
        cursor.close()


def show_needs_delta(conn, show_list_id: int) -> bool:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT SHRShowID FROM sResults.ShowList WHERE ID = ?", show_list_id)
        row = cursor.fetchone()
        if not row or not row[0]:
            return True
        cursor.execute("SELECT COUNT(*) FROM sResults.ShowJudge WHERE ShowListID = ?", show_list_id)
        if cursor.fetchone()[0] == 0:
            return True
        cursor.execute(
            """
            SELECT sc.ID, sc.Placings, sc.Entries, sc.NonPlacingComplete,
                   SUM(CASE WHEN sr.Place > 0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN sr.Place = 0 THEN 1 ELSE 0 END)
            FROM sResults.ShowClass sc
            LEFT JOIN sResults.ShowResults sr ON sr.ShowClassID = sc.ID
            WHERE sc.ShowListID = ?
            GROUP BY sc.ID, sc.Placings, sc.Entries, sc.NonPlacingComplete
            """,
            show_list_id,
        )
        classes = cursor.fetchall()
        if not classes:
            return True
        for _cid, placings, entries, nonplacing_complete, placing_rows, nonplacing_rows in classes:
            placings = placings or 0
            entries = entries or 0
            placing_rows = placing_rows or 0
            nonplacing_rows = nonplacing_rows or 0
            if placings > 0 and placing_rows < placings:
                return True
            if placing_rows == 0 and nonplacing_rows > 0 and placings > 0:
                return True
            if entries > placings and not nonplacing_complete:
                return True
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM sResults.ShowResults_JudgeCard jc
            INNER JOIN sResults.ShowResults sr ON jc.ShowResultsID = sr.ID
            INNER JOIN sResults.ShowClass sc ON sr.ShowClassID = sc.ID
            WHERE sc.ShowListID = ?
            """,
            show_list_id,
        )
        return cursor.fetchone()[0] == 0
    finally:
        cursor.close()


def parse_place(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def assert_still_authenticated(driver, context: str) -> None:
    """Abort rather than writing bogus ShowList rows from a logged-out page."""
    low = (driver.page_source or "").lower()
    title = (driver.title or "").lower()
    if (
        "you are not logged in" in low
        or "you are not logged in" in title
        or title.strip() == "logged out"
    ):
        raise SystemExit(f"Lost auth during {context}")


def process_show_results(driver, conn, show: Dict[str, str], horse_cache: Dict[str, dict]) -> int:
    sid = show["sid"]
    print_with_timestamp(f"Results sid={sid}: {show['name']}")
    driver.get(show["url"])
    time.sleep(1.2)
    assert_still_authenticated(driver, f"results sid={sid}")
    year_hint = int(show.get("year") or datetime.now().year)
    save_driver_page(
        driver,
        year_hint,
        "results",
        show["name"],
        sid=sid,
    )
    soup = soup_of(driver)
    meta = parse_show_meta(soup)
    show_name = meta.get("show_name") or show["name"]
    if "not logged in" in (show_name or "").lower():
        raise SystemExit(f"Lost auth during results sid={sid} (bad show title)")
    year = meta.get("year") or year_hint
    # Re-save under resolved year if it differs from the year-list hint
    if year != year_hint:
        save_driver_page(driver, year, "results", show_name, sid=sid)
    show_list_id = find_or_insert_show(
        conn,
        show_name=show_name,
        year=year,
        show_date=meta.get("show_date") or "",
        location=meta.get("location") or "",
        state=meta.get("state") or "",
        shr_id=sid,
    )
    judge_map = upsert_judges(conn, show_list_id, meta.get("judges") or [])
    classes = parse_results_classes(soup)
    print_with_timestamp(f"  classes={len(classes)} judges={len(judge_map)}")
    for cls in classes:
        class_id = find_or_insert_class(conn, show_list_id, cls["class_name"])
        for entry in cls.get("entries") or []:
            details: Dict[str, Optional[str]] = {"owner": entry.get("owner")}
            horse_url = entry.get("horse_url")
            horse_name = (entry.get("horse") or "").strip()
            # Skip horse-detail fetch when SHR put a rider in the Horse column
            if horse_url and horse_name:
                if horse_url not in horse_cache:
                    try:
                        driver.get(horse_url)
                        time.sleep(0.7)
                        horse_id_m = re.search(r"horse=(\d+)", horse_url, re.I)
                        horse_key = horse_id_m.group(1) if horse_id_m else sanitize_filename(
                            horse_name or "horse"
                        )
                        save_driver_page(
                            driver,
                            year,
                            "horse",
                            horse_name or f"horse_{horse_key}",
                            sid=sid,
                            extra_id=f"horse{horse_key}",
                        )
                        horse_cache[horse_url] = parse_horse_detail(soup_of(driver))
                    except Exception as e:
                        print_with_timestamp(f"    [WARNING] horse page: {e}")
                        horse_cache[horse_url] = details
                merged = dict(horse_cache.get(horse_url) or {})
                if details.get("owner") and not merged.get("owner"):
                    merged["owner"] = details["owner"]
                details = merged
            horse_id = (
                get_or_create_horse_fill_nulls(conn, horse_name, details)
                if horse_name
                else None
            )
            rider_id = get_or_create_competitor(conn, entry.get("rider") or "", "Rider")
            if entry.get("owner"):
                get_or_create_competitor(conn, entry["owner"], "Owner")
            if not horse_id and not rider_id:
                continue
            get_or_create_show_result(
                conn,
                class_id,
                None,
                parse_place(entry.get("place")),
                horse_id,
                rider_id=rider_id,
            )
    return show_list_id


def process_judge_cards(driver, conn, show: Dict[str, str]) -> None:
    sid = show["sid"]
    url = show["judges_url"]
    print_with_timestamp(f"Judge cards cid={sid}: {show['name']}")
    driver.get(url)
    time.sleep(1.2)
    assert_still_authenticated(driver, f"judge cards cid={sid}")
    year_hint = int(show.get("year") or datetime.now().year)
    save_driver_page(
        driver,
        year_hint,
        "judges",
        show["name"],
        sid=sid,
    )
    soup = soup_of(driver)
    meta = parse_show_meta(soup)
    show_name = meta.get("show_name") or show["name"]
    year = meta.get("year") or year_hint
    if year != year_hint:
        save_driver_page(driver, year, "judges", show_name, sid=sid)
    show_list_id = find_or_insert_show(
        conn,
        show_name=show_name,
        year=year,
        show_date=meta.get("show_date") or "",
        location=meta.get("location") or "",
        state=meta.get("state") or "",
        shr_id=sid,
    )
    judge_map = upsert_judges(conn, show_list_id, meta.get("judges") or [])
    class_cards = parse_judge_card_classes(soup)
    print_with_timestamp(f"  judge-card class blocks={len(class_cards)}")
    for block in class_cards:
        class_id = find_or_insert_class(conn, show_list_id, block["class_name"])
        for card in block["cards"]:
            jname = card["judge_name"]
            if jname not in judge_map:
                judge_map.update(
                    upsert_judges(
                        conn,
                        show_list_id,
                        [{"name": jname, "role": None, "sort_order": None}],
                    )
                )
            # Attach JudgeCard to the ShowResults row for THIS judge's Entry
            # (not Final). Place is that judge's rank for that entry.
            # When entry == final, also stamp the official Final place on the result.
            entry_num = (card.get("entry") or "").strip() or None
            final_num = (card.get("final") or "").strip() or None
            judge_place = card.get("place")
            official_place = judge_place if (entry_num and final_num and entry_num == final_num) else None
            result_id = get_or_create_show_result(
                conn,
                class_id,
                entry_num or final_num,
                official_place,
                None,
            )
            if result_id and jname in judge_map:
                upsert_judge_card(
                    conn,
                    result_id,
                    judge_map[jname],
                    judge_place,
                    entry=entry_num,
                )
            # Ensure Final entry has official Place even when this judge picked someone else
            if final_num and final_num != entry_num and judge_place is not None:
                get_or_create_show_result(
                    conn,
                    class_id,
                    final_num,
                    judge_place,
                    None,
                )
def run(
    full: bool = False,
    years: Optional[List[int]] = None,
    skip_results: bool = False,
    skip_judges: bool = False,
    list_only: bool = False,
    only_sids: Optional[List[str]] = None,
) -> None:
    email, password = credentials_from_env_or_prompt()
    conn = get_db_connection()
    ensure_schema(conn)
    cookies = headed_login_cookies(
        email,
        password,
        attempts=int(os.environ.get("SHR_LOGIN_ATTEMPTS", "3")),
    )
    driver = setup_headless_with_cookies(cookies)
    horse_cache: Dict[str, dict] = {}
    try:
        year_list = collect_result_years(driver)
        if years:
            year_list = [(y, u) for y, u in year_list if y in years]
        if list_only:
            for year, url in year_list:
                print_with_timestamp(f"YEAR {year}: {url}")
                for s in collect_shows_for_year(driver, year, url):
                    print_with_timestamp(f"  {s['sid']} {s['name']}")
            return

        for year, url in year_list:
            print_with_timestamp(f"=== Year {year} ===")
            shows = collect_shows_for_year(driver, year, url)
            if only_sids:
                shows = [s for s in shows if s["sid"] in only_sids]
            # Archive the judges year index for the same year
            try:
                driver.get(absolute_url(f"judges?y={year}"))
                time.sleep(1.2)
                save_driver_page(driver, year, "judgesyear", f"judges_year_{year}")
            except Exception as e:
                print_with_timestamp(f"[WARNING] Could not archive judges year {year}: {e}")
            for show in shows:
                if not full:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT ID FROM sResults.ShowList WHERE SHRShowID = ?",
                        show["sid"],
                    )
                    row = cursor.fetchone()
                    cursor.close()
                    if row and not show_needs_delta(conn, row[0]):
                        print_with_timestamp(f"  Skip delta-complete sid={show['sid']}")
                        continue
                if not skip_results:
                    process_show_results(driver, conn, show, horse_cache)
                if not skip_judges:
                    process_judge_cards(driver, conn, show)
        print_with_timestamp("[OK] Saddle Horse Report scrape finished")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scrape saddlehorsereport.com into HorseShows.sResults")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="Process all years/shows")
    mode.add_argument("--delta", action="store_true", help="Skip fully captured shows (default)")
    parser.add_argument("--year", type=int, action="append", help="Limit to year(s)")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--sid", action="append", help="Limit to SHR show id(s); repeatable")
    parser.add_argument("--skip-results", action="store_true")
    parser.add_argument("--skip-judges", action="store_true")
    # kept for CLI compatibility; scraping is headless after headed login
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_true", help="Unused; login is always headed")
    args = parser.parse_args()
    run(
        full=bool(args.full),
        years=args.year,
        skip_results=args.skip_results,
        skip_judges=args.skip_judges,
        list_only=args.list_only,
        only_sids=args.sid,
    )


if __name__ == "__main__":
    main()
