import os
import json

def _base_dir(provided=None):
    if provided:
        return provided
    # default to project root (parent of this module)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def save_category(name: str, entries, out_path: str = None, base_dir: str = None):
    """Save entries for a named category. Default filename is <NAME>.json in project root.
    This centralizes writes so callers can switch to a data/ folder or different naming later.
    """
    bd = _base_dir(base_dir)
    if out_path:
        path = out_path
    else:
        path = os.path.join(bd, f"{name}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(entries)} {name} entries to {path}")
    except Exception as e:
        print(f"Failed to save {name} JSON: {e}")


def load_category(name: str, path: str = None, base_dir: str = None):
    bd = _base_dir(base_dir)
    p = path or os.path.join(bd, f"{name}.json")
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []
