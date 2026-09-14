#!/usr/bin/env python3
"""Generate the single, shareable profiling report from verified experiment data."""
import collections, datetime, hashlib, json, math, re, statistics, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
OUT=REPO/'benchmark-results/gc-profile'

def val(row,key):
 for part in key.split('.'):row=row[part]
 return row

def num(x):
 if x==0:return '0'
 if abs(x)<10000 and float(x).is_integer():return str(int(x))
 return f'{x:.3e}' if abs(x)>=10000 or abs(x)<0.001 else f'{x:.3f}'

def samples(folder):
 blocks=re.split(r'\n\s*\n',(folder/'perf-samples.txt').read_text().strip())
 counts=collections.Counter();tids=set();total=0
 for b in blocks:
  lines=b.splitlines()
  if not lines or 'cpu-clock:' not in lines[0]:continue
  total+=1
  m=re.search(r'(\d+)/(\d+)',lines[0]);tids.add(m.group(2))
  leaf=next((s for s in lines[1:] if s.strip()),'')
  if '[kernel.kallsyms]' in leaf:counts['kernel']+=1
  if 'clear_page_erms' in leaf:counts['clear']+=1
  if 'libgc.so' in leaf:counts['gc']+=1
  if 'libgmp.so' in leaf:counts['gmp']+=1
  if 'M2-binary)' in leaf:counts['m2']+=1
  if any('clear_page_erms' in s for s in lines[1:]) and any('GC_malloc_kind' in s for s in lines[1:]):counts['gc_clear_chain']+=1
 assert total>0
 return dict(counts,total=total,threads=len(tids))


