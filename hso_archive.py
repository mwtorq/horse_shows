"""Archive HorseShowsOnline pages to disk (HTML + stripped text).

Layout mirrors saddlehorsereport/:
  horseshowsonline/{year}/{kind}/debug_hso_*.html (+ *_raw.txt)

For class detail pages (many per show), nest under a show subfolder:
  horseshowsonline/{year}/classes/{show}/debug_hso_*.html

kind is typically results, showdetails, classes, showlist, or other.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
HSO_ARCHIVE_ROOT = os.path.join(REPO_ROOT, "horseshowsonline")

HSO_ARCHIVE_KIND_DIRS = {
    "results": "results",
    "classresults": "results",
    "showdetails": "showdetails",
    "showlist": "showlist",
    "classes": "classes",
    # Expanded class rows archive under classes/{show}/ (same tree)
    "classdetail": "classes",
    "other": "other",
}

# Kinds that write many files per show and need a show subfolder
_KINDS_WITH_SHOW_SUBDIR = {"classes", "classdetail"}


def print_with_timestamp(message: str, end: str = "\n") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", end=end, flush=True)


def sanitize_filename(name: str, max_len: int = 50) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    safe = safe.replace(" ", "_").replace("&", "and").replace("'", "")
    safe = re.sub(r"_+", "_", safe).strip("_")
    return (safe[:max_len] or "unknown")


def build_show_subdir(label: str, show_guid: Optional[str] = None, extra_id: Optional[str] = None) -> str:
    """Build a stable per-show folder name under classes/."""
    parts = [sanitize_filename(label, 60)]
    if show_guid:
        parts.append(sanitize_filename(str(show_guid), 36))
    elif extra_id:
        # Prefer ShowList id token from extra_id like "sl10296_class..."
        m = re.search(r"\bsl(\d+)\b", str(extra_id), re.I)
        if m:
            parts.append(f"sl{m.group(1)}")
    return "_".join(parts) or "unknown_show"


def build_hso_raw_text(html_content: str, source_url: str, label: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback: crude strip if bs4 unavailable
        text = re.sub(r"<[^>]+>", "\n", html_content or "")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    else:
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


def html_has_class_entry_substance(html_content: str) -> bool:
    """True when page looks like an expanded class with placing/entry grids."""
    if not html_content:
        return False
    lower = html_content.lower()
    if "grplacing" in lower:
        return True
    if "entries that placed" in lower:
        return True
    if "grnonplacing" in lower or "non-placing" in lower or "nonplacing" in lower:
        return True
    return False


def save_hso_page(
    html_content: str,
    year: Optional[int],
    page_kind: str,
    label: str,
    source_url: str,
    show_guid: Optional[str] = None,
    extra_id: Optional[str] = None,
    require_class_substance: bool = False,
) -> Optional[str]:
    """Save full HTML and stripped text under horseshowsonline/{year}/{kind}/[show]/.

    If require_class_substance is True (classdetail), skip write when the HTML
    has no placing/entry grids — avoids archiving empty ClassResults shells.
    """
    kind_key = (page_kind or "").lower()
    if require_class_substance or kind_key == "classdetail":
        if not html_has_class_entry_substance(html_content):
            print_with_timestamp(
                "  [WARNING] Skipping HSO classdetail archive: no grPlacing/entry substance"
            )
            return None
    kind_dir_name = HSO_ARCHIVE_KIND_DIRS.get(kind_key, "other")
    out_dir = os.path.join(HSO_ARCHIVE_ROOT, str(year or "unknown"), kind_dir_name)
    if kind_key in _KINDS_WITH_SHOW_SUBDIR:
        out_dir = os.path.join(
            out_dir, build_show_subdir(label, show_guid=show_guid, extra_id=extra_id)
        )
    os.makedirs(out_dir, exist_ok=True)
    parts = ["debug_hso", page_kind, sanitize_filename(label)]
    if show_guid:
        parts.append(sanitize_filename(str(show_guid), 40))
    if extra_id:
        parts.append(sanitize_filename(str(extra_id), 40))
    base = "_".join(parts)
    html_path = os.path.join(out_dir, f"{base}.html")
    raw_path = os.path.join(out_dir, f"{base}_raw.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(build_hso_raw_text(html_content, source_url, label))
    print_with_timestamp(f"  Saved HSO HTML+raw ({len(html_content)} chars) {html_path}")
    return html_path


def driver_html_snapshot(driver, chunk_size: int = 262144) -> str:
    """Capture the complete page HTML without hanging ChromeDriver.

    Building/returning multi‑MB outerHTML in one WebDriver round-trip has wedged
    chromedriver for 40+ minutes. Materialize once in-page, then pull in chunks.
    Never uses driver.page_source (also a known hang).
    Writes are still the full document — suitable for disk replay.
    """
    try:
        length = driver.execute_script(
            """
            try { delete window.__hsoSnap; } catch (e) {}
            window.__hsoSnap = document.documentElement
                ? document.documentElement.outerHTML : '';
            return window.__hsoSnap.length;
            """
        )
        if not length:
            return ""
        parts = []
        offset = 0
        while offset < length:
            end = min(offset + chunk_size, int(length))
            chunk = driver.execute_script(
                "return window.__hsoSnap.substring(arguments[0], arguments[1]);",
                offset,
                end,
            )
            if chunk is None:
                break
            parts.append(chunk)
            offset = end
        try:
            driver.execute_script("window.__hsoSnap = null;")
        except Exception:
            pass
        return "".join(parts)
    except Exception as e:
        print_with_timestamp(f"  [WARNING] chunked HTML snapshot failed ({e})")
        try:
            driver.execute_script("window.__hsoSnap = null;")
        except Exception:
            pass
        return ""


def save_hso_driver_page(
    driver,
    year: Optional[int],
    page_kind: str,
    label: str,
    show_guid: Optional[str] = None,
    extra_id: Optional[str] = None,
    require_class_substance: bool = False,
    class_row_id: Optional[str] = None,  # unused; kept for call-site compat
) -> Optional[str]:
    """Archive complete page HTML + *_raw.txt for disk replay (never hits HSO again)."""
    del class_row_id  # complete page only — no scoped/partial archives
    return save_hso_page(
        driver_html_snapshot(driver),
        year,
        page_kind,
        label,
        getattr(driver, "current_url", "") or "",
        show_guid=show_guid,
        extra_id=extra_id,
        require_class_substance=require_class_substance,
    )
