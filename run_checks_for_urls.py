from komento_koodit import check_capacity
import json
urls = [
    'https://discgolfmetrix.com/3519179',
    'https://discgolfmetrix.com/3512047'
]
for u in urls:
    print('Checking', u)
    res = check_capacity.check_competition_capacity(u)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print('-'*60)
