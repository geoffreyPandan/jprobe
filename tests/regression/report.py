#!/usr/bin/env python3
"""Generate a bounded report from recorded evidence, including unfinished runs."""
import argparse,json,datetime,csv,re
from pathlib import Path
def generate(root,dest):
 root=Path(root).resolve();dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
 rows=[];failures=[];detections=[]
 for path in sorted(root.rglob('results.json')):
  d=json.loads(path.read_text());name=str(path.parent.relative_to(root));counts=d['counts'];completion=path.parent/'completion.json'
  status='完成' if completion.exists() else '未完成/旧格式记录'
  if (path.parent/'watchdog.json').exists():status='看门狗终止'
  rows.append(f"| {name} | {counts['PASS']} | {counts['FAIL']} | {counts['BLOCKED']} | {counts['SKIP']} | {status} |")
  for c in d['cases']:
   if c['status']=='FAIL':failures.append(f"- `{name}` / `{c['id']}`：{c.get('error','')[:250].split(chr(10))[0]}")
   actual=c.get('actual')
   if isinstance(actual,dict) and 'detected' in actual:detections.append({'run':name,'case':c['id'],'detected':actual['detected']})
 for resource in root.rglob('resources.jsonl'):
  with resource.with_suffix('.csv').open('w') as target:
   writer=csv.DictWriter(target,fieldnames=['time','pid','rss_kb','pss_kb','threads','fds']);writer.writeheader()
   for line in resource.read_text().splitlines():
    try:record=json.loads(line)
    except ValueError:continue
    sample=record['sample']
    def metric(label):
     m=re.search(r'^'+label+r':\s+(\d+)',sample,re.M);return int(m.group(1)) if m else None
    writer.writerow({'time':record['time'],'pid':record['pid'],'rss_kb':metric('VmRSS'),'pss_kb':metric('Pss'),'threads':metric('Threads'),'fds':sample.splitlines()[-1] if sample else None})
 stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
 text=f'''# jprobe 回归测试执行记录

更新时间（北京时间）：{stamp}

证据目录：`{root}`。PASS 表示对应断言通过；检测用例的 PASS 仅表示原始结果采集成功，是否检出另列。不同运行可能是重试，不能把总次数当成独立功能数量。未完成与看门狗终止的运行不算整套通过。

## 逐次运行

| 运行 | PASS | FAIL | BLOCKED | SKIP | 状态 |
|---|---:|---:|---:|---:|---|
'''+ '\n'.join(rows)+ '\n\n## 失败记录\n\n'+('\n'.join(failures) or '尚无已记录失败；这不代表未执行项目已通过。')
 text+='\n\n## 检测采集\n\n'+f'已结构化采集 {len(detections)} 条；检出 {sum(x["detected"] for x in detections)} 条。历史解析失败不包含在此计数内；重新解析旧 XML 的结果另存 historical-ui-reparsed.json。原始子项见对应 status.txt 和 UI XML；不同模式、版本不得混合推导不可检测结论。\n'
 grouped={}
 for item in detections:
  counts=grouped.setdefault(item['run'],[0,0]);counts[0]+=1;counts[1]+=int(item['detected'])
 text+='\n| 运行 | 已采集 | 检出 |\n|---|---:|---:|\n'+'\n'.join(f'| {name} | {counts[0]} | {counts[1]} |' for name,counts in sorted(grouped.items()))+'\n'
 text+='''
## 已确认的边界

- 当前主要环境为 MuMu Android 12/API 32 ARM64；ARM32、真机、其他 Android 版本未验证。
- 原版 17.25.0 在本次环境附加测试 APK 时出现 SIGABRT，原因文本为 Unable to locate the libc；其后续性能对照不能视为有效。
- 历史 R7/R8 在模块回调内立即查找导出符号时触发 linker did_read_ 断言。R9 修复及新产物验证分别记录，不能把旧版本的失败和新版本复测混作同一次结果。
- 2026-11-02 的三项部署失败实际发生在 ss 未显示监听 PID 时，不能直接认定为端口被其他进程占用；修复后的测试器通过 /proc socket inode 校验所有权。
- 初期端口误连、广播后台队列阻塞及脚本调用错误属于测试框架问题；旧失败记录保留，复测另存。
- Core/Gum 官方全套和底层故障注入所需的匹配测试构建尚未准备，未完成；当前交付产物的黑盒结果不能替代这些项目。
- 所有长期测试以各自 completion.json 和结果为准，启动长测不代表长测通过。
'''
 if dest.exists():
  # Keep previous reports as separate immutable snapshots, not destructive overwrite.
  archive_dir=dest.parent/'snapshots';archive_dir.mkdir(exist_ok=True)
  archive=archive_dir/(dest.stem+'-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+dest.suffix)
  dest.rename(archive)
 dest.write_text(text,encoding='utf-8');(root/'detector-summary.json').write_text(json.dumps(detections,ensure_ascii=False,indent=2));return dest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(generate(a.root,a.output))
