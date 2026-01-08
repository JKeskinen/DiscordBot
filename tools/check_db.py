import os
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from komento_koodit import data_store

print('DB path:', data_store._db_path())
alerts = data_store.load_category('CAPACITY_ALERTS')
print('CAPACITY_ALERTS count:', len(alerts) if alerts else 0)
print('Sample:', alerts[:2])
