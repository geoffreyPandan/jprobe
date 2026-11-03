package dev.jprobe.lab;
public class Fixture {
 static { System.loadLibrary("lab"); }
 public int value;
 public Fixture(int value){this.value=value;}
 public static int add(int a,int b){return a+b;}
 public static String add(String a,String b){return a+b;}
 public int instance(int a){return value+a;}
 public static long wide(long a){return a+1;}
 public static int[] array(int[] a){return a;}
 public static String fail(){throw new IllegalArgumentException("fixture-error");}
 public static void loadDelay(){System.loadLibrary("delay");}
 public static native int nativeAdd(int a,int b);
}
