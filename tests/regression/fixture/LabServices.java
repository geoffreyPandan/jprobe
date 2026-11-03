package dev.jprobe.lab;
import android.app.Service;
import android.content.Intent;
import android.os.Handler;
import android.os.IBinder;
public class LabServices {
 public static class Base extends Service {
  Handler handler;Runnable tick;
  public IBinder onBind(Intent i){return null;}
  public void onCreate(){super.onCreate();handler=new Handler(getMainLooper());tick=new Runnable(){public void run(){
   String value="{\"pid\":"+android.os.Process.myPid()+",\"java\":"+Fixture.add(19,23)+",\"native\":"+Fixture.nativeAdd(19,23)+",\"time\":"+System.currentTimeMillis()+"}";
   try{String name="process-"+Base.this.getClass().getSimpleName()+".json";java.io.File tmp=new java.io.File(getFilesDir(),name+".tmp");java.nio.file.Files.write(tmp.toPath(),value.getBytes(java.nio.charset.StandardCharsets.UTF_8));tmp.renameTo(new java.io.File(getFilesDir(),name));}catch(Exception e){android.util.Log.e("JprobeFixture","heartbeat write",e);}
   handler.postDelayed(this,1000);
  }};handler.post(tick);}
  public void onDestroy(){handler.removeCallbacks(tick);super.onDestroy();}
 }
 public static class P0 extends Base {}
 public static class P1 extends Base {}
 public static class P2 extends Base {}
 public static class P3 extends Base {}
}
