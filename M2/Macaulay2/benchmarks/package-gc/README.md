# Package GC benchmarks

This suite runs deterministic workloads derived from examples in six
distributed Macaulay2 packages. It compares normal Boehm garbage collection
with a fresh M2 process started under `GC_DONT_GC=1`.

The package workloads are written in the M2 language rather than added to the
C++ `M2-benchmarks` executable. Package loading requires the interpreter, and
the collector mode must be set before that interpreter initializes.

From the repository root, build and run the default five-trial comparison:

```sh
cmake --build build --target M2-core --parallel 4
python3 M2/Macaulay2/benchmarks/package-gc/run.py --m2 build/M2
```

Alternatively, after configuring with `BUILD_BENCHMARKS=ON`, use the CMake
convenience target:

```sh
cmake --build build --target M2-package-gc-benchmarks
```

Results are written to `benchmark-results/package-gc/report.md` and
`raw-results.json`. Use `--output-dir`, `--repetitions`, `--warmups`, or
repeatable `--workload NAME` arguments to customize a run. `python3 run.py
--help` lists the workload names.

GNU `time` is required for process CPU and peak-RSS measurements (`sudo apt
install time` on Debian/Ubuntu).

Disabling collection can consume several gigabytes even for these bounded
workloads. Every trial therefore runs in a fresh process with a timeout. Do not
use `GC_DONT_GC=1` for unbounded or production computations.
