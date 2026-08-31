#!/usr/bin/env python3
"""Run package workloads with normal GC and GC_DONT_GC=1."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import platform
import re
import shutil
import signal
import statistics
import subprocess
import tempfile
from pathlib import Path


WORKLOADS = {
    "graphs-edge-resolution": {
        "package": "Graphs",
        "iterations": 1,
        "description": "Resolve the edge ideal of the complete graph K_12.",
        "source": "M2/Macaulay2/packages/Graphs.m2 (completeGraph and edgeIdeal examples)",
    },
    "hyperplane-orlik-terao": {
        "package": "HyperplaneArrangements",
        "iterations": 120,
        "description": "Construct the braid arrangement and resolve its Orlik-Terao ideal.",
        "source": "M2/Macaulay2/packages/HyperplaneArrangements.m2 (orlikTerao braid example)",
    },
    "primary-decomposition": {
        "package": "PrimaryDecomposition",
        "iterations": 150,
        "description": "Decompose the documented five-component monomial ideal.",
        "source": "M2/Macaulay2/packages/PrimaryDecomposition/examples.m2 (starter example)",
    },
    "schubert-lines": {
        "package": "Schubert2",
        "iterations": 120,
        "description": "Compute the 2,875 lines on a quintic threefold.",
        "source": "M2/Macaulay2/packages/Schubert2/demo.m2 (lines on a quintic example)",
    },
    "simplicial-dual-resolution": {
        "package": "SimplicialComplexes",
        "iterations": 120,
        "description": "Resolve a complex and its Alexander dual and verify duality.",
        "source": "M2/Macaulay2/packages/SimplicialComplexes/Documentation.m2 (Bayer-Charalambous-Popescu example)",
    },
    "boij-soederberg": {
        "package": "BoijSoederberg",
        "iterations": 80,
        "description": "Resolve a complete intersection and eliminate its Betti table.",
        "source": "M2/Macaulay2/packages/BoijSoederberg.m2 (eliminateBetti test example)",
    },
}

MODES = {
    "gc-on": "normal Boehm GC configuration (GC_DONT_GC unset)",
    "gc-off": "Boehm GC disabled (GC_DONT_GC=1)",
}
MARKER = "M2_PACKAGE_BENCHMARK|"


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    repo = script.parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m2", type=Path, default=repo / "build" / "M2")
    parser.add_argument("--output-dir", type=Path,
                        default=repo / "benchmark-results" / "package-gc")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300,
                        help="per-process timeout in seconds")
    parser.add_argument("--workload", action="append", choices=WORKLOADS,
                        help="run only this workload; repeat the option to select several")
    args = parser.parse_args()
    if args.repetitions < 1 or args.warmups < 0 or args.timeout < 1:
        parser.error("repetitions and timeout must be positive; warmups must be nonnegative")
    return args


def run_text(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    return result.stdout.strip()


def read_cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        match = re.search(r"^model name\s*:\s*(.+)$", cpuinfo.read_text(), re.MULTILINE)
        if match:
            return match.group(1)
    return platform.processor() or "unknown"


def read_memory() -> str:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        match = re.search(r"^MemTotal:\s*(.+)$", meminfo.read_text(), re.MULTILINE)
        if match:
            return match.group(1)
    return "unknown"


def read_build_type(repo: Path) -> str:
    cache = repo / "build" / "CMakeCache.txt"
    if cache.exists():
        match = re.search(r"^CMAKE_BUILD_TYPE:STRING=(.*)$", cache.read_text(), re.MULTILINE)
        if match:
            return match.group(1) or "unspecified"
    return "unknown"


def metadata(repo: Path, m2: Path, args: argparse.Namespace) -> dict:
    status = run_text(["git", "status", "--short"], repo)
    return {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": str(repo),
        "branch": run_text(["git", "branch", "--show-current"], repo),
        "commit": run_text(["git", "rev-parse", "HEAD"], repo),
        "git_description": run_text(["git", "describe", "--always", "--dirty"], repo),
        "working_tree_clean": not bool(status),
        "working_tree_status": status,
        "m2": str(m2),
        "m2_version": run_text([str(m2), "--version"], repo),
        "build_type": read_build_type(repo),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "cpu": read_cpu_model(),
        "logical_cpus": os.cpu_count(),
        "memory": read_memory(),
        "repetitions": args.repetitions,
        "warmups_per_mode": args.warmups,
        "timeout_seconds": args.timeout,
        "controlled_environment": {
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "LC_ALL": "C",
        },
    }


def parse_m2_result(stdout: str, expected_name: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise RuntimeError(f"expected one {MARKER!r} line, found {len(lines)}\n{stdout}")
    parts = lines[0].split("|")
    if len(parts) != 7 or parts[1] != expected_name:
        raise RuntimeError(f"malformed workload result: {lines[0]}")
    return {
        "internal_seconds": float(parts[2]),
        "gc_collections": int(parts[3]),
        "bytes_allocated": int(parts[4]),
        "heap_bytes": int(parts[5]),
        "gc_cpu_seconds": float(parts[6]),
    }


def run_sample(repo: Path, m2: Path, workload_script: Path, time_binary: str,
               workload: str, mode: str, trial: int, timeout: int,
               warmup: bool = False) -> dict:
    spec = WORKLOADS[workload]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GC_"):
            del env[key]
    env.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "LC_ALL": "C"})
    if mode == "gc-off":
        env["GC_DONT_GC"] = "1"

    time_file = tempfile.NamedTemporaryFile(prefix="m2-package-gc-", delete=False)
    time_path = Path(time_file.name)
    time_file.close()
    command = [
        time_binary, "-q", "-f", "%e\t%U\t%S\t%M\t%x", "-o", str(time_path), "--",
        str(m2), "--script", str(workload_script), workload, str(spec["iterations"]),
    ]
    process = subprocess.Popen(command, cwd=repo, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        time_path.unlink(missing_ok=True)
        raise RuntimeError(f"{workload} ({mode}) exceeded {timeout}s\n{stdout}\n{stderr}")

    resource_line = time_path.read_text().strip() if time_path.exists() else ""
    time_path.unlink(missing_ok=True)
    if process.returncode != 0:
        raise RuntimeError(
            f"{workload} ({mode}) exited {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}")
    fields = resource_line.split("\t")
    if len(fields) != 5 or fields[4] != "0":
        raise RuntimeError(f"malformed resource data for {workload} ({mode}): {resource_line!r}")

    result = parse_m2_result(stdout, workload)
    result.update({
        "workload": workload,
        "package": spec["package"],
        "mode": mode,
        "trial": trial,
        "warmup": warmup,
        "inner_iterations": spec["iterations"],
        "process_wall_seconds": float(fields[0]),
        "process_user_seconds": float(fields[1]),
        "process_system_seconds": float(fields[2]),
        "peak_rss_kb": int(fields[3]),
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "command": command,
        "environment": {
            "GC_DONT_GC": env.get("GC_DONT_GC", "<unset>"),
            "OPENBLAS_NUM_THREADS": env["OPENBLAS_NUM_THREADS"],
            "OMP_NUM_THREADS": env["OMP_NUM_THREADS"],
            "LC_ALL": env["LC_ALL"],
        },
    })
    return result


def median(results: list[dict], key: str) -> float:
    return statistics.median(item[key] for item in results)


def percent_delta(on_value: float, off_value: float) -> float:
    return (off_value / on_value - 1.0) * 100.0


def signed_percent(value: float) -> str:
    return f"{value:+.1f}%"


def mib(kib: float) -> float:
    return kib / 1024.0


def markdown_report(data: dict, selected: list[str]) -> str:
    meta = data["metadata"]
    results = data["results"]
    lines = [
        "# Macaulay2 garbage collector benchmark comparison",
        "",
        f"Generated: `{meta['generated_utc']}`  ",
        f"Branch/commit: `{meta['branch']}` / `{meta['git_description']}`  ",
        f"Macaulay2: `{meta['m2_version']}`  ",
        f"Build type: `{meta['build_type']}`",
        "",
        "## Result summary",
        "",
        "Positive deltas mean `GC_DONT_GC=1` took more time or memory. Internal time is the primary timing metric; package loading is outside that timer.",
        "",
        "| Workload | Inner runs | GC on median (s) | GC off median (s) | Time delta | GC on peak RSS (MiB) | GC off peak RSS (MiB) | RSS delta | GC on collections | GC off collections |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    total_on = 0.0
    total_off = 0.0
    rss_ratios = []
    for name in selected:
        on = [r for r in results if r["workload"] == name and r["mode"] == "gc-on"]
        off = [r for r in results if r["workload"] == name and r["mode"] == "gc-off"]
        on_time = median(on, "internal_seconds")
        off_time = median(off, "internal_seconds")
        on_rss = median(on, "peak_rss_kb")
        off_rss = median(off, "peak_rss_kb")
        total_on += on_time
        total_off += off_time
        rss_ratios.append(off_rss / on_rss)
        lines.append(
            f"| `{name}` | {WORKLOADS[name]['iterations']} | {on_time:.6f} | {off_time:.6f} | "
            f"{signed_percent(percent_delta(on_time, off_time))} | {mib(on_rss):.1f} | "
            f"{mib(off_rss):.1f} | {signed_percent(percent_delta(on_rss, off_rss))} | "
            f"{median(on, 'gc_collections'):.0f} | {median(off, 'gc_collections'):.0f} |")

    geometric_rss_ratio = math.exp(statistics.mean(math.log(value) for value in rss_ratios))
    lines += [
        "",
        f"Across the {len(selected)} selected workload median{'s' if len(selected) != 1 else ''}:",
        "",
        f"- Sum of internal medians: `{total_on:.6f} s` with GC on versus `{total_off:.6f} s` with GC off ({signed_percent(percent_delta(total_on, total_off))}).",
        f"- Geometric mean peak-RSS ratio: `{geometric_rss_ratio:.2f}x` for GC off versus GC on.",
        "- These are descriptive measurements from this WSL machine, not a universal performance claim.",
        "",
        "## Workloads",
        "",
        "| Workload | Package | Derivation | Timed operation |",
        "| --- | --- | --- | --- |",
    ]
    for name in selected:
        spec = WORKLOADS[name]
        lines.append(f"| `{name}` | `{spec['package']}` | {spec['source']} | {spec['description']} |")

    lines += [
        "",
        "Each workload contains correctness assertions. A failed assertion aborts the runner instead of recording a timing.",
        "",
        "## Exact trial data",
    ]
    for name in selected:
        lines += [
            "",
            f"### `{name}`",
            "",
            "| Trial | Mode | Internal (s) | Process wall (s) | User (s) | System (s) | Peak RSS (KiB) | Collections | Bytes allocated | Final heap (bytes) | GC CPU (s) |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        rows = [r for r in results if r["workload"] == name]
        rows.sort(key=lambda r: (r["trial"], r["mode"]))
        for row in rows:
            lines.append(
                f"| {row['trial']} | `{row['mode']}` | {row['internal_seconds']:.9f} | "
                f"{row['process_wall_seconds']:.2f} | {row['process_user_seconds']:.2f} | "
                f"{row['process_system_seconds']:.2f} | {row['peak_rss_kb']} | "
                f"{row['gc_collections']} | {row['bytes_allocated']} | {row['heap_bytes']} | "
                f"{row['gc_cpu_seconds']:.6f} |")

    lines += [
        "",
        "## Methodology",
        "",
        f"- `{meta['repetitions']}` recorded fresh-process trials per workload and mode, after `{meta['warmups_per_mode']}` unrecorded warm-up per mode.",
        "- Modes alternate order on successive trials to reduce ordering bias.",
        "- GC-on removes inherited `GC_*` variables. GC-off does the same and then sets `GC_DONT_GC=1` before process initialization.",
        "- `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and `LC_ALL=C` are fixed for every process.",
        "- Internal elapsed time and GC counters cover only the workload loop after package loading. GNU `time` process metrics include M2 startup, package loading, and the workload.",
        "- Peak RSS is process-wide. Disabling collection intentionally retains unreachable allocations, so it is expected to increase memory and may cause larger workloads to exhaust memory.",
        "",
        "## Environment",
        "",
        f"- Platform: `{meta['platform']}`",
        f"- Kernel: `{meta['kernel']}`",
        f"- CPU: `{meta['cpu']}` ({meta['logical_cpus']} logical CPUs)",
        f"- WSL-visible memory: `{meta['memory']}`",
        f"- Source tree clean at capture: `{meta['working_tree_clean']}`",
        "",
        "The adjacent `raw-results.json` file contains full-precision structured data, commands, stdout, stderr, and source-tree status.",
        "",
    ]
    return "\n".join(lines)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main() -> int:
    args = parse_args()
    script = Path(__file__).resolve()
    repo = script.parents[4]
    m2 = args.m2.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    workload_script = script.with_name("workloads.m2")
    selected = args.workload or list(WORKLOADS)
    time_binary = shutil.which("time")
    if not m2.is_file():
        raise SystemExit(f"M2 executable not found: {m2}")
    if not workload_script.is_file():
        raise SystemExit(f"workload script not found: {workload_script}")
    if not time_binary or Path(time_binary).name != "time":
        raise SystemExit("GNU time is required (Debian/Ubuntu: sudo apt install time)")

    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "metadata": metadata(repo, m2, args),
        "modes": MODES,
        "workloads": {name: WORKLOADS[name] for name in selected},
        "results": [],
    }
    raw_path = output_dir / "raw-results.json"
    report_path = output_dir / "report.md"

    for workload in selected:
        for mode in MODES:
            for warmup in range(1, args.warmups + 1):
                print(f"warm-up {warmup}/{args.warmups}: {workload} [{mode}]", flush=True)
                run_sample(repo, m2, workload_script, time_binary, workload, mode, 0,
                           args.timeout, warmup=True)
        for trial in range(1, args.repetitions + 1):
            order = list(MODES) if trial % 2 else list(reversed(MODES))
            for mode in order:
                print(f"trial {trial}/{args.repetitions}: {workload} [{mode}]", flush=True)
                result = run_sample(repo, m2, workload_script, time_binary, workload,
                                    mode, trial, args.timeout)
                data["results"].append(result)
                write_json(raw_path, data)

    write_json(raw_path, data)
    report_path.write_text(markdown_report(data, selected))
    print(f"raw results: {raw_path}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
