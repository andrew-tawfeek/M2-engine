# Why GC-off can take longer

This harness profiles the existing Release binary, without changing its build.
It reuses the slow-GC workload inputs and correctness assertions. The matrix
contains unprofiled resource measurements, hardware-counter runs, sampled
CPU profiles, and two interventions. Each process is limited to 24 GiB of
virtual address space and 300 seconds; runs are strictly sequential.

Requirements: Linux/WSL, Python 3, GCC, libgc development headers, GNU time,
`prlimit`, Linux perf, and permission for noninteractive `sudo -n` perf
collection and execution of the child as the normal user. The runner uses the
staged ELF at `build/usr-dist/x86_64-Linux-Debian-/bin/M2-binary`; adjust
`BINARY` in `run.py` if your staging path differs.
On Debian, the profiling packages can be installed with
`sudo apt-get install linux-perf libgc-dev gcc time`.

From the repository root:

```sh
mkdir -p benchmark-results/gc-profile
gcc -O2 -g -shared -fPIC M2/Macaulay2/benchmarks/gc-profile/probe.c \
  -o benchmark-results/gc-profile/probe.so -ldl -lgc
python3 M2/Macaulay2/benchmarks/gc-profile/experiments.py \
  > benchmark-results/gc-profile/experiments.log 2>&1
python3 M2/Macaulay2/benchmarks/gc-profile/report.py
```

Completed samples are reused; failures stop the matrix. To make a wholly new
comparison, archive the existing output directory first. Each saved result has
binary, probe and input fingerprints, exact commands, stdout/stderr, CPU and
fault counters. `perf.data` and readable profile exports are kept for sampled
runs. Samples are tagged by kind, workload, policy and trial number.

The preload library interposes the two `GC_get_prof_stats` calls made by the
unchanged slow-GC wrapper. It records `getrusage` immediately around the test.
For perf runs, an acknowledged FIFO protocol enables counters at the first
snapshot and disables them at the second: startup is outside the profile.
`GC_start_performance_measurement` enables Boehm's optional full-collection
wall-time counter. The existing JSON key `gc_cpu_seconds` is inherited from
the earlier harness; do not treat it as CPU time.

Policies:

* `on`: normal GC from startup through exit.
* `off`: `GC_DONT_GC=1` before startup.
* `late-off`: normal startup, then `GC_disable()` just before the test.
* `reserve`: GC off throughout; before the test, allocate a 3-GiB atomic
  Boehm block, write every byte, then explicitly `GC_free` it for reuse.
  Its setup cost is measured separately and remains in whole-process time.
  This is a diagnostic intervention, not a recommendation to disable GC.

The seed and source parameters remain fixed. There are five resource trials
per mode/workload, five trials per forms intervention, three counter runs
per selected case, and sampled profiles as specified in `experiments.py`.
There is no designated per-case warm-up in this follow-up; preparatory runs
prime file caches. Profiling timings are never pooled with resource timings.
