from datetime import datetime
import re


def _try_parse(fmt_list, s: str):
    for fmt in fmt_list:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def normalize_date_string(s: str, prefer_month_first: bool = False) -> str:
    """Normalize various date string formats to DD.MM.YYYY (with optional time HH:MM).

    Examples handled:
    - '01/02/26 12:00' -> '01.02.2026 12:00'
    - '1.2.2026 12:00' -> '01.02.2026 12:00'
    - '02/01/26' -> '02.01.2026'
    - '2026-02-01' -> '01.02.2026'
    If parsing fails, returns the original string.
    """
    if not s or not isinstance(s, str):
        return s
    s = s.strip()
    # normalize common separators
    s_clean = s.replace('.', '/').replace('-', '/').replace('\u2013', '/').replace('\u2014', '/')

    # Try a set of formats with and without time
    if prefer_month_first:
        fmts = [
            '%m/%d/%Y %H:%M',
            '%m/%d/%y %H:%M',
            '%m/%d/%Y',
            '%m/%d/%y',
            '%d/%m/%Y %H:%M',
            '%d/%m/%y %H:%M',
            '%d/%m/%Y',
            '%d/%m/%y',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d',
        ]
    else:
        fmts = [
            '%d/%m/%Y %H:%M',
            '%d/%m/%y %H:%M',
            '%d/%m/%Y',
            '%d/%m/%y',
            '%m/%d/%Y %H:%M',
            '%m/%d/%y %H:%M',
            '%m/%d/%Y',
            '%m/%d/%y',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d',
        ]

    # trim extra text after comma or '—'
    s_trim = re.split('[,–—-]', s_clean)[0].strip()

    dt = _try_parse(fmts, s_trim)
    if not dt:
        # try to extract date-like token
        m = re.search(r'(\d{1,4}[/\.]\d{1,2}[/\.]\d{1,4})(?:\s+(\d{1,2}:\d{2}))?', s)
        if m:
            part = m.group(1).replace('.', '/').replace('-', '/')
            timepart = m.group(2) or ''
            dt = _try_parse(fmts, (part + (' ' + timepart if timepart else '')).strip())
    if not dt:
        return s

    out = dt.strftime('%d.%m.%Y')
    if dt.hour or dt.minute:
        out = f"{out} {dt.strftime('%H:%M')}"
    return out
