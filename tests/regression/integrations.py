"""Gadget and external detector integrations; never replace detector results."""
import json,time,threading,socket,re
from pathlib import Path
def detector_result(tree):
 """Parse both the ordinary result and an authoritative detection dialog.

 Generic instructions mentioning Frida are not evidence of a detection.
 """
 texts=[n.get('text','').strip() for n in tree.iter('node')]
 positive=[s for s in texts if s=='已被 Frida 检测' or s.startswith('检测到 Frida 注入')]
 if positive:return {'detected':True,'status':'\n'.join(positive),'presentation':'dialog'}
 statuses=[s for s in texts if s.startswith('检测结果')]
 if not statuses:raise AssertionError('Missing detector result: '+repr(texts))
 text='\n'.join(statuses)
 if '未检出' in text:return {'detected':False,'status':text,'presentation':'result'}
 if '检出' in text or '检测到' in text:return {'detected':True,'status':text,'presentation':'result'}
 raise AssertionError('Unknown detector verdict: '+text)

def gadget(r):
 import run
 pkg=json.loads((r.fixture/'build.json').read_text())['package'];mode=json.loads((r.fixture/'build.json').read_text())['interaction']
 # run.py may execute as __main__; do not rely on imported run.PKG for package identity.
 r.shell(f'am force-stop {pkg}');portal=None;reverse=False
 def script_text(marker):
  return "rpc.exports.init=function(){setTimeout(()=>{const m=Process.getModuleByName('liblab.so');const f=new NativeFunction(m.getExportByName('lab_add'),'int',['int','int']);File.writeAllText('/data/user/0/"+pkg+"/gadget-"+marker+".json',JSON.stringify({value:f(19,23),uid:new NativeFunction(Module.getGlobalExportByName('getuid'),'uint',[])(),runtime:Script.runtime}));},100);};"
 try:
  if mode in ['script','script-directory']:
   r.shell('mkdir -p /data/local/tmp/jprobe-regression/gadget-scripts')
   for marker in (['one'] if mode=='script' else ['one','two']):
    p=r.out/f'{marker}.js';p.write_text(script_text(marker));dest='/data/local/tmp/jprobe-regression/gadget-script.js' if mode=='script' else f'/data/local/tmp/jprobe-regression/gadget-scripts/{marker}.js'
    r.adb('push',str(p),dest);r.shell(f'chmod 644 {dest}')
   r.shell(f'am start -W -n {pkg}/dev.jprobe.lab.MainActivity')
   for marker in (['one'] if mode=='script' else ['one','two']):
    def check(m=marker):
     for _ in range(40):
      output=r.shell(f'am broadcast --user 0 --receiver-foreground -a dev.jprobe.lab.RUN -n {pkg}/dev.jprobe.lab.RunReceiver --es marker {m}')
      match=re.search(r'MARKER:(\{.*\})',output)
      raw=match.group(1) if match else ''
      if raw.startswith('{'):break
      time.sleep(.25)
     data=json.loads(raw);r.expect(data['value'],42);assert data['uid']>=10000;return data
    r.case(f'gadget-{mode}-{marker}',check)
   return
  if mode=='connect':
   # Reserve a host port; reverse exposes it only inside this selected emulator.
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   ep=r.api.EndpointParameters(address='127.0.0.1',port=port)
   portal=r.api.PortalService(ep,None);joined=threading.Event();apps=[]
   portal.on('node-joined',lambda cid,app:(apps.append(app),joined.set()));portal.start()
   r.adb('reverse','tcp:35113',f'tcp:{port}');reverse=True;r.device=portal.device
   r.shell(f'am start -n {pkg}/dev.jprobe.lab.MainActivity');assert joined.wait(20),'Gadget did not join Portal'
  else:
   r.shell(f'am start -W -n {pkg}/dev.jprobe.lab.MainActivity')
   r.forward=int(r.adb('forward','tcp:0','tcp:35112'));r.device=r.api.get_device_manager().add_remote_device(f'127.0.0.1:{r.forward}')
  for _ in range(40):
   try:
    processes=r.device.enumerate_processes()
    if processes:break
   except Exception:pass
   time.sleep(.25)
  else:raise RuntimeError('Gadget process not enumerated')
  r.pid=int(r.shell(f'pidof {pkg}'));r.session=r.device.attach(processes[0].pid)
  if mode=='connect':r.device.resume(processes[0].pid)
  r.script=r.session.create_script(r.source,runtime=r.a.runtime);r.script.load()
  r.case(f'gadget-{mode}-rpc',lambda:r.expect(r.script.exports_sync.sum(19,23),42))
  r.case(f'gadget-{mode}-java',r.java_roundtrip)
  r.case(f'gadget-{mode}-native',r.native_roundtrip)
  r.case(f'gadget-{mode}-detach',lambda:(r.detach(),r.independent())[1])
 finally:
  r.detach()
  if portal:portal.stop()
  if reverse:r.adb('reverse','--remove','tcp:35113',check=False)

