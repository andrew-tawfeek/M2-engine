# Garbage collection in Macaulay2: slow-test workloads

Measured 2026-09-13 on this WSL machine, using the Release build of `benchmark-gc` at commit `267c1f7`.

This comparison ran **8 workloads taken from `M2/Macaulay2/tests/slow/`**, with **five recorded fresh processes per workload per mode**, after one warm-up per mode. All 80 recorded runs and 16 warm-ups passed their checks. These are new slow-test workloads; the previous six package workloads were not rerun.

With garbage collection disabled, the **sum of workload-internal median wall times** changed from **37.553 s to 47.450 s (+26.4%)**. The **sum of whole-process median wall times** changed from **57.04 s to 74.96 s (+31.4%)**. The geometric mean of the per-workload peak-memory ratios was **10.74×** with GC off. These aggregates describe this selection on this machine, not a general speed prediction.

GC off had a higher internal-time median in **8 of 8 workloads** and a higher whole-process-time median in **8 of 8**. Its largest median peak memory was **20.8 GiB**, in `gbZZbug3`. Each workload contributes one median to the timing sums; the five repetitions and warm-ups are not added together.

## What the measurements mean

| Term | Meaning and scope |
| --- | --- |
| GC on | Normal automatic Boehm garbage collection. Unreachable managed allocations can be reclaimed. All inherited `GC_*` environment variables are removed. |
| GC off | The same executable and environment, with `GC_DONT_GC=1` set before M2 starts. Unreachable GC-managed allocations are retained until the process exits. This does not disable every allocator or every explicit free in external libraries. |
| Internal wall time, seconds | A stopwatch **inside Macaulay2**, using `elapsedTiming input testFile`. It measures real elapsed time while reading, parsing, evaluating, and printing the active test, including its assertions and any package loading it triggers. It excludes M2 startup, the random-seed setup, and final benchmark output. **It is not CPU time.** |
| Whole-process wall time, seconds | GNU `/usr/bin/time` measures elapsed time from launching M2 to its exit. This includes startup, initialization, the entire test, and shutdown. It is the closer measure of how long a user waits for a fresh command. |
| Peak RSS, MiB | **RSS means resident set size**: memory resident in physical RAM for the process. Peak RSS is the highest such value during the whole process, including startup. It includes managed heap, other allocations, stacks, and resident code/library pages. It is neither total allocated bytes nor the amount of live mathematical data. |
| MiB and GiB | Binary units: 1 MiB = 2²⁰ bytes (about 1.049 × 10⁶ bytes); 1 GiB = 1,024 MiB. GNU time reports RSS in KiB on Linux; this report divides by 1,024 to obtain MiB. |
| Median | The middle of five measurements, computed separately for each metric. It reduces the influence of an unusually fast or slow run. The median internal time, wall time, and RSS need not come from the same trial. |
| Change / ratio | Change is `(GC off / GC on − 1) × 100%`; positive means more time or memory with GC off. A memory ratio of 2× means twice the peak memory, not 2% more. |

The geometric-mean memory ratio is an average of multiplication factors: multiply the per-workload off/on ratios and take the root corresponding to the number of workloads. Each workload has equal weight in this measure.

The internal and whole-process timers overlap: **do not add them**. Startup is deliberately included only in the whole-process measure. The internal timer here differs from the previous package suite: lazy package loading and test-output formatting are inside it. Output is captured through pipes and saved to files, rather than displayed in a terminal.

Some original tests also print their own `time` diagnostics in the logs. Those CPU/thread/GC messages are not the timing values used in these tables; the tables use the wrapper's `elapsedTiming` result and GNU time's process measurements.

## Timing results

Every value below is a median of five runs. Both timing columns measure elapsed wall time, but over different boundaries.

| Workload | Internal GC on (s) | Internal GC off (s) | Internal change | Whole process GC on (s) | Whole process GC off (s) | Whole-process change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4c | 0.261 | 0.351 | +34.4% | 2.71 | 3.64 | +34.3% |
| complete-intersections | 0.346 | 0.586 | +69.1% | 2.74 | 3.88 | +41.6% |
| forms | 1.597 | 3.036 | +90.1% | 4.03 | 6.44 | +59.8% |
| gb-1 | 0.744 | 1.429 | +92.2% | 3.16 | 4.67 | +47.8% |
| gbZZbug3 | 25.771 | 30.211 | +17.2% | 28.22 | 34.78 | +23.2% |
| global | 6.377 | 8.493 | +33.2% | 8.85 | 12.05 | +36.2% |
| roos2 | 0.706 | 1.028 | +45.5% | 3.14 | 4.10 | +30.6% |
| sturmfels | 1.751 | 2.316 | +32.3% | 4.19 | 5.40 | +28.9% |

