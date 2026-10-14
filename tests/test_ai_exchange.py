"""File exchange contract tests in disposable directories; no model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in [
            "scripts/ai_exchange.py",
            "ai-collaboration/tasks/document-finalization-evaluation/TASK.md",
            "tests/skills/document-finalization-pilot/active-batch.json",
        ]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / relative, target)
        relative = "tests/skills/document-finalization-pilot/batches/v0.3.0"
        shutil.copytree(PROJECT / relative, self.root / relative)

    def cli(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts/ai_exchange.py"), *args],
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

    def complete(self, run):
        self.fill(run)
        self.cli("checkpoint", "--run", str(run))
        self.cli("finalize", "--run", str(run), "--status", "completed")

    def test_unique_prepared_runs_and_snapshot(self):
        first, second = self.init(), self.init()
        self.assertNotEqual(first, second)
        self.assertEqual(json.loads((first / "run.json").read_text())["status"], "prepared")
        self.assertEqual(
            (first / "task-snapshot.md").read_bytes(),
            (self.root / "ai-collaboration/tasks/document-finalization-evaluation/TASK.md").read_bytes(),
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
        (self.root / "ai-collaboration/tasks/document-finalization-evaluation/TASK.md").write_text("new task")
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
                prefix + name for name in ["run.json", "task-snapshot.md", "report.md", "transcript.md", "NEXT.md"]
            })
        self.cli("pack", "--run", str(run), ok=False)
        self.assertEqual(archive.read_bytes(), original)
        self.cli("finalize", "--run", str(run), "--status", "completed", ok=False)

    def test_frozen_batch_change_prevents_new_run(self):
        path = self.root / "tests/skills/document-finalization-pilot/batches/v0.3.0/inputs/00-skill.md"
        path.write_text("changed input")
        self.cli("init", "--ai", "Synthetic", ok=False)

    def test_symlink_and_outside_run_rejected(self):
        run = self.init()
        (run / "report.md").unlink()
        (run / "report.md").symlink_to(self.root / "scripts/ai_exchange.py")
        self.cli("validate", "--run", str(run), ok=False)
        self.cli("validate", "--run", str(self.root), ok=False)

    def test_manual_unknown_hashes_are_disclosed(self):
        run = self.init()
        self.fill(run)
        path = run / "run.json"
        meta = json.loads(path.read_text())
        meta["status"] = "partial"
        meta["task_sha256"] = "unknown"
        meta["artifact_sha256"] = {name: "unknown" for name in ["report.md", "transcript.md", "NEXT.md"]}
        path.write_text(json.dumps(meta))
        result = self.cli("validate", "--run", str(run))
        self.assertIn("WARNING", result.stdout)


if __name__ == "__main__":
    unittest.main()