def detection(r):
 import xml.etree.ElementTree as ET
 import hashlib
 pkg='com.fatdog.reverse'
 apk=Path(r.a.detector_apk);assert apk.is_file(),apk
 r.adb('install','--no-incremental','-r',str(apk))
 (r.out/'detector.json').write_text(json.dumps({'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'mode':r.a.detection_mode,'port':r.port,'repeats':r.a.repeats}))
 screens=[('fox','c58Activity'),('owl','d59Activity'),('sun','e60Activity'),('ice','f61Activity'),('dusk','h63Activity'),('veil','i64Activity'),('snow','j65Activity')]
 def dump(path):
  remote='/data/local/tmp/jprobe-regression/fatdog-ui.xml'
  r.shell(f'uiautomator dump {remote}',timeout=20);xml=r.shell(f'cat {remote}');path.write_text(xml);return ET.fromstring(xml)
 for rep in range(r.a.repeats):
  for lib,activity in screens:
   def check():
    r.detach();r.shell(f'am force-stop {pkg}');r.shell(f'am start -W -n {pkg}/.MainActivity');pid=int(r.shell(f'pidof {pkg}'))
    before=r.shell(f'cat /proc/{pid}/maps');assert f'lib{lib}.so' not in before,'detector already loaded before instrumentation'
    if r.a.detection_mode not in ['baseline','server']:
     r.session=r.device.attach(pid)
     source='rpc.exports.ping=()=>42;'
     if r.a.detection_mode=='native':source+="const h=Interceptor.attach(Module.getGlobalExportByName('getpid'),{onEnter(){}});rpc.exports.ready=()=>true;"
     if r.a.detection_mode=='java':source=r.bridge.read_text()+"\nconst Java=bridge;\n"+source+"rpc.exports.ready=()=>new Promise((resolve,reject)=>Java.perform(()=>{try{const A=Java.use('android.app.Activity');const m=A.getTitle.overload();m.implementation=function(){return m.call(this);};resolve(true);}catch(e){reject(e);}}));"
     r.script=r.session.create_script(source,runtime=r.a.runtime);r.script.on('message',r.message);r.script.load();r.expect(r.script.exports_sync.ping(),42)
     if r.a.detection_mode in ['native','java']:r.expect(r.script.exports_sync.ready(),True)
    r.shell(f'am start -W -n {pkg}/.{activity}')
    folder=r.out/f'{rep:02d}-{lib}';folder.mkdir()
    tree=dump(folder/'before.xml')
    button=next((n for n in tree.iter('node') if n.get('text')=='运行检测'),None)
    if button is not None:
     coords=list(map(int,re.findall(r'\d+',button.get('bounds'))));r.shell(f'input tap {(coords[0]+coords[2])//2} {(coords[1]+coords[3])//2}')
     tree=dump(folder/'after.xml')
    result=detector_result(tree)
    r.expect(r.shell(f'pidof {pkg}',check=False),str(pid))
    (folder/'maps.txt').write_text(r.shell(f'cat /proc/{pid}/maps'))
    (folder/'threads.txt').write_text(r.shell(f'for f in /proc/{pid}/task/*/comm; do cat "$f"; done'))
    (folder/'status.txt').write_text(result['status'])
    return {**result,'pid':pid,'collectionOnly':True}
   r.case(f'detector-{rep:02d}-{lib}',check)
   r.detach();r.shell(f'am force-stop {pkg}')

def lifecycle(r):
 import subprocess,os
 r.shell(f'mkdir -p {r.remote}')
 host=r.fixture/'gadget-host'
 if not host.exists():
  cc=Path.home()/'Library/Android/sdk/ndk/29.0.13113456/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android32-clang'
  host=r.out/'gadget-host';subprocess.run([str(cc),str(Path(__file__).parent/'fixture/gadget-host.c'),'-ldl','-o',str(host)],check=True)
 r.adb('push',str(host),f'{r.remote}/gadget-host');r.adb('push',str(r.artifact),f'{r.remote}/libgadget.so');r.shell(f'chmod 755 {r.remote}/gadget-host')
 for mode in ['minimal','full']:
  def check():
   config=r.out/(mode+'.json');config.write_text(json.dumps({'interaction':{'type':'listen','address':'127.0.0.1','port':35112,'on_load':'resume'},'teardown':mode,'runtime':r.a.runtime}))
   r.adb('push',str(config),f'{r.remote}/libgadget.config.so');control=f'{r.remote}/unload-{mode}';log=f'{r.remote}/{mode}.log'
   exit_arg='exit' if mode=='minimal' else 'unload'
   r.shell(f'nohup {r.remote}/gadget-host {r.remote}/libgadget.so {control} {exit_arg} >{log} 2>&1 </dev/null & echo $! >{r.remote}/host.pid')
   pid=int(r.shell(f'cat {r.remote}/host.pid'));forward=int(r.adb('forward','tcp:0','tcp:35112'));session=None;script=None
   try:
    device=r.api.get_device_manager().add_remote_device(f'127.0.0.1:{forward}')
    for _ in range(40):
     try:processes=device.enumerate_processes();break
     except Exception:time.sleep(.1)
    session=device.attach(processes[0].pid);script=session.create_script('rpc.exports.sum=(a,b)=>a+b;',runtime=r.a.runtime);script.load();r.expect(script.exports_sync.sum(19,23),42);script.unload();script=None;session.detach();session=None
    r.shell(f'touch {control}')
    for _ in range(100):
     output=r.shell(f'cat {log}')
     if 'HOST_EXIT_OK' in output:break
     time.sleep(.1)
    (r.out/(mode+'-host.log')).write_text(output);assert 'HOST_EXIT_OK' in output,output
    metrics={k:int(v) for k,v in re.findall(r'(BASE_THREADS|LOADED_THREADS|UNLOADED_THREADS):(\d+)',output)}
    if mode=='full':assert metrics['UNLOADED_THREADS']<=metrics['BASE_THREADS']+1,metrics
    for _ in range(50):
     if r.shell(f'readlink /proc/{pid}/exe',check=False)!=f'{r.remote}/gadget-host':break
     time.sleep(.1)
    else:raise AssertionError('host did not exit after completion marker')
    return metrics
   finally:
    if script:script.unload()
    if session:session.detach()
    r.adb('forward','--remove',f'tcp:{forward}',check=False)
    if r.shell(f'readlink /proc/{pid}/exe',check=False)==f'{r.remote}/gadget-host':r.shell(f'kill {pid}',check=False)
  r.case('gadget-'+('normal-exit-minimal' if mode=='minimal' else 'dlclose-full'),check)

def detection_signals(r):
 """Read the lab detector's integer subchecks; never replace their results."""
 pkg='com.fatdog.reverse'
 for mode in ('empty','bridge','java-hook'):
  def check():
   r.detach();r.shell(f'am force-stop {pkg}');r.shell(f'am start -W -n {pkg}/.MainActivity')
   pid=int(r.shell(f'pidof {pkg}'));r.session=r.device.attach(pid)
   source='rpc.exports.ready=()=>true;'
   if mode!='empty':
    action="const A=Java.use('android.app.Activity');const m=A.getTitle.overload();m.implementation=function(){return m.call(this);};" if mode=='java-hook' else ''
    source=r.bridge.read_text()+'\nconst Java=bridge;\nrpc.exports.ready=()=>new Promise((resolve,reject)=>Java.perform(()=>{try{'+action+'resolve(true);}catch(e){reject(e);}}));'
   source+="rpc.exports.signals=()=>{const m=Process.getModuleByName('libdusk.so');const result={};for(const name of ['Timing','Version','SmapsDirty','AnonExec','Trampoline','LibcPrologue'])result[name]=new NativeFunction(m.getExportByName('Java_com_fatdog_reverse_Sk_native'+name),'int',['pointer','pointer'])(ptr(0),ptr(0));return result;};"
   r.script=r.session.create_script(source,runtime=r.a.runtime);r.script.load();r.expect(r.script.exports_sync.ready(),True)
   r.shell(f'am start -W -n {pkg}/.h63Activity')
   signals=r.script.exports_sync.signals();r.expect(r.shell(f'pidof {pkg}'),str(pid))
   (r.out/(mode+'-maps.txt')).write_text(r.shell(f'cat /proc/{pid}/maps'))
   (r.out/(mode+'-smaps.txt')).write_text(r.shell(f'cat /proc/{pid}/smaps'))
   return {'mode':mode,'pid':pid,'signals':signals,'observationOnly':True}
  r.case('dusk-signals-'+mode,check)
  r.detach();r.shell(f'am force-stop {pkg}')
