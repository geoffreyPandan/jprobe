'use strict';
let hooks = [], replacements = [], savedJava = null;
let attributedPage = null;
let attributedCallback = null;
const eq = (a,b) => { if (JSON.stringify(a)!==JSON.stringify(b)) throw new Error(JSON.stringify({actual:a,expected:b})); };
const lab = () => Process.getModuleByName('liblab.so');
const sym = n => lab().getExportByName(n);
const add = () => new NativeFunction(sym('lab_add'),'int',['int','int']);
rpc.exports = {
 identity() { return {version:typeof Jprobe!=='undefined'?Jprobe.version:Frida.version, runtime:Script.runtime, arch:Process.arch, pid:Process.id, old:typeof Frida}; },
 sum(a,b) {return a+b;}, async asyncSum(a,b) {await new Promise(r=>setTimeout(r,5));return a+b;},
 fail() {throw new Error('expected-rpc-error');}, echo(data){return data;},
 messages(n){for(let i=0;i<n;i++)send({seq:i});return n;},
 semantics(){eq(new Date('2026-10-30T12:00:00Z').toUTCString(),'Fri, 30 Oct 2026 12:00:00 GMT');eq(JSON.parse(JSON.stringify({a:'中文🙂'})),{a:'中文🙂'});return true;},
 memory(){let p=Memory.alloc(4096);p.writeUtf8String('hello-中文');eq(p.readUtf8String(),'hello-中文');p.add(64).writeU64(uint64('9007199254740993'));eq(p.add(64).readU64().toString(),'9007199254740993');eq(Memory.scanSync(p,32,'68 65 6c 6c 6f').length,1);let caught=false;try{ptr(1).readU32();}catch(e){caught=true;}eq(caught,true);return true;},
 attributedMemory(executable){
  if(!executable){attributedPage=Memory.alloc(Process.pageSize);const w=new Arm64Writer(attributedPage);w.putLdrRegU64('x0',42);w.putRet();w.flush();}
  else {eq(Memory.protect(attributedPage,Process.pageSize,'r-x'),true);eq(new NativeFunction(attributedPage,'int',[])(),42);}
  return attributedPage.toString();
 },
 attributedClosure(){attributedCallback=new NativeCallback(()=>42,'int',[]);eq(new NativeFunction(attributedCallback,'int',[])(),42);return attributedCallback.toString();},
 native(){eq(add()(19,23),42);eq(new NativeFunction(sym('lab_double'),'double',['double'])(1.25),2.5);eq(new NativeFunction(sym('lab_i64'),'int64',['int64'])(int64('9007199254740993')).toString(),'9007199254740994');const cb=new NativeCallback(x=>x+1,'int',['int']);eq(new NativeFunction(sym('lab_callback'),'int',['pointer','int'])(cb,41),42);const r=new SystemFunction(sym('lab_errno'),'int',[])();eq(r.value,-1);eq(r.errno,22);eq(new NativeFunction(sym('lab_recurse'),'int',['int'])(5),5);return true;},
 installNative(){hooks.push(Interceptor.attach(sym('lab_add'),{onLeave(r){r.replace(r.toInt32()+1);}}));Interceptor.flush();return true;},
 replaceNative(){const p=sym('lab_add');const cb=new NativeCallback((a,b)=>a+b+1,'int',['int','int']);Interceptor.replace(p,cb);replacements.push({p,cb});Interceptor.flush();return true;},
 restoreNative(){hooks.forEach(h=>h.detach());hooks=[];replacements.forEach(x=>Interceptor.revert(x.p));replacements=[];Interceptor.flush();return true;},
 cmodule(){const cm=new CModule('int answer(void){return 42;}');eq(new NativeFunction(cm.answer,'int',[])(),42);cm.dispose();return true;},
 patch(){const p=Memory.alloc(Process.pageSize);Memory.patchCode(p,16,c=>{const w=new Arm64Writer(c,{pc:p});w.putLdrRegU64('x0',42);w.putRet();w.flush();});Memory.protect(p,Process.pageSize,'r-x');eq(new NativeFunction(p,'int',[])(),42);return Instruction.parse(p).mnemonic;},
 symbols(){eq(Module.getGlobalExportByName('getpid').isNull(),false);eq(Module.findGlobalExportByName('jprobe_missing_symbol_9d7c'),null);eq(lab().enumerateExports().some(x=>x.name==='lab_add'),true);return {threads:Process.enumerateThreads().length,modules:Process.enumerateModules().length};},
 stalker(){let n=0;const f=new NativeFunction(sym('lab_add'),'int',['int','int'],{traps:'all'});const target=sym('lab_add');const tid=Process.getCurrentThreadId();Stalker.follow(tid,{transform(it){let ins;while((ins=it.next())!==null){if(ins.address.equals(target))it.putCallout(()=>n++);it.keep();}}});let value=f(19,23);Stalker.unfollow(tid);Stalker.flush();eq(value,42);eq(n,1);return new Promise(resolve=>setTimeout(()=>{Stalker.garbageCollect();resolve(n);},50));},
 javaBasic(){return new Promise((resolve,reject)=>Java.perform(()=>{try{const F=Java.use('dev.jprobe.lab.Fixture');eq(F.add.overload('int','int').call(F,19,23),42);eq(String(F.add.overload('java.lang.String','java.lang.String').call(F,'中','文')),'中文');const x=F.$new(19);eq(x.instance(23),42);x.value.value=20;eq(x.instance(22),42);eq(Array.from(F.array(Java.array('int',[1,2,3]))),[1,2,3]);let threw=false;try{F.fail();}catch(e){threw=String(e).includes('fixture-error');}eq(threw,true);x.$dispose();resolve(true);}catch(e){reject(e);}}));},
 installJava(deopt){return new Promise((resolve,reject)=>Java.perform(()=>{try{if(deopt)Java.deoptimizeEverything();const F=Java.use('dev.jprobe.lab.Fixture');savedJava=F.add.overload('int','int');let sampled=0;savedJava.implementation=function(a,b){const original=savedJava.call(this,a,b);if(sampled++<5)send({kind:'java-hook-call',pid:Process.id,a,b,original,result:original+1});return original+1;};resolve(true);}catch(e){reject(e);}}));},
 restoreJava(){return new Promise(resolve=>Java.perform(()=>{if(savedJava)savedJava.implementation=null;savedJava=null;resolve(true);}));},
 javaMain(){return new Promise(resolve=>Java.perform(()=>Java.scheduleOnMainThread(()=>resolve(Java.isMainThread()))));},
 javaClasses(){return new Promise(resolve=>Java.perform(()=>{const names=Java.enumerateLoadedClassesSync();resolve({fixture:names.includes('dev.jprobe.lab.Fixture'),loaders:Java.enumerateClassLoadersSync().length});}));},
 javaObjects(){return new Promise((resolve,reject)=>Java.perform(()=>{try{const F=Java.use('dev.jprobe.lab.Fixture');const x=Java.retain(F.$new(7));let found=0;Java.choose('dev.jprobe.lab.Fixture',{onMatch(v){if(v.value.value===7)found++;},onComplete(){try{if(found<1)throw new Error('retained object not found');x.$dispose();const T=Java.registerClass({name:'dev.jprobe.test.DynamicRunnable',implements:[Java.use('java.lang.Runnable')],methods:{run(){}}});const obj=T.$new();obj.run();obj.$dispose();resolve(found);}catch(e){reject(e);}}});}catch(e){reject(e);}}));},
 javaLoader(path){const data=File.readAllBytes(path);return new Promise((resolve,reject)=>Java.perform(()=>{try{const bytes=Java.array('byte',Array.from(new Uint8Array(data),x=>x>127?x-256:x));const buffer=Java.use('java.nio.ByteBuffer').wrap(bytes);const parent=Java.use('dev.jprobe.lab.Fixture').class.getClassLoader();const loader=Java.use('dalvik.system.InMemoryDexClassLoader').$new(buffer,parent);const F=Java.ClassFactory.get(loader).use('dev.jprobe.plugin.Plugin');eq(F.answer(),42);resolve(true);}catch(e){reject(e);}}));},
 lateModule(mode='lookup'){
  let seen=false,addr=null,hook=null,callbackError=null;
  const observer=mode==='none'?null:Process.attachModuleObserver({onAdded(m){
   if(m.name!=='libdelay.so')return;
   seen=true;
   try{
    if(mode==='lookup'||mode==='hook'){
     eq(m.findExportByName('not_a_real_export'),null);
     addr=m.getExportByName('delayed_answer');
     eq(m.enumerateExports().find(e=>e.name==='delayed_answer').address.equals(addr),true);
     const data=m.findExportByName('delayed_value');
     if(data!==null)eq(data.readS32(),17);
     if(mode==='hook')hook=Interceptor.attach(addr,{onLeave(ret){ret.replace(43);}});
    }
   }catch(e){callbackError=e;}
  }});
  return new Promise((resolve,reject)=>Java.perform(()=>{try{
   Java.use('dev.jprobe.lab.Fixture').loadDelay();
   if(callbackError)throw callbackError;
   if(mode!=='none')eq(seen,true);
   const m=Process.getModuleByName('libdelay.so'),after=m.getExportByName('delayed_answer');
   if(addr!==null)eq(addr.equals(after),true);
   eq(new NativeFunction(after,'int',[])(),mode==='hook'?43:42);
   if(mode==='hook'){
    eq(new NativeFunction(m.getExportByName('delayed_constructor_value'),'int',[])(),43);
    hook.detach();hook=null;Interceptor.flush();
    eq(new NativeFunction(after,'int',[])(),42);
   }
   resolve(true);
  }catch(e){reject(e);}finally{if(hook)hook.detach();if(observer)observer.detach();}}));
 },
 benchmark(count){const f=add();let total=0;for(let i=0;i<count;i++)total+=f(19,23);return total;},
 javaBacktrace(){return new Promise(resolve=>Java.perform(()=>resolve(Java.backtrace({limit:16}).frames.length)));}
};
