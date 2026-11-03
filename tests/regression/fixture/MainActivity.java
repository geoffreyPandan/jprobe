package dev.jprobe.lab;
import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
public class MainActivity extends Activity {
 @Override public void onCreate(Bundle b){super.onCreate(b);TextView v=new TextView(this);
 v.setText("jprobe regression fixture\nJava="+Fixture.add(19,23)+" JNI="+Fixture.nativeAdd(19,23));setContentView(v);}
}
