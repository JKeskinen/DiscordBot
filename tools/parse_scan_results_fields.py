import sqlite3, json, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB = os.path.join(ROOT, 'data', 'discordbot.db')
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT results, class_definitions FROM CAPACITY_SCAN_RESULTS LIMIT 1")
row = cur.fetchone()
if not row:
    print('No CAPACITY_SCAN_RESULTS')
else:
    results_txt, class_defs = row
    print('class_definitions column:', class_defs)
    try:
        arr = json.loads(results_txt)
    except Exception as e:
        print('Could not parse results JSON:', e)
        arr = []
    count = 0
    for item in arr:
        count += 1
        comp_id = item.get('id')
        name = item.get('name')
        cap = item.get('capacity_result', {})
        # find rating keys
        rating_keys = {k: v for k, v in item.items() if 'rating' in k.lower()}
        cap_rating_keys = {k: v for k, v in cap.items() if 'rating' in k.lower()}
        class_keys = {k: v for k, v in item.items() if 'class' in k.lower()}
        # also check nested 'classes' inside item
        nested_classes = item.get('classes') or cap.get('classes') or item.get('class_definitions')
        if rating_keys or cap_rating_keys or class_keys or nested_classes:
            print('\nCompetition', comp_id, name)
            if rating_keys:
                print(' item-level rating keys:', rating_keys)
            if cap_rating_keys:
                print(' capacity_result rating keys:', cap_rating_keys)
            if class_keys:
                print(' item-level class keys:', class_keys)
            if nested_classes:
                print(' nested classes/class_definitions present (type):', type(nested_classes).__name__)
                try:
                    print(' sample nested:', json.dumps(nested_classes)[:400])
                except Exception:
                    print(' sample nested (repr):', repr(nested_classes)[:400])
    print('\nTotal scanned competitions:', count)
conn.close()
