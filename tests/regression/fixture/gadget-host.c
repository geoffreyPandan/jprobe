#include <dlfcn.h>
#include <stdio.h>
#include <unistd.h>
#include <dirent.h>
#include <string.h>
static int threads(void){int count=0;DIR*d=opendir("/proc/self/task");struct dirent*e;while((e=readdir(d)))if(e->d_name[0]!='.')count++;closedir(d);return count;}
int main(int argc,char**argv){
 if(argc<3)return 2;setbuf(stdout,NULL);printf("BASE_THREADS:%d\n",threads());
 void*h=dlopen(argv[1],RTLD_NOW);if(!h){fprintf(stderr,"%s\n",dlerror());return 3;}
 printf("LOADED_THREADS:%d\n",threads());
 for(int n=0;access(argv[2],F_OK)!=0;n++){if(n>600)return 4;usleep(100000);}
 if(argc==4&&strcmp(argv[3],"exit")==0){puts("HOST_EXIT_OK");return 0;}
 if(dlclose(h)!=0)return 5;sleep(2);printf("UNLOADED_THREADS:%d\n",threads());sleep(2);puts("HOST_EXIT_OK");return 0;
}
