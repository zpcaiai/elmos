import json,sys
d=json.load(open(sys.argv[1])); m=d['mappings']; assert d['product_skill_count']==172 and len(m)==172 and {x['product_skill_id'] for x in m}==set(range(1325,1497)); print('coverage ok: 172')
