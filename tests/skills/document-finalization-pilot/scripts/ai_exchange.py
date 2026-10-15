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
LEGACY_FILES = {"report": "report.md", "transcript": "transcript.md", "next": "NEXT.md"}
V2_FILES = {**LEGACY_FILES, "evidence": "evidence.json"}
FILES = {**V2_FILES, "handoff": "handoff.json"}
CAPTURE_MODES = {"native_events", "formatted_transcript", "unknown"}
TOOL_ACCESS = {"disabled", "restricted", "unrestricted", "unknown"}
TERMINAL = {"completed", "partial", "blocked"}
MODES = {"isolated_contexts", "single_context_rehearsal", "mixed", "unknown"}
PENDING = "<!-- awaiting-output -->"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def contract_files(meta):
    versions = (meta.get("schema_version"), meta.get("task_version"))
    if versions == (1, 1):
        return LEGACY_FILES
    if versions == (2, 2):
        return V2_FILES
    if versions == (3, 3):
        return FILES
    raise ValueError("Unsupported schema/task version")


def regular_file(run, name):
    path = run / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing regular file: {name}")
    return path


def reject_non_json_number(value):
    raise ValueError(f"Non-JSON number: {value}")


def handoff_record(run, meta):
    """Check captured text transfer only, not package quality or model execution."""
    if meta["schema_version"] < 3:
        return None
    record = read_json(regular_file(run, "handoff.json"))
    required = {"schema_version", "status", "a_output", "b_input", "limitations"}
    if not isinstance(record, dict) or required - record.keys():
        raise ValueError("Incomplete handoff record")
    if record["schema_version"] != 1 or record["status"] not in {"not_run", "partial", "recorded"}:
        raise ValueError("Unsupported handoff schema or status")
    if not all(isinstance(record[name], str) for name in ("a_output", "b_input")):
        raise ValueError("Handoff a_output and b_input must be strings")
    if not isinstance(record["limitations"], list) or not all(
        isinstance(item, str) for item in record["limitations"]
    ):
        raise ValueError("Handoff limitations must be a list of strings")
    a_output, b_input = record["a_output"], record["b_input"]
    if record["status"] == "not_run" and (a_output or b_input):
        raise ValueError("not_run handoff must have empty a_output and b_input")
    if record["status"] == "partial" and not (a_output.strip() or b_input.strip()):
        raise ValueError("partial handoff needs captured text; use not_run if no text was captured")
    if record["status"] == "recorded":
        if not a_output.strip() or not b_input.strip():
            raise ValueError("recorded handoff requires nonempty a_output and b_input")
        if a_output not in b_input:
            raise ValueError("recorded handoff requires the unchanged a_output as one continuous block in b_input")
    return record


def evidence_files(run, meta, warn=True):
    """Validate the evidence declaration, not its claimed authenticity."""
    if meta["schema_version"] == 1:
        return []
    evidence = read_json(regular_file(run, "evidence.json"))
    required = {"schema_version", "capture_mode", "raw_events_file", "tool_access", "limitations"}
    if not isinstance(evidence, dict) or required - evidence.keys():
        raise ValueError("Incomplete evidence declaration")
    if evidence["schema_version"] != 1 or evidence["capture_mode"] not in CAPTURE_MODES:
        raise ValueError("Unsupported evidence schema or capture mode")
    if evidence["tool_access"] not in TOOL_ACCESS:
        raise ValueError("Unsupported tool access declaration")
    if not isinstance(evidence["limitations"], list) or not all(
        isinstance(item, str) for item in evidence["limitations"]
    ):
        raise ValueError("Evidence limitations must be a list of strings")
    names = ["evidence.json"]
    if evidence["capture_mode"] == "native_events":
        if evidence["raw_events_file"] != "raw-events.jsonl":
            raise ValueError("native_events requires raw_events_file: raw-events.jsonl")
        raw = regular_file(run, "raw-events.jsonl").read_text(encoding="utf-8")
        if not raw.strip():
            raise ValueError("Native raw events must not be empty")
        for number, line in enumerate(raw.splitlines(), 1):
            try:
                event = json.loads(line, parse_constant=reject_non_json_number)
            except ValueError as error:
                raise ValueError(f"Invalid raw-events.jsonl JSON on line {number}") from error
            if not isinstance(event, dict):
                raise ValueError(f"raw-events.jsonl line {number} must be an object")
        names.append("raw-events.jsonl")
    elif evidence["raw_events_file"] is not None:
        raise ValueError("Only native_events may declare a raw_events_file")
    elif warn:
        print("WARNING: no native event export; original message bytes and tool events are unverified")
    if warn and evidence["tool_access"] == "unknown":
        print("WARNING: executor tool access was not captured")
    return names


