import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from komento_koodit import commands_tulokset as ct

url='https://discgolfmetrix.com/3523186&view=result'
rows = ct._fetch_handicap_table(url)
print('HC rows found:', len(rows))
lines = ct._format_hc_top3_lines(rows)
print('\n'.join(lines))
