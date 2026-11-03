#!/usr/bin/env python3
"""Isolated Android regression runner. Every device command requires --serial.

The parent watchdog survives blocking bindings. Results are checkpointed per case.
Only this runner's server, forwarding rule and fixture package are cleaned up.
"""
import argparse,hashlib,importlib,json,os,re,shlex,signal,subprocess,sys,time,traceback,threading,shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from resources import listening_inodes,wait_listener,stop_owned,verify_heartbeat_time
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[2]
PKG='dev.jprobe.lab'
REMOTE='/data/local/tmp/jprobe-regression'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def command(args,timeout=60,check=True):
 r=subprocess.run([str(x) for x in args],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if check and r.returncode:raise RuntimeError(f'{args[0]} exit={r.returncode}: {r.stderr[-2500:]} {r.stdout[-2500:]}')
 return r
class Runner:
 def __init__(self,a):
  self.a=a;self.out=a.output;self.results=[];self.session=None;self.script=None;self.device=None;self.forward=None;self.pid=None;self.server_pid=None;self.seq=0
  self.api=importlib.import_module('frida' if a.variant=='upstream' else 'jprobe')
  self.fixture=a.fixture.resolve();self.run_tag=hashlib.sha256(str(a.output.resolve()).encode()).hexdigest()[:12];self.remote=f'{REMOTE}/{a.variant}-{self.run_tag}';self.port=a.port
  self.bridge=Path(importlib.import_module('frida_tools' if a.variant=='upstream' else 'jprobe_tools').__file__).parent/'bridges/java.js'
  self.source=(ROOT/'agent.js').read_text()
  if self.bridge.exists():self.source=self.bridge.read_text()+'\nconst Java = bridge;\n'+self.source
 def adb(self,*args,**kw):return command(['adb','-s',self.a.serial,*args],**kw).stdout.strip()
 def shell(self,s,**kw):return self.adb('shell',s,**kw)
 def checkpoint(self):
  data={'variant':self.a.variant,'runtime':self.a.runtime,'suite':self.a.suite,'serial':self.a.serial,'cases':self.results,'counts':{s:sum(x['status']==s for x in self.results) for s in ['PASS','FAIL','BLOCKED','SKIP']}}
  tmp=self.out/'results.tmp';tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str));tmp.replace(self.out/'results.json')
  suite=ET.Element('testsuite',name=f'{self.a.variant}-{self.a.runtime}-{self.a.suite}',tests=str(len(self.results)),failures=str(data['counts']['FAIL']))
  for c in self.results:
   t=ET.SubElement(suite,'testcase',name=c['id'],time=str(c.get('duration',0)))
   if c['status']=='FAIL':ET.SubElement(t,'failure',message=c.get('error','')).text=c.get('trace','')
   elif c['status'] in ['BLOCKED','SKIP']:ET.SubElement(t,'skipped',message=c.get('reason',''))
  ET.ElementTree(suite).write(self.out/'junit.xml',encoding='utf-8',xml_declaration=True)
 def case(self,name,fn):
  start=time.monotonic();c={'id':name,'status':'PASS'}
  (self.out/'active.json').write_text(json.dumps({'id':name,'started':time.time()}))
  try:c['actual']=fn()
  except Exception as e:c.update(status='FAIL',error=str(e),trace=traceback.format_exc())
  c['duration']=round(time.monotonic()-start,3);self.results.append(c);self.checkpoint();print(json.dumps(c,ensure_ascii=False,default=str),flush=True);return c['status']=='PASS'
 def blocked(self,name,reason):self.results.append({'id':name,'status':'BLOCKED','reason':reason});self.checkpoint()
 def expect(self,v,w):
  if v!=w:raise AssertionError(f'actual={v!r} expected={w!r}')
  return v
 def setup(self):
  assert re.fullmatch(r'[A-Za-z0-9_.:-]+',self.a.serial)
  info=self.shell('id')
  if self.a.suite!='gadget':assert 'uid=0(root)' in info,info
  assert 'arm64-v8a' in self.shell('getprop ro.product.cpu.abilist')
  build=json.loads((self.fixture/'build.json').read_text());global PKG;PKG=build['package']
  self.artifact=self.a.server.resolve()
  self.source_hashes={name:sha(ROOT/name) for name in ['run.py','agent.js','build.py','integrations.py','resources.py']}
  for name in self.source_hashes:shutil.copyfile(ROOT/name,self.out/name)
  needs_server=self.a.suite not in ['gadget','lifecycle'] and not (self.a.suite=='detection' and self.a.detection_mode=='baseline')
  if needs_server and listening_inodes(self.shell('cat /proc/net/tcp /proc/net/tcp6'),self.port):raise RuntimeError('test port already occupied; refusing to use another server')
  env={'serial':self.a.serial,'id':info,'properties':self.shell('getprop ro.build.version.release; getprop ro.build.version.sdk; getprop ro.product.cpu.abilist; uname -a; getconf PAGESIZE; getenforce'), 'clientVersion':self.api.__version__,'clientModule':self.api.__file__,'python':sys.version,'build':build,'serverSha256':sha(self.artifact),'bridgeSha256':sha(self.bridge),'agentScriptSha256':sha(ROOT/'agent.js'),'fileMode':self.a.file_mode}
  ext=list(Path(self.api.__file__).parent.glob('_*.so'));env['extensionSha256']={p.name:sha(p) for p in ext}
  env['harnessSha256']=self.source_hashes;(self.out/'environment.json').write_text(json.dumps(env,indent=2))
  if self.a.suite=='gadget':self.adb('uninstall',PKG,check=False)
  self.adb('install','--no-incremental','-r',str(self.fixture/'fixture.apk'))
  if self.a.suite in ['gadget','lifecycle'] or (self.a.suite=='detection' and self.a.detection_mode=='baseline'):return
  self.shell(f'mkdir -p {self.remote}')
  self.adb('push',str(self.artifact),f'{self.remote}/server')
  self.adb('push',str(self.fixture/'lab'),f'{self.remote}/lab')
  if (self.fixture/'plugin.dex').exists():self.adb('push',str(self.fixture/'plugin.dex'),f'{self.remote}/plugin.dex')
  self.shell(f'chmod 755 {self.remote}/server {self.remote}/lab')
  remote_hash=self.shell(f'sha256sum {self.remote}/server').split()[0];self.expect(remote_hash,env['serverSha256'])
  if self.shell(f'pidof {self.remote}/server',check=False):raise RuntimeError('test server already running; refusing duplicate')
  extra='' if self.a.variant=='upstream' else f'--directory re.jprobe.regression.{self.run_tag}'
  prefix='JPROBE_AGENT_FILE_MODE=1 ' if self.a.file_mode=='file' and self.a.variant!='upstream' else ''
  self.shell(f'{prefix}nohup {self.remote}/server -l 127.0.0.1:{self.port} {extra} >{self.remote}/server.log 2>&1 </dev/null & echo $! >{self.remote}/server.pid')
  self.server_pid=int(self.shell(f'cat {self.remote}/server.pid'))
  self.save_owned()
  wait_listener(self.shell,self.server_pid,f'{self.remote}/server',self.port)
  self.forward=int(self.adb('forward','tcp:0',f'tcp:{self.port}'))
  self.save_owned()
  self.device=self.api.get_device_manager().add_remote_device(f'127.0.0.1:{self.forward}')
  for _ in range(30):
   try:self.device.enumerate_processes();break
   except Exception:time.sleep(.2)
  else:raise RuntimeError('server did not become ready: '+self.shell(f'cat {self.remote}/server.log'))
 def save_owned(self):
  temp=self.out/'owned.tmp';temp.write_text(json.dumps({'serverPid':self.server_pid,'serverPath':f'{self.remote}/server','nativePath':f'{self.remote}/lab','forward':self.forward,'package':PKG}));temp.replace(self.out/'owned.json')
 def independent(self,j=42,n=42,rounds=1):
  if self.pid:self.expect(self.shell(f'pidof {PKG}',check=False),str(self.pid))
  out=self.shell(f'am broadcast --user 0 --receiver-foreground -a dev.jprobe.lab.RUN -n {PKG}/dev.jprobe.lab.RunReceiver --ei rounds {rounds}',timeout=30)
  m=re.search(r'JAVA=(\d+);NATIVE=(\d+);TOTAL=(\d+);UID=(\d+)',out);assert m,out
  actual=list(map(int,m.groups()));self.expect(actual[:3],[j,n,j*rounds]);assert actual[3]>=10000,actual
  if self.pid:self.expect(self.shell(f'pidof {PKG}',check=False),str(self.pid))
  return actual
 def detach(self):
  if self.script:
   try:self.script.unload()
   except self.api.InvalidOperationError:pass
   finally:self.script=None
  if self.session:
   try:self.session.detach()
   except self.api.InvalidOperationError:pass
   finally:self.session=None
 def start(self,spawn=False,bridge=True):
  self.detach();self.shell(f'am force-stop {PKG}')
  if spawn:
   self.pid=self.device.spawn([PKG]);self.session=self.device.attach(self.pid)
   early=self.session.create_script('rpc.exports.pid=()=>Process.id;',runtime=self.a.runtime);early.load();self.expect(early.exports_sync.pid(),self.pid);self.device.resume(self.pid);early.unload()
  else:
   self.shell(f'am start -W -n {PKG}/dev.jprobe.lab.MainActivity')
   self.pid=int(self.shell(f'pidof {PKG}'));self.session=self.device.attach(self.pid)
  for _ in range(40):
   if 'liblab.so' in self.shell(f'cat /proc/{self.pid}/maps'):break
   time.sleep(.2)
  self.script=self.session.create_script(self.source if bridge else (ROOT/'agent.js').read_text(),runtime=self.a.runtime);self.script.on('message',lambda m,d:self.message(m,d));self.script.load();return self.script.exports_sync
 def message(self,m,d):
  with (self.out/'messages.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'message':m,'bytes':len(d) if d else 0},default=str)+'\n')
 def native_roundtrip(self,replace=False):
  self.independent();r=self.script.exports_sync
  try:
   (r.replace_native if replace else r.install_native)();self.independent(42,43)
  finally:r.restore_native()
  return self.independent()
 def java_roundtrip(self,deopt=False):
  self.independent();r=self.script.exports_sync
  try:r.install_java(deopt);self.independent(43,42)
  finally:r.restore_java()
  return self.independent()
 def smoke(self):
  self.case('enumerate',lambda: self.expect(any(p.name for p in self.device.enumerate_processes()),True))
  if not self.case('attach-load',lambda:self.start().identity()):return
  for name,fn in [('independent-baseline',self.independent),('rpc',lambda:self.expect(self.script.exports_sync.sum(19,23),42)),('java-hook-restore',self.java_roundtrip),('native-hook-restore',self.native_roundtrip),('spawn-resume',lambda:self.start(True).sum(19,23))]:self.case(name,fn)
 def functional(self):
  if not self.case('attach-load',lambda:self.start().identity()):return
  r=self.script.exports_sync
  for name in ['semantics','memory','native','cmodule','patch','symbols','stalker','java_basic','java_main','java_classes']:
   self.case(name,lambda n=name:getattr(r,n)())
  if self.a.variant=='r9':
   def attributed_memory():
    observed=[]
    for executable in (False,True):
     address=int(r.attributed_memory(executable),16)
     maps=self.shell(f'cat /proc/{self.pid}/maps');row=next(line for line in maps.splitlines() if int(line.split('-')[0],16)<=address<int(line.split()[0].split('-')[1],16))
     assert '[anon:jprobe-page]' in row,row
     self.expect(row.split()[1],'r-xp' if executable else 'rw-p');observed.append(row)
    return observed
   self.case('owned-page-rw-to-rx',attributed_memory)
   def attributed_closure():
    address=int(r.attributed_closure(),16);maps=self.shell(f'cat /proc/{self.pid}/maps')
    row=next(line for line in maps.splitlines() if int(line.split('-')[0],16)<=address<int(line.split()[0].split('-')[1],16))
    assert '[anon:jprobe-closure]' in row or '/memfd:' in row,row
    assert 'x' in row.split()[1],row
    return row
   self.case('owned-closure-page',attributed_closure)
  self.case('main-thread-assertion',lambda:self.expect(r.java_main(),True))
  self.case('class-enumeration-assertion',lambda:self.expect(r.java_classes()['fixture'],True))
  self.case('java-retain-choose-register',lambda:r.java_objects())
  if (self.fixture/'plugin.dex').exists():
   self.case('dynamic-class-loader',lambda:self.expect(r.java_loader(f'{self.remote}/plugin.dex'),True))
  else:self.blocked('dynamic-class-loader-and-late-module','Requires base-v2 fixture')
  self.case('rpc-async',lambda:self.expect(r.async_sum(19,23),42))
  def error():
   try:r.fail()
   except self.api.RPCException as e:assert 'expected-rpc-error' in str(e);return r.sum(1,2)
   raise AssertionError('RPC error not delivered')
  self.case('rpc-error-recovery',error)
  for size in [0,1024,1048576,8388608]:
   self.case(f'binary-{size}',lambda n=size:self.expect(hashlib.sha256(r.echo(bytes(i%251 for i in range(n)))).hexdigest(),hashlib.sha256(bytes(i%251 for i in range(n))).hexdigest()))
  self.case('native-replace-revert',lambda:self.native_roundtrip(True))
  self.case('java-cold-hook',self.java_roundtrip)
  self.case('java-warmup',lambda:self.independent(rounds=100000))
  self.case('java-warm-hook',self.java_roundtrip)
  self.case('java-warm-deopt-hook',lambda:self.java_roundtrip(True))
  def multi():
   s=self.session.create_script('rpc.exports.sum=(a,b)=>a+b;',runtime=self.a.runtime);s.load()
   try:self.expect(s.exports_sync.sum(19,23),42);self.expect(r.sum(19,23),42)
   finally:s.unload()
   return r.sum(19,23)
  self.case('multiple-scripts',multi)
  def syntax():
   try:self.session.create_script('function {',runtime=self.a.runtime)
   except Exception:return r.sum(19,23)
   raise AssertionError('invalid source accepted')
  self.case('syntax-error-recovery',syntax)
  def compiler():
   ts=self.out/'input.ts';ts.write_text('rpc.exports.sum=(a:number,b:number):number=>a+b;')
   bundle=self.api.Compiler().build(str(ts));(self.out/'compiled.js').write_text(bundle)
   s=self.session.create_script(bundle,runtime=self.a.runtime);s.load()
   try:return self.expect(s.exports_sync.sum(19,23),42)
   finally:s.unload()
  self.case('typescript-compiler',compiler)
  def cli():
   exe=Path(sys.executable).parent/('frida' if self.a.variant=='upstream' else 'jprobe')
   c=command([exe,'-H',f'127.0.0.1:{self.forward}','-p',str(self.pid),'--runtime',self.a.runtime,'-q','-t','2','-e',"Java.perform(()=>{const F=Java.use('dev.jprobe.lab.Fixture');console.log('CLI_RESULT:'+F.add.overload('int','int').call(F,19,23));});"],timeout=40)
   (self.out/'cli.log').write_text(c.stdout+c.stderr);assert 'CLI_RESULT:42' in c.stdout,c.stdout;return True
  self.case('cli-java-bridge',cli)
  self.case('cli-help-entrypoints',self.cli_help)
  for size in [0,524565]:self.case(f'cli-file-roundtrip-{size}',lambda n=size:self.cli_files(n))
  self.case('message-stream',lambda:self.message_stream(1000))
  self.case('post-recv',self.post_recv)
  self.case('spawn-gating',self.spawn_gating)
  self.case('detach-target-alive',lambda:(self.detach(),self.independent())[1])
  self.case('native-cli-trace',self.cli_trace)
  if self.a.runtime=='qjs':self.case('worker-rpc-termination',self.worker_test)
  else:
   self.results.append({'id':'worker-rpc-termination','status':'SKIP','reason':'Pinned upstream gumjs tests restrict Worker to QuickJS'});self.checkpoint()
  if (self.artifact.parent/'jprobe-inject').exists():self.case('standalone-inject',self.standalone_inject)
 def worker_test(self):
  main="import { url } from './worker.js'; rpc.exports.check=async()=>{const w=new Worker(url);try{return await w.exports.add(19,23);}finally{w.terminate();}};\n"
  worker="export const url=import.meta.url; export function run(){rpc.exports.add=(a,b)=>a+b;}\n"
  source=f'📦\n{len(main.encode())} /main.js\n{len(worker.encode())} /worker.js\n✄\n{main}\n✄\n{worker}'
  s=self.session.create_script(source,runtime=self.a.runtime);s.load()
  try:return self.expect(s.exports_sync.check(),42)
  finally:s.unload()
 def performance(self):
  import random,statistics,csv
  if not self.case('attach-load',lambda:self.start().identity()):return
  r=self.script.exports_sync;rows=[];order=['empty','native-attach','native-replace'];random.Random(20261102).shuffle(order)
  for mode in order:
   def measure(m=mode):
    if m=='native-attach':r.install_native()
    if m=='native-replace':r.replace_native()
    try:
     expected=(42 if m=='empty' else 43)*2000
     for i in range(35):
      start=time.perf_counter_ns();self.expect(r.benchmark(2000),expected);elapsed=time.perf_counter_ns()-start
      if i>=5:rows.append({'mode':m,'iteration':i-5,'ns':elapsed,'calls':2000})
    finally:r.restore_native()
    values=sorted(x['ns'] for x in rows if x['mode']==m);return {'median_ns':statistics.median(values),'p95_ns':values[28],'samples':len(values),'includes_rpc':True}
   self.case('benchmark-'+mode,measure)
  with (self.out/'performance.csv').open('w') as f:
   w=csv.DictWriter(f,fieldnames=['mode','iteration','ns','calls']);w.writeheader();w.writerows(rows)
 def recovery(self):
  for iteration in range(10):
   def target_exit():
    self.start();done=threading.Event();reasons=[]
    self.session.on('detached',lambda reason,*rest:(reasons.append(str(reason)),done.set()))
    self.shell(f'am force-stop {PKG}');assert done.wait(10),'target exit did not detach session'
    self.start();self.independent();return reasons
   self.case(f'target-exit-{iteration}',target_exit)
   def reconnect():
    self.start();endpoint=f'127.0.0.1:{self.forward}';self.detach()
    self.api.get_device_manager().remove_remote_device(endpoint)
    self.device=self.api.get_device_manager().add_remote_device(endpoint);self.start();return self.independent()
   self.case(f'client-reconnect-{iteration}',reconnect)
   def restart_server():
    self.start();done=threading.Event();self.session.on('detached',lambda *args:done.set())
    stop_owned(self.shell,self.server_pid,f'{self.remote}/server');assert done.wait(10),'server exit did not detach session';self.detach()
    extra='' if self.a.variant=='upstream' else f'--directory re.jprobe.regression.{self.run_tag}'
    prefix='JPROBE_AGENT_FILE_MODE=1 ' if self.a.file_mode=='file' and self.a.variant!='upstream' else ''
    self.shell(f'{prefix}nohup {self.remote}/server -l 127.0.0.1:{self.port} {extra} >>{self.remote}/server.log 2>&1 </dev/null & echo $! >{self.remote}/server.pid')
    self.server_pid=int(self.shell(f'cat {self.remote}/server.pid'));self.save_owned()
    wait_listener(self.shell,self.server_pid,f'{self.remote}/server',self.port)
    endpoint=f'127.0.0.1:{self.forward}'
    self.api.get_device_manager().remove_remote_device(endpoint);self.device=self.api.get_device_manager().add_remote_device(endpoint)
    for _ in range(40):
     try:self.device.enumerate_processes();break
     except Exception:time.sleep(.1)
    self.start();return self.independent()
   self.case(f'server-restart-{iteration}',restart_server)
 def edge(self):
  if self.a.edge_case=='child':self.case('native-child-gating',self.child_gating)
  else:self.case('late-load-'+self.a.edge_case,lambda:self.expect(self.start().late_module(self.a.edge_case),True))
 def cli_help(self):
  prefix='frida' if self.a.variant=='upstream' else 'jprobe';files=sorted(Path(sys.executable).parent.glob(prefix+'*'))
  for path in files:
   if path.is_file():command([path,'--help'],timeout=15)
  return {'entrypoints':[p.name for p in files]}
 def cli_files(self,size):
  prefix='frida' if self.a.variant=='upstream' else 'jprobe';bin=Path(sys.executable).parent
  source=self.out/f'测试-{size}.bin';source.write_bytes(bytes(i%251 for i in range(size)));target=self.out/f'returned-{size}.bin';remote=f'{self.remote}/file-{size}.bin'
  command([bin/(prefix+'-push'),'-H',f'127.0.0.1:{self.forward}',source,remote])
  command([bin/(prefix+'-pull'),'-H',f'127.0.0.1:{self.forward}',remote,target])
  return self.expect(sha(source),sha(target))
 def standalone_inject(self):
  self.detach();self.shell(f'am force-stop {PKG}');self.shell(f'am start -W -n {PKG}/dev.jprobe.lab.MainActivity');self.pid=int(self.shell(f'pidof {PKG}'))
  binary=self.artifact.parent/'jprobe-inject';self.adb('push',str(binary),f'{self.remote}/inject');self.shell(f'chmod 755 {self.remote}/inject')
  marker=f'/data/user/0/{PKG}/inject-{self.run_tag}.json';source=self.out/'inject.js';source.write_text(f"File.writeAllText('{marker}',JSON.stringify({{pid:Process.id,value:19+23}}));")
  self.adb('push',str(source),f'{self.remote}/inject.js')
  output=self.shell(f'JPROBE_AGENT_FILE_MODE=1 {self.remote}/inject -p {self.pid} -s {self.remote}/inject.js -R {self.a.runtime} -e',timeout=45)
  (self.out/'inject.log').write_text(output);result=json.loads(self.shell(f'cat {marker}'));self.expect(result,{'pid':self.pid,'value':42});return {'result':result,'injectSha256':sha(binary)}
 def concurrency(self):
  self.case('four-process-concurrency',self.concurrent_run)
 def concurrent_run(self):
  self.shell(f'am start -W -n {PKG}/dev.jprobe.lab.MainActivity');sessions=[];scripts=[];pids=[]
  try:
   for i in range(4):
    component=shlex.quote(f'{PKG}/dev.jprobe.lab.LabServices$P{i}');self.shell(f'am startservice -n {component}')
    for _ in range(40):
     raw=self.shell(f'pidof {PKG}:p{i}',check=False)
     if raw:break
     time.sleep(.1)
    pid=int(raw);pids.append(pid)
    for _ in range(60):
     baseline=self.shell(f'cat /data/user/0/{PKG}/files/process-P{i}.json',check=False)
     try:data=json.loads(baseline)
     except ValueError:data={}
     if data.get('pid')==pid and data.get('java')==42 and data.get('native')==42:break
     time.sleep(.1)
    else:raise AssertionError(f'process {i} never became ready: {baseline}')
    s=self.device.attach(pid);sessions.append(s);agent=s.create_script(self.source,runtime=self.a.runtime);scripts.append(agent);agent.on('message',self.message);agent.load();agent.exports_sync.install_java(False);agent.exports_sync.install_native()
   start=time.monotonic();checks=0;time.sleep(1.5)
   while time.monotonic()-start<self.a.concurrent_seconds:
    for i,pid in enumerate(pids):
     raw=self.shell(f'cat /data/user/0/{PKG}/files/process-P{i}.json; echo; date +%s');payload,device_time=raw.rsplit('\n',1);data=json.loads(payload)
     with (self.out/'concurrency-values.jsonl').open('a') as f:f.write(json.dumps({'expectedPid':pid,'process':i,'actual':data,'time':time.time(),'deviceTime':int(device_time)})+'\n')
     self.expect(data['pid'],pid);self.expect(data['java'],43);self.expect(data['native'],43);verify_heartbeat_time(data['time'],device_time)
    checks+=1;(self.out/'heartbeat.json').write_text(json.dumps({'time':time.time(),'elapsed':time.monotonic()-start,'checks':checks,'pids':pids}));time.sleep(5)
   return {'pids':pids,'checks':checks,'seconds':time.monotonic()-start}
  finally:
   for script in scripts:
    try:script.unload()
    except Exception:pass
   for session in sessions:
    try:session.detach()
    except Exception:pass
 def child_gating(self):
  def stage(s):(self.out/'child-stage.json').write_text(json.dumps({'stage':s,'time':time.time()}))
  children=[];ready=threading.Event();stage('spawn');pid=self.device.spawn([f'{self.remote}/lab','fork']);stage('attach');session=self.device.attach(pid)
  def child(c):
   if c.parent_pid==pid:children.append(c.pid);ready.set()
  self.device.on('child-added',child);stage('enable');session.enable_child_gating()
  try:
   stage('resume');self.device.resume(pid);stage('wait-event');assert ready.wait(15),'child event absent'
   stage('resume-child')
   for child_pid in children:self.device.resume(child_pid)
   stage('complete');return children
  finally:
   self.device.off('child-added',child)
   try:session.detach()
   except self.api.InvalidOperationError:pass
   for p in [pid,*children]:
    try:self.device.kill(p)
    except Exception:pass
 def cli_trace(self):
  self.start();exe=Path(sys.executable).parent/('frida-trace' if self.a.variant=='upstream' else 'jprobe-trace')
  logfile=self.out/'trace.log'
  with logfile.open('w') as log:
   proc=subprocess.Popen([str(exe),'-H',f'127.0.0.1:{self.forward}','-p',str(self.pid),'-i','liblab.so!lab_add','-q'],cwd=self.out.resolve(),stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.PIPE,start_new_session=True)
   try:
    for _ in range(10):self.independent();time.sleep(.3)
   finally:
    if proc.poll() is None:
     proc.send_signal(signal.SIGINT)
     try:proc.wait(5)
     except subprocess.TimeoutExpired:proc.kill();proc.wait()
  text=logfile.read_text();assert re.search(r'lab_add\(',text),text[-2000:];return {'observed':len(re.findall(r'lab_add\(',text))}
 def message_stream(self,count):
  received=[];ready=threading.Event()
  s=self.session.create_script('rpc.exports.emit=(base,n)=>{for(let i=0;i<n;i++)send(base+i);};',runtime=self.a.runtime)
  def message(m,d):
   if m['type']=='send':
    received.append(m['payload'])
    if len(received)%1000==0:ready.set()
  s.on('message',message);s.load()
  try:
   for base in range(0,count,1000):
    ready.clear();s.exports_sync.emit(base,min(1000,count-base))
    assert ready.wait(15),'message batch timed out'
   self.expect(received,list(range(count)));return {'received':len(received)}
  finally:s.unload()
 def post_recv(self):
  ready=threading.Event();seen=[]
  s=self.session.create_script("recv('ping',m=>send({echo:m.payload}));",runtime=self.a.runtime)
  s.on('message',lambda m,d:(seen.append(m),ready.set()));s.load()
  try:s.post({'type':'ping','payload':'中文🙂'});assert ready.wait(10);self.expect(seen[0]['payload']['echo'],'中文🙂');return True
  finally:s.unload()
 def spawn_gating(self):
  self.detach();self.shell(f'am force-stop {PKG}');seen=[];ready=threading.Event()
  def spawned(spawn):
   if spawn.identifier==PKG:seen.append(spawn.pid);ready.set()
   else:
    def resume_other():
     try:self.device.resume(spawn.pid)
     except Exception:pass
    threading.Thread(target=resume_other,daemon=True).start()
  self.device.on('spawn-added',spawned);self.device.enable_spawn_gating()
  try:
   self.shell(f'am start -n {PKG}/dev.jprobe.lab.MainActivity');assert ready.wait(15),'no matching spawn event'
   self.pid=seen[0];self.session=self.device.attach(self.pid)
   s=self.session.create_script('rpc.exports.pid=()=>Process.id;',runtime=self.a.runtime);s.load();self.expect(s.exports_sync.pid(),self.pid);self.device.resume(self.pid);s.unload()
  finally:
   self.device.disable_spawn_gating();self.device.off('spawn-added',spawned)
   for pid in seen:
    try:self.device.resume(pid)
    except Exception:pass
  for _ in range(40):
   if 'liblab.so' in self.shell(f'cat /proc/{self.pid}/maps'):break
   time.sleep(.2)
  else:raise RuntimeError('fixture did not finish loading after spawn gating')
  self.script=self.session.create_script(self.source,runtime=self.a.runtime);self.script.load();return self.independent()
 def custom(self):
  if not self.case('attach-load',lambda:self.start(bridge=False).identity()):return
  r=self.script.exports_sync
  def identity():
   v=r.identity();self.expect(v['version'],'17.25.0');self.expect(v['arch'],'arm64')
   if self.a.variant!='upstream':self.expect(v['old'],'undefined')
   return v
  self.case('runtime-identity',identity)
  def collect(stage):
   text=self.shell(f'cat /proc/{self.pid}/maps; cat /proc/{self.pid}/smaps; ls -l /proc/{self.pid}/fd; for f in /proc/{self.pid}/task/*/comm; do cat "$f"; done')
   (self.out/f'{stage}-proc.txt').write_text(text);return len(text)
  self.case('empty-script-mappings',lambda:collect('empty'))
  self.case('native-hook-mappings',lambda:(r.install_native(),collect('native'),r.restore_native()))
  self.case('cmodule-mappings',lambda:(r.cmodule(),collect('cmodule-after')))
  self.case('stalker-mappings',lambda:(r.stalker(),collect('stalker-after')))
  def threads():
   snapshots=[]
   for _ in range(10):
    r.sum(19,23);snapshots+=self.shell(f'for f in /proc/{self.pid}/task/*/comm; do cat "$f"; done').splitlines();time.sleep(.1)
   names=sorted(set(snapshots));(self.out/'thread-names.json').write_text(json.dumps(names))
   if self.a.variant in ['r8','r9']:
    for old in ['gmain','gdbus','gum-js-loop']:assert old not in names,names
    for new in ['jp-main','jp-ipc','jp-js-loop']:assert new in names,names
   return names
  self.case('thread-names',threads)
  def audit():
   data=self.artifact.read_bytes();hits={k:[m.start() for m in re.finditer(p,data,re.I)] for k,p in [('ascii',b'frida'),('utf16le',b'f\x00r\x00i\x00d\x00a\x00')]}
   (self.out/'keyword-hits.json').write_text(json.dumps(hits))
   if self.a.variant!='upstream':assert not any(hits.values()),hits
   return {k:len(v) for k,v in hits.items()}
  self.case('server-keyword-audit',audit)
 def stress(self):
  if not self.case('attach-load',lambda:self.start().identity()):return
  self.case('messages-100000',lambda:self.message_stream(100000))
  for i in range(100):
   if not self.case(f'attach-cycle-{i}',lambda:(self.detach(),self.reattach())[1]):break
  for i in range(50):
   if not self.case(f'spawn-cycle-{i}',lambda:self.expect(self.start(True).sum(19,23),42)):break
  for i in range(500):
   def load():
    s=self.session.create_script('rpc.exports.sum=(a,b)=>a+b;',runtime=self.a.runtime);s.load()
    try:self.expect(s.exports_sync.sum(19,23),42)
    finally:s.unload()
   if not self.case(f'script-cycle-{i}',load):break
  for i in range(50):
   def switch():
    self.shell('input keyevent KEYCODE_HOME');time.sleep(.1);self.shell(f'am start -W -n {PKG}/dev.jprobe.lab.MainActivity');self.expect(int(self.shell(f'pidof {PKG}')),self.pid);return self.java_roundtrip()
   if not self.case(f'foreground-{i}',switch):break
  self.case('soak',self.soak)
 def soak(self):
  r=self.script.exports_sync;r.install_java(False);r.install_native();start=time.monotonic();last_sample=0;checks=0
  try:
   while time.monotonic()-start<self.a.soak_seconds:
    i=int(time.monotonic()-start)
    self.independent(43,43);checks+=1
    (self.out/'heartbeat.json').write_text(json.dumps({'time':time.time(),'elapsed':i,'checks':checks,'duration':self.a.soak_seconds}))
    if time.monotonic()-last_sample>=10:
     for pid in [self.pid,self.server_pid]:
      sample=self.shell(f'cat /proc/{pid}/status; cat /proc/{pid}/smaps_rollup; cat /proc/{pid}/stat; ls /proc/{pid}/fd | wc -l',check=False)
      with (self.out/'resources.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'pid':pid,'sample':sample})+'\n')
     last_sample=time.monotonic()
    time.sleep(5)
  finally:r.restore_java();r.restore_native()
  return {'elapsed':time.monotonic()-start,'checks':checks}
 def reattach(self):
  self.session=self.device.attach(self.pid);self.script=self.session.create_script(self.source,runtime=self.a.runtime);self.script.load();return self.expect(self.script.exports_sync.sum(19,23),42)
 def gadget(self):
  from integrations import gadget
  gadget(self)
 def lifecycle(self):
  from integrations import lifecycle
  lifecycle(self)
 def detection(self):
  from integrations import detection
  detection(self)
 def detection_signals(self):
  from integrations import detection_signals
  detection_signals(self)
 def cleanup(self):
  if hasattr(self,'source_hashes'):
   changed=[name for name,digest in self.source_hashes.items() if sha(ROOT/name)!=digest]
   if changed:self.results.append({'id':'harness-source-stability','status':'BLOCKED','reason':'Harness changed during run: '+','.join(changed)})
  try:self.detach()
  except Exception as e:self.results.append({'id':'cleanup-session','status':'FAIL','error':str(e)})
  try:
   if self.pid:(self.out/'target-logcat.txt').write_text(self.adb('logcat','-d',f'--pid={self.pid}','-t','500',check=False))
   (self.out/'server.log').write_text(self.shell(f'cat {self.remote}/server.log',check=False))
   if self.server_pid:stop_owned(self.shell,self.server_pid,f'{self.remote}/server')
   if self.forward:self.adb('forward','--remove',f'tcp:{self.forward}',check=False)
   self.shell(f'am force-stop {PKG}',check=False)
  except Exception as e:self.results.append({'id':'cleanup-device','status':'FAIL','error':str(e)})
  self.checkpoint()
def main():
 p=argparse.ArgumentParser();p.add_argument('--serial',required=True);p.add_argument('--variant',choices=['upstream','r7','r8','r9'],required=True);p.add_argument('--runtime',choices=['qjs','v8'],required=True);p.add_argument('--suite',choices=['smoke','functional','custom','stress','all','gadget','detection','edge','performance','recovery','concurrency','lifecycle','detection_signals'],required=True);p.add_argument('--port',type=int,default=35110);p.add_argument('--detection-mode',choices=['baseline','server','empty','java','native'],default='empty');p.add_argument('--repeats',type=int,default=10);p.add_argument('--detector-apk',default=str(Path.home()/'workspace/pj/pjspace/fatdog/FatdogReverse.apk'));p.add_argument('--edge-case',choices=['none','record','lookup','hook','child'],default='record');p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,default=WORK/'verification/jprobe-regression/fixtures/base-v3');p.add_argument('--server',type=Path,required=True);p.add_argument('--file-mode',choices=['file','default'],default='file');p.add_argument('--concurrent-seconds',type=int,default=1800);p.add_argument('--soak-seconds',type=int,default=7200);p.add_argument('--worker',action='store_true');a=p.parse_args()
 if not a.worker:
  import fcntl
  lock=open('/tmp/jprobe-regression-'+hashlib.sha256(a.serial.encode()).hexdigest()[:12]+'.lock','w')
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
  a.output.mkdir(parents=True,exist_ok=False)
  with (a.output/'console.log').open('w') as log:
   child=subprocess.Popen([sys.executable,__file__,*sys.argv[1:],'--worker'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:
    deadline=time.monotonic()+(a.soak_seconds+2400 if a.suite in ['stress','all','concurrency'] else (a.repeats*7*50+300 if a.suite=='detection' else 1200))
    while child.poll() is None:
     if time.monotonic()>deadline:raise subprocess.TimeoutExpired('suite',deadline)
     active=a.output/'active.json'
     if active.exists():
      try:
       c=json.loads(active.read_text());age=time.time()-c['started']
       if c['id'] in ['soak','four-process-concurrency']:
        heartbeat=a.output/'heartbeat.json'
        age=time.time()-json.loads(heartbeat.read_text())['time'] if heartbeat.exists() else age
       if age>90:raise subprocess.TimeoutExpired(c['id'],90)
      except (json.JSONDecodeError,FileNotFoundError):pass
     time.sleep(.5)
    rc=child.returncode
   except (subprocess.TimeoutExpired,KeyboardInterrupt):
    os.killpg(child.pid,signal.SIGKILL);child.wait();rc=124
    (a.output/'watchdog.json').write_text(json.dumps({'status':'FAIL','reason':'watchdog timeout or interrupt'}))
    rec=Runner.__new__(Runner);rec.a=a;rec.out=a.output;rec.results=[]
    if (a.output/'results.json').exists():rec.results=json.loads((a.output/'results.json').read_text())['cases']
    current=json.loads((a.output/'active.json').read_text()) if (a.output/'active.json').exists() else {'id':'startup'}
    rec.results.append({'id':'watchdog-'+current['id'],'status':'FAIL','error':'worker exceeded deadline or was interrupted'});rec.checkpoint()
   finally:
    owned=a.output/'owned.json'
    if owned.exists():
     d=json.loads(owned.read_text());adb=['adb','-s',a.serial]
     try:stop_owned(lambda s,**kw:command(adb+['shell',s],**kw).stdout.strip(),d['serverPid'],d['serverPath'])
     except Exception as e:
      rc=1;(a.output/'cleanup-error.json').write_text(json.dumps({'error':str(e)}))
     if d.get('forward'):command(adb+['forward','--remove',f'tcp:{d["forward"]}'],check=False)
     command(adb+['shell',f'am force-stop {d["package"]}'],check=False)
     if d.get('nativePath'):
      cleanup='for p in /proc/[0-9]*; do e=$(readlink "$p/exe"); if [ "$e" = '+shlex.quote(d['nativePath'])+' ]; then kill -9 "${p##*/}"; fi; done'
      command(adb+['shell',cleanup],check=False)
  (a.output/'completion.json').write_text(json.dumps({'exitCode':rc,'finished':time.time()}))
  print(f'{a.output}: exit={rc}');return rc
 r=Runner(a)
 try:
  if r.case('environment-and-deploy',r.setup):
   for s in (['smoke','functional','custom','stress'] if a.suite=='all' else [a.suite]):
    if hasattr(r,s):getattr(r,s)()
    else:r.blocked(s,'Suite requires dedicated orchestration; not implemented by generic server runner')
 except Exception as e:
  r.results.append({'id':'suite-infrastructure','status':'FAIL','error':str(e),'trace':traceback.format_exc()});r.checkpoint()
 finally:r.cleanup()
 return 1 if any(x['status']=='FAIL' for x in r.results) else (2 if any(x['status']=='BLOCKED' for x in r.results) else 0)
if __name__=='__main__':sys.exit(main())
