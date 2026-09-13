#!/usr/bin/env python3
"""Validate a completed slow-GC comparison and generate a readable report."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import statistics as st

DESCRIPTIONS = {
    "4c": "Sturmfels counterexample over a finite field and the rationals: codimension, decomposition, singular locus, and resolution. Checks include codimensions 4 and 6, the Hilbert polynomial, and rank 281 at resolution step five.",
    "complete-intersections": "Ext and Poincaré-series calculations over the quotient by (x³, y⁴, z⁵). Compares seven coefficients of the series with independently computed Ext ranks.",
    "forms": "Degree-16 random forms in three variables over the rationals, using the original 76-by-98 construction. Computes a degree-limited Gröbner basis; added checks require 76 generators and zero remainders for the input matrix.",
    "gb-1": "Runs the original gb-1.aux examples with four Gröbner-basis algorithms. Preserves the suite's exact-basis and syzygy assertions.",
    "gbZZbug3": "Integer-polynomial membership regression with p=2 and k=2. Performs both original membership reductions and verifies the explicit polynomial certificate G₀J₀ + G₁J₁ + G₂J₂ = f₀.",
    "global": "Sheaf cohomology on projective spaces and an elliptic curve, plus mixed-support direct sums. Preserves the dimension, degree, and direct-sum assertions.",
    "isSubset": "Large explicit ideals over the integers. Checks ideal containment, reductions, and idempotence of the computed Gröbner basis.",
    "plethysms": "Schubert2 calculation on flagBundle {6,4}: the 21 Euler characteristics of exterior powers and a Chern-number integral. Checks the expected sequence and integral 1.452 × 10⁷.",
    "roos2": "Resolution of the residue field of the original five-variable quotient, with length limits six and five using two strategies. Added checks require both differentials to square to zero and matching ranks through step four.",
    "sturmfels": "The original ten-variable quadratic example over ZZ/7, with an extra homogenizing variable. Computes a Gröbner basis and saturation and checks degree 638.",
}


def hardware_rows(meta):
    cpu = {r["field"].rstrip(":"): r["data"] for r in meta["lscpu"]["lscpu"]}
    rows = [f"| CPU model | {cpu['Model name']} |",
            f"| Visible topology | {cpu['CPU(s)']} logical CPUs; {cpu['Core(s) per socket']} cores; {cpu['Thread(s) per core']} threads per core; {cpu['Socket(s)']} socket |",
            f"| Architecture / virtualization | {cpu['Architecture']}; {cpu.get('Hypervisor vendor', 'unknown')} hypervisor; WSL 2 |"]
    for cache in meta['cpu0_caches']:
        level, kind = cache['level'], cache['type']
        label = 'L' + level + ({'Data':'d', 'Instruction':'i'}.get(kind, '') if level == '1' else '')
        aggregate = cpu.get(label + ' cache', 'not reported')
        kib = int(cache['size'].rstrip('K'))
        size = f"{kib / 1024:g} MiB" if kib >= 1024 else f"{kib:g} KiB"
        rows.append(f"| {label} cache | {size} per instance; {aggregate} visible in total; {cache['ways_of_associativity']}-way associative |")
    rows += [f"| Cache-line size | {meta['cpu0_caches'][0]['coherency_line_size']} bytes |",
             f"| Visible RAM | {float(meta['memory'].split()[0])/1024**2:.1f} GiB |"]
    values = {line.split(':')[0]: int(line.split()[1]) for line in meta['meminfo_before'].splitlines() if line.startswith(('MemAvailable:', 'SwapTotal:', 'SwapFree:'))}
    rows += [f"| Available RAM before the recorded run | {values['MemAvailable']/1024**2:.1f} GiB |",
             f"| WSL swap | {values['SwapTotal']/1024**2:.1f} GiB total; {values['SwapFree']/1024**2:.1f} GiB free before the run |",
             "| Guest OS | " + next(line.split('=',1)[1].strip('\"') for line in meta['os_release'].splitlines() if line.startswith('PRETTY_NAME=')) + " |"]
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path)
    p.add_argument("--pilot", type=Path, required=True)
    p.add_argument("--large-pilot", type=Path, action="append", default=[])
    p.add_argument("--output", type=Path, default=Path("report.md"))
    args = p.parse_args()
    raw = args.results.resolve()
    data = json.loads(raw.read_text())
    pilot = json.loads(args.pilot.read_text())
    meta, rows, names = data["metadata"], data["results"], list(data["workloads"])
    assert meta.get("finished_utc") and not meta["pilot"], "incomplete or pilot data"
    assert len(rows) == len(names) * 2 * meta["repetitions"]
    assert len(data["warmups"]) == len(names) * 2 * meta["warmups_per_mode"]
    for row in rows + data["warmups"] + data.get("resume_warmups", []):
        assert row["status"] == "ok" and row["returncode"] == 0
        if row["mode"] == "gc-off":
            assert row["gc_collections"] == row["process_gc_collections"] == 0
        for field in ["stdout_file", "stderr_file"]:
            assert (raw.parent / row[field]).is_file()
    for name in names:
        script = raw.parent / "scripts" / (name + ".m2")
        assert hashlib.sha256(script.read_bytes()).hexdigest() == data["workloads"][name]["script_sha256"]
        for mode in ["gc-on", "gc-off"]:
            assert sorted(r["trial"] for r in rows if r["workload"] == name and r["mode"] == mode) == list(range(1, meta["repetitions"] + 1))
            assert sorted(r["trial"] for r in data['warmups'] if r["workload"] == name and r["mode"] == mode) == list(range(1, meta["warmups_per_mode"] + 1))
    assert meta['repetitions'] == 5 and meta['warmups_per_mode'] == 1, "this report template describes five trials and one warm-up"
    def subset(name, mode):
        return [r for r in rows if r["workload"] == name and r["mode"] == mode]
    def median(name, mode, field):
        return st.median(r[field] for r in subset(name, mode))
    def pair(name, field):
        return [median(name, m, field) for m in ["gc-on", "gc-off"]]
    def change(on, off):
        return f"{(off/on-1)*100:+.1f}%"
    def link(path):
        return os.path.relpath(path, args.output.resolve().parent)
    totals = {f: [sum(median(n, m, f) for n in names) for m in ["gc-on", "gc-off"]] for f in ["internal_seconds", "process_wall_seconds"]}
    rss_ratio = math.exp(st.mean(math.log(pair(n, "peak_rss_kib")[1] / pair(n, "peak_rss_kib")[0]) for n in names))
    internal_slower = sum(pair(n, 'internal_seconds')[1] > pair(n, 'internal_seconds')[0] for n in names)
    wall_slower = sum(pair(n, 'process_wall_seconds')[1] > pair(n, 'process_wall_seconds')[0] for n in names)
    largest_memory = max(names, key=lambda n: median(n, 'gc-off', 'peak_rss_kib'))
    lines = ["# Garbage collection in Macaulay2: slow-test workloads", "",
        f"Measured {meta['generated_utc'][:10]} on this WSL machine, using the Release build of `{meta['branch']}` at commit `{meta['commit'][:7]}`.", "",
        f"This comparison ran **{len(names)} workloads taken from `M2/Macaulay2/tests/slow/`**, with **five recorded fresh processes per workload per mode**, after one warm-up per mode. All {len(rows)} recorded runs and {len(data['warmups'])} warm-ups passed their checks. These are new slow-test workloads; the previous six package workloads were not rerun.", "",
        f"With garbage collection disabled, the **sum of workload-internal median wall times** changed from **{totals['internal_seconds'][0]:.3f} s to {totals['internal_seconds'][1]:.3f} s ({change(*totals['internal_seconds'])})**. The **sum of whole-process median wall times** changed from **{totals['process_wall_seconds'][0]:.2f} s to {totals['process_wall_seconds'][1]:.2f} s ({change(*totals['process_wall_seconds'])})**. The geometric mean of the per-workload peak-memory ratios was **{rss_ratio:.2f}×** with GC off. These aggregates describe this selection on this machine, not a general speed prediction.", "",
        f"GC off had a higher internal-time median in **{internal_slower} of {len(names)} workloads** and a higher whole-process-time median in **{wall_slower} of {len(names)}**. Its largest median peak memory was **{median(largest_memory, 'gc-off', 'peak_rss_kib')/1024**2:.1f} GiB**, in `{largest_memory}`. Each workload contributes one median to the timing sums; the five repetitions and warm-ups are not added together.", "",
        "## What the measurements mean", "",
        "| Term | Meaning and scope |", "| --- | --- |",
        "| GC on | Normal automatic Boehm garbage collection. Unreachable managed allocations can be reclaimed. All inherited `GC_*` environment variables are removed. |",
        "| GC off | The same executable and environment, with `GC_DONT_GC=1` set before M2 starts. Unreachable GC-managed allocations are retained until the process exits. This does not disable every allocator or every explicit free in external libraries. |",
        "| Internal wall time, seconds | A stopwatch **inside Macaulay2**, using `elapsedTiming input testFile`. It measures real elapsed time while reading, parsing, evaluating, and printing the active test, including its assertions and any package loading it triggers. It excludes M2 startup, the random-seed setup, and final benchmark output. **It is not CPU time.** |",
        "| Whole-process wall time, seconds | GNU `/usr/bin/time` measures elapsed time from launching M2 to its exit. This includes startup, initialization, the entire test, and shutdown. It is the closer measure of how long a user waits for a fresh command. |",
        "| Peak RSS, MiB | **RSS means resident set size**: memory resident in physical RAM for the process. Peak RSS is the highest such value during the whole process, including startup. It includes managed heap, other allocations, stacks, and resident code/library pages. It is neither total allocated bytes nor the amount of live mathematical data. |",
        "| MiB and GiB | Binary units: 1 MiB = 2²⁰ bytes (about 1.049 × 10⁶ bytes); 1 GiB = 1,024 MiB. GNU time reports RSS in KiB on Linux; this report divides by 1,024 to obtain MiB. |",
        "| Median | The middle of five measurements, computed separately for each metric. It reduces the influence of an unusually fast or slow run. The median internal time, wall time, and RSS need not come from the same trial. |",
        "| Change / ratio | Change is `(GC off / GC on − 1) × 100%`; positive means more time or memory with GC off. A memory ratio of 2× means twice the peak memory, not 2% more. |", "",
        "The geometric-mean memory ratio is an average of multiplication factors: multiply the per-workload off/on ratios and take the root corresponding to the number of workloads. Each workload has equal weight in this measure.", "",
        "The internal and whole-process timers overlap: **do not add them**. Startup is deliberately included only in the whole-process measure. The internal timer here differs from the previous package suite: lazy package loading and test-output formatting are inside it. Output is captured through pipes and saved to files, rather than displayed in a terminal.", "",
        "Some original tests also print their own `time` diagnostics in the logs. Those CPU/thread/GC messages are not the timing values used in these tables; the tables use the wrapper's `elapsedTiming` result and GNU time's process measurements.", "",
        "## Timing results", "", "Every value below is a median of five runs. Both timing columns measure elapsed wall time, but over different boundaries.", "",
        "| Workload | Internal GC on (s) | Internal GC off (s) | Internal change | Whole process GC on (s) | Whole process GC off (s) | Whole-process change |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for n in names:
        a, b = pair(n, "internal_seconds")
        c, d = pair(n, "process_wall_seconds")
        lines.append(f"| {n} | {a:.3f} | {b:.3f} | {change(a,b)} | {c:.2f} | {d:.2f} | {change(c,d)} |")
    lines += ["", "## Memory and collection results", "",
        "The memory figures are **medians of five process-wide peaks**. Large values use scientific notation: for example, `2.129e+04 MiB` means 2.129 × 10⁴ MiB (about 20.8 GiB). Collection-counter snapshots bracket the timed test input; a separate lifetime counter also confirmed **zero collections from startup through test completion in every GC-off run**, including warm-ups.", "",
        "| Workload | Peak RSS GC on (MiB) | Peak RSS GC off (MiB) | Off/on memory ratio | Timed collections GC on (median) | Timed collections GC off (median) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for n in names:
        a, b = pair(n, "peak_rss_kib")
        c, d = pair(n, "gc_collections")
        lines.append(f"| {n} | {a/1024:.4g} | {b/1024:.4g} | {b/a:.2f}× | {c:g} | {d:g} |")
    lines += ["", "Turning off collection also retains allocations made during startup. Thus a short test can have a large whole-process memory ratio even if it does relatively little work after initialization. This experiment does not separately measure startup-only memory, so these peaks should not be attributed entirely to the algebra calculation.", "",
        "## Which slow tests were used", "",
        "The input sizes and original assertions were preserved. Each fresh process executes its workload once; no artificial inner repetition loop was added. All tests start with the same fixed random seed (saved in the JSON).", "",
        "| Workload and source | Work performed and correctness checks |", "| --- | --- |"]
    for n in names:
        source = data["workloads"][n]["source"]
        lines.append(f"| [{n}]({source}) | {DESCRIPTIONS[n]} |")
    lines += ["", "The generated inputs preserve the original `input` behavior, including assertions that refer to `oo`, the previous result. Material after an explicit `end` is historical scratch work and is omitted. `forms` and `roos2` gain the checks described above because their originals mainly run computations without asserting the results. No original test file was edited.", "",
        "### Coverage and exclusions", "",
        "There are twelve `.m2` files in the slow-test directory. Ten distinct active candidates were piloted. `gbZZ5.m2` is already deferred by an `end` before its calculation. `gbZZbug3-a.m2` repeats the core membership calculation of `gbZZbug3.m2`; the latter also verifies an explicit certificate, so the duplicate was not separately benchmarked. `gb-1.aux` is supporting input and is exercised by `gb-1`.", ""]
    excluded = [n for n in pilot["workloads"] if n not in names]
    if excluded:
        lines += ["The following candidates were not included in the timing comparison. Failed or resource-limited runs are **not successful timings** and do not enter any summary:", "", "| Candidate | Pilot outcome |", "| --- | --- |"]
        for n in excluded:
            outcomes = []
            for r in pilot['results']:
                if r['workload'] != n:
                    continue
                outcome = r.get('error', 'passed')
                if r['status'] != 'ok' and 'out of memory' in (args.pilot.parent / r['stderr_file']).read_text():
                    outcome = "out of memory under the 6-GiB address-space limit"
                outcomes.append(f"{r['mode']}: {outcome}")
            lines.append(f"| {n} | {'; '.join(outcomes)} |")
        if args.large_pilot:
            lines += ["", "Both excluded candidates also reported out of memory with GC off when retried at a 24-GiB address-space limit. They remain excluded at their original sizes. The separate retry evidence appears below. The integer regression `gbZZbug3` passed at the larger limit and is included. All recorded workloads used the same 24-GiB limit in both modes."]
    else:
        lines += ["All ten candidates completed in both modes during screening and are included in the recorded comparison."]
    lines += ["", f"[Pilot results]({link(args.pilot.resolve())}) are separate from the recorded measurements. The pilot used a {pilot['metadata']['timeout_seconds']}-second wall timeout per process and a {pilot['metadata']['memory_limit_gib']}-GiB virtual-address-space limit.", "",
        "## Repeatability and limits of the conclusions", "",
        "Five samples are enough to show the observed spread, but do not establish a universal performance result or statistical significance. These are fixed-seed regression inputs, not a survey of all user computations. The sums of medians are a descriptive aggregate, not the measured duration of a single suite run; slower tests have more weight. The geometric-mean memory ratio gives each selected workload equal weight and is not a total RAM requirement.", "",
        "The following ranges show the fastest and slowest recorded runs, alongside the median used above. Ranges are observed variation, not confidence intervals.", "",
        "| Workload | Mode | Internal min / median / max (s) | Whole-process min / median / max (s) | Peak RSS min / median / max (MiB) |", "| --- | --- | ---: | ---: | ---: |"]
    for n in names:
        for mode in ["gc-on", "gc-off"]:
            cells = []
            for f, scale, digits in [("internal_seconds", 1, 3), ("process_wall_seconds", 1, 2), ("peak_rss_kib", 1024, 1)]:
                v = [r[f]/scale for r in subset(n, mode)]
                cells.append(" / ".join((f"{x:.4g}" if f == "peak_rss_kib" else f"{x:.{digits}f}") for x in [min(v), st.median(v), max(v)]))
            lines.append(f"| {n} | {mode} | " + " | ".join(cells) + " |")
    lines += ["", "## How the comparison was run", "",
        f"- Same native WSL checkout and Release executable for both modes. `cmake --build build --target M2-core --parallel 4` completed successfully before the pilot. Measurements ran sequentially, with no overlapping benchmark processes.",
        "- One fresh-process warm-up per mode per workload, excluded from statistics but retained in the data. Warm-ups may prime operating-system file caches; they do not reuse the measured process's heap.",
        "- Five measured fresh processes per mode per workload. Order alternates: on/off for trials 1, 3, and 5; off/on for trials 2 and 4. This reduces but does not eliminate ordering or background-load effects.",
        "- Fixed `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and `LC_ALL=C`. This is not a claim that all M2 or GC activity is single-threaded. No CPU affinity was imposed, and other host/WSL activity was not controlled.",
        f"- Each process has a {meta['timeout_seconds']}-second wall timeout and a {meta['memory_limit_gib']}-GiB virtual-address-space limit (`RLIMIT_AS`). The latter bounds address space, not just resident RAM; it is not the RSS column. Core dumps are disabled. A timeout kills the process group. A failed check, nonzero exit, missing result, or unexpected collection in GC-off aborts the recorded comparison.",
        "- GNU time's wall/user/system fields have hundredth-of-a-second output granularity. The internal timing is stored at M2's printed precision. Rounded report figures should not be treated as exact or as evidence of sub-millisecond reproducibility.", "",
        "### Other fields in the raw data", "",
        "`process_user_seconds` is CPU time spent executing user-space code; `process_system_seconds` is CPU time spent in the kernel. These are whole-process CPU usage, not stopwatch duration, and can differ from wall time, especially with multiple threads. `bytes_allocated` is the increase in Boehm's cumulative allocated-byte counter around the timed test: allocation traffic, not live memory. `heap_bytes` is Boehm's mapped heap size after the test, not process RSS.", "",
        "The inherited raw field `gc_cpu_seconds` comes from M2's `GCstats()` key `gcCpuTimeSecs`. Its implementation calls Boehm's full-collection timing counter. Do not interpret a zero as proof that GC took no time: this counter requires performance measurement support/activation and may be unavailable or inactive. It is not used to explain the timing differences in this report. Collection counts provide the verification that GC was disabled.", "",
        "Timing boundaries and counters were checked against the repository implementations in [chrono.dd](M2/Macaulay2/d/chrono.dd), [actors5.d](M2/Macaulay2/d/actors5.d), and [Boehm's API declarations](M2/submodules/bdwgc/include/gc.h).", "",
        "## System hardware and cache layout", "",
        "These are the resources reported inside WSL, measured with `lscpu`, Linux cache sysfs entries, and `/proc/meminfo`. They describe the guest's view; they should not be read as a complete inventory of the Windows host.", "",
        "| Property | Observed configuration |", "| --- | --- |",
        *hardware_rows(meta), "",
        "L1 is the smallest, closest cache: L1d holds data and L1i holds instructions. L2 is larger and shared by the two logical threads of a visible core. L3 is the larger last-level cache shared across the visible cores. Cache capacity can affect algebra workloads that repeatedly access allocated data, but this experiment did not measure cache hits, cache misses, bandwidth, or clock frequency under load. The memory and timing differences alone cannot identify a cache-related cause.", "",
        "The processor's model name describes an eight-core CPU, while WSL exposes seven cores and fourteen logical CPUs. The cache totals above are the WSL-visible inventory, not evidence that the physical host has only seven cores. Host RAM, DRAM speed/timings, and power settings were not independently measured.", "",
        "## Environment and saved evidence", "",
        f"- Run window: {dt.datetime.fromisoformat(meta['generated_utc']).strftime('%b %d, %Y, %H:%M UTC')} to {dt.datetime.fromisoformat(meta['finished_utc']).strftime('%H:%M UTC')}.",
        f"- Macaulay2 version: `{meta['m2_version'].split('-')[0]}`; build type: `{meta['build_type']}`. The complete embedded version string is in the JSON.",
        f"- CPU: {meta['cpu']}; {meta['logical_cpus']} logical CPUs visible to WSL.",
        f"- Platform: `{meta['platform']}`; kernel: `{meta['kernel']}`.",
        f"- Memory visible to WSL: {float(meta['memory'].split()[0])/1024**2:.1f} GiB.",
        f"- Base source commit: `{meta['commit'][:7]}`. The new benchmark harness was an uncommitted addition during this run; the exact status and hashes are recorded in the JSON.",
        "- Full binary and source fingerprints are saved in the JSON rather than printed as long identifiers here.", "",
        f"[Recorded data and warm-ups]({link(raw)}) contain every measurement, command, controlled environment, exit status, and source/script hash. [Captured inputs]({link(raw.parent / 'scripts')}) and [stdout/stderr logs]({link(raw.parent / 'logs')}) allow inspection of the actual tests and assertions. The results directory is local and ignored by Git; retain it with this report when sharing or archiving the experiment.", "",
        "## Individual recorded trials", "",
        "Warm-ups are in the JSON only. Internal time is rounded to four significant figures here; the JSON retains the stored values. Scientific notation uses e for a power of ten (for example, 1.234e+04 means 1.234 × 10⁴).", ""]
    for n in names:
        lines += [f"### {n}", "", "| Trial | Mode | Internal wall (s) | Whole-process wall (s) | Peak RSS (MiB) | Timed collections |", "| ---: | --- | ---: | ---: | ---: | ---: |"]
        for r in [r for r in rows if r["workload"] == n]:
            lines.append(f"| {r['trial']} | {r['mode']} | {r['internal_seconds']:.4g} | {r['process_wall_seconds']:.2f} | {r['peak_rss_kib']/1024:.4g} | {r['gc_collections']} |")
        lines.append("")
    if args.large_pilot:
        lines += ["## Additional pilot evidence", ""]
    for large_path in args.large_pilot:
        large = json.loads(large_path.read_text())
        lines += [
            f"Candidates that exceeded the first pilot's memory bound were retried at their original sizes with a {large['metadata']['memory_limit_gib']}-GiB address-space limit and a {large['metadata']['timeout_seconds']}-second timeout. [The retry data and logs]({link(large_path.resolve())}) are retained separately; they do not enter the recorded medians.", "",
            "| Candidate | Mode | Retry result |", "| --- | --- | --- |"]
        for r in large['results']:
            outcome = (f"Passed; internal wall {r['internal_seconds']:.3f} s; peak RSS {r['peak_rss_kib']/1024**2:.2f} GiB"
                       if r['status'] == 'ok' else r['error'])
            if r['status'] != 'ok':
                stderr = (large_path.parent / r['stderr_file']).read_text()
                if 'out of memory' in stderr:
                    outcome += " (M2 reported out of memory under the address-space limit)"
            lines.append(f"| {r['workload']} | {r['mode']} | {outcome} |")
        lines.append("")
        if not large['metadata'].get('finished_utc'):
            lines += ["This pilot session was interrupted after the saved samples above. Its unfinished candidate was rerun in the next pilot session; no unfinished process contributes a measurement.", ""]
    lines += ["## Benchmark structure and reproduction", "",
        "The benchmark has four layers:", "",
        "1. **Workload inputs.** The original slow tests supply the algebra and expected results. `slow-gc/run.py` copies their active portions to the results directory, preserves original parameters, and adds the documented checks for `forms` and `roos2`.",
        "2. **One fresh process per sample.** The Python runner clears inherited GC settings, selects GC on or off, applies the same resource limits, and launches M2 through GNU time. `slow-gc/workload.m2` sets the fixed seed, snapshots GC counters, and starts the internal wall timer around the test input. Original assertions must pass before it emits its result marker.",
        "3. **Measurements and evidence.** M2 reports internal wall time and GC-counter changes. GNU time independently reports whole-process wall/CPU time and peak RSS. The runner checks exit status and markers, verifies that GC-off performed no collections, and saves each sample immediately to JSON with separate stdout/stderr logs.",
        "4. **Summary.** One warm-up per mode is excluded. Five recorded samples per mode are summarized using separate medians for each workload and metric. `slow-gc/report.py` checks sample counts, successful exits, GC-off counters, saved logs, and input hashes before generating this report. It also shows the individual samples and observed ranges.", "",
        "To reproduce, use Linux/WSL with Python 3, GNU time, and the repository's build dependencies. Keep the checkout in the native Linux filesystem. From the repository root:", "", "```sh",
        "cmake -S M2 -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON",
        "cmake --build build --target build-libraries --parallel 4",
        "cmake --build build --target M2-core --parallel 4",
        "python3 M2/Macaulay2/benchmarks/slow-gc/run.py \\",
        "  --output-dir benchmark-results/slow-gc-repeat \\",
        f"  --repetitions 5 --warmups 1 --timeout {meta['timeout_seconds']} --memory-gib {meta['memory_limit_gib']} \\",
        "  " + " \\\n  ".join(f"--workload {n}" for n in names),
        "```", "",
        "Use a new output directory each time; the runner refuses to overwrite existing measurements. Run samples sequentially and keep the same build and machine for both modes. The optional `--pilot` flag continues after candidate failures for screening; omit it for the recorded comparison, which must abort on failure.", "",
        "To regenerate the report from the evidence saved for this run:", "", "```sh",
        f"python3 M2/Macaulay2/benchmarks/slow-gc/report.py {link(raw)} \\",
        f"  --pilot {link(args.pilot.resolve())} \\"]
    for large_path in args.large_pilot:
        lines += [f"  --large-pilot {link(large_path.resolve())} \\"]
    lines += ["  --output report.md", "```", "",
        "For a new experiment, replace the results path with the new run's JSON and use its corresponding pilot evidence. The harness and report generator are in [M2/Macaulay2/benchmarks/slow-gc](M2/Macaulay2/benchmarks/slow-gc). The complete source identifiers, fixed seed, binary fingerprint, and hardware snapshot are saved with the measurements so the prose can stay readable.", ""]
    if data.get("resume_sessions"):
        lines += [f"The recorded run resumed after {len(data['resume_sessions'])} interruption(s). Completed samples were retained, and {len(data.get('resume_warmups', []))} additional warm-ups were excluded from the summaries. Resume hardware snapshots are in the JSON.", ""]
    args.output.write_text("\n".join(lines))
    print(f"Validated {len(rows)} trials and {len(data['warmups'])} warm-ups; wrote {args.output}")

if __name__ == "__main__":
    main()