## Memory and collection results

The memory figures are **medians of five process-wide peaks**. Large values use scientific notation: for example, `2.129e+04 MiB` means 2.129 × 10⁴ MiB (about 20.8 GiB). Collection-counter snapshots bracket the timed test input; a separate lifetime counter also confirmed **zero collections from startup through test completion in every GC-off run**, including warm-ups.

| Workload | Peak RSS GC on (MiB) | Peak RSS GC off (MiB) | Off/on memory ratio | Timed collections GC on (median) | Timed collections GC off (median) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4c | 293.2 | 1586 | 5.41× | 1 | 0 |
| complete-intersections | 316.8 | 1794 | 5.66× | 2 | 0 |
| forms | 311.6 | 3607 | 11.58× | 12 | 0 |
| gb-1 | 311.7 | 2532 | 8.12× | 7 | 0 |
| gbZZbug3 | 380.4 | 2.129e+04 | 55.95× | 199 | 0 |
| global | 192.7 | 4701 | 24.39× | 97 | 0 |
| roos2 | 311.9 | 1914 | 6.14× | 3 | 0 |
| sturmfels | 312 | 2290 | 7.34× | 6 | 0 |

Turning off collection also retains allocations made during startup. Thus a short test can have a large whole-process memory ratio even if it does relatively little work after initialization. This experiment does not separately measure startup-only memory, so these peaks should not be attributed entirely to the algebra calculation.

## Which slow tests were used

The input sizes and original assertions were preserved. Each fresh process executes its workload once; no artificial inner repetition loop was added. All tests start with the same fixed random seed (saved in the JSON).

| Workload and source | Work performed and correctness checks |
| --- | --- |
| [4c](M2/Macaulay2/tests/slow/4c.m2) | Sturmfels counterexample over a finite field and the rationals: codimension, decomposition, singular locus, and resolution. Checks include codimensions 4 and 6, the Hilbert polynomial, and rank 281 at resolution step five. |
| [complete-intersections](M2/Macaulay2/tests/slow/complete-intersections.m2) | Ext and Poincaré-series calculations over the quotient by (x³, y⁴, z⁵). Compares seven coefficients of the series with independently computed Ext ranks. |
| [forms](M2/Macaulay2/tests/slow/forms.m2) | Degree-16 random forms in three variables over the rationals, using the original 76-by-98 construction. Computes a degree-limited Gröbner basis; added checks require 76 generators and zero remainders for the input matrix. |
| [gb-1](M2/Macaulay2/tests/slow/gb-1.m2) | Runs the original gb-1.aux examples with four Gröbner-basis algorithms. Preserves the suite's exact-basis and syzygy assertions. |
| [gbZZbug3](M2/Macaulay2/tests/slow/gbZZbug3.m2) | Integer-polynomial membership regression with p=2 and k=2. Performs both original membership reductions and verifies the explicit polynomial certificate G₀J₀ + G₁J₁ + G₂J₂ = f₀. |
| [global](M2/Macaulay2/tests/slow/global.m2) | Sheaf cohomology on projective spaces and an elliptic curve, plus mixed-support direct sums. Preserves the dimension, degree, and direct-sum assertions. |
| [roos2](M2/Macaulay2/tests/slow/roos2.m2) | Resolution of the residue field of the original five-variable quotient, with length limits six and five using two strategies. Added checks require both differentials to square to zero and matching ranks through step four. |
| [sturmfels](M2/Macaulay2/tests/slow/sturmfels.m2) | The original ten-variable quadratic example over ZZ/7, with an extra homogenizing variable. Computes a Gröbner basis and saturation and checks degree 638. |

The generated inputs preserve the original `input` behavior, including assertions that refer to `oo`, the previous result. Material after an explicit `end` is historical scratch work and is omitted. `forms` and `roos2` gain the checks described above because their originals mainly run computations without asserting the results. No original test file was edited.

