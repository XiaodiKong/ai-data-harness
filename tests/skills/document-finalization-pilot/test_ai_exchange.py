"""File exchange contract tests in disposable directories; no model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[3]


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in [
            "tests/skills/document-finalization-pilot/scripts/ai_exchange.py",
            "tests/skills/document-finalization-pilot/collaboration/tasks/evaluation/TASK.md",
            "tests/skills/document-finalization-pilot/active-batch.json",
        ]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / relative, target)
        self.pilot = self.root / "tests/skills/document-finalization-pilot"
        active = json.loads((self.pilot / "active-batch.json").read_text())
        relative = Path("tests/skills/document-finalization-pilot") / active["path"]
        self.batch = self.root / relative
        shutil.copytree(PROJECT / relative, self.batch)

    def cli(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(self.root / "tests/skills/document-finalization-pilot/scripts/ai_exchange.py"), *args],
            cwd=self.root, capture_output=True, text=True,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def init(self):
        result = self.cli("init", "--ai", "Synthetic test", "--model", "unknown")
        return self.root / result.stdout.splitlines()[0]

    def fill(self, run):
        for name in ["report.md", "transcript.md", "NEXT.md"]:
            (run / name).write_text("Synthetic file-contract fixture. No AI evaluation ran.\n")
        path = run / "run.json"
        meta = json.loads(path.read_text())
        meta["status"] = "running"
        meta["completed_scope"] = ["synthetic file test"]
        path.write_text(json.dumps(meta))

    def evidence(self, run, capture_mode="formatted_transcript", tool_access="disabled"):
        value = {
            "schema_version": 1, "capture_mode": capture_mode,
            "raw_events_file": "raw-events.jsonl" if capture_mode == "native_events" else None,
            "tool_access": tool_access,
            "limitations": ["Synthetic contract fixture; no model or native platform export was used."],
        }
        (run / "evidence.json").write_text(json.dumps(value))

    def native_fixture(self, run):
        self.evidence(run, "native_events")
        # Synthetic JSONL tests parsing and packaging, not native-export authenticity.
        (run / "raw-events.jsonl").write_text(
            '{"fixture": "synthetic", "type": "input", "text": "hello"}\n'
            '{"fixture": "synthetic", "type": "output", "text": "world"}\n'
        )

    def complete(self, run):
        self.fill(run)
        self.cli("checkpoint", "--run", str(run))
        self.cli("finalize", "--run", str(run), "--status", "completed")

    def test_unique_prepared_runs_and_snapshot(self):
        first, second = self.init(), self.init()
        self.assertNotEqual(first, second)
        meta = json.loads((first / "run.json").read_text())
        self.assertEqual(meta["status"], "prepared")
        self.assertEqual((meta["schema_version"], meta["task_version"]), (2, 2))
        self.assertEqual(meta["files"]["evidence"], "evidence.json")
        self.assertEqual(meta["evidence_before_review_sha256"], {})
        evidence = json.loads((first / "evidence.json").read_text())
        self.assertEqual(evidence["capture_mode"], "unknown")
        self.assertEqual(evidence["tool_access"], "unknown")
        self.assertIsNone(evidence["raw_events_file"])
        self.assertEqual(
            (first / "task-snapshot.md").read_bytes(),
            (self.root / "tests/skills/document-finalization-pilot/collaboration/tasks/evaluation/TASK.md").read_bytes(),
        )
        self.cli("validate", "--run", str(first))

    def test_incomplete_outputs_cannot_finalize_or_pack(self):
        run = self.init()
        self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)
        self.cli("pack", "--run", str(run), ok=False)

    def test_checkpoint_required_and_changes_detected(self):
        run = self.init()
        self.fill(run)
        self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)
        self.cli("checkpoint", "--run", str(run))
        self.cli("checkpoint", "--run", str(run), ok=False)
        (run / "transcript.md").write_text("changed after review began")
        self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)

    def test_delivered_output_changes_detected(self):
        run = self.init()
        self.complete(run)
        (run / "report.md").write_text("changed after delivery")
        self.cli("validate", "--run", str(run), ok=False)
        self.cli("pack", "--run", str(run), ok=False)

    def test_old_task_remains_reproducible(self):
        run = self.init()
        self.complete(run)
        (self.root / "tests/skills/document-finalization-pilot/collaboration/tasks/evaluation/TASK.md").write_text("new task")
        self.cli("validate", "--run", str(run))
        self.cli("pack", "--run", str(run))

    def test_archive_contains_only_contract_files_and_does_not_overwrite(self):
        run = self.init()
        self.complete(run)
        (run / "unrelated.txt").write_text("not to be packaged")
        self.cli("pack", "--run", str(run))
        archive = run.with_suffix(".zip")
        original = archive.read_bytes()
        with zipfile.ZipFile(archive) as z:
            prefix = str(run.relative_to(self.root)) + "/"
            self.assertEqual(set(z.namelist()), {
                prefix + name for name in ["run.json", "task-snapshot.md", "report.md", "transcript.md", "NEXT.md", "evidence.json"]
            })
        self.cli("pack", "--run", str(run), ok=False)
        self.assertEqual(archive.read_bytes(), original)
        self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)

    def test_frozen_batch_change_prevents_new_run(self):
        path = self.batch / "inputs/00-skill.md"
        path.write_text("changed input")
        self.cli("init", "--ai", "Synthetic", ok=False)

    def test_symlink_and_outside_run_rejected(self):
        run = self.init()
        (run / "report.md").unlink()
        (run / "report.md").symlink_to(self.root / "tests/skills/document-finalization-pilot/scripts/ai_exchange.py")
        self.cli("validate", "--run", str(run), ok=False)
        self.cli("validate", "--run", str(self.root), ok=False)

    def test_manual_unknown_hashes_are_disclosed(self):
        run = self.init()
        self.fill(run)
        path = run / "run.json"
        meta = json.loads(path.read_text())
        meta["status"] = "partial"
        meta["task_sha256"] = "unknown"
        meta["artifact_sha256"] = {name: "unknown" for name in meta["files"].values()}
        path.write_text(json.dumps(meta))
        result = self.cli("validate", "--run", str(run))
        self.assertIn("WARNING", result.stdout)

    def test_legacy_schema_one_remains_valid_and_packable(self):
        run = self.init()
        path = run / "run.json"
        meta = json.loads(path.read_text())
        meta["schema_version"] = meta["task_version"] = 1
        del meta["files"]["evidence"]
        del meta["evidence_before_review_sha256"]
        (run / "evidence.json").unlink()
        (run / "task-snapshot.md").write_text("Historical task version 1 fixture.\n")
        meta["task_sha256"] = hashlib.sha256((run / "task-snapshot.md").read_bytes()).hexdigest()
        path.write_text(json.dumps(meta))
        self.complete(run)
        before = {file.name: file.read_bytes() for file in run.iterdir()}
        self.cli("validate", "--run", str(run))
        self.cli("pack", "--run", str(run))
        self.assertEqual(before, {file.name: file.read_bytes() for file in run.iterdir()})
        with zipfile.ZipFile(run.with_suffix(".zip")) as archive:
            self.assertEqual({Path(name).name for name in archive.namelist()}, {
                "run.json", "task-snapshot.md", "report.md", "transcript.md", "NEXT.md",
            })

    def test_native_raw_events_checkpoint_and_archive(self):
        run = self.init()
        self.native_fixture(run)
        raw_bytes = (run / "raw-events.jsonl").read_bytes()
        self.complete(run)
        meta = json.loads((run / "run.json").read_text())
        self.assertEqual(set(meta["evidence_before_review_sha256"]), {"evidence.json", "raw-events.jsonl"})
        self.assertEqual(meta["artifact_sha256"]["raw-events.jsonl"], hashlib.sha256(raw_bytes).hexdigest())
        (run / "unrelated-secret.txt").write_text("excluded fixture")
        self.cli("pack", "--run", str(run))
        with zipfile.ZipFile(run.with_suffix(".zip")) as archive:
            self.assertEqual({Path(name).name for name in archive.namelist()}, {
                "run.json", "task-snapshot.md", "report.md", "transcript.md", "NEXT.md",
                "evidence.json", "raw-events.jsonl",
            })
            self.assertEqual(archive.read(str(run.relative_to(self.root) / "raw-events.jsonl")), raw_bytes)

    def test_native_raw_events_missing_or_empty_rejected(self):
        for content in [None, "", " \n"]:
            with self.subTest(content=content):
                run = self.init()
                self.evidence(run, "native_events")
                if content is not None:
                    (run / "raw-events.jsonl").write_text(content)
                self.cli("validate", "--run", str(run), ok=False)

    def test_native_raw_events_invalid_jsonl_rejected(self):
        for content in ["not-json\n", "[]\n", '"text"\n', '{}\n\n{}\n', '{"x":NaN}\n']:
            with self.subTest(content=content):
                run = self.init()
                self.evidence(run, "native_events")
                (run / "raw-events.jsonl").write_text(content)
                self.cli("validate", "--run", str(run), ok=False)

    def test_native_raw_events_symlink_rejected(self):
        run = self.init()
        self.native_fixture(run)
        target = run / "other-events.jsonl"
        (run / "raw-events.jsonl").rename(target)
        (run / "raw-events.jsonl").symlink_to(target)
        self.cli("validate", "--run", str(run), ok=False)

    def test_raw_events_changed_after_checkpoint_rejected(self):
        run = self.init()
        self.native_fixture(run)
        self.fill(run)
        self.cli("checkpoint", "--run", str(run))
        (run / "raw-events.jsonl").write_text('{"fixture": "changed"}\n')
        result = self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)
        self.assertIn("Evidence changed", result.stderr)

    def test_evidence_changed_after_checkpoint_rejected(self):
        run = self.init()
        self.evidence(run)
        self.fill(run)
        self.cli("checkpoint", "--run", str(run))
        self.evidence(run, tool_access="restricted")
        result = self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)
        self.assertIn("Evidence changed", result.stderr)

    def test_raw_events_changed_after_delivery_rejected(self):
        run = self.init()
        self.native_fixture(run)
        self.complete(run)
        (run / "raw-events.jsonl").write_text('{"fixture": "changed after delivery"}\n')
        self.cli("validate", "--run", str(run), ok=False)
        self.cli("pack", "--run", str(run), ok=False)

    def test_declared_raw_path_and_capture_mode_must_agree(self):
        for capture_mode, filename in [
            ("native_events", None), ("native_events", "other.jsonl"),
            ("native_events", "../raw-events.jsonl"), ("formatted_transcript", "raw-events.jsonl"),
            ("unknown", "raw-events.jsonl"),
        ]:
            with self.subTest(mode=capture_mode, filename=filename):
                run = self.init()
                self.evidence(run, capture_mode)
                path = run / "evidence.json"
                declaration = json.loads(path.read_text())
                declaration["raw_events_file"] = filename
                path.write_text(json.dumps(declaration))
                self.cli("validate", "--run", str(run), ok=False)

    def test_formatted_transcript_declares_limitations_without_native_export(self):
        run = self.init()
        self.evidence(run)
        self.complete(run)
        result = self.cli("validate", "--run", str(run))
        self.assertIn("original message bytes and tool events are unverified", result.stdout)
        self.assertNotIn("tool access was not captured", result.stdout)
        meta = json.loads((run / "run.json").read_text())
        self.assertEqual(set(meta["evidence_before_review_sha256"]), {"evidence.json"})


if __name__ == "__main__":
    unittest.main()
