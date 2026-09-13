# GC comparison using the slow regression tests

Run from the repository root with the existing Release build:

```sh
cmake --build build --target M2-core --parallel 4
python3 M2/Macaulay2/benchmarks/slow-gc/run.py \
  --output-dir benchmark-results/slow-gc-new
```

Requires Linux, Python 3, and GNU `/usr/bin/time`. The default selects the eight candidates that passed the bounded pilots (excluding `isSubset` and `plethysms`). It runs one warm-up
and five measured fresh processes per mode and test. GC-on clears inherited
`GC_*` variables; GC-off additionally sets `GC_DONT_GC=1` before startup.
Both modes use the same seed and a 24-GiB virtual-address-space limit, and
have a 300-second wall timeout. The limit is **not** an RSS measurement.
A failed assertion, missing marker, resource failure, or GC-off collection
aborts the comparison. Results are saved after each process. Existing result
files are never overwritten.

Use `--pilot --warmups 0 --repetitions 1` for candidate screening; pilot mode
records failures and continues, but never turns a failed run into a timing.
Use repeated `--workload NAME` options to choose a subset. Pilot data must not
be combined with the measured trials.

The ten candidates cover every distinct active `.m2` test in
`M2/Macaulay2/tests/slow/`. `gbZZ5.m2` is already deferred by an early `end`;
`gbZZbug3-a.m2` duplicates the membership calculation in `gbZZbug3.m2`.
Test sizes and original assertions are preserved. Only scratch material after
`end` is omitted. `forms` gains checks for the expected generator count and
zero input remainder. `roos2` gains checks that both differentials square to
zero and that the two strategies have matching ranks through degree four.
The `gb-1.aux` input is resolved from the original slow-test directory.

`workload.m2` uses `elapsedTiming input ...`, preserving the tests' use of
`oo` (the previous output). Its timer is elapsed **wall** time inside M2,
including reading, parsing, printing, lazy package loading, computations, and
assertions in the test. It excludes M2 startup and wrapper setup. GNU time's
wall and peak RSS measurements cover the entire process. stdout and stderr
are redirected to individual log files. No artificial repetition loop is
added within a process.

The JSON contains all measured trials, warm-ups, limits, source hashes,
script hashes, the built binary hash, environment settings, and log paths.
Generated scripts are saved alongside it. Timings use the precision printed
by M2 and GNU time; extra decimal places must not be interpreted as accuracy.

`--resume` continues an interrupted run in its existing output directory, checking the build, settings, and saved inputs. Successful samples are retained; an interrupted workload receives additional unrecorded warm-ups. Failed comparisons cannot be resumed as successes. JSON checkpoints are replaced atomically.

Generate the root report with `report.py RESULTS/raw-results.json --pilot PILOT/raw-results.json --output report.md`. Repeat `--large-pilot PATH` to include additional resource-limit screening. The report validates counts and recorded evidence before writing.
