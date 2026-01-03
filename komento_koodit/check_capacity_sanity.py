import os
import json

from .check_capacity import check_competition_capacity


def _load_comps(files):
    comps = []
    for p in files:
        try:
            if not os.path.exists(p):
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                comps.extend(data)
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        comps.extend(v)
                    else:
                        comps.append(v)
        except Exception:
            continue
    return comps


def main():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    default_files = [
        os.path.join(base, "PDGA.json"),
        os.path.join(base, "VIIKKOKISA.json"),
        os.path.join(base, "DOUBLES.json"),
    ]

    comps = _load_comps(default_files)
    total = len(comps)
    ok = 0
    no_data = 0
    negatives = []
    errors = []

    for c in comps:
        url = c.get("url") or c.get("link") or ""
        if not url:
            continue
        cap = check_competition_capacity(url)
        reg = cap.get("registered")
        lim = cap.get("limit")
        rem = cap.get("remaining")
        note = str(cap.get("note") or "")

        if rem is not None and rem < 0:
            negatives.append((c, cap))

        if (reg is None and lim is None and rem is None) or note.startswith("http "):
            no_data += 1
        else:
            ok += 1

        if note and note not in ("", "metrix-reg-table", "metrix-playwright-phrase", "metrix-playwright") \
           and not note.startswith("registration-") and not note.startswith("tjing"):
            errors.append((c, cap))

    print(f"Kilpailuja yhteensä: {total}")
    print(f"Kelvolliset kapasiteettitiedot: {ok}")
    print(f"Ilman kapasiteettitietoja / HTTP-ongelmia: {no_data}")
    print(f"Negatiivisia jäljellä-merkintöjä: {len(negatives)}")
    if negatives:
        print("  Esimerkki negatiivisesta:")
        for c, cap in negatives[:5]:
            print("   -", c.get("title") or c.get("name"), c.get("url") or c.get("link"), cap)

    print(f"Epäilyttäviä huomautuksia: {len(errors)}")
    if errors:
        print("  Esimerkki epäilyttävästä:")
        for c, cap in errors[:5]:
            print("   -", c.get("title") or c.get("name"), c.get("url") or c.get("link"), cap)


if __name__ == "__main__":
    main()
