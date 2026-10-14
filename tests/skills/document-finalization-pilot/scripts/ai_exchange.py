#!/usr/bin/env python3
"""Create and package file-based AI runs. Never executes or grades model tests."""
import argparse
import hashlib
import json
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import subprocess

PILOT = Path(__file__).resolve().parents[1]
ROOT = PILOT.parents[2]
RUNS = PILOT / "collaboration/runs"
TASK = PILOT / "collaboration/tasks/evaluation/TASK.md"
FILES = {"report": "report.md", "transcript": "transcript.md", "next": "NEXT.md"}
TERMINAL = {"completed", "partial", "blocked"}
MODES = {"isolated_contexts", "single_context_rehearsal", "mixed", "unknown"}
PENDING = "<!-- awaiting-output -->"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inside(base, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe relative path: {relative}")
    path = base / relative
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError(f"Path escapes allowed directory: {relative}")
    return path


def verify_batch(batch, expected_id):
    manifest_path = batch / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("batch_id") != expected_id:
        raise ValueError("Batch identity does not match")
    for name, expected in manifest["files"].items():
        path = inside(batch, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Frozen file missing or changed: {name}")
    return manifest_path


def init_run(args):
    active = read_json(PILOT / "active-batch.json")
    batch = inside(PILOT, active["path"])
    manifest_path = verify_batch(batch, active["batch_id"])
    task_bytes = TASK.read_bytes()
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "-", args.ai.lower()).strip("-")[:32] or "ai"
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{slug}-{uuid.uuid4().hex[:10]}"
    run = RUNS / run_id
    run.mkdir(parents=True, exist_ok=False)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True
        ).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit, dirty = "unknown", "unknown"
    metadata = {
        "schema_version": 1, "run_id": run_id,
        "task_id": "document-finalization-evaluation", "task_version": 1,
        "created_at": now.isoformat(), "ai_product": args.ai, "model": args.model,
        "source_commit": commit, "source_tracked_changes": dirty,
        "batch_id": active["batch_id"], "batch_path": str(batch.relative_to(ROOT)),
        "batch_manifest_sha256": digest(manifest_path),
        "task_sha256": hashlib.sha256(task_bytes).hexdigest(), "task_snapshot": "task-snapshot.md",
        "transcript_before_review_sha256": "unknown",
        "execution_mode": "unknown", "context_isolation": "unknown",
        "review_mode": "unknown", "status": "prepared", "completed_scope": [],
        "limitations": [], "files": FILES, "artifact_sha256": {},
    }
    write_json(run / "run.json", metadata)
    (run / "task-snapshot.md").write_bytes(task_bytes)
    templates = {
        "report.md": "# Test report\n\nEnvironment, scope, criterion results, evidence locations, findings and limitations.\n",
        "transcript.md": "# Original transcript\n\nRecord actual inputs and complete outputs by scenario and turn.\n",
        "NEXT.md": "# Handoff\n\nIdentify the run, completed scope, files, unresolved items and next review action.\n",
    }
    for name, text in templates.items():
        (run / name).write_text(text + "\n" + PENDING + "\n", encoding="utf-8")
    print(run.relative_to(ROOT))
    print("Prepared only; no model tests have run.")


def resolve_run(value):
    path = Path(value)
    run = (path if path.is_absolute() else ROOT / path).resolve()
    if run.parent != RUNS.resolve() or not run.is_dir():
        raise ValueError("Run must be an existing direct child of this Skill test area: collaboration/runs")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run.name):
        raise ValueError("Run directory name contains unsupported characters")
    for name in ["run.json", "task-snapshot.md", *FILES.values()]:
        p = run / name
        if p.is_symlink() or not p.is_file():
            raise ValueError(f"Missing regular file: {name}")
    return run


