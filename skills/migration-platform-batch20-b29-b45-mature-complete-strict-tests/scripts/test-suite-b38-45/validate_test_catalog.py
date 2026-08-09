import json,sys
d=json.load(open(sys.argv[1])); c=d['cases']; assert d['case_count']==400 and len(c)==400 and len({x['case_id'] for x in c})==400; print('catalog ok: 400')
