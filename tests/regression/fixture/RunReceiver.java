package dev.jprobe.lab;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
public class RunReceiver extends BroadcastReceiver {
 @Override public void onReceive(Context c,Intent i){
  String marker=i.getStringExtra("marker");
  if(marker!=null){
   if(!marker.equals("one")&&!marker.equals("two")){setResultData("INVALID_MARKER");return;}
   try{java.io.File f=new java.io.File(c.getDataDir(),"gadget-"+marker+".json");setResultData("MARKER:"+new String(java.nio.file.Files.readAllBytes(f.toPath()),java.nio.charset.StandardCharsets.UTF_8));}
   catch(Exception e){setResultData("MARKER_PENDING");}return;
  }
  int rounds=i.getIntExtra("rounds",1); long total=0;
  for(int n=0;n<rounds;n++)total+=Fixture.add(19,23);
  setResultData("JAVA="+Fixture.add(19,23)+";NATIVE="+Fixture.nativeAdd(19,23)+";TOTAL="+total+";UID="+android.os.Process.myUid());
 }
}
