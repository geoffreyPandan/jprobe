#!/usr/bin/env python3
"""Offline fixture build using installed Android SDK/NDK and JDK 17."""
import argparse,hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def run(*a):subprocess.run([str(x) for x in a],check=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--gadget',type=Path);p.add_argument('--runtime',default='qjs',choices=['qjs','v8']);p.add_argument('--interaction',default='listen',choices=['listen','script','script-directory','connect']);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 sdk=Path(os.environ.get('ANDROID_HOME',str(Path.home()/'Library/Android/sdk')))
 bt=sdk/'build-tools/35.0.1'; android=sdk/'platforms/android-32/android.jar'
 cc=sdk/'ndk/29.0.13113456/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android32-clang'
 java=Path('/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin')
 for x in [bt/'aapt',bt/'d8',cc,java/'javac']:assert x.exists(),x
 src=ROOT/'fixture';classes=out/'classes';classes.mkdir();dex=out/'dex';dex.mkdir()
 package='dev.jprobe.lab.gadget' if a.gadget else 'dev.jprobe.lab'
 manifest=out/'AndroidManifest.xml'
 manifest.write_text(f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{package}" android:versionCode="1" android:versionName="1"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="32"/><uses-permission android:name="android.permission.INTERNET"/><application android:label="Jprobe Regression" android:debuggable="false" android:extractNativeLibs="true" android:allowBackup="false"><activity android:name="dev.jprobe.lab.MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity><receiver android:name="dev.jprobe.lab.RunReceiver" android:exported="true"/></application></manifest>''')
 services=''.join(f'<service android:name="dev.jprobe.lab.LabServices$P{i}" android:process=":p{i}" android:exported="true"/>' for i in range(4))
 manifest.write_text(manifest.read_text().replace('</application>',services+'</application>'))
 sources=[p for p in src.glob('*.java') if p.name!='Plugin.java']
 if a.gadget:
  f=out/'Fixture.java';f.write_text((src/'Fixture.java').read_text().replace('System.loadLibrary("lab");','System.loadLibrary("lab"); System.loadLibrary("gadget");'));sources=[x for x in sources if x.name!='Fixture.java']+[f]
 run(java/'javac','-source','8','-target','8','-bootclasspath',android,'-d',classes,*sources)
 run(bt/'d8','--lib',android,'--min-api','26','--output',dex,*classes.rglob('*.class'))
 pc=out/'plugin-classes';pc.mkdir();pd=out/'plugin-dex';pd.mkdir()
 run(java/'javac','-source','8','-target','8','-bootclasspath',android,'-d',pc,src/'Plugin.java')
 run(bt/'d8','--lib',android,'--min-api','26','--output',pd,*pc.rglob('*.class'))
 shutil.copyfile(pd/'classes.dex',out/'plugin.dex')
 run(cc,'-O0','-g','-fno-omit-frame-pointer','-shared','-fPIC',src/'lab.c','-o',out/'liblab.so')
 run(cc,'-O0','-g','-fno-omit-frame-pointer','-Wl,--export-dynamic',src/'lab.c','-o',out/'lab')
 run(cc,'-shared','-fPIC',src/'delay.c','-o',out/'libdelay.so')
 run(cc,src/'gadget-host.c','-ldl','-o',out/'gadget-host')
 apk=out/'unsigned.apk';run(bt/'aapt','package','-f','-M',manifest,'-I',android,'-F',apk)
 with zipfile.ZipFile(apk,'a') as z:
  z.write(dex/'classes.dex','classes.dex');z.write(out/'liblab.so','lib/arm64-v8a/liblab.so');z.write(out/'libdelay.so','lib/arm64-v8a/libdelay.so')
  if a.gadget:
   z.write(a.gadget,'lib/arm64-v8a/libgadget.so')
   interaction={'type':'listen','address':'127.0.0.1','port':35112,'on_load':'resume'}
   if a.interaction=='script':interaction={'type':'script','path':'/data/local/tmp/jprobe-regression/gadget-script.js'}
   if a.interaction=='script-directory':interaction={'type':'script-directory','path':'/data/local/tmp/jprobe-regression/gadget-scripts'}
   if a.interaction=='connect':interaction={'type':'connect','address':'127.0.0.1','port':35113}
   z.writestr('lib/arm64-v8a/libgadget.config.so',json.dumps({'interaction':interaction,'runtime':a.runtime,'teardown':'full'}))
 run(bt/'zipalign','-f','4',apk,out/'aligned.apk')
 key=out/'fixture.keystore';existing=out.parent/'base/fixture.keystore'
 if existing.exists() and existing!=key:shutil.copyfile(existing,key)
 else:run(java/'keytool','-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','fixture','-keyalg','RSA','-validity','3650','-dname','CN=Regression Fixture')
 run(bt/'apksigner','sign','--ks',key,'--ks-pass','pass:android','--out',out/'fixture.apk',out/'aligned.apk')
 run(bt/'apksigner','verify',out/'fixture.apk')
 files=['fixture.apk','lab','liblab.so','libdelay.so','plugin.dex'];(out/'build.json').write_text(json.dumps({'package':package,'runtime':a.runtime,'gadget':str(a.gadget),'interaction':a.interaction,'sha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in files}},indent=2))
 print(out/'fixture.apk')
if __name__=='__main__':main()
