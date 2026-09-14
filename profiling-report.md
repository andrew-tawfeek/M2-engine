# Why disabling garbage collection slowed Macaulay2

Measured 2026-09-14 on the WSL system described below.

## Answer in plain language

**Garbage collection is doing useful memory-recycling work. Turning it off saves collection work, but forces later allocations to obtain and touch much more fresh memory. On this machine, Linux spends substantial time supplying and zeroing those pages. That cost can exceed the time saved by skipping collection.**

The clearest case is `forms`: the median internal elapsed time rose from **1.588 s with GC on to 3.010 s with GC off (+89.6%)**. During the test, kernel CPU time increased by **1.250 s**, while user-space CPU time changed by **-0.361 s**. This is direct evidence of extra operating-system work, not simply a slower algebra routine. CPU seconds and elapsed seconds have different meanings, so these changes must not be added or subtracted as if they were one stopwatch.

A diagnostic control reinforces that explanation. With GC still off, we allocated, touched, and explicitly freed a **3-GiB Boehm memory block before the timer**, making its pages available for reuse. The median internal time then fell from **2.874 s to 1.388 s (-51.7%)**. The setup itself cost **1.990 s** and remains part of whole-process time. This control moves costs; it is not a free end-to-end optimization.

The evidence supports fresh-page allocation and zeroing as a major cause of the observed GC-off penalty, especially in `forms`. It also shows higher allocation-related memory pressure in sheaf cohomology and the large integer Gröbner-basis regression. It does **not** prove that every timing difference is caused by page faults, nor that cache/TLB effects or thread coordination are irrelevant.

This is a follow-up to `report.md`, using the same Release executable and original-size slow-test inputs. It contains the experiment results, all key numerical trial data, profile summaries, and reproduction instructions in one file. Raw sampled stacks and commands remain available for deeper reanalysis; they are not needed to understand the conclusions.

## What was measured

| Measurement | Meaning |
| --- | --- |
| Internal elapsed time | M2 `elapsedTiming input testFile`: real wall time for reading, evaluating, printing, and checking the test. Startup and the diagnostic memory preparation are outside this timer. |
| Phase user CPU | CPU seconds executing user-space code during the same test interval, summed across the process’s threads. This includes M2, GMP and Boehm code. |
| Phase kernel CPU | CPU seconds spent in the kernel on behalf of those threads, including memory faults and synchronization. |
| Minor page fault | A page fault serviced without disk I/O. It can still allocate a physical page, zero it, update mappings, and incur synchronization. “Minor” does not mean free. |
| Major page fault | A fault requiring I/O. Its absence in the test interval argues against disk-backed paging as the explanation for that interval. |
| Peak RSS | Highest resident set size during the whole process: memory resident in RAM, including startup and diagnostic preparation. It is not just the live algebra data. GiB means 2³⁰ bytes. |
| Allocation traffic | Bytes requested from Boehm during the test, including memory later made unreachable; different from final heap size or RSS. |
| CPU-sample percentage | Fraction of sampled CPU activity whose instruction pointer was in a function or component. It is not a percentage of elapsed time, and includes all sampled threads. |

