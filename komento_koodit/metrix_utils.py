import re
from typing import Optional

import requests
try:
    from bs4 import BeautifulSoup as BS
except Exception:
    BS = None  # type: ignore

from .date_utils import normalize_date_string


def fetch_metrix_canonical_date(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch Metrix result page and try to extract the canonical event datetime string.

    Returns a normalized date string (DD/MM/YYYY HH:MM) or None.
    """
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout)
    except Exception:
        return None
    if getattr(resp, "status_code", 0) != 200 or not resp.text:
        return None
    html = resp.text
    # Prefer BeautifulSoup when available
    try:
        if BS is not None:
            soup = BS(html, "html.parser")
            # Common Metrix header area contains <header> with <p> elements showing date/time
            # Search for the first text node matching a date pattern like 03.01.2026 12:00
            for p in soup.select("header p"):
                txt = (p.get_text(" ", strip=True) or "").strip()
                if not txt:
                    continue
                m = re.search(r"(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4}(?:\s+\d{1,2}:\d{2})?)", txt)
                if m:
                    return normalize_date_string(m.group(1))
            # fallback: search body text for first matching token
            body_text = soup.get_text(" ", strip=True)
            m = re.search(r"(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4}(?:\s+\d{1,2}:\d{2})?)", body_text)
            if m:
                return normalize_date_string(m.group(1))
        else:
            # BeautifulSoup not available: do a regex search on raw HTML
            m = re.search(r">\s*(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4}(?:\s+\d{1,2}:\d{2})?)\s*<", html)
            if m:
                return normalize_date_string(m.group(1))
    except Exception:
        return None
    return None
