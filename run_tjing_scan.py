#!/usr/bin/env python3
import json
from komento_koodit.check_capacity import scan_pdga_for_tjing

if __name__ == '__main__':
    res = scan_pdga_for_tjing()
    print(json.dumps(res, ensure_ascii=False, indent=2))