def validate_run(run, require_outputs=False, verify_artifacts=True):
    meta = read_json(run / "run.json")
    required = {"schema_version", "run_id", "task_id", "task_version", "created_at",
                "ai_product", "model", "source_commit", "batch_id", "batch_path",
                "batch_manifest_sha256", "task_sha256", "execution_mode",
                "context_isolation", "review_mode", "status", "completed_scope",
                "limitations", "files", "artifact_sha256", "task_snapshot",
                "transcript_before_review_sha256"}
    if required - meta.keys():
        raise ValueError(f"Missing fields: {sorted(required - meta.keys())}")
    if meta["schema_version"] != 1 or meta["task_version"] != 1:
        raise ValueError("Unsupported schema/task version")
    if meta["run_id"] != run.name or meta["task_id"] != "document-finalization-evaluation":
        raise ValueError("Run/task identity mismatch")
    if meta["status"] not in TERMINAL | {"prepared", "running"}:
        raise ValueError("Unknown run status")
    if meta["execution_mode"] not in MODES or meta["files"] != FILES:
        raise ValueError("Unsupported execution mode or file mapping")
    if meta["task_snapshot"] != "task-snapshot.md":
        raise ValueError("Unsupported task snapshot path")
    if not isinstance(meta["completed_scope"], list) or not isinstance(meta["limitations"], list):
        raise ValueError("completed_scope and limitations must be lists")
    batch = inside(ROOT, meta["batch_path"])
    if not batch.resolve().is_relative_to(PILOT.resolve()):
        raise ValueError("Batch path is outside the test area")
    manifest_path = verify_batch(batch, meta["batch_id"])
    for field, p in [("batch_manifest_sha256", manifest_path), ("task_sha256", run / "task-snapshot.md")]:
        if meta[field] == "unknown":
            print(f"WARNING: {field} was not captured by executor")
        elif digest(p) != meta[field]:
            raise ValueError(f"{field} mismatch; retrieve the original source before review")
    if TASK.exists() and digest(TASK) != digest(run / "task-snapshot.md"):
        print("NOTE: current task differs; validating the captured task snapshot")
    final = require_outputs or meta["status"] in TERMINAL
    for name in FILES.values():
        text = (run / name).read_text(encoding="utf-8")
        if final and (not text.strip() or PENDING in text):
            raise ValueError(f"Output not filled: {name}")
    if verify_artifacts and meta["status"] in TERMINAL:
        if set(meta["artifact_sha256"]) != set(FILES.values()):
            raise ValueError("Final run needs artifact hashes; use finalize")
        for name, expected in meta["artifact_sha256"].items():
            if expected == "unknown":
                print(f"WARNING: original output hash was not captured: {name}")
            elif digest(run / name) != expected:
                raise ValueError(f"Delivered output changed: {name}")
    checkpoint = meta["transcript_before_review_sha256"]
    if checkpoint != "unknown" and digest(run / "transcript.md") != checkpoint:
        raise ValueError("Transcript changed after the pre-review checkpoint")
    if checkpoint == "unknown" and meta["status"] in TERMINAL:
        print("WARNING: no pre-review transcript hash was captured; grading separation is unverified")
    return meta


def checkpoint_run(run):
    meta = validate_run(run)
    if meta["status"] in TERMINAL or meta["transcript_before_review_sha256"] != "unknown":
        raise ValueError("Checkpoint already recorded or run already delivered")
    text = (run / "transcript.md").read_text(encoding="utf-8")
    if not text.strip() or PENDING in text:
        raise ValueError("Fill the actual transcript before checkpointing")
    meta["transcript_before_review_sha256"] = digest(run / "transcript.md")
    meta["transcript_checkpoint_at"] = datetime.now(timezone.utc).isoformat()
    write_json(run / "run.json", meta)
    print("Transcript checkpoint recorded. Keep the raw transcript unchanged during review.")


def finalize_run(run, status):
    meta = validate_run(run, require_outputs=True)
    if meta["status"] in TERMINAL:
        raise ValueError("Delivered runs are not overwritten; start a new run")
    if not meta["completed_scope"] and status == "completed":
        raise ValueError("A completed run needs an explicit completed_scope")
    if meta["transcript_before_review_sha256"] == "unknown":
        raise ValueError("Record a transcript checkpoint before grading/finalizing")
    meta["artifact_sha256"] = {name: digest(run / name) for name in FILES.values()}
    meta["status"] = status
    meta["delivered_at"] = datetime.now(timezone.utc).isoformat()
    write_json(run / "run.json", meta)
    print(f"Recorded {status}; this is not a test-quality verdict.")


def pack_run(run):
    meta = validate_run(run)
    if meta["status"] not in TERMINAL:
        raise ValueError("Finalize the run before packaging")
    output = run.with_suffix(".zip")
    names = ["run.json", "task-snapshot.md", *FILES.values()]
    if (run / "review.md").exists():
        if (run / "review.md").is_symlink() or not (run / "review.md").is_file():
            raise ValueError("review.md must be a regular file")
        names.append("review.md")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(run / name, arcname=str((run / name).relative_to(ROOT)))
    print(output.relative_to(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init")
    init.add_argument("--ai", required=True)
    init.add_argument("--model", default="unknown")
    for name in ["validate", "checkpoint", "finalize", "pack"]:
        sub = subs.add_parser(name)
        sub.add_argument("--run", required=True)
        if name == "finalize":
            sub.add_argument("--status", choices=sorted(TERMINAL), required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            init_run(args)
        else:
            run = resolve_run(args.run)
            if args.command == "validate":
                validate_run(run)
                print("File structure and available hashes verified; model behavior is not graded.")
            elif args.command == "finalize":
                finalize_run(run, args.status)
            elif args.command == "checkpoint":
                checkpoint_run(run)
            else:
                pack_run(run)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
