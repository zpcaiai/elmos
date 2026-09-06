#!/usr/bin/env python3
"""Real DAP roundtrip against the original bundled Python fixture.
The adapter uses stdio. Its own loopback debug-server listener is temporary.
This is a TRUSTED LOCAL LAB, not an untrusted-code sandbox or hosted workbench.
"""
from __future__ import annotations
import argparse,datetime,importlib.util,json,os,queue,signal,subprocess,sys,threading,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]

class DapClient:
    def __init__(self):
        self.proc=subprocess.Popen([sys.executable,'-m','debugpy.adapter'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        self.q=queue.Queue();self.buffer=[];self.seq=0;self.log=[]
        threading.Thread(target=self._read,daemon=True).start()
        threading.Thread(target=lambda:self.proc.stderr.read(),daemon=True).start()
    def _read(self):
        try:
            while True:
                header={}
                while True:
                    raw=self.proc.stdout.readline()
                    if not raw:raise EOFError('DAP stdout closed')
                    if raw in (b'\r\n',b'\n'):break
                    k,v=raw.decode().split(':',1);header[k.lower()]=v.strip()
                length=int(header['content-length'])
                if length>4*1024*1024:raise ValueError('oversized DAP frame')
                data=b''
                while len(data)<length:
                    part=self.proc.stdout.read(length-len(data))
                    if not part:raise EOFError('partial DAP body')
                    data+=part
                self.q.put(json.loads(data))
        except BaseException as e:self.q.put(e)
    def send(self,name,args=None):
        self.seq+=1
        m={'seq':self.seq,'type':'request','command':name,'arguments':args or {}}
        b=json.dumps(m).encode();self.proc.stdin.write(f'Content-Length: {len(b)}\r\n\r\n'.encode()+b);self.proc.stdin.flush()
        self.log.append({'direction':'request','seq':self.seq,'command':name})
        return self.seq
    def wait(self,predicate,timeout=20):
        deadline=time.monotonic()+timeout
        while True:
            for i,m in enumerate(self.buffer):
                if predicate(m):return self.buffer.pop(i)
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('DAP wait deadline')
            m=self.q.get(timeout=remaining)
            if isinstance(m,BaseException):raise m
            self.log.append({'direction':'incoming','type':m.get('type'),'event':m.get('event'),'command':m.get('command'),'success':m.get('success')})
            if m.get('type')=='request':raise RuntimeError('unexpected reverse request denied: '+str(m.get('command')))
            self.buffer.append(m)
    def response(self,seq):
        m=self.wait(lambda x:x.get('type')=='response' and x.get('request_seq')==seq)
        if not m.get('success'):raise RuntimeError(str(m))
        return m.get('body',{})
    def request(self,name,args=None):return self.response(self.send(name,args))
    def event(self,name):return self.wait(lambda x:x.get('type')=='event' and x.get('event')==name).get('body',{})
    def close(self):
        # All fixture/adapter descendants belong to this local process group.
        try:os.killpg(self.proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:os.killpg(self.proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            self.proc.wait(timeout=3)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(R/'reports/debugpy-lab.json'));a=p.parse_args()
    start=time.perf_counter();report={'scope':'trusted local Python DAP sample only','generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'not_run','hosted_workbench_tested':False,'isolated_provider_tested':False,'real_600_seconds_tested':False};c=None
    try:
        if importlib.util.find_spec('debugpy') is None:raise RuntimeError('debugpy is not installed')
        import debugpy
        file=R/'fixtures/cart-python/quote.py'
        line=next(i for i,t in enumerate(file.read_text().splitlines(),1) if 'EL-LW-BREAKPOINT' in t)
        c=DapClient()
        capabilities=c.request('initialize',{'clientID':'elmos-reference-lab','adapterID':'python','pathFormat':'path','linesStartAt1':True,'columnsStartAt1':True,'supportsRunInTerminalRequest':False})
        launch=c.send('launch',{'name':'original-cart-fixture','type':'python','request':'launch','program':str(file),'args':['10000'],'cwd':str(file.parent),'console':'internalConsole','justMyCode':True,'redirectOutput':True,'python':[sys.executable]})
        c.event('initialized')
        bps=c.request('setBreakpoints',{'source':{'path':str(file)},'breakpoints':[{'line':line}]})
        c.request('configurationDone');c.response(launch)
        stop=c.event('stopped');thread=stop['threadId']
        stack=c.request('stackTrace',{'threadId':thread,'startFrame':0,'levels':10})
        frame=stack['stackFrames'][0]
        if frame['line']!=line:raise AssertionError(f"requested line {line}, got {frame['line']}")
        scopes=c.request('scopes',{'frameId':frame['id']})
        local=next(s for s in scopes['scopes'] if s['name']=='Locals')
        variables=c.request('variables',{'variablesReference':local['variablesReference']})
        primitives={v['name']:v['value'] for v in variables['variables'] if v['name'] in ['subtotal','discount','amount_cents']}
        if primitives.get('subtotal')!='10000' or primitives.get('discount')!='1000':raise AssertionError(primitives)
        c.request('next',{'threadId':thread});nextstop=c.event('stopped')
        nextstack=c.request('stackTrace',{'threadId':nextstop['threadId'],'startFrame':0,'levels':1})
        if nextstack['stackFrames'][0]['line']<=line:raise AssertionError('next did not advance')
        c.request('continue',{'threadId':nextstop['threadId']});c.event('terminated')
        c.request('disconnect',{'terminateDebuggee':True})
        report.update(status='passed',debugpy_version=debugpy.__version__,python_version=sys.version.split()[0],requested_line=line,actual_line=frame['line'],breakpoints=bps['breakpoints'],primitive_values=primitives,next_line=nextstack['stackFrames'][0]['line'],protocol_steps=['initialize','launch','initialized','setBreakpoints','configurationDone','stopped','stackTrace','scopes','variables','next','stopped','continue','terminated','disconnect'])
    except BaseException as e:
        report.update(status='failed',error=type(e).__name__+': '+str(e))
    finally:
        if c:
            report['protocol_summary']=c.log
            c.close()
        report['wall_clock_seconds']=round(time.perf_counter()-start,6)
        path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'output':str(path),'wall_clock_seconds':report['wall_clock_seconds'],'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':sys.exit(main())