### Coverage and exclusions

There are twelve `.m2` files in the slow-test directory. Ten distinct active candidates were piloted. `gbZZ5.m2` is already deferred by an `end` before its calculation. `gbZZbug3-a.m2` repeats the core membership calculation of `gbZZbug3.m2`; the latter also verifies an explicit certificate, so the duplicate was not separately benchmarked. `gb-1.aux` is supporting input and is exercised by `gb-1`.

The following candidates were not included in the timing comparison. Failed or resource-limited runs are **not successful timings** and do not enter any summary:

| Candidate | Pilot outcome |
| --- | --- |
| isSubset | gc-on: passed; gc-off: out of memory under the 6-GiB address-space limit |
| plethysms | gc-on: passed; gc-off: out of memory under the 6-GiB address-space limit |

Both excluded candidates also reported out of memory with GC off when retried at a 24-GiB address-space limit. They remain excluded at their original sizes. The separate retry evidence appears below. The integer regression `gbZZbug3` passed at the larger limit and is included. All recorded workloads used the same 24-GiB limit in both modes.

[Pilot results](benchmark-results/slow-gc-pilot/raw-results.json) are separate from the recorded measurements. The pilot used a 180-second wall timeout per process and a 6-GiB virtual-address-space limit.

## Repeatability and limits of the conclusions

Five samples are enough to show the observed spread, but do not establish a universal performance result or statistical significance. These are fixed-seed regression inputs, not a survey of all user computations. The sums of medians are a descriptive aggregate, not the measured duration of a single suite run; slower tests have more weight. The geometric-mean memory ratio gives each selected workload equal weight and is not a total RAM requirement.

The following ranges show the fastest and slowest recorded runs, alongside the median used above. Ranges are observed variation, not confidence intervals.

| Workload | Mode | Internal min / median / max (s) | Whole-process min / median / max (s) | Peak RSS min / median / max (MiB) |
| --- | --- | ---: | ---: | ---: |
| 4c | gc-on | 0.248 / 0.261 / 0.279 | 2.68 / 2.71 / 2.77 | 293 / 293.2 / 293.6 |
| 4c | gc-off | 0.343 / 0.351 / 0.356 | 3.16 / 3.64 / 3.70 | 1586 / 1586 / 1587 |
| complete-intersections | gc-on | 0.318 / 0.346 / 0.391 | 2.70 / 2.74 / 2.87 | 316.6 / 316.8 / 317 |
| complete-intersections | gc-off | 0.584 / 0.586 / 0.589 | 3.83 / 3.88 / 3.93 | 1793 / 1794 / 1794 |
| forms | gc-on | 1.575 / 1.597 / 1.629 | 3.99 / 4.03 / 4.26 | 311.4 / 311.6 / 312 |
| forms | gc-off | 3.025 / 3.036 / 3.046 | 6.21 / 6.44 / 6.51 | 3607 / 3607 / 3608 |
| gb-1 | gc-on | 0.715 / 0.744 / 0.757 | 3.12 / 3.16 / 3.21 | 311.6 / 311.7 / 311.7 |
| gb-1 | gc-off | 1.420 / 1.429 / 1.436 | 4.30 / 4.67 / 4.88 | 2532 / 2532 / 2532 |
| gbZZbug3 | gc-on | 25.151 / 25.771 / 26.020 | 27.66 / 28.22 / 28.61 | 380 / 380.4 / 385.3 |
| gbZZbug3 | gc-off | 27.107 / 30.211 / 30.338 | 31.37 / 34.78 / 34.91 | 2.129e+04 / 2.129e+04 / 2.129e+04 |
| global | gc-on | 6.340 / 6.377 / 6.553 | 8.73 / 8.85 / 8.98 | 192.5 / 192.7 / 193 |
| global | gc-off | 8.127 / 8.493 / 8.528 | 11.12 / 12.05 / 12.12 | 4701 / 4701 / 4702 |
| roos2 | gc-on | 0.697 / 0.706 / 0.713 | 3.10 / 3.14 / 3.16 | 311.4 / 311.9 / 312.2 |
| roos2 | gc-off | 1.024 / 1.028 / 1.035 | 3.88 / 4.10 / 4.33 | 1913 / 1914 / 1914 |
| sturmfels | gc-on | 1.684 / 1.751 / 1.825 | 4.11 / 4.19 / 4.28 | 311.6 / 312 / 312.4 |
| sturmfels | gc-off | 2.302 / 2.316 / 2.340 | 5.23 / 5.40 / 5.67 | 2290 / 2290 / 2290 |

