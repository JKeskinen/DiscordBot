from komento_koodit import check_capacity
import json

# single-run for event under inspection
res = check_capacity.check_competition_capacity('https://discgolfmetrix.com/3512588', timeout=30)
print(json.dumps(res, ensure_ascii=False, indent=2))
