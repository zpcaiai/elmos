#!/usr/bin/env python3
"""Runs ONLY the bundled, trusted original fixtures; never a generic repo executor."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]

def execute(command:list[str], value):
    cp=subprocess.run(command+[json.dumps(value)],capture_output=True,text=True,timeout=5,check=True)
    return json.loads(cp.stdout)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(R/'reports/native-fixtures.json'));a=parser.parse_args()
    started=time.perf_counter();node=shutil.which('node')
    report={'schema_version':'lw.v1','scope':'original bounded cart fixtures, native processes only','generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'isolated_provider_tested':False,'real_600_seconds_tested':False,'results':[]}
    if not node:
        report.update(status='not_run',reason='node executable not found')
    else:
        cases=json.loads((R/'fixtures/cart-cases.json').read_text())
        commands={'python':[sys.executable,str(R/'fixtures/cart-python/quote.py')],'javascript':[node,str(R/'fixtures/cart-js/quote.cjs')]}
        for c in cases:
            outputs={lang:execute(cmd,c['input']) for lang,cmd in commands.items()}
            report['results'].append({'input':c['input'],'expected':c['expected'],'outputs':outputs,'passed':all(v==c['expected'] for v in outputs.values())})
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/'mutant.cjs';bad.write_text((R/'fixtures/cart-js/quote.cjs').read_text().replace('subtotal >= 10000','subtotal > 10000'))
            observed=execute([node,str(bad)],10000)
            correct=execute(commands['python'],10000)
            report['mutation_test']={'mutation':'>=10000 to >10000','input':10000,'expected':correct,'mutant_output':observed,'detected':observed!=correct}
        report['status']='passed' if all(x['passed'] for x in report['results']) and report['mutation_test']['detected'] else 'failed'
        report['versions']={'python':sys.version.split()[0],'node':subprocess.check_output([node,'--version'],text=True).strip()}
        report['commands']=commands
    report['wall_clock_seconds']=round(time.perf_counter()-started,6)
    p=Path(a.output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':len(report['results']),'output':str(p),'wall_clock_seconds':report['wall_clock_seconds']},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':sys.exit(main())
