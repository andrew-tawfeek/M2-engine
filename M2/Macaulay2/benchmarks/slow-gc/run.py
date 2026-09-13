#!/usr/bin/env python3
"""Bounded GC comparison of the active slow regression tests, at original sizes."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import sys
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = REPO / "M2/Macaulay2/tests/slow"
spec = importlib.util.spec_from_file_location("package_gc", HERE.parent / "package-gc/run.py")
common = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(common)
NAMES = ["4c", "complete-intersections", "forms", "gb-1", "gbZZbug3", "global", "isSubset", "plethysms", "roos2", "sturmfels"]

DEFAULT_WORKLOADS = [n for n in NAMES if n not in {"isSubset", "plethysms"}]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    temporary = path.with_suffix(".json.tmp")
    common.write_json(temporary, data)
    temporary.replace(path)


def prepare(name, output):
    # Preserve input/oo semantics and original parameters. Remove only material
    # after an explicit end: historical scratch work, not the active test.
    text = (SOURCE / (name + ".m2")).read_text()
    import re
    text = re.split(r"(?m)^end\b.*$", text, maxsplit=1)[0]
    if name == "forms":
        text += '\nassert(numColumns gens G == r);\nassert(f % G == 0);\n'
    if name == "roos2":
        # Check both algorithms' overlapping Betti numbers and chain condition.
        text = text.replace('betti C', 'slowGCFirstC = C;\nbetti C', 1)
        text += '\nassert(C.dd^2 == 0);\nassert(slowGCFirstC.dd^2 == 0);\nscan(0..4, i -> assert(rank C_i == rank slowGCFirstC_i));\n'
    path = output / (name + ".m2")
    if path.exists() and path.read_text() != text:
        raise RuntimeError(f"refusing to replace a different saved input: {path}")
    path.write_text(text)
    return path


def sample(name, mode, trial, warmup, args, script, logs):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GC_")}
    env.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", LC_ALL="C")
    if mode == "gc-off":
        env["GC_DONT_GC"] = "1"
    with tempfile.NamedTemporaryFile() as timing:
        cmd = ["/usr/bin/time", "-q", "-f", "%e\t%U\t%S\t%M\t%x", "-o", timing.name,
               str(args.m2), "--script", str(HERE / "workload.m2"), name, str(script)]
        def limits():
            resource.setrlimit(resource.RLIMIT_AS, (args.memory_gib * 1024**3,) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        proc = subprocess.Popen(cmd, cwd=SOURCE, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True, preexec_fn=limits)
        failure = None
        try:
            stdout, stderr = proc.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            failure = f"timeout after {args.timeout} seconds"
        resource_line = Path(timing.name).read_text().strip()
    tag = f"{name}-{mode}-{'warmup' if warmup else 'trial'}-{trial}"
    (logs / (tag + ".stdout")).write_text(stdout)
    (logs / (tag + ".stderr")).write_text(stderr)
    row = dict(workload=name, mode=mode, trial=trial, warmup=warmup,
               returncode=proc.returncode, command=cmd, resource_line=resource_line,
               environment={k: env.get(k, "<unset>") for k in ["GC_DONT_GC", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "LC_ALL"]},
               stdout_file=f"logs/{tag}.stdout", stderr_file=f"logs/{tag}.stderr")
    try:
        if failure or proc.returncode:
            raise RuntimeError(failure or f"exit {proc.returncode}")
        row.update(common.parse_m2_result(stdout, name))
        fields = resource_line.split("\t")
        assert len(fields) == 5 and fields[4] == "0", resource_line
        row.update(process_wall_seconds=float(fields[0]), process_user_seconds=float(fields[1]),
                   process_system_seconds=float(fields[2]), peak_rss_kib=int(fields[3]))
        totals = [s for s in stdout.splitlines() if s.startswith("M2_SLOW_GC_TOTAL|")]
        assert len(totals) == 1
        row["process_gc_collections"] = int(totals[0].split("|")[1])
        if mode == "gc-off" and row["process_gc_collections"] != 0:
            raise RuntimeError("GC-off process performed collections")
        row["status"] = "ok"
    except (RuntimeError, ValueError, AssertionError) as exc:
        row.update(status="failed", error=str(exc))
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m2", type=Path, default=REPO / "build/M2")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--workload", choices=NAMES, action="append")
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--warmups", type=int, default=1)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--memory-gib", type=int, default=24)
    p.add_argument("--pilot", action="store_true", help="continue to next candidate after a failure")
    p.add_argument("--resume", action="store_true", help="resume saved successful samples with identical inputs and settings")
    args = p.parse_args()
    if args.repetitions < 1 or args.warmups < 0 or args.timeout < 1 or args.memory_gib < 1:
        p.error("invalid repetition, warmup, timeout, or memory limit")
    args.m2 = args.m2.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw-results.json"
    if raw.exists() and not args.resume:
        p.error("output already contains results; use a fresh directory")
    if args.resume and not raw.exists():
        p.error("no saved results to resume")
    logs = out / "logs"
    scripts = out / "scripts"
    logs.mkdir(exist_ok=True)
    scripts.mkdir(exist_ok=True)
    selected = args.workload or (NAMES if args.pilot else DEFAULT_WORKLOADS)
    data = dict(metadata=common.metadata(REPO, args.m2, args), workloads={}, results=[], warmups=[])
    data["metadata"].update(memory_limit_gib=args.memory_gib, random_seed=20260913,
                            pilot=args.pilot, runner_sha256=sha(Path(__file__)),
                            wrapper_sha256=sha(HERE / "workload.m2"),
                            shared_runner_sha256=sha(HERE.parent / "package-gc/run.py"),
                            gb_aux_sha256=sha(SOURCE / "gb-1.aux"))
    executable = REPO / "build/usr-dist/x86_64-Linux-Debian-/bin/M2-binary"
    data["metadata"]["built_executable_sha256"] = sha(executable)
    data["metadata"]["lscpu"] = json.loads(common.run_text(["lscpu", "--json"], REPO))
    data["metadata"]["os_release"] = Path("/etc/os-release").read_text()
    data["metadata"]["cpu0_caches"] = [
        {key: (index / key).read_text().strip() for key in
         ["level", "type", "size", "coherency_line_size", "ways_of_associativity", "shared_cpu_list"]}
        for index in sorted(Path("/sys/devices/system/cpu/cpu0/cache").glob("index*"))]
    data["metadata"]["meminfo_before"] = Path("/proc/meminfo").read_text()
    data["metadata"]["loadavg_before"] = Path("/proc/loadavg").read_text().strip()
    if args.resume:
        previous = json.loads(raw.read_text())
        for key in ["commit", "m2", "build_type", "cpu", "logical_cpus", "kernel",
                    "repetitions", "warmups_per_mode", "timeout_seconds", "memory_limit_gib",
                    "pilot", "runner_sha256", "wrapper_sha256", "shared_runner_sha256",
                    "gb_aux_sha256", "built_executable_sha256"]:
            if previous["metadata"][key] != data["metadata"][key]:
                p.error(f"cannot resume with changed {key}")
        if previous.get("selected_workloads") != selected:
            p.error("cannot resume a different workload selection")
        if any(r["status"] != "ok" for r in previous["results"] + previous["warmups"]):
            p.error("a failed comparison must not be resumed as a success")
        previous.setdefault("resume_sessions", []).append(data["metadata"])
        data = previous
    data["selected_workloads"] = selected
    save(raw, data)
    for name in selected:
        script = prepare(name, scripts)
        workload_spec = dict(source=str((SOURCE / (name + ".m2")).relative_to(REPO)),
                                       source_sha256=sha(SOURCE / (name + ".m2")),
                                       script_sha256=sha(script))
        if name in data["workloads"] and data["workloads"][name] != workload_spec:
            p.error(f"cannot resume with changed input for {name}")
        data["workloads"][name] = workload_spec
        if args.resume and any(r['workload'] == name for r in data['results']) and sum(r['workload'] == name for r in data['results']) < 2 * args.repetitions:
            # Restore the warm-up routine after a process/host interruption.
            for mode in ["gc-on", "gc-off"]:
                row = sample(name, mode, len(data['resume_sessions']) + args.warmups, True, args, script, logs)
                data.setdefault('resume_warmups', []).append(row)
                save(raw, data)
                if row['status'] != 'ok':
                    raise SystemExit("Resume warm-up failed")
        failed = False
        for warmup, count in [(True, args.warmups), (False, args.repetitions)]:
            for trial in range(1, count + 1):
                for mode in (["gc-on", "gc-off"] if trial % 2 else ["gc-off", "gc-on"]):
                    if any(r['workload'] == name and r['mode'] == mode and r['trial'] == trial
                           for r in data['warmups' if warmup else 'results']):
                        continue
                    print(f"{name}: {mode} {'warmup' if warmup else 'trial'} {trial}/{count}", flush=True)
                    row = sample(name, mode, trial, warmup, args, script, logs)
                    data["warmups" if warmup else "results"].append(row)
                    save(raw, data)
                    print(f"  {row['status']}: " + (f"internal {row['internal_seconds']:.3f}s, wall {row['process_wall_seconds']:.2f}s, RSS {row['peak_rss_kib']/1024:.1f} MiB" if row['status'] == 'ok' else row['error']), flush=True)
                    if row["status"] != "ok":
                        if not args.pilot:
                            raise SystemExit(f"Comparison aborted: {name} {mode}; see {raw}")
                        failed = True
                if failed:
                    break
            if failed:
                break
    data["metadata"]["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(raw, data)
    print(raw, flush=True)

if __name__ == "__main__":
    main()