def pre_review_files(run, meta, warn=True):
    names = evidence_files(run, meta, warn=warn)
    if handoff_record(run, meta) is not None:
        names.append("handoff.json")
    return names


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
        "schema_version": 3, "run_id": run_id,
        "task_id": "document-finalization-evaluation", "task_version": 3,
        "created_at": now.isoformat(), "ai_product": args.ai, "model": args.model,
        "source_commit": commit, "source_tracked_changes": dirty,
        "batch_id": active["batch_id"], "batch_path": str(batch.relative_to(ROOT)),
        "batch_manifest_sha256": digest(manifest_path),
        "task_sha256": hashlib.sha256(task_bytes).hexdigest(), "task_snapshot": "task-snapshot.md",
        "transcript_before_review_sha256": "unknown",
        "evidence_before_review_sha256": {},
        "execution_mode": "unknown", "context_isolation": "unknown",
        "review_mode": "unknown", "status": "prepared", "completed_scope": [],
        "limitations": [], "files": FILES, "artifact_sha256": {},
    }
    write_json(run / "run.json", metadata)
    write_json(run / "evidence.json", {
        "schema_version": 1, "capture_mode": "unknown", "raw_events_file": None,
        "tool_access": "unknown", "limitations": [],
    })
    write_json(run / "handoff.json", {
        "schema_version": 1, "status": "not_run", "a_output": "", "b_input": "",
        "limitations": [],
    })
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
    regular_file(run, "run.json")
    meta = read_json(run / "run.json")
    for name in ["task-snapshot.md", *contract_files(meta).values()]:
        regular_file(run, name)
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
    files = contract_files(meta)
    if meta["schema_version"] >= 2 and "evidence_before_review_sha256" not in meta:
        raise ValueError("Missing evidence_before_review_sha256")
    if meta["run_id"] != run.name or meta["task_id"] != "document-finalization-evaluation":
        raise ValueError("Run/task identity mismatch")
    if meta["status"] not in TERMINAL | {"prepared", "running"}:
        raise ValueError("Unknown run status")
    if meta["execution_mode"] not in MODES or meta["files"] != files:
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
    evidence_names = pre_review_files(run, meta)
    if meta["schema_version"] >= 3 and meta["status"] == "completed":
        if handoff_record(run, meta)["status"] != "recorded":
            raise ValueError("A completed run requires a recorded handoff")
    artifact_names = set(files.values()) | set(evidence_names)
    for name in LEGACY_FILES.values():
        text = (run / name).read_text(encoding="utf-8")
        if final and (not text.strip() or PENDING in text):
            raise ValueError(f"Output not filled: {name}")
    if verify_artifacts and meta["status"] in TERMINAL:
        if set(meta["artifact_sha256"]) != artifact_names:
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
    if meta["schema_version"] >= 2:
        evidence_checkpoint = meta["evidence_before_review_sha256"]
        if not isinstance(evidence_checkpoint, dict):
            raise ValueError("evidence_before_review_sha256 must be a mapping")
        if evidence_checkpoint:
            if set(evidence_checkpoint) != set(evidence_names):
                raise ValueError("Pre-review evidence file list does not match the declaration")
            for name, expected in evidence_checkpoint.items():
                if expected == "unknown":
                    print(f"WARNING: no pre-review evidence hash was captured: {name}")
                elif digest(run / name) != expected:
                    raise ValueError(f"Evidence changed after the pre-review checkpoint: {name}")
        elif meta["status"] in TERMINAL:
            print("WARNING: no pre-review evidence hashes were captured; grading separation is unverified")
    return meta


def checkpoint_run(run):
    meta = validate_run(run)
    if meta["status"] in TERMINAL or meta["transcript_before_review_sha256"] != "unknown":
        raise ValueError("Checkpoint already recorded or run already delivered")
    text = (run / "transcript.md").read_text(encoding="utf-8")
    if not text.strip() or PENDING in text:
        raise ValueError("Fill the actual transcript before checkpointing")
    meta["transcript_before_review_sha256"] = digest(run / "transcript.md")
    if meta["schema_version"] >= 2:
        meta["evidence_before_review_sha256"] = {
            name: digest(run / name) for name in pre_review_files(run, meta, warn=False)
        }
    meta["transcript_checkpoint_at"] = datetime.now(timezone.utc).isoformat()
    write_json(run / "run.json", meta)
    print("Pre-review checkpoint recorded. Keep the transcript and declared evidence unchanged during review.")


def finalize_run(run, status):
    meta = validate_run(run, require_outputs=True)
    if meta["status"] in TERMINAL:
        raise ValueError("Delivered runs are not overwritten; start a new run")
    if not meta["completed_scope"] and status == "completed":
        raise ValueError("A completed run needs an explicit completed_scope")
    if meta["transcript_before_review_sha256"] == "unknown":
        raise ValueError("Record a transcript checkpoint before grading/finalizing")
    if meta["schema_version"] >= 2 and not meta["evidence_before_review_sha256"]:
        raise ValueError("Record an evidence checkpoint before grading/finalizing")
    if meta["schema_version"] >= 3 and status == "completed":
        if handoff_record(run, meta)["status"] != "recorded":
            raise ValueError("A completed run requires a recorded handoff")
    names = [*contract_files(meta).values()]
    names.extend(name for name in evidence_files(run, meta, warn=False) if name not in names)
    meta["artifact_sha256"] = {name: digest(run / name) for name in names}
    meta["status"] = status
    meta["delivered_at"] = datetime.now(timezone.utc).isoformat()
    write_json(run / "run.json", meta)
    print(f"Recorded {status}; this is not a test-quality verdict.")


def pack_run(run):
    meta = validate_run(run)
    if meta["status"] not in TERMINAL:
        raise ValueError("Finalize the run before packaging")
    output = run.with_suffix(".zip")
    names = ["run.json", "task-snapshot.md", *contract_files(meta).values()]
    names.extend(name for name in evidence_files(run, meta, warn=False) if name not in names)
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