## How the comparison was run

- Same native WSL checkout and Release executable for both modes. `cmake --build build --target M2-core --parallel 4` completed successfully before the pilot. Measurements ran sequentially, with no overlapping benchmark processes.
- One fresh-process warm-up per mode per workload, excluded from statistics but retained in the data. Warm-ups may prime operating-system file caches; they do not reuse the measured process's heap.
- Five measured fresh processes per mode per workload. Order alternates: on/off for trials 1, 3, and 5; off/on for trials 2 and 4. This reduces but does not eliminate ordering or background-load effects.
- Fixed `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and `LC_ALL=C`. This is not a claim that all M2 or GC activity is single-threaded. No CPU affinity was imposed, and other host/WSL activity was not controlled.
- Each process has a 300-second wall timeout and a 24-GiB virtual-address-space limit (`RLIMIT_AS`). The latter bounds address space, not just resident RAM; it is not the RSS column. Core dumps are disabled. A timeout kills the process group. A failed check, nonzero exit, missing result, or unexpected collection in GC-off aborts the recorded comparison.
- GNU time's wall/user/system fields have hundredth-of-a-second output granularity. The internal timing is stored at M2's printed precision. Rounded report figures should not be treated as exact or as evidence of sub-millisecond reproducibility.

### Other fields in the raw data

`process_user_seconds` is CPU time spent executing user-space code; `process_system_seconds` is CPU time spent in the kernel. These are whole-process CPU usage, not stopwatch duration, and can differ from wall time, especially with multiple threads. `bytes_allocated` is the increase in Boehm's cumulative allocated-byte counter around the timed test: allocation traffic, not live memory. `heap_bytes` is Boehm's mapped heap size after the test, not process RSS.

The inherited raw field `gc_cpu_seconds` comes from M2's `GCstats()` key `gcCpuTimeSecs`. Its implementation calls Boehm's full-collection timing counter. Do not interpret a zero as proof that GC took no time: this counter requires performance measurement support/activation and may be unavailable or inactive. It is not used to explain the timing differences in this report. Collection counts provide the verification that GC was disabled.

Timing boundaries and counters were checked against the repository implementations in [chrono.dd](M2/Macaulay2/d/chrono.dd), [actors5.d](M2/Macaulay2/d/actors5.d), and [Boehm's API declarations](M2/submodules/bdwgc/include/gc.h).

## System hardware and cache layout

These are the resources reported inside WSL, measured with `lscpu`, Linux cache sysfs entries, and `/proc/meminfo`. They describe the guest's view; they should not be read as a complete inventory of the Windows host.

| Property | Observed configuration |
| --- | --- |
| CPU model | AMD Ryzen 7 9800X3D 8-Core Processor |
| Visible topology | 14 logical CPUs; 7 cores; 2 threads per core; 1 socket |
| Architecture / virtualization | x86_64; Microsoft hypervisor; WSL 2 |
| L1d cache | 48 KiB per instance; 336 KiB (7 instances) visible in total; 12-way associative |
| L1i cache | 32 KiB per instance; 224 KiB (7 instances) visible in total; 8-way associative |
| L2 cache | 1 MiB per instance; 7 MiB (7 instances) visible in total; 16-way associative |
| L3 cache | 96 MiB per instance; 96 MiB (1 instance) visible in total; 16-way associative |
| Cache-line size | 64 bytes |
| Visible RAM | 47.0 GiB |
| Available RAM before the recorded run | 45.7 GiB |
| WSL swap | 16.0 GiB total; 16.0 GiB free before the run |
| Guest OS | Debian GNU/Linux 13 (trixie) |

L1 is the smallest, closest cache: L1d holds data and L1i holds instructions. L2 is larger and shared by the two logical threads of a visible core. L3 is the larger last-level cache shared across the visible cores. Cache capacity can affect algebra workloads that repeatedly access allocated data, but this experiment did not measure cache hits, cache misses, bandwidth, or clock frequency under load. The memory and timing differences alone cannot identify a cache-related cause.

The processor's model name describes an eight-core CPU, while WSL exposes seven cores and fourteen logical CPUs. The cache totals above are the WSL-visible inventory, not evidence that the physical host has only seven cores. Host RAM, DRAM speed/timings, and power settings were not independently measured.

## Environment and saved evidence

- Run window: Sep 13, 2026, 20:16 UTC to 20:29 UTC.
- Macaulay2 version: `1.26.06`; build type: `Release`. The complete embedded version string is in the JSON.
- CPU: AMD Ryzen 7 9800X3D 8-Core Processor; 14 logical CPUs visible to WSL.
- Platform: `Linux-6.18.33.1-microsoft-standard-WSL2-x86_64-with-glibc2.41`; kernel: `6.18.33.1-microsoft-standard-WSL2`.
- Memory visible to WSL: 47.0 GiB.
- Base source commit: `267c1f7`. The new benchmark harness was an uncommitted addition during this run; the exact status and hashes are recorded in the JSON.
- Full binary and source fingerprints are saved in the JSON rather than printed as long identifiers here.

[Recorded data and warm-ups](benchmark-results/slow-gc-recorded/raw-results.json) contain every measurement, command, controlled environment, exit status, and source/script hash. [Captured inputs](benchmark-results/slow-gc-recorded/scripts) and [stdout/stderr logs](benchmark-results/slow-gc-recorded/logs) allow inspection of the actual tests and assertions. The results directory is local and ignored by Git; retain it with this report when sharing or archiving the experiment.

## Individual recorded trials

Warm-ups are in the JSON only. Internal time is rounded to four significant figures here; the JSON retains the stored values. Scientific notation uses e for a power of ten (for example, 1.234e+04 means 1.234 × 10⁴).

### 4c

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 0.266 | 2.71 | 293.3 | 1 |
| 1 | gc-off | 0.3511 | 3.64 | 1586 | 0 |
| 2 | gc-off | 0.3556 | 3.16 | 1586 | 0 |
| 2 | gc-on | 0.2792 | 2.71 | 293 | 1 |
| 3 | gc-on | 0.2483 | 2.68 | 293 | 1 |
| 3 | gc-off | 0.343 | 3.70 | 1586 | 0 |
| 4 | gc-off | 0.3485 | 3.16 | 1587 | 0 |
| 4 | gc-on | 0.2611 | 2.77 | 293.6 | 1 |
| 5 | gc-on | 0.2607 | 2.70 | 293.2 | 1 |
| 5 | gc-off | 0.3553 | 3.64 | 1586 | 0 |

### complete-intersections

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 0.3486 | 2.74 | 316.7 | 2 |
| 1 | gc-off | 0.5852 | 3.92 | 1793 | 0 |
| 2 | gc-off | 0.5888 | 3.93 | 1794 | 0 |
| 2 | gc-on | 0.3408 | 2.70 | 316.9 | 2 |
| 3 | gc-on | 0.3908 | 2.87 | 317 | 2 |
| 3 | gc-off | 0.5837 | 3.88 | 1794 | 0 |
| 4 | gc-off | 0.5883 | 3.84 | 1793 | 0 |
| 4 | gc-on | 0.3465 | 2.81 | 316.6 | 2 |
| 5 | gc-on | 0.3181 | 2.74 | 316.8 | 2 |
| 5 | gc-off | 0.5858 | 3.83 | 1794 | 0 |

### forms

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 1.575 | 4.03 | 312 | 12 |
| 1 | gc-off | 3.041 | 6.44 | 3607 | 0 |
| 2 | gc-off | 3.025 | 6.36 | 3607 | 0 |
| 2 | gc-on | 1.629 | 4.26 | 311.6 | 12 |
| 3 | gc-on | 1.597 | 4.00 | 311.4 | 12 |
| 3 | gc-off | 3.025 | 6.48 | 3608 | 0 |
| 4 | gc-off | 3.036 | 6.21 | 3608 | 0 |
| 4 | gc-on | 1.614 | 4.06 | 311.6 | 12 |
| 5 | gc-on | 1.586 | 3.99 | 311.7 | 12 |
| 5 | gc-off | 3.046 | 6.51 | 3607 | 0 |

### gb-1

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 0.7312 | 3.14 | 311.6 | 7 |
| 1 | gc-off | 1.42 | 4.67 | 2532 | 0 |
| 2 | gc-off | 1.432 | 4.30 | 2532 | 0 |
| 2 | gc-on | 0.7571 | 3.16 | 311.7 | 7 |
| 3 | gc-on | 0.715 | 3.12 | 311.7 | 7 |
| 3 | gc-off | 1.424 | 4.88 | 2532 | 0 |
| 4 | gc-off | 1.429 | 4.36 | 2532 | 0 |
| 4 | gc-on | 0.7517 | 3.21 | 311.6 | 7 |
| 5 | gc-on | 0.7437 | 3.21 | 311.7 | 7 |
| 5 | gc-off | 1.436 | 4.78 | 2532 | 0 |

### gbZZbug3

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 25.92 | 28.36 | 385.3 | 188 |
| 1 | gc-off | 30.34 | 34.91 | 2.129e+04 | 0 |
| 2 | gc-off | 27.45 | 31.67 | 2.129e+04 | 0 |
| 2 | gc-on | 26.02 | 28.61 | 380.1 | 199 |
| 3 | gc-on | 25.15 | 27.66 | 381.5 | 199 |
| 3 | gc-off | 30.25 | 34.82 | 2.129e+04 | 0 |
| 4 | gc-off | 27.11 | 31.37 | 2.129e+04 | 0 |
| 4 | gc-on | 25.77 | 28.22 | 380 | 198 |
| 5 | gc-on | 25.2 | 27.75 | 380.4 | 199 |
| 5 | gc-off | 30.21 | 34.78 | 2.129e+04 | 0 |

### global

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 6.53 | 8.97 | 192.7 | 97 |
| 1 | gc-off | 8.528 | 12.12 | 4701 | 0 |
| 2 | gc-off | 8.127 | 11.27 | 4701 | 0 |
| 2 | gc-on | 6.377 | 8.85 | 192.7 | 97 |
| 3 | gc-on | 6.369 | 8.77 | 192.5 | 97 |
| 3 | gc-off | 8.493 | 12.05 | 4702 | 0 |
| 4 | gc-off | 8.211 | 11.12 | 4702 | 0 |
| 4 | gc-on | 6.553 | 8.98 | 192.9 | 97 |
| 5 | gc-on | 6.34 | 8.73 | 193 | 97 |
| 5 | gc-off | 8.501 | 12.11 | 4701 | 0 |

### roos2

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 0.6974 | 3.10 | 311.7 | 3 |
| 1 | gc-off | 1.03 | 4.10 | 1914 | 0 |
| 2 | gc-off | 1.035 | 3.88 | 1914 | 0 |
| 2 | gc-on | 0.7098 | 3.16 | 311.4 | 3 |
| 3 | gc-on | 0.7063 | 3.16 | 312.2 | 3 |
| 3 | gc-off | 1.026 | 4.33 | 1914 | 0 |
| 4 | gc-off | 1.028 | 3.92 | 1914 | 0 |
| 4 | gc-on | 0.7127 | 3.14 | 312.1 | 3 |
| 5 | gc-on | 0.7014 | 3.12 | 311.9 | 3 |
| 5 | gc-off | 1.024 | 4.28 | 1913 | 0 |

### sturmfels

| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | gc-on | 1.684 | 4.11 | 311.6 | 6 |
| 1 | gc-off | 2.302 | 5.40 | 2290 | 0 |
| 2 | gc-off | 2.316 | 5.23 | 2290 | 0 |
| 2 | gc-on | 1.756 | 4.20 | 312 | 6 |
| 3 | gc-on | 1.713 | 4.11 | 312 | 6 |
| 3 | gc-off | 2.315 | 5.66 | 2290 | 0 |
| 4 | gc-off | 2.333 | 5.26 | 2290 | 0 |
| 4 | gc-on | 1.825 | 4.28 | 312.4 | 6 |
| 5 | gc-on | 1.751 | 4.19 | 312.1 | 6 |
| 5 | gc-off | 2.34 | 5.67 | 2290 | 0 |

## Additional pilot evidence

Candidates that exceeded the first pilot's memory bound were retried at their original sizes with a 24-GiB address-space limit and a 300-second timeout. [The retry data and logs](benchmark-results/slow-gc-large-pilot/raw-results.json) are retained separately; they do not enter the recorded medians.

| Candidate | Mode | Retry result |
| --- | --- | --- |
| gbZZbug3 | gc-on | Passed; internal wall 24.772 s; peak RSS 0.37 GiB |
| gbZZbug3 | gc-off | Passed; internal wall 32.076 s; peak RSS 20.79 GiB |
| isSubset | gc-on | Passed; internal wall 15.542 s; peak RSS 0.30 GiB |
| isSubset | gc-off | exit 1 (M2 reported out of memory under the address-space limit) |

This pilot session was interrupted after the saved samples above. Its unfinished candidate was rerun in the next pilot session; no unfinished process contributes a measurement.

Candidates that exceeded the first pilot's memory bound were retried at their original sizes with a 24-GiB address-space limit and a 300-second timeout. [The retry data and logs](benchmark-results/slow-gc-plethysms-pilot/raw-results.json) are retained separately; they do not enter the recorded medians.

| Candidate | Mode | Retry result |
| --- | --- | --- |
| plethysms | gc-on | Passed; internal wall 51.741 s; peak RSS 0.30 GiB |
| plethysms | gc-off | exit 1 (M2 reported out of memory under the address-space limit) |

## Benchmark structure and reproduction

The benchmark has four layers:

1. **Workload inputs.** The original slow tests supply the algebra and expected results. `slow-gc/run.py` copies their active portions to the results directory, preserves original parameters, and adds the documented checks for `forms` and `roos2`.
2. **One fresh process per sample.** The Python runner clears inherited GC settings, selects GC on or off, applies the same resource limits, and launches M2 through GNU time. `slow-gc/workload.m2` sets the fixed seed, snapshots GC counters, and starts the internal wall timer around the test input. Original assertions must pass before it emits its result marker.
3. **Measurements and evidence.** M2 reports internal wall time and GC-counter changes. GNU time independently reports whole-process wall/CPU time and peak RSS. The runner checks exit status and markers, verifies that GC-off performed no collections, and saves each sample immediately to JSON with separate stdout/stderr logs.
4. **Summary.** One warm-up per mode is excluded. Five recorded samples per mode are summarized using separate medians for each workload and metric. `slow-gc/report.py` checks sample counts, successful exits, GC-off counters, saved logs, and input hashes before generating this report. It also shows the individual samples and observed ranges.

To reproduce, use Linux/WSL with Python 3, GNU time, and the repository's build dependencies. Keep the checkout in the native Linux filesystem. From the repository root:

```sh
cmake -S M2 -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON
cmake --build build --target build-libraries --parallel 4
cmake --build build --target M2-core --parallel 4
python3 M2/Macaulay2/benchmarks/slow-gc/run.py \
  --output-dir benchmark-results/slow-gc-repeat \
  --repetitions 5 --warmups 1 --timeout 300 --memory-gib 24 \
  --workload 4c \
  --workload complete-intersections \
  --workload forms \
  --workload gb-1 \
  --workload gbZZbug3 \
  --workload global \
  --workload roos2 \
  --workload sturmfels
```

Use a new output directory each time; the runner refuses to overwrite existing measurements. Run samples sequentially and keep the same build and machine for both modes. The optional `--pilot` flag continues after candidate failures for screening; omit it for the recorded comparison, which must abort on failure.

To regenerate the report from the evidence saved for this run:

```sh
python3 M2/Macaulay2/benchmarks/slow-gc/report.py benchmark-results/slow-gc-recorded/raw-results.json \
  --pilot benchmark-results/slow-gc-pilot/raw-results.json \
  --large-pilot benchmark-results/slow-gc-large-pilot/raw-results.json \
  --large-pilot benchmark-results/slow-gc-plethysms-pilot/raw-results.json \
  --output report.md
```

For a new experiment, replace the results path with the new run's JSON and use its corresponding pilot evidence. The harness and report generator are in [M2/Macaulay2/benchmarks/slow-gc](M2/Macaulay2/benchmarks/slow-gc). The complete source identifiers, fixed seed, binary fingerprint, and hardware snapshot are saved with the measurements so the prose can stay readable.
