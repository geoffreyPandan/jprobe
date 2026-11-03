#include <jni.h>
#include <stdint.h>
#include <unistd.h>
#include <stdio.h>
#include <errno.h>
#include <pthread.h>
#include <sys/wait.h>
__attribute__((visibility("default"),noinline)) int lab_add(int a,int b){return a+b;}
__attribute__((visibility("default"),noinline)) double lab_double(double a){return a*2.0;}
__attribute__((visibility("default"),noinline)) int64_t lab_i64(int64_t a){return a+1;}
__attribute__((visibility("default"),noinline)) int lab_callback(int (*cb)(int),int a){return cb(a);}
__attribute__((visibility("default"),noinline)) int lab_errno(void){errno=EINVAL;return -1;}
__attribute__((visibility("default"),noinline)) int lab_recurse(int n){return n ? lab_recurse(n-1)+1 : 0;}
JNIEXPORT jint JNICALL Java_dev_jprobe_lab_Fixture_nativeAdd(JNIEnv* e,jclass c,jint a,jint b){return lab_add(a,b);}
int main(int argc,char**argv){
 setbuf(stdout,NULL); printf("LAB_READY:%d:%d\n",getpid(),lab_add(19,23));
 if(argc>1){pid_t p=fork();if(p==0){printf("CHILD:%d\n",getpid());return 0;}waitpid(p,NULL,0);return 0;}
 for(;;){printf("VALUE:%d\n",lab_add(19,23));sleep(1);}return 0;
}
