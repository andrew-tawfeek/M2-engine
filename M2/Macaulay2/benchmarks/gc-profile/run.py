#!/usr/bin/env python3
"""Phase-resolved resource measurements, perf counters/profiles, and memory interventions."""
import argparse, datetime, hashlib, importlib.util, json, os, signal, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OUT = REPO/'benchmark-results/gc-profile'
BINARY = REPO/'build/usr-dist/x86_64-Linux-Debian-/bin/M2-binary'
spec=importlib.util.spec_from_file_location('slowgc', HERE.parent/'slow-gc/run.py')
slow=importlib.util.module_from_spec(spec);spec.loader.exec_module(slow)
FIELDS=['wall','user','system','minor_faults','major_faults','peak_rss_kib','voluntary_switches','involuntary_switches']

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,indent=2)+'\n');t.replace(p)

def export_profile(folder):
 with (folder/'perf-report.txt').open('w') as f:
  subprocess.run(['sudo','-n','perf','report','-f','--stdio','--no-children','--call-graph','none','--sort','dso,symbol','--percent-limit','0.5','-i',str(folder/'perf.data')],stdout=f,check=True)
 with (folder/'perf-samples.txt').open('w') as f:
  subprocess.run(['sudo','-n','perf','script','-f','-i',str(folder/'perf.data'),'-F','comm,pid,tid,time,event,ip,sym,dso'],stdout=f,check=True)

