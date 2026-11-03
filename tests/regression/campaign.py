#!/usr/bin/env python3
"""Serial campaign with durable state, independent watchdogs and final recovery.

No server runs in parallel on a device. Resume uses the exact saved job list;
failed jobs are retained and never silently retried as passes.
"""
import argparse,datetime,json,os,signal,subprocess,sys,time,hashlib
from pathlib import Path
from report import generate
ROOT=Path(__file__).resolve().parent;WORK=ROOT.parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--serial',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--soak-seconds',type=int,default=7200);p.add_argument('--repeats',type=int,default=10);p.add_argument('--restore-instance',type=int);p.add_argument('--resume',action='store_true');a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=a.resume);statefile=out/'campaign.json'
 jobs=[]
 def add(v,engine,suite,label=None,extra=()):
  python=WORK/('verification/jprobe-regression/upstream-env-313/bin/python' if v=='upstream' else 'venv-macos-clean/bin/python')
  server=WORK/{'r8':'dist/android-thread-names-r8/artifacts/jprobe-server','r7':'dist/android-thread-name-r7/artifacts/jprobe-server','upstream':'verification/jprobe-regression/upstream-artifacts/frida-server'}[v]
  name=f'{v}-{engine}-{label or suite}';cmd=[str(python),str(ROOT/'run.py'),'--serial',a.serial,'--variant',v,'--runtime',engine,'--suite',suite,'--server',str(server),'--output',str(out/name),*extra]
  jobs.append({'name':name,'command':cmd,'status':'PENDING'})
 for v in ['r8','r7']:
  for engine in ['qjs','v8']:
   add(v,engine,'functional');add(v,engine,'custom');add(v,engine,'performance')
  for mode in ['none','record','lookup','child']:add(v,'qjs','edge','edge-'+mode,('--edge-case',mode))
 for engine in ['qjs','v8']:add('r8',engine,'recovery')
 # Baseline has no listening port, so it is collected once, not duplicated by port.
 add('r8','qjs','detection','detection-baseline',('--detection-mode','baseline','--repeats',str(a.repeats)))
 for v in ['r8','r7','upstream']:
  for port in ([35110,27042] if v=='upstream' else [35110,35000]):
   for mode in (['server'] if v=='upstream' else ['server','empty','java','native']):
    add(v,'qjs','detection',f'detection-{port}-{mode}',('--port',str(port),'--detection-mode',mode,'--repeats',str(a.repeats)))
 for engine in ['qjs','v8']:add('r8',engine,'concurrency')
 for engine in ['qjs','v8']:add('r8',engine,'stress',extra=('--soak-seconds',str(a.soak_seconds)))
 state={'started':time.time(),'serial':a.serial,'jobs':jobs,'status':'RUNNING','sourceSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')},'notes':['Gadget root/no-root tests are executed separately with pinned APK variants.','Original Frida injected comparison blocked by reproducible libc initialization abort.','Official Core/Gum and allocator fault-injection need matching test builds.']}
 if a.resume:state=json.loads(statefile.read_text())
 def save():
  temp=statefile.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(statefile)
 report=Path('/Users/sunjie.sj/software/vault/pj/jprobe功能回归测试/自动执行报告.md')
 child=None
 def stop(*args):raise KeyboardInterrupt()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  for job in state['jobs']:
   if job['status'] in ['PASS','FAIL','INCOMPLETE']:continue
   if (out/job['name']).exists():job['status']='INCOMPLETE';save();continue
   job['status']='RUNNING';job['started']=time.time();state['current']=job['name'];save()
   with (out/(job['name']+'.log')).open('w') as log:
    child=subprocess.Popen(job['command'],stdout=log,stderr=subprocess.STDOUT,cwd=WORK)
    while child.poll() is None:state['heartbeat']=time.time();save();time.sleep(5)
    job['exitCode']=child.returncode;job['status']='PASS' if child.returncode==0 else ('INCOMPLETE' if child.returncode==2 else 'FAIL');job['finished']=time.time();save();child=None
   generate(WORK/'verification/jprobe-regression',report)
  state['status']='FINISHED_WITH_FAILURES' if any(j['status']!='PASS' for j in state['jobs']) else 'FINISHED';state['finished']=time.time();save()
 except KeyboardInterrupt:
  state['status']='INTERRUPTED';save()
  if child:
   child.terminate()
   try:child.wait(90)
   except subprocess.TimeoutExpired:child.kill();child.wait()
 finally:
  generate(WORK/'verification/jprobe-regression',report)
  if a.restore_instance is not None:
   r=subprocess.run(['/Applications/MuMuPlayer.app/Contents/MacOS/mumu-cli','open',str(a.restore_instance)],capture_output=True,text=True)
   (out/'restore-original.json').write_text(r.stdout+r.stderr)
   for _ in range(30):
    check=subprocess.run(['/Applications/MuMuPlayer.app/Contents/MacOS/mumu-cli','info',str(a.restore_instance)],capture_output=True,text=True)
    try:info=json.loads(check.stdout);running=info['return'].get('state')=='running'
    except (ValueError,KeyError):running=False
    if running:break
    time.sleep(1)
   (out/'restore-original-verified.json').write_text(check.stdout+check.stderr)
   state['originalInstanceRestored']=running;save()
 print(state['status']);return 0 if state['status']=='FINISHED' else 1
if __name__=='__main__':sys.exit(main())