Resource counters come from Linux `getrusage(RUSAGE_SELF)`. CPU times cover all process threads, so their sum may exceed elapsed time. The definitions of user/system time and minor/major faults follow the [Linux getrusage manual](https://man7.org/linux/man-pages/man2/getrusage.2.html). Numerical summaries below are medians of independent fresh-process trials; they are descriptive, not significance tests.

## Experiment design

| Experiment | Cases and repetitions | Purpose |
| --- | --- | --- |
| Resource baseline | Startup-only, forms, global, gbZZbug3; five trials per GC mode: 40 processes | Separate user CPU, kernel CPU, page faults, memory, and startup from internal elapsed time. |
| Memory controls | Forms with GC off from startup, off only after startup, or off with a pre-touched reusable block; five trials each: 15 processes | Test whether startup policy and fresh-page costs explain the difference. |
| Hardware counters | Forms on/off/reserve and global on/off; three trials each: 15 processes | Check CPU instructions, cycles, generic cache events and data-TLB events during the test only. |
| Sampled CPU profiles | Forms on/off: three each; forms reserve: one; global and gbZZbug3 on/off: one each; 11 processes | Locate the actual functions and call paths consuming CPU time. |

In total, **81 successful measured processes** support this report. Profiling and resource runs are separate datasets and their timings are not pooled. Preparatory probe-validation runs are excluded from the resource summaries. There is no designated per-case warm-up in this follow-up; preparatory runs primed file caches. Modes alternate order between trials within each batch; the batches themselves were run sequentially. Background host activity and CPU frequency were not controlled.

We used Linux `perf` instead of traditional GNU `gprof`: this preserved the existing Release build and allowed kernel, shared-library, and hardware-counter measurements. Traditional gprof normally requires recompilation/linking with `-pg`, as described in the [GNU gprof manual](https://sourceware.org/binutils/docs/gprof.html).

A small preload library observes the two `GC_get_prof_stats` calls already used by the benchmark wrapper. It records resource snapshots around the test. For perf runs, counters start disabled; an acknowledged FIFO command enables them immediately before the first snapshot and disables them after the second. Thus the profiles exclude M2 startup and the memory-control preparation. This uses perf’s documented [control-FIFO interface](https://man7.org/linux/man-pages/man1/perf-stat.1.html). The snapshots include small instrumentation overhead around the M2 timer.

The original slow-test parameters, fixed random seed, and assertions are retained. `forms` checks the Gröbner basis generator count and zero input remainders; `global` retains its cohomology checks; `gbZZbug3` retains both ideal-membership reductions and the explicit polynomial certificate. Every process has a 300-second timeout and a 24-GiB address-space limit, with core dumps disabled. These are address-space bounds, not the RSS measurements.

GC-on clears inherited `GC_*` variables. GC-off clears them and sets `GC_DONT_GC=1` before M2 starts. `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and `LC_ALL=C` are fixed. M2 runs as the normal user, even when a privileged perf parent collects kernel data. No benchmark processes overlap.

## Resource results: where the extra work went

The selected tests cover three distinct allocation-heavy cases: `forms` constructs random degree-16 forms over the rationals in three variables and computes a degree-limited Gröbner basis; `global` checks sheaf cohomology and global sections on projective spaces and an elliptic curve; `gbZZbug3` exercises a large integer Gröbner-basis regression. The timer covers each complete active test, including input construction and assertions.

| Workload | Mode | Internal elapsed (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Whole-process elapsed (s) | Peak RSS (GiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| forms | GC on | 1.588 | 1.827 | 0.297 | 3.010e+04 | 0 | 4.040 | 0.304 |
| forms | GC off | 3.010 | 1.467 | 1.547 | 5.718e+05 | 0 | 6.210 | 3.525 |
| global | GC on | 6.423 | 8.988 | 1.767 | 4956 | 0 | 8.860 | 0.188 |
| global | GC off | 8.297 | 5.749 | 2.487 | 8.519e+05 | 0 | 11.710 | 4.593 |
| gbZZbug3 | GC on | 25.392 | 35.794 | 37.559 | 4.965e+04 | 0 | 28.030 | 0.376 |
| gbZZbug3 | GC off | 30.208 | 15.669 | 14.536 | 5.098e+06 | 0 | 34.870 | 20.789 |

The CPU columns are separate medians and are sums over threads. A mode can consume fewer total CPU seconds but have a longer elapsed time: work on several CPUs is not equivalent to serial work on the critical path. In these runs, normal collection uses concurrent CPU activity, while fresh-page faults delay the allocating thread directly.

For example, `gbZZbug3` used a median 73.036 total CPU seconds with GC on, versus 30.205 with it off, yet GC-off elapsed time rose by 19.0%. Thus GC-off does not increase aggregate kernel CPU in every workload. The claim about fresh-page costs concerns the allocation path; it is not an additive explanation of every CPU or wall-time difference.

| Workload | Mode | Boehm allocation traffic in test (GiB) | Collections in test | Boehm full-collection time (s) |
| --- | --- | ---: | ---: | ---: |
| forms | GC on | 1.991 | 12 | 0.296 |
| forms | GC off | 1.991 | 0 | 0.000 |
| global | GC on | 2.980 | 97 | 2.124 |
| global | GC off | 3.034 | 0 | 0.000 |
| gbZZbug3 | GC on | 18.083 | 197 | 11.243 |
| gbZZbug3 | GC off | 18.083 | 0 | 0.000 |

The probe enables Boehm’s optional performance timer. Despite the inherited JSON field name `gc_cpu_seconds`, this counter reports **full-collection elapsed time**, not CPU usage. It does not measure all allocator work and must not be subtracted from whole-process time to predict GC-off performance. Collection work is real, but so is the reuse benefit it provides.

### Startup is a separate source of overhead

The startup-only input contains just a successful assertion. Its internal interval is too short to compare meaningfully; the following whole-process figures quantify starting and stopping M2 with each GC policy. They include wrapper and shutdown overhead, so they are a startup baseline rather than a pure initialization timer.

| Mode | Process wall (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Peak RSS (GiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GC on | 2.490 | 2.750 | 0.460 | 5.323e+04 | 0 | 0.189 |
| GC off | 3.290 | 2.160 | 1.030 | 3.477e+05 | 0 | 1.343 |

Do not subtract independently measured startup medians from workload medians to claim an exact phase decomposition. The directly bracketed resource measurements above already isolate the test.

## Sampled profiles: an allocation request reaches the kernel

The table aggregates the CPU-clock samples within each case. Forms on/off each combine three profile runs; other cases use one. Sampling frequency is 199 Hz per active thread. No lost samples were reported. A displayed 0.0% is rounded and does not prove an event never occurred. “All kernel” includes the page-clearing subset; these columns are not additive. Some internal Boehm functions lack debug symbols, so we report the entire library. The exporter also emitted addr2line warnings for some M2 frames; named allocation-to-kernel paths were still recovered, but complete source-line attribution is unavailable.

| Workload | Mode | CPU samples | All kernel (%) | clear_page_erms (%) | Boehm library (%) | GMP library (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| forms | on | 1149 | 15.1 | 0.7 | 33.5 | 36.5 |
| forms | off | 1806 | 51.8 | 25.5 | 12.1 | 23.6 |
| forms | reserve | 274 | 12.0 | 4.4 | 20.8 | 49.6 |
| global | on | 2085 | 16.5 | 0.0 | 46.4 | 1.1 |
| global | off | 1636 | 29.0 | 15.1 | 12.8 | 2.3 |
| gbZZbug3 | on | 1.427e+04 | 46.0 | 0.0 | 34.9 | 4.0 |
| gbZZbug3 | off | 6200 | 45.2 | 22.6 | 15.4 | 9.4 |

Sampling is not free: the profiled GC-on integer regression took 30.446 s internally, compared with its 25.392-s resource-run median. We therefore use unprofiled resource runs for timing comparisons and use sampled runs to locate CPU activity; profile percentages are approximate and can be affected by the profiler.

A captured GC-off forms stack contains the following path (simplified, with addresses removed):

```text
M2 polynomial/matrix operation
  → getmem / getmem_atomic
    → GC_malloc_kind
      → GC_generic_malloc_many
        → page fault
          → do_user_addr_fault → do_anonymous_page
            → physical-page allocation → clear_page_erms
```

`clear_page_erms` is the kernel’s page-zeroing routine. The observed call stacks connect it to Boehm allocation requests originating in polynomial and matrix work. Anonymous mappings must present zero-initialized contents (see the [Linux mmap manual](https://man7.org/linux/man-pages/man2/mmap.2.html)); servicing such faults costs CPU and memory bandwidth even without disk I/O. This is stronger evidence than inferring a cause from RSS alone.

Boehm’s allocator normally chooses between collection/reuse and heap expansion. In the [8.2.8 allocator source](https://github.com/ivmai/bdwgc/blob/v8.2.8/alloc.c), `GC_collect_or_expand` guards its collection path with `!GC_dont_gc`, and `GC_expand_hp_inner` obtains more memory. Disabling collection preserves the allocator but removes its normal reclamation path. The [Boehm algorithm overview](https://www.hboehm.info/gc/gcdescr.html) describes this allocation/collection tradeoff.

## Controlled interventions

All three cases below use the same forms input and have **zero collections during the test**. “Late off” allows normal startup and then calls `GC_disable()` just before the test. “Reserve” disables GC from startup, allocates a 3-GiB atomic block, writes every byte, and explicitly frees that block into Boehm before starting the timer.

| Policy | Preparation (s) | Internal elapsed (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Process elapsed (s) | Peak RSS (GiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| off | 2.894e-05 | 2.874 | 1.366 | 1.517 | 5.718e+05 | 5.730 | 3.524 |
| late-off | 3.108e-05 | 2.419 | 1.351 | 1.037 | 5.691e+05 | 5.090 | 2.361 |
| reserve | 1.990 | 1.388 | 1.255 | 0.152 | 4.505e+04 | 6.300 | 4.522 |

The late-off internal median was 2.419 s; its minor-fault count remained about 5.691e+05. Reserving reusable pages reduced faults by 92.1%. Late-off improved elapsed time relative to disabling GC before startup, but retained almost all of the workload’s minor faults. The reserve policy changed the median full command time from 5.730 s to 6.300 s. This is the essential distinction between an internally faster test and a faster complete invocation.

The late-off control tests whether disabling collection only during the workload removes the penalty caused by an already bloated startup heap. The reserve control instead makes a large stock of resident pages reusable. Read its internal improvement together with its preparation and process times: allocation and page-touch costs are paid earlier, and peak memory includes the preparation.

This intervention changes heap availability/layout and page residency together; it is not a perfectly isolated test of one hardware event. Combined with the fault counts and the kernel stacks, however, it gives strong evidence that repeatedly obtaining fresh resident pages is a major mechanism. It does not justify disabling GC in a long-running session: the reserve is finite, and unreachable allocations would keep accumulating.

## Hardware counters and cache interpretation

These are medians of three phase-gated perf-stat runs. All six counters were reported as running for the full enabled interval, without multiplex scaling. Generic cache-event names are those reported by perf; we do not relabel them as L1, L2 or L3 measurements. TLB means translation lookaside buffer, the CPU’s address-translation cache. The measured GC-off runs actually have fewer generic cache misses and data-TLB load misses than GC-on in both workloads. These totals therefore do not support a simple claim that more cache misses caused the slowdown; GC-on also performs extra collector work, which generates its own events.

| Workload | Mode | Cycles | Instructions | Cache references | Cache misses | Data-TLB loads | Data-TLB load misses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| forms | on | 9.666e+09 | 2.565e+10 | 4.015e+08 | 8.211e+07 | 2.363e+07 | 6.744e+06 |
| forms | off | 1.135e+10 | 2.588e+10 | 6.528e+08 | 5.538e+07 | 2.351e+07 | 3.453e+06 |
| forms | reserve | 6.817e+09 | 2.390e+10 | 2.895e+08 | 3.577e+07 | 6.536e+06 | 9.760e+05 |
| global | on | 4.743e+10 | 7.075e+10 | 2.789e+09 | 6.493e+08 | 3.832e+08 | 5.795e+07 |
| global | off | 3.632e+10 | 5.193e+10 | 3.085e+09 | 3.578e+08 | 2.538e+08 | 1.021e+07 |

These counters describe the combined program and kernel activity during the test. They cannot independently separate cache effects from the extra memory-management work: that work itself generates instructions, cache traffic and translations. Because this is WSL, the virtualized PMU also limits how confidently generic events can be interpreted. The named kernel stacks and the resource/intervention results carry more weight than an isolated cache-miss ratio.

## System and provenance

| Property | Recorded value |
| --- | --- |
| CPU | AMD Ryzen 7 9800X3D 8-Core Processor |
| Guest OS | Debian GNU/Linux 13 (trixie) |
| WSL-visible topology | 14 logical CPUs; 7 cores; 2 threads per core |
| L1d cache | 336 KiB (7 instances) |
| L1i cache | 224 KiB (7 instances) |
| L2 cache | 7 MiB (7 instances) |
| L3 cache | 96 MiB (1 instance) |
| WSL-visible RAM | 47.0 GiB |
| Kernel | 6.18.33.1-microsoft-standard-WSL2 |
| Base page size / transparent huge pages | 4 KiB / always [madvise] never (brackets indicate the active policy) |
| Build | Existing CMake Release binary; no recompilation for profiling |
| Source checkout | `7ffc3b9` on `benchmark-gc`; profiling harness added locally |
| libgc1:amd64 | 1:8.2.8-1 |
| linux-perf | 6.12.107-1 |
| strace | 6.13+ds-1 |

Cache totals and topology are the guest’s view. L1d holds data and L1i holds instructions; L2 and L3 provide larger levels of cache. Host DRAM timings, power settings and clock frequency under load were not measured.

The CPU-zero sysfs cache details are listed below. Sharing lists use logical CPU numbers; two logical CPUs on one core share its private caches.

| Level / type | Size | Line size (bytes) | Shared logical CPUs |
| --- | ---: | ---: | --- |
| L1 / Data | 48 KiB | 64 | 0-1 |
| L1 / Instruction | 32 KiB | 64 | 0-1 |
| L2 / Unified | 1 MiB | 64 | 0-1 |
| L3 / Unified | 96 MiB | 64 | 0-13 |

All measured samples use the same executable and probe fingerprints, recorded with the raw data. Full hashes and high-precision timestamps are kept there instead of printing long identifiers here. The collector actually loaded by this binary is Debian’s system Boehm library; the source discussion uses its matching 8.2.8 release, rather than assuming a bundled library was used.

## What we can conclude—and what remains open

- **Supported:** GC-off substantially increases the number of minor faults and resident memory needed by these allocation-heavy workloads. Sampled stacks show kernel page allocation/zeroing on the Boehm allocation path.
- **Supported by the forms control:** reusing already resident pages sharply reduces the internal GC-off penalty, while its preparation cost remains visible in whole-process time.
- **Important distinction:** disabling GC does remove collector work. That does not guarantee a shorter critical path when allocation has to wait for new pages; nor does lower summed CPU time guarantee lower elapsed time.
- **Not established:** a precise percentage of the wall-time penalty attributable separately to page faults, cache misses, TLB misses, allocator bookkeeping, or thread scheduling. Sampling percentages are CPU shares, not an exact additive wall-time decomposition.
- **Scope:** three selected slow-test workloads plus startup, on one WSL machine. Five resource repetitions characterize the observed spread, not all inputs or all machines. The profiles on global and gbZZbug3 have only one sampled run per mode.

For these workloads, the measurements support leaving GC enabled. If performance work continues, the observed allocation call paths suggest examining temporary polynomial/matrix allocation traffic and reuse, then checking changes with the same correctness assertions and whole-process metrics. Changing GC policy alone should not be assumed to be an optimization.

## Appendix A: every resource and control trial

No perf-counter or sampling runs enter this table. Values are rounded for readability; large counts use scientific notation (`e+05` means ×10⁵). Startup-only internal timings are shown as “—” because the input does essentially no work. For startup-only rows, CPU and fault columns cover the whole process; for other rows they cover the timed test.

| Kind / workload | Policy | Trial | Internal wall (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Process wall (s) | Peak RSS (GiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| control / forms | late-off | 1 | 2.223 | 1.300 | 0.923 | 5.691e+05 | 0 | 5.040 | 2.360 |
| control / forms | off | 1 | 2.141 | 1.307 | 0.828 | 5.718e+05 | 0 | 4.960 | 3.524 |
| control / forms | reserve | 1 | 1.374 | 1.214 | 0.161 | 4.505e+04 | 0 | 5.360 | 4.521 |
| control / forms | late-off | 2 | 2.419 | 1.351 | 1.060 | 5.691e+05 | 0 | 5.090 | 2.361 |
| control / forms | off | 2 | 2.884 | 1.367 | 1.517 | 5.718e+05 | 0 | 5.660 | 3.525 |
| control / forms | reserve | 2 | 1.408 | 1.256 | 0.152 | 4.505e+04 | 0 | 6.460 | 4.522 |
| control / forms | late-off | 3 | 2.450 | 1.408 | 1.037 | 5.690e+05 | 0 | 5.010 | 2.360 |
| control / forms | off | 3 | 2.874 | 1.357 | 1.517 | 5.718e+05 | 0 | 5.820 | 3.525 |
| control / forms | reserve | 3 | 1.388 | 1.220 | 0.169 | 4.505e+04 | 0 | 6.300 | 4.521 |
| control / forms | late-off | 4 | 2.415 | 1.330 | 1.085 | 5.691e+05 | 0 | 5.120 | 2.361 |
| control / forms | off | 4 | 2.895 | 1.366 | 1.528 | 5.718e+05 | 0 | 5.730 | 3.524 |
| control / forms | reserve | 4 | 1.385 | 1.255 | 0.130 | 4.505e+04 | 0 | 6.350 | 4.522 |
| control / forms | late-off | 5 | 2.445 | 1.412 | 1.028 | 5.692e+05 | 0 | 5.100 | 2.361 |
| control / forms | off | 5 | 2.824 | 1.372 | 1.451 | 5.718e+05 | 0 | 5.800 | 3.524 |
| control / forms | reserve | 5 | 1.425 | 1.277 | 0.149 | 4.505e+04 | 0 | 6.280 | 4.522 |
| resource / forms | off | 1 | 3.010 | 1.486 | 1.523 | 5.718e+05 | 0 | 6.520 | 3.525 |
| resource / forms | on | 1 | 1.598 | 1.755 | 0.380 | 3.010e+04 | 0 | 4.090 | 0.304 |
| resource / forms | off | 2 | 3.038 | 1.467 | 1.572 | 5.718e+05 | 0 | 5.960 | 3.524 |
| resource / forms | on | 2 | 1.588 | 1.863 | 0.297 | 3.003e+04 | 0 | 4.150 | 0.304 |
| resource / forms | off | 3 | 3.009 | 1.496 | 1.512 | 5.718e+05 | 0 | 6.470 | 3.525 |
| resource / forms | on | 3 | 1.555 | 1.823 | 0.273 | 3.011e+04 | 0 | 4.010 | 0.304 |
| resource / forms | off | 4 | 3.010 | 1.429 | 1.578 | 5.718e+05 | 0 | 6.060 | 3.524 |
| resource / forms | on | 4 | 1.598 | 1.854 | 0.333 | 3.005e+04 | 0 | 4.040 | 0.304 |
| resource / forms | off | 5 | 3.008 | 1.459 | 1.547 | 5.718e+05 | 0 | 6.210 | 3.525 |
| resource / forms | on | 5 | 1.570 | 1.827 | 0.288 | 3.010e+04 | 0 | 3.980 | 0.305 |
| resource / gbZZbug3 | off | 1 | 31.508 | 15.911 | 15.598 | 5.098e+06 | 0 | 35.930 | 20.789 |
| resource / gbZZbug3 | on | 1 | 25.098 | 35.482 | 36.404 | 4.939e+04 | 0 | 27.640 | 0.376 |
| resource / gbZZbug3 | off | 2 | 28.800 | 15.611 | 13.163 | 5.098e+06 | 0 | 33.330 | 20.789 |
| resource / gbZZbug3 | on | 2 | 26.655 | 37.186 | 39.621 | 5.109e+04 | 0 | 29.130 | 0.376 |
| resource / gbZZbug3 | off | 3 | 30.727 | 16.176 | 14.544 | 5.098e+06 | 0 | 35.350 | 20.789 |
| resource / gbZZbug3 | on | 3 | 25.316 | 35.818 | 36.666 | 5.114e+04 | 0 | 27.960 | 0.376 |
| resource / gbZZbug3 | off | 4 | 28.265 | 15.461 | 12.783 | 5.098e+06 | 0 | 32.760 | 20.789 |
| resource / gbZZbug3 | on | 4 | 25.691 | 35.794 | 38.041 | 4.951e+04 | 0 | 28.180 | 0.376 |
| resource / gbZZbug3 | off | 5 | 30.208 | 15.669 | 14.536 | 5.098e+06 | 0 | 34.870 | 20.789 |
| resource / gbZZbug3 | on | 5 | 25.392 | 35.477 | 37.559 | 4.965e+04 | 0 | 28.030 | 0.371 |
| resource / global | off | 1 | 8.297 | 5.705 | 2.592 | 8.519e+05 | 0 | 11.730 | 4.593 |
| resource / global | on | 1 | 6.382 | 8.988 | 1.754 | 4956 | 0 | 8.860 | 0.188 |
| resource / global | off | 2 | 7.902 | 5.565 | 2.336 | 8.519e+05 | 0 | 10.760 | 4.593 |
| resource / global | on | 2 | 6.452 | 9.296 | 1.767 | 5000 | 0 | 8.880 | 0.188 |
| resource / global | off | 3 | 8.465 | 5.979 | 2.487 | 8.519e+05 | 0 | 11.710 | 4.593 |
| resource / global | on | 3 | 6.423 | 8.933 | 1.863 | 5008 | 0 | 8.840 | 0.188 |
| resource / global | off | 4 | 8.144 | 5.749 | 2.394 | 8.518e+05 | 0 | 11.220 | 4.593 |
| resource / global | on | 4 | 6.451 | 9.282 | 1.780 | 4849 | 0 | 8.930 | 0.188 |
| resource / global | off | 5 | 8.459 | 5.920 | 2.540 | 8.519e+05 | 0 | 11.930 | 4.593 |
| resource / global | on | 5 | 6.409 | 8.987 | 1.711 | 4906 | 0 | 8.830 | 0.188 |
| resource / startup | off | 1 | — | 2.250 | 1.030 | 3.477e+05 | 0 | 3.290 | 1.343 |
| resource / startup | on | 1 | — | 2.780 | 0.440 | 5.324e+04 | 0 | 2.500 | 0.189 |
| resource / startup | off | 2 | — | 2.160 | 0.630 | 3.477e+05 | 0 | 2.790 | 1.343 |
| resource / startup | on | 2 | — | 2.750 | 0.610 | 5.323e+04 | 0 | 2.540 | 0.189 |
| resource / startup | off | 3 | — | 2.320 | 1.040 | 3.477e+05 | 0 | 3.370 | 1.343 |
| resource / startup | on | 3 | — | 2.760 | 0.440 | 5.310e+04 | 0 | 2.420 | 0.189 |
| resource / startup | off | 4 | — | 2.020 | 0.770 | 3.477e+05 | 0 | 2.810 | 1.343 |
| resource / startup | on | 4 | — | 2.680 | 0.600 | 5.302e+04 | 0 | 2.490 | 0.189 |
| resource / startup | off | 5 | — | 2.160 | 1.150 | 3.477e+05 | 0 | 3.310 | 1.343 |
| resource / startup | on | 5 | — | 2.740 | 0.460 | 5.332e+04 | 0 | 2.440 | 0.190 |

### Control preparation costs for every trial

| Policy | Trial | Preparation wall (s) | Preparation user CPU (s) | Preparation kernel CPU (s) | Preparation minor faults |
| --- | ---: | ---: | ---: | ---: | ---: |
| late-off | 1 | 3.122e-05 | 3.400e-05 | 7.000e-06 | 0 |
| off | 1 | 2.894e-05 | 3.100e-05 | 8.000e-06 | 0 |
| reserve | 1 | 0.955 | 0.096 | 0.850 | 7.881e+05 |
| late-off | 2 | 2.969e-05 | 3.300e-05 | 6.000e-06 | 0 |
| off | 2 | 2.595e-05 | 2.600e-05 | 8.000e-06 | 0 |
| reserve | 2 | 2.113 | 0.099 | 2.012 | 7.881e+05 |
| late-off | 3 | 3.239e-05 | 3.900e-05 | 6.000e-06 | 0 |
| off | 3 | 2.994e-05 | 3.100e-05 | 8.000e-06 | 0 |
| reserve | 3 | 1.990 | 0.087 | 1.901 | 7.881e+05 |
| late-off | 4 | 2.991e-05 | 3.500e-05 | 5.000e-06 | 0 |
| off | 4 | 2.752e-05 | 2.800e-05 | 8.000e-06 | 0 |
| reserve | 4 | 1.951 | 0.095 | 1.855 | 7.881e+05 |
| late-off | 5 | 3.108e-05 | 3.800e-05 | 4.000e-06 | 0 |
| off | 5 | 3.349e-05 | 3.200e-05 | 1.000e-05 | 0 |
| reserve | 5 | 1.998 | 0.092 | 1.904 | 7.881e+05 |

## Appendix B: every hardware-counter run

| Workload | Policy | Trial | Cycles | Instructions | Cache references | Cache misses | Data-TLB loads | Data-TLB load misses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| forms | off | 1 | 1.135e+10 | 2.585e+10 | 6.528e+08 | 5.482e+07 | 2.351e+07 | 3.453e+06 |
| forms | off | 2 | 1.125e+10 | 2.588e+10 | 6.329e+08 | 5.538e+07 | 2.267e+07 | 3.301e+06 |
| forms | off | 3 | 1.140e+10 | 2.588e+10 | 6.636e+08 | 5.619e+07 | 2.423e+07 | 3.637e+06 |
| forms | on | 1 | 9.666e+09 | 2.570e+10 | 4.015e+08 | 8.496e+07 | 2.393e+07 | 6.744e+06 |
| forms | on | 2 | 9.623e+09 | 2.565e+10 | 4.012e+08 | 8.211e+07 | 2.363e+07 | 6.773e+06 |
| forms | on | 3 | 9.699e+09 | 2.564e+10 | 4.033e+08 | 8.169e+07 | 2.352e+07 | 6.652e+06 |
| forms | reserve | 1 | 6.817e+09 | 2.389e+10 | 2.888e+08 | 3.607e+07 | 6.893e+06 | 9.852e+05 |
| forms | reserve | 2 | 6.790e+09 | 2.390e+10 | 2.895e+08 | 3.577e+07 | 6.536e+06 | 9.760e+05 |
| forms | reserve | 3 | 6.833e+09 | 2.390e+10 | 2.958e+08 | 3.302e+07 | 6.170e+06 | 7.866e+05 |
| global | off | 1 | 3.632e+10 | 5.193e+10 | 3.085e+09 | 3.578e+08 | 2.562e+08 | 1.021e+07 |
| global | off | 2 | 3.552e+10 | 5.192e+10 | 2.968e+09 | 3.465e+08 | 2.488e+08 | 9.846e+06 |
| global | off | 3 | 3.701e+10 | 5.194e+10 | 3.176e+09 | 3.723e+08 | 2.538e+08 | 1.047e+07 |
| global | on | 1 | 4.708e+10 | 7.075e+10 | 2.789e+09 | 6.493e+08 | 3.787e+08 | 5.795e+07 |
| global | on | 2 | 4.915e+10 | 7.079e+10 | 2.811e+09 | 6.592e+08 | 3.842e+08 | 5.939e+07 |
| global | on | 3 | 4.743e+10 | 7.065e+10 | 2.735e+09 | 6.464e+08 | 3.832e+08 | 5.765e+07 |

## Appendix C: every sampled profile

| Workload | Policy | Trial | Samples | Active sampled threads | Kernel (%) | Page zeroing (%) | Boehm (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| forms | off | 1 | 603 | 1 | 51.6 | 25.4 | 10.9 |
| forms | off | 2 | 608 | 1 | 51.3 | 26.3 | 13.5 |
| forms | off | 3 | 595 | 1 | 52.4 | 24.7 | 11.9 |
| forms | on | 1 | 413 | 14 | 15.7 | 1.9 | 36.6 |
| forms | on | 2 | 373 | 14 | 14.5 | 0.0 | 33.0 |
| forms | on | 3 | 363 | 14 | 14.9 | 0.0 | 30.6 |
| forms | reserve | 1 | 274 | 1 | 12.0 | 4.4 | 20.8 |
| gbZZbug3 | off | 1 | 6200 | 1 | 45.2 | 22.6 | 15.4 |
| gbZZbug3 | on | 1 | 1.427e+04 | 22 | 46.0 | 0.0 | 34.9 |
| global | off | 1 | 1636 | 1 | 29.0 | 15.1 | 12.8 |
| global | on | 1 | 2085 | 15 | 16.5 | 0.0 | 46.4 |

## Appendix D: timings of instrumented runs

These measurements show the runs that produced the counters and profiles above. They are reported separately because instrumentation can change runtime. CPU and fault figures cover the timed phase; RSS and process wall cover the whole invocation.

| Kind / workload | Policy | Trial | Internal wall (s) | User CPU (s) | Kernel CPU (s) | Minor faults | Major faults | Process wall (s) | Peak RSS (GiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record / forms | off | 1 | 3.036 | 1.461 | 1.572 | 5.718e+05 | 0 | 6.500 | 3.524 |
| record / forms | off | 2 | 3.063 | 1.434 | 1.626 | 5.718e+05 | 0 | 6.230 | 3.524 |
| record / forms | off | 3 | 2.996 | 1.501 | 1.496 | 5.718e+05 | 0 | 6.080 | 3.525 |
| record / forms | on | 1 | 1.622 | 1.802 | 0.399 | 3.009e+04 | 0 | 4.190 | 0.304 |
| record / forms | on | 2 | 1.585 | 1.837 | 0.313 | 2.997e+04 | 0 | 4.060 | 0.305 |
| record / forms | on | 3 | 1.577 | 1.800 | 0.342 | 3.011e+04 | 0 | 4.040 | 0.305 |
| record / forms | reserve | 1 | 1.382 | 1.268 | 0.113 | 4.511e+04 | 0 | 6.480 | 4.521 |
| record / gbZZbug3 | off | 1 | 31.218 | 17.275 | 13.886 | 5.098e+06 | 0 | 35.830 | 20.788 |
| record / gbZZbug3 | on | 1 | 30.446 | 39.266 | 37.100 | 4.982e+04 | 0 | 33 | 0.372 |
| record / global | off | 1 | 8.224 | 5.808 | 2.416 | 8.519e+05 | 0 | 11.130 | 4.593 |
| record / global | on | 1 | 6.638 | 9.211 | 2.052 | 4834 | 0 | 9.120 | 0.188 |
| stat / forms | off | 1 | 3.036 | 1.364 | 1.671 | 5.718e+05 | 0 | 6.030 | 3.525 |
| stat / forms | off | 2 | 2.894 | 1.484 | 1.409 | 5.718e+05 | 0 | 5.760 | 3.524 |
| stat / forms | off | 3 | 3.068 | 1.459 | 1.608 | 5.718e+05 | 0 | 6.380 | 3.524 |
| stat / forms | on | 1 | 1.487 | 1.747 | 0.419 | 3.012e+04 | 0 | 4.040 | 0.304 |
| stat / forms | on | 2 | 1.491 | 1.821 | 0.338 | 3.004e+04 | 0 | 3.970 | 0.304 |
| stat / forms | on | 3 | 1.512 | 1.774 | 0.398 | 3.009e+04 | 0 | 3.980 | 0.304 |
| stat / forms | reserve | 1 | 1.405 | 1.208 | 0.196 | 4.512e+04 | 0 | 7.070 | 4.522 |
| stat / forms | reserve | 2 | 1.401 | 1.222 | 0.179 | 4.511e+04 | 0 | 6.160 | 4.522 |
| stat / forms | reserve | 3 | 1.403 | 1.239 | 0.163 | 4.512e+04 | 0 | 6.130 | 4.521 |
| stat / global | off | 1 | 8.405 | 5.700 | 2.704 | 8.519e+05 | 0 | 11.740 | 4.593 |
| stat / global | off | 2 | 8.095 | 5.538 | 2.555 | 8.519e+05 | 0 | 10.930 | 4.593 |
| stat / global | off | 3 | 8.672 | 5.957 | 2.713 | 8.519e+05 | 0 | 12.070 | 4.593 |
| stat / global | on | 1 | 5.939 | 8.911 | 2.152 | 4834 | 0 | 8.530 | 0.189 |
| stat / global | on | 2 | 6.175 | 9.213 | 2.593 | 4857 | 0 | 8.660 | 0.188 |
| stat / global | on | 3 | 5.900 | 8.916 | 2.150 | 4844 | 0 | 8.350 | 0.189 |

## Benchmark structure and reproduction

The pipeline is: original slow-test input → fresh M2 process with the phase probe → optional phase-gated perf collection → correctness and counter checks → per-sample JSON/logs → median tables and profile summaries in this file. Preparation, timed input and whole-process measurements remain separate throughout.

Use the native Linux checkout. Build prerequisites are described in [BENCHMARK.md](BENCHMARK.md). For a fresh Release build, run `cmake -S M2 -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON`, then `cmake --build build --target build-libraries --parallel 4` and `cmake --build build --target M2-core --parallel 4`. The runner’s `BINARY` setting points directly to `build/usr-dist/x86_64-Linux-Debian-/bin/M2-binary`; adjust that setting if the staging path differs. Comparing a rebuilt binary is a new experiment, not a continuation of these samples.

The profiling harness requires Python 3, GCC, libgc development headers, GNU time, prlimit, and Linux perf. On Debian, install the profiling tools with `sudo apt-get install linux-perf libgc-dev gcc time util-linux`. With the Release binary available:

```sh
mkdir -p benchmark-results/gc-profile
gcc -O2 -g -shared -fPIC M2/Macaulay2/benchmarks/gc-profile/probe.c \
  -o benchmark-results/gc-profile/probe.so -ldl -lgc
python3 M2/Macaulay2/benchmarks/gc-profile/experiments.py \
  > benchmark-results/gc-profile/experiments.log 2>&1
python3 M2/Macaulay2/benchmarks/gc-profile/report.py
```

The runner uses `sudo -n` and needs permission for noninteractive perf collection and running the child as the normal user. Validate that access before starting the matrix. It needs `sudo perf` access for kernel sampling and executes the M2 workload as the normal user. Its precise commands and environment settings are saved per sample. The resource suite and controls use five trials; counter runs use three; profile counts are listed above. A failed assertion, timeout, or unexpected collection in an off policy prevents a successful result. Completed samples are reused after interruption, so archive the output directory before starting a wholly new experiment.

To inspect a captured profile directly:

```sh
perf report --stdio --no-children --call-graph none \
  -i benchmark-results/gc-profile/record-forms-off-1/perf.data
```

The [profiling harness](M2/Macaulay2/benchmarks/gc-profile), [raw experiment directory](benchmark-results/gc-profile), and [original slow tests](M2/Macaulay2/tests/slow) provide the supporting code and evidence. The raw directory is ignored by Git; retain it if future stack-level reanalysis is needed. This report itself contains the numerical findings and trial tables needed for colleagues to review the argument without those files.