def run(workload, mode, trial, kind):
 tag=f'{kind}-{workload}-{mode}-{trial}'
 folder=OUT/tag; folder.mkdir(parents=True,exist_ok=True)
 result=folder/'result.json'
 if result.exists():
  d=json.loads(result.read_text())
  if d['status']!='ok': raise RuntimeError(f'previous failure: {result}')
  assert d['binary_sha256']==digest(BINARY) and d['probe_sha256']==digest(OUT/'probe.so'), 'changed executable or probe'
  if kind=='record':export_profile(folder)
  print('saved: '+tag,flush=True);return
 script=HERE/'startup.m2' if workload=='startup' else slow.prepare(workload,folder)
 for p in folder.iterdir():
  if p.name in ['control','ack']:p.unlink()
 settings={'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','LC_ALL':'C',
           'LD_PRELOAD':str(OUT/'probe.so'),'PROFILE_LOG':str(folder/'phases.txt')}
 if mode in ['off','reserve']:settings['GC_DONT_GC']='1'
 if mode in ['late-off','reserve']:settings['PROFILE_POLICY']=mode
 if mode=='reserve':settings['PROFILE_RESERVE_MIB']='3072'
 env={k:v for k,v in os.environ.items() if not k.startswith(('GC_','PROFILE_')) and k!='LD_PRELOAD'}
 phases=folder/'phases.txt';phases.unlink(missing_ok=True)
 command=['prlimit','--as='+str(24*1024**3),'--core=0','/usr/bin/time','-q','-f','%e\t%U\t%S\t%M\t%R\t%F\t%x','-o',str(folder/'time.txt'),
          '/usr/bin/env',*[f'{k}={v}' for k,v in settings.items()],str(BINARY),'--script',str(HERE.parent/'slow-gc/workload.m2'),workload,str(script)]
 if kind in ['stat','record']:
  for n in ['control','ack']:os.mkfifo(folder/n)
  # Environment passed by env after sudo, so only M2 loads the probe.
  position=command.index(str(BINARY));command[position:position]=['PROFILE_CTL='+str(folder/'control'),'PROFILE_ACK='+str(folder/'ack')]
  opts=['-D','-1','--control',f'fifo:{folder}/control,{folder}/ack']
  if kind=='stat':
   opts+=['-x',';','-o',str(folder/'perf-stat.txt'),'-e','cycles,instructions,cache-references,cache-misses,dTLB-loads,dTLB-load-misses']
  else:
   opts+=['-e','cpu-clock','-F','199','--call-graph','dwarf,8192','-o',str(folder/'perf.data')]
  command=['sudo','-n','perf',kind,*opts,'--','sudo','-n','-u',os.environ.get('USER','andrew'),*command]
 print('running: '+tag,flush=True)
 proc=subprocess.Popen(command,cwd=slow.SOURCE,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 try:stdout,stderr=proc.communicate(timeout=300)
 except subprocess.TimeoutExpired:
  subprocess.run(['sudo','-n','kill','-KILL','--',f'-{proc.pid}'],check=False)
  stdout,stderr=proc.communicate();raise RuntimeError('timeout: '+tag)
 (folder/'stdout.txt').write_text(stdout);(folder/'stderr.txt').write_text(stderr)
 if kind in ['stat','record']:subprocess.run(['sudo','-n','chown','-R',f'{os.getuid()}:{os.getgid()}',str(folder)],check=True)
 d=dict(workload=workload,mode=mode,trial=trial,kind=kind,command=command,settings=settings,
        binary_sha256=digest(BINARY),probe_sha256=digest(OUT/'probe.so'),input_sha256=digest(script),returncode=proc.returncode,status='failed')
 if proc.returncode:save(result,d);raise RuntimeError(tag+'\n'+stderr[-3000:])
 d.update(slow.common.parse_m2_result(stdout,workload))
 stamps={}
 for line in phases.read_text().splitlines():
  s=line.split('|');stamps[s[0]]=dict(zip(FIELDS,map(float,s[1:])))
 assert set(stamps)=={'constructor','setup-start','begin','end'},stamps
 d['snapshots']=stamps
 d['phase']={k:stamps['end'][k]-stamps['begin'][k] for k in FIELDS if k!='peak_rss_kib'}
 d['setup']={k:stamps['begin'][k]-stamps['setup-start'][k] for k in FIELDS if k!='peak_rss_kib'}
 tf=(folder/'time.txt').read_text().strip().split('\t');assert tf[-1]=='0'
 d['process']=dict(zip(['wall','user','system','peak_rss_kib','minor_faults','major_faults'],map(float,tf[:-1])))
 if mode in ['off','late-off','reserve']:assert d['gc_collections']==0
 d['status']='ok';save(result,d)
 print(f"  {d['internal_seconds']:.3f}s internal; {d['phase']['user']:.3f}s user, {d['phase']['system']:.3f}s kernel; {d['phase']['minor_faults']:.0f} minor faults",flush=True)
 if kind=='record':export_profile(folder)
 for n in ['control','ack']:(folder/n).unlink(missing_ok=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--kind',choices=['resource','control','stat','record'],default='resource')
 p.add_argument('--workloads',nargs='+',default=['startup','forms','global','gbZZbug3'])
 p.add_argument('--modes',nargs='+',default=['on','off'])
 p.add_argument('--trials',type=int,default=5)
 a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
 meta=OUT/'metadata.json'
 if not meta.exists():
  save(meta,{'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'binary_sha256':digest(BINARY),
    'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    'lscpu':json.loads(subprocess.check_output(['lscpu','--json'],text=True)),
    'versions':subprocess.check_output(['dpkg-query','-W','libgc1','linux-perf','strace'],text=True),
    'kernel':os.uname().release,'memory':Path('/proc/meminfo').read_text(),'runner_sha256':digest(Path(__file__)),'probe_source_sha256':digest(HERE/'probe.c'),
    'os_release':Path('/etc/os-release').read_text(), 'page_size':os.sysconf('SC_PAGE_SIZE'),
    'transparent_hugepages':Path('/sys/kernel/mm/transparent_hugepage/enabled').read_text().strip(),
    'cpu0_caches':[{key:(index/key).read_text().strip() for key in
      ['level','type','size','coherency_line_size','shared_cpu_list']}
      for index in sorted(Path('/sys/devices/system/cpu/cpu0/cache').glob('index*'))]})
 for w in a.workloads:
  for t in range(1,a.trials+1):
   for m in (a.modes if t%2 else list(reversed(a.modes))):run(w,m,t,a.kind)