def main():
 allrows=[json.loads(p.read_text()) | {'folder':p.parent} for p in OUT.glob('*/result.json')]
 def chosen(r):
  return ((r['kind']=='resource' and r['mode'] in ['on','off'] and r['workload'] in ['startup','forms','global','gbZZbug3'])
    or r['kind'] in ['control','stat','record'])
 rows=[r for r in allrows if chosen(r)]
 counts=collections.Counter(r['kind'] for r in rows)
 assert counts=={'resource':40,'control':15,'stat':15,'record':11},counts
 expected=set()
 for kind,workloads,modes,trials in [
  ('resource',['startup','forms','global','gbZZbug3'],['on','off'],5),
  ('control',['forms'],['off','late-off','reserve'],5),
  ('stat',['forms','global'],['on','off'],3),
  ('stat',['forms'],['reserve'],3),
  ('record',['forms'],['on','off'],3),
  ('record',['global','gbZZbug3'],['on','off'],1),
  ('record',['forms'],['reserve'],1)]:
  expected.update((kind,w,m,t) for w in workloads for m in modes for t in range(1,trials+1))
 assert {(r['kind'],r['workload'],r['mode'],r['trial']) for r in rows}==expected
 assert all(r['phase']['major_faults']==0 for r in rows if r['kind']=='resource')
 meta=json.loads((OUT/'metadata.json').read_text())
 for r in rows:
  assert r['status']=='ok' and r['returncode']==0
  assert r['binary_sha256']==meta['binary_sha256']
  assert r['probe_sha256']==hashlib.sha256((OUT/'probe.so').read_bytes()).hexdigest()
  assert abs(r['phase']['wall']-r['internal_seconds'])<0.02
  if r['mode'] in ['off','late-off','reserve']:assert r['gc_collections']==0
  assert (r['folder']/'stdout.txt').exists() and (r['folder']/'phases.txt').exists()
 def group(w,m,k='resource'):return [r for r in rows if r['workload']==w and r['mode']==m and r['kind']==k]
 def med(w,m,key,k='resource'):return statistics.median(val(r,key) for r in group(w,m,k))
 def change(w,key,k='resource'):return 100*(med(w,'off',key,k)/med(w,'on',key,k)-1)
 def link(p):return str(p.relative_to(REPO))
 workloads=['forms','global','gbZZbug3']
 profiles={}
 for r in rows:
  if r['kind']=='record':
   assert 'Total Lost Samples: 0' in (r['folder']/'perf-report.txt').read_text()
   profiles[(r['workload'],r['mode'],r['trial'])]=samples(r['folder'])
 counter={}
 for r in rows:
  if r['kind']=='stat':
   events={}
   for line in (r['folder']/'perf-stat.txt').read_text().splitlines():
    if not line or line.startswith('#'):continue
    f=line.split(';');assert len(f)>=5 and float(f[4])>=99.9,line
    events[f[2]]=float(f[0])
   assert len(events)==6,events
   counter[(r['workload'],r['mode'],r['trial'])]=events
 on,off=(med('forms',m,'internal_seconds') for m in ['on','off'])
 co,cr=(med('forms',m,'internal_seconds','control') for m in ['off','reserve'])
 kdelta=med('forms','off','phase.system')-med('forms','on','phase.system')
 udelta=med('forms','off','phase.user')-med('forms','on','phase.user')
 lines=['# Why disabling garbage collection slowed Macaulay2','', f'Measured {meta["created_utc"][:10]} on the WSL system described below.', '',
 '## Answer in plain language','',
 '**Garbage collection is doing useful memory-recycling work. Turning it off saves collection work, but forces later allocations to obtain and touch much more fresh memory. On this machine, Linux spends substantial time supplying and zeroing those pages. That cost can exceed the time saved by skipping collection.**','',
 f'The clearest case is `forms`: the median internal elapsed time rose from **{on:.3f} s with GC on to {off:.3f} s with GC off ({change("forms","internal_seconds"):+.1f}%)**. During the test, kernel CPU time increased by **{kdelta:.3f} s**, while user-space CPU time changed by **{udelta:+.3f} s**. This is direct evidence of extra operating-system work, not simply a slower algebra routine. CPU seconds and elapsed seconds have different meanings, so these changes must not be added or subtracted as if they were one stopwatch.','',
 f'A diagnostic control reinforces that explanation. With GC still off, we allocated, touched, and explicitly freed a **3-GiB Boehm memory block before the timer**, making its pages available for reuse. The median internal time then fell from **{co:.3f} s to {cr:.3f} s ({100*(cr/co-1):+.1f}%)**. The setup itself cost **{med("forms","reserve","setup.wall","control"):.3f} s** and remains part of whole-process time. This control moves costs; it is not a free end-to-end optimization.','',
 'The evidence supports fresh-page allocation and zeroing as a major cause of the observed GC-off penalty, especially in `forms`. It also shows higher allocation-related memory pressure in sheaf cohomology and the large integer Gröbner-basis regression. It does **not** prove that every timing difference is caused by page faults, nor that cache/TLB effects or thread coordination are irrelevant.','',
 'This is a follow-up to `report.md`, using the same Release executable and original-size slow-test inputs. It contains the experiment results, all key numerical trial data, profile summaries, and reproduction instructions in one file. Raw sampled stacks and commands remain available for deeper reanalysis; they are not needed to understand the conclusions.','',
 '## What was measured','',
 '| Measurement | Meaning |','| --- | --- |',
 '| Internal elapsed time | M2 `elapsedTiming input testFile`: real wall time for reading, evaluating, printing, and checking the test. Startup and the diagnostic memory preparation are outside this timer. |',
 '| Phase user CPU | CPU seconds executing user-space code during the same test interval, summed across the process’s threads. This includes M2, GMP and Boehm code. |',
 '| Phase kernel CPU | CPU seconds spent in the kernel on behalf of those threads, including memory faults and synchronization. |',
 '| Minor page fault | A page fault serviced without disk I/O. It can still allocate a physical page, zero it, update mappings, and incur synchronization. “Minor” does not mean free. |',
 '| Major page fault | A fault requiring I/O. Its absence in the test interval argues against disk-backed paging as the explanation for that interval. |',
 '| Peak RSS | Highest resident set size during the whole process: memory resident in RAM, including startup and diagnostic preparation. It is not just the live algebra data. GiB means 2³⁰ bytes. |',
 '| Allocation traffic | Bytes requested from Boehm during the test, including memory later made unreachable; different from final heap size or RSS. |',
 '| CPU-sample percentage | Fraction of sampled CPU activity whose instruction pointer was in a function or component. It is not a percentage of elapsed time, and includes all sampled threads. |','',
 'Resource counters come from Linux `getrusage(RUSAGE_SELF)`. CPU times cover all process threads, so their sum may exceed elapsed time. The definitions of user/system time and minor/major faults follow the [Linux getrusage manual](https://man7.org/linux/man-pages/man2/getrusage.2.html). Numerical summaries below are medians of independent fresh-process trials; they are descriptive, not significance tests.','',
 '## Experiment design','',
 '| Experiment | Cases and repetitions | Purpose |','| --- | --- | --- |',
 '| Resource baseline | Startup-only, forms, global, gbZZbug3; five trials per GC mode: 40 processes | Separate user CPU, kernel CPU, page faults, memory, and startup from internal elapsed time. |',
 '| Memory controls | Forms with GC off from startup, off only after startup, or off with a pre-touched reusable block; five trials each: 15 processes | Test whether startup policy and fresh-page costs explain the difference. |',
 '| Hardware counters | Forms on/off/reserve and global on/off; three trials each: 15 processes | Check CPU instructions, cycles, generic cache events and data-TLB events during the test only. |',
 '| Sampled CPU profiles | Forms on/off: three each; forms reserve: one; global and gbZZbug3 on/off: one each; 11 processes | Locate the actual functions and call paths consuming CPU time. |','',
 'In total, **81 successful measured processes** support this report. Profiling and resource runs are separate datasets and their timings are not pooled. Preparatory probe-validation runs are excluded from the resource summaries. There is no designated per-case warm-up in this follow-up; preparatory runs primed file caches. Modes alternate order between trials within each batch; the batches themselves were run sequentially. Background host activity and CPU frequency were not controlled.','',
 'We used Linux `perf` instead of traditional GNU `gprof`: this preserved the existing Release build and allowed kernel, shared-library, and hardware-counter measurements. Traditional gprof normally requires recompilation/linking with `-pg`, as described in the [GNU gprof manual](https://sourceware.org/binutils/docs/gprof.html).','',
 'A small preload library observes the two `GC_get_prof_stats` calls already used by the benchmark wrapper. It records resource snapshots around the test. For perf runs, counters start disabled; an acknowledged FIFO command enables them immediately before the first snapshot and disables them after the second. Thus the profiles exclude M2 startup and the memory-control preparation. This uses perf’s documented [control-FIFO interface](https://man7.org/linux/man-pages/man1/perf-stat.1.html). The snapshots include small instrumentation overhead around the M2 timer.','',
 'The original slow-test parameters, fixed random seed, and assertions are retained. `forms` checks the Gröbner basis generator count and zero input remainders; `global` retains its cohomology checks; `gbZZbug3` retains both ideal-membership reductions and the explicit polynomial certificate. Every process has a 300-second timeout and a 24-GiB address-space limit, with core dumps disabled. These are address-space bounds, not the RSS measurements.','',
 'GC-on clears inherited `GC_*` variables. GC-off clears them and sets `GC_DONT_GC=1` before M2 starts. `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and `LC_ALL=C` are fixed. M2 runs as the normal user, even when a privileged perf parent collects kernel data. No benchmark processes overlap.','',
 '## Resource results: where the extra work went','',
 'The selected tests cover three distinct allocation-heavy cases: `forms` constructs random degree-16 forms over the rationals in three variables and computes a degree-limited Gröbner basis; `global` checks sheaf cohomology and global sections on projective spaces and an elliptic curve; `gbZZbug3` exercises a large integer Gröbner-basis regression. The timer covers each complete active test, including input construction and assertions.','',
 '| Workload | Mode | Internal elapsed (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Whole-process elapsed (s) | Peak RSS (GiB) |',
 '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
 for w in workloads:
  for m in ['on','off']:
   keys=['internal_seconds','phase.user','phase.system','phase.minor_faults','phase.major_faults','process.wall']
   lines.append(f'| {w} | GC {m} | '+' | '.join(num(med(w,m,k)) for k in keys)+f' | {med(w,m,"process.peak_rss_kib")/1024**2:.3f} |')
 lines+=['','The CPU columns are separate medians and are sums over threads. A mode can consume fewer total CPU seconds but have a longer elapsed time: work on several CPUs is not equivalent to serial work on the critical path. In these runs, normal collection uses concurrent CPU activity, while fresh-page faults delay the allocating thread directly.','',
 f'For example, `gbZZbug3` used a median {statistics.median(r["phase"]["user"]+r["phase"]["system"] for r in group("gbZZbug3","on")):.3f} total CPU seconds with GC on, versus {statistics.median(r["phase"]["user"]+r["phase"]["system"] for r in group("gbZZbug3","off")):.3f} with it off, yet GC-off elapsed time rose by {change("gbZZbug3","internal_seconds"):.1f}%. Thus GC-off does not increase aggregate kernel CPU in every workload. The claim about fresh-page costs concerns the allocation path; it is not an additive explanation of every CPU or wall-time difference.','',
 '| Workload | Mode | Boehm allocation traffic in test (GiB) | Collections in test | Boehm full-collection time (s) |','| --- | --- | ---: | ---: | ---: |']
 for w in workloads:
  for m in ['on','off']:
   lines.append(f'| {w} | GC {m} | {med(w,m,"bytes_allocated")/1024**3:.3f} | {med(w,m,"gc_collections"):.0f} | {med(w,m,"gc_cpu_seconds"):.3f} |')
 lines+=['',
 'The probe enables Boehm’s optional performance timer. Despite the inherited JSON field name `gc_cpu_seconds`, this counter reports **full-collection elapsed time**, not CPU usage. It does not measure all allocator work and must not be subtracted from whole-process time to predict GC-off performance. Collection work is real, but so is the reuse benefit it provides.','',
 '### Startup is a separate source of overhead','',
 'The startup-only input contains just a successful assertion. Its internal interval is too short to compare meaningfully; the following whole-process figures quantify starting and stopping M2 with each GC policy. They include wrapper and shutdown overhead, so they are a startup baseline rather than a pure initialization timer.','',
 '| Mode | Process wall (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Peak RSS (GiB) |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
 for m in ['on','off']:
  lines.append(f'| GC {m} | '+' | '.join(num(med('startup',m,k)) for k in ['process.wall','process.user','process.system','process.minor_faults','process.major_faults'])+f' | {med("startup",m,"process.peak_rss_kib")/1024**2:.3f} |')
 lines+=['','Do not subtract independently measured startup medians from workload medians to claim an exact phase decomposition. The directly bracketed resource measurements above already isolate the test.','',
 '## Sampled profiles: an allocation request reaches the kernel','',
 'The table aggregates the CPU-clock samples within each case. Forms on/off each combine three profile runs; other cases use one. Sampling frequency is 199 Hz per active thread. No lost samples were reported. A displayed 0.0% is rounded and does not prove an event never occurred. “All kernel” includes the page-clearing subset; these columns are not additive. Some internal Boehm functions lack debug symbols, so we report the entire library. The exporter also emitted addr2line warnings for some M2 frames; named allocation-to-kernel paths were still recovered, but complete source-line attribution is unavailable.','',
 '| Workload | Mode | CPU samples | All kernel (%) | clear_page_erms (%) | Boehm library (%) | GMP library (%) |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
 for w,m in [('forms','on'),('forms','off'),('forms','reserve'),('global','on'),('global','off'),('gbZZbug3','on'),('gbZZbug3','off')]:
  ps=[v for (ww,mm,t),v in profiles.items() if ww==w and mm==m];total=sum(v['total'] for v in ps)
  lines.append(f'| {w} | {m} | {num(total)} | '+' | '.join(f'{100*sum(v.get(k,0) for v in ps)/total:.1f}' for k in ['kernel','clear','gc','gmp'])+' |')
 lines+=['',
 f'Sampling is not free: the profiled GC-on integer regression took {group("gbZZbug3","on","record")[0]["internal_seconds"]:.3f} s internally, compared with its {med("gbZZbug3","on","internal_seconds"):.3f}-s resource-run median. We therefore use unprofiled resource runs for timing comparisons and use sampled runs to locate CPU activity; profile percentages are approximate and can be affected by the profiler.', '',
 'A captured GC-off forms stack contains the following path (simplified, with addresses removed):','',
 '```text\nM2 polynomial/matrix operation\n  → getmem / getmem_atomic\n    → GC_malloc_kind\n      → GC_generic_malloc_many\n        → page fault\n          → do_user_addr_fault → do_anonymous_page\n            → physical-page allocation → clear_page_erms\n```','',
 '`clear_page_erms` is the kernel’s page-zeroing routine. The observed call stacks connect it to Boehm allocation requests originating in polynomial and matrix work. Anonymous mappings must present zero-initialized contents (see the [Linux mmap manual](https://man7.org/linux/man-pages/man2/mmap.2.html)); servicing such faults costs CPU and memory bandwidth even without disk I/O. This is stronger evidence than inferring a cause from RSS alone.','',
 'Boehm’s allocator normally chooses between collection/reuse and heap expansion. In the [8.2.8 allocator source](https://github.com/ivmai/bdwgc/blob/v8.2.8/alloc.c), `GC_collect_or_expand` guards its collection path with `!GC_dont_gc`, and `GC_expand_hp_inner` obtains more memory. Disabling collection preserves the allocator but removes its normal reclamation path. The [Boehm algorithm overview](https://www.hboehm.info/gc/gcdescr.html) describes this allocation/collection tradeoff.','',
 '## Controlled interventions','',
 'All three cases below use the same forms input and have **zero collections during the test**. “Late off” allows normal startup and then calls `GC_disable()` just before the test. “Reserve” disables GC from startup, allocates a 3-GiB atomic block, writes every byte, and explicitly frees that block into Boehm before starting the timer.','',
 '| Policy | Preparation (s) | Internal elapsed (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Process elapsed (s) | Peak RSS (GiB) |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
 for m in ['off','late-off','reserve']:
  lines.append(f'| {m} | '+' | '.join(num(med('forms',m,k,'control')) for k in ['setup.wall','internal_seconds','phase.user','phase.system','phase.minor_faults','process.wall'])+f' | {med("forms",m,"process.peak_rss_kib","control")/1024**2:.3f} |')
 lines+=['',
 f'The late-off internal median was {med("forms","late-off","internal_seconds","control"):.3f} s; its minor-fault count remained about {num(med("forms","late-off","phase.minor_faults","control"))}. Reserving reusable pages reduced faults by {100*(1-med("forms","reserve","phase.minor_faults","control")/med("forms","off","phase.minor_faults","control")):.1f}%. Late-off improved elapsed time relative to disabling GC before startup, but retained almost all of the workload’s minor faults. The reserve policy changed the median full command time from {med("forms","off","process.wall","control"):.3f} s to {med("forms","reserve","process.wall","control"):.3f} s. This is the essential distinction between an internally faster test and a faster complete invocation.', '',
 'The late-off control tests whether disabling collection only during the workload removes the penalty caused by an already bloated startup heap. The reserve control instead makes a large stock of resident pages reusable. Read its internal improvement together with its preparation and process times: allocation and page-touch costs are paid earlier, and peak memory includes the preparation.','',
 'This intervention changes heap availability/layout and page residency together; it is not a perfectly isolated test of one hardware event. Combined with the fault counts and the kernel stacks, however, it gives strong evidence that repeatedly obtaining fresh resident pages is a major mechanism. It does not justify disabling GC in a long-running session: the reserve is finite, and unreachable allocations would keep accumulating.','',
 '## Hardware counters and cache interpretation','',
 'These are medians of three phase-gated perf-stat runs. All six counters were reported as running for the full enabled interval, without multiplex scaling. Generic cache-event names are those reported by perf; we do not relabel them as L1, L2 or L3 measurements. TLB means translation lookaside buffer, the CPU’s address-translation cache. The measured GC-off runs actually have fewer generic cache misses and data-TLB load misses than GC-on in both workloads. These totals therefore do not support a simple claim that more cache misses caused the slowdown; GC-on also performs extra collector work, which generates its own events.','',
 '| Workload | Mode | Cycles | Instructions | Cache references | Cache misses | Data-TLB loads | Data-TLB load misses |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
 evnames=['cycles','instructions','cache-references','cache-misses','dTLB-loads','dTLB-load-misses']
 for w,m in [('forms','on'),('forms','off'),('forms','reserve'),('global','on'),('global','off')]:
  es=[v for (ww,mm,t),v in counter.items() if ww==w and mm==m]
  lines.append(f'| {w} | {m} | '+' | '.join(num(statistics.median(e[k] for e in es)) for k in evnames)+' |')
 lines+=['','These counters describe the combined program and kernel activity during the test. They cannot independently separate cache effects from the extra memory-management work: that work itself generates instructions, cache traffic and translations. Because this is WSL, the virtualized PMU also limits how confidently generic events can be interpreted. The named kernel stacks and the resource/intervention results carry more weight than an isolated cache-miss ratio.','',
 '## System and provenance','']
 cpu={r['field'].rstrip(':'):r['data'] for r in meta['lscpu']['lscpu']}
 lines+=['| Property | Recorded value |','| --- | --- |',f'| CPU | {cpu["Model name"]} |',
 f'| Guest OS | {next(x.split(chr(61),1)[1].strip(chr(34)) for x in meta["os_release"].splitlines() if x.startswith("PRETTY_NAME="))} |',
 f'| WSL-visible topology | {cpu["CPU(s)"]} logical CPUs; {cpu["Core(s) per socket"]} cores; {cpu["Thread(s) per core"]} threads per core |']
 for k in ['L1d cache','L1i cache','L2 cache','L3 cache']:lines.append(f'| {k} | {cpu[k]} |')
 mem=int(re.search(r'MemTotal:\s*(\d+)',meta['memory']).group(1))/1024**2
 lines += [f'| WSL-visible RAM | {mem:.1f} GiB |',f'| Kernel | {meta["kernel"]} |',
 f'| Base page size / transparent huge pages | {num(meta["page_size"]/1024)} KiB / {meta["transparent_hugepages"]} (brackets indicate the active policy) |',
 '| Build | Existing CMake Release binary; no recompilation for profiling |',
 f'| Source checkout | `{meta["source_commit"][:7]}` on `benchmark-gc`; profiling harness added locally |']
 for line in meta['versions'].splitlines():
  package,version=line.split();lines.append(f'| {package} | {version} |')
 lines+=['',
 'Cache totals and topology are the guest’s view. L1d holds data and L1i holds instructions; L2 and L3 provide larger levels of cache. Host DRAM timings, power settings and clock frequency under load were not measured.','',
 'The CPU-zero sysfs cache details are listed below. Sharing lists use logical CPU numbers; two logical CPUs on one core share its private caches.','',
 '| Level / type | Size | Line size (bytes) | Shared logical CPUs |',
 '| --- | ---: | ---: | --- |',
 *[f'| L{c["level"]} / {c["type"]} | {(num(int(c["size"].rstrip("K"))/1024)+" MiB") if int(c["size"].rstrip("K"))>=1024 else (c["size"].rstrip("K")+" KiB")} | {c["coherency_line_size"]} | {c["shared_cpu_list"]} |' for c in meta['cpu0_caches']], '',
 'All measured samples use the same executable and probe fingerprints, recorded with the raw data. Full hashes and high-precision timestamps are kept there instead of printing long identifiers here. The collector actually loaded by this binary is Debian’s system Boehm library; the source discussion uses its matching 8.2.8 release, rather than assuming a bundled library was used.','',
 '## What we can conclude—and what remains open','',
 '- **Supported:** GC-off substantially increases the number of minor faults and resident memory needed by these allocation-heavy workloads. Sampled stacks show kernel page allocation/zeroing on the Boehm allocation path.','- **Supported by the forms control:** reusing already resident pages sharply reduces the internal GC-off penalty, while its preparation cost remains visible in whole-process time.','- **Important distinction:** disabling GC does remove collector work. That does not guarantee a shorter critical path when allocation has to wait for new pages; nor does lower summed CPU time guarantee lower elapsed time.','- **Not established:** a precise percentage of the wall-time penalty attributable separately to page faults, cache misses, TLB misses, allocator bookkeeping, or thread scheduling. Sampling percentages are CPU shares, not an exact additive wall-time decomposition.','- **Scope:** three selected slow-test workloads plus startup, on one WSL machine. Five resource repetitions characterize the observed spread, not all inputs or all machines. The profiles on global and gbZZbug3 have only one sampled run per mode.','',
 'For these workloads, the measurements support leaving GC enabled. If performance work continues, the observed allocation call paths suggest examining temporary polynomial/matrix allocation traffic and reuse, then checking changes with the same correctness assertions and whole-process metrics. Changing GC policy alone should not be assumed to be an optimization.','',
 '## Appendix A: every resource and control trial','',
 'No perf-counter or sampling runs enter this table. Values are rounded for readability; large counts use scientific notation (`e+05` means ×10⁵). Startup-only internal timings are shown as “—” because the input does essentially no work. For startup-only rows, CPU and fault columns cover the whole process; for other rows they cover the timed test.','',
 '| Kind / workload | Policy | Trial | Internal wall (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Process wall (s) | Peak RSS (GiB) |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
 for r in sorted([r for r in rows if r['kind'] in ['resource','control']],key=lambda r:(r['kind'],r['workload'],r['trial'],r['mode'])):
  timing='—' if r['workload']=='startup' else num(r['internal_seconds'])
  cpu_scope='process' if r['workload']=='startup' else 'phase'
  lines.append(f'| {r["kind"]} / {r["workload"]} | {r["mode"]} | {r["trial"]} | {timing} | '+' | '.join(num(val(r,k)) for k in [cpu_scope+'.user',cpu_scope+'.system',cpu_scope+'.minor_faults',cpu_scope+'.major_faults','process.wall'])+f' | {r["process"]["peak_rss_kib"]/1024**2:.3f} |')
 lines+=['','### Control preparation costs for every trial','','| Policy | Trial | Preparation wall (s) | Preparation user CPU (s) | Preparation kernel CPU (s) | Preparation minor faults |','| --- | ---: | ---: | ---: | ---: | ---: |']
 for r in sorted([r for r in rows if r['kind']=='control'],key=lambda r:(r['trial'],r['mode'])):
  lines.append(f'| {r["mode"]} | {r["trial"]} | '+' | '.join(num(r['setup'][k]) for k in ['wall','user','system','minor_faults'])+' |')
 lines+=['','## Appendix B: every hardware-counter run','','| Workload | Policy | Trial | Cycles | Instructions | Cache references | Cache misses | Data-TLB loads | Data-TLB load misses |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
 for (w,m,t),e in sorted(counter.items()):lines.append(f'| {w} | {m} | {t} | '+' | '.join(num(e[k]) for k in evnames)+' |')
 lines+=['','## Appendix C: every sampled profile','','| Workload | Policy | Trial | Samples | Active sampled threads | Kernel (%) | Page zeroing (%) | Boehm (%) |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
 for (w,m,t),v in sorted(profiles.items()):lines.append(f'| {w} | {m} | {t} | {num(v["total"])} | {v["threads"]} | '+' | '.join(f'{100*v.get(k,0)/v["total"]:.1f}' for k in ['kernel','clear','gc'])+' |')
 lines+=['','## Appendix D: timings of instrumented runs','',
 'These measurements show the runs that produced the counters and profiles above. They are reported separately because instrumentation can change runtime. CPU and fault figures cover the timed phase; RSS and process wall cover the whole invocation.','',
 '| Kind / workload | Policy | Trial | Internal wall (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Process wall (s) | Peak RSS (GiB) |',
 '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
 for r in sorted([r for r in rows if r['kind'] in ['stat','record']],key=lambda r:(r['kind'],r['workload'],r['mode'],r['trial'])):
  lines.append(f'| {r["kind"]} / {r["workload"]} | {r["mode"]} | {r["trial"]} | '+' | '.join(num(val(r,k)) for k in ['internal_seconds','phase.user','phase.system','phase.minor_faults','phase.major_faults','process.wall'])+f' | {r["process"]["peak_rss_kib"]/1024**2:.3f} |')
 lines+=['','## Benchmark structure and reproduction','','The pipeline is: original slow-test input → fresh M2 process with the phase probe → optional phase-gated perf collection → correctness and counter checks → per-sample JSON/logs → median tables and profile summaries in this file. Preparation, timed input and whole-process measurements remain separate throughout.','',
 'Use the native Linux checkout. Build prerequisites are described in [BENCHMARK.md](BENCHMARK.md). For a fresh Release build, run `cmake -S M2 -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON`, then `cmake --build build --target build-libraries --parallel 4` and `cmake --build build --target M2-core --parallel 4`. The runner’s `BINARY` setting points directly to `build/usr-dist/x86_64-Linux-Debian-/bin/M2-binary`; adjust that setting if the staging path differs. Comparing a rebuilt binary is a new experiment, not a continuation of these samples.','',
 'The profiling harness requires Python 3, GCC, libgc development headers, GNU time, prlimit, and Linux perf. On Debian, install the profiling tools with `sudo apt-get install linux-perf libgc-dev gcc time util-linux`. With the Release binary available:','','```sh\nmkdir -p benchmark-results/gc-profile\ngcc -O2 -g -shared -fPIC M2/Macaulay2/benchmarks/gc-profile/probe.c \\\n  -o benchmark-results/gc-profile/probe.so -ldl -lgc\npython3 M2/Macaulay2/benchmarks/gc-profile/experiments.py \\\n  > benchmark-results/gc-profile/experiments.log 2>&1\npython3 M2/Macaulay2/benchmarks/gc-profile/report.py\n```','',
 'The runner uses `sudo -n` and needs permission for noninteractive perf collection and running the child as the normal user. Validate that access before starting the matrix. It needs `sudo perf` access for kernel sampling and executes the M2 workload as the normal user. Its precise commands and environment settings are saved per sample. The resource suite and controls use five trials; counter runs use three; profile counts are listed above. A failed assertion, timeout, or unexpected collection in an off policy prevents a successful result. Completed samples are reused after interruption, so archive the output directory before starting a wholly new experiment.','',
 'To inspect a captured profile directly:','','```sh\nperf report --stdio --no-children --call-graph none \\\n  -i benchmark-results/gc-profile/record-forms-off-1/perf.data\n```','',
 'The [profiling harness](M2/Macaulay2/benchmarks/gc-profile), [raw experiment directory](benchmark-results/gc-profile), and [original slow tests](M2/Macaulay2/tests/slow) provide the supporting code and evidence. The raw directory is ignored by Git; retain it if future stack-level reanalysis is needed. This report itself contains the numerical findings and trial tables needed for colleagues to review the argument without those files.','']
 report='\n'.join(lines)
 assert not re.search(r'\d{5,}',report),'long digit string'
 (REPO/'profiling-report.md').write_text(report)
 print('Validated 81 measured processes; wrote profiling-report.md')

if __name__=='__main__':main()
