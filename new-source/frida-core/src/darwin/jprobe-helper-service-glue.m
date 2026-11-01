#include "jprobe-helper-service-glue.h"

#import <Foundation/Foundation.h>

static volatile BOOL jprobe_run_loop_running = NO;

void
_jprobe_start_run_loop (void)
{
  NSRunLoop * loop = [NSRunLoop mainRunLoop];

  jprobe_run_loop_running = YES;
  while (jprobe_run_loop_running && [loop runMode:NSDefaultRunLoopMode beforeDate:[NSDate distantFuture]])
    ;
}

void
_jprobe_stop_run_loop (void)
{
  jprobe_run_loop_running = NO;
  CFRunLoopStop ([[NSRunLoop mainRunLoop] getCFRunLoop]);
}
