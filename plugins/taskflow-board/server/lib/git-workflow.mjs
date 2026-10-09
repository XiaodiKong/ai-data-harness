import { createHash } from "node:crypto";
import { access, mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { execFile } from "node:child_process";

const execFileAsync = promisify(execFile);

async function git(cwd, args, options = {}) {
  try {
    const result = await execFileAsync("git", args, {
      cwd,
      encoding: "utf8",
      maxBuffer: 4 * 1024 * 1024,
      ...options,
    });
    return result.stdout.trim();
  } catch (error) {
    const detail = (error.stderr || error.stdout || error.message || "Git command failed").trim();
    throw new Error(detail);
  }
}

async function branchExists(repoRoot, branchName) {
  try {
    await git(repoRoot, ["show-ref", "--verify", "--quiet", `refs/heads/${branchName}`]);
    return true;
  } catch {
    return false;
  }
}

async function chooseBaseBranch(repoRoot, requested) {
  if (requested) {
    await git(repoRoot, ["check-ref-format", "--branch", requested]);
    if (!(await branchExists(repoRoot, requested))) {
      throw new Error(`Base branch does not exist locally: ${requested}`);
    }
    return requested;
  }
  for (const candidate of ["main", "master"]) {
    if (await branchExists(repoRoot, candidate)) return candidate;
  }
  const current = await git(repoRoot, ["branch", "--show-current"]);
  if (!current) throw new Error("Cannot determine a base branch from a detached HEAD");
  return current;
}

function repoKey(repoRoot) {
  return createHash("sha256").update(repoRoot).digest("hex").slice(0, 12);
}

function taskBranchName(taskId) {
  const suffix = taskId.toLowerCase().replace(/[^a-z0-9-]/g, "-");
  return `codex/taskflow-${suffix}`;
}

async function ensurePathMissing(path) {
  try {
    await access(path);
    throw new Error(`Worktree path already exists: ${path}`);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}

export async function prepareGitWorktree(store, taskId, requestedBaseBranch = "") {
  const task = await store.get(taskId);
  if (task.git.state === "prepared") throw new Error(`Task already has a worktree: ${task.git.worktreePath}`);
  if (!task.project.path) throw new Error("Task has no project path");

  const projectPath = resolve(task.project.path);
  const repoRoot = await git(projectPath, ["rev-parse", "--show-toplevel"]);
  const baseBranch = await chooseBaseBranch(repoRoot, requestedBaseBranch);
  const branchName = taskBranchName(task.id);
  if (await branchExists(repoRoot, branchName)) {
    throw new Error(`Task branch already exists: ${branchName}`);
  }

  const worktreePath = join(store.dataDir, "worktrees", repoKey(repoRoot), task.id.toLowerCase());
  await ensurePathMissing(worktreePath);
  await mkdir(join(store.dataDir, "worktrees", repoKey(repoRoot)), { recursive: true });
  await git(repoRoot, ["worktree", "add", "-b", branchName, worktreePath, baseBranch]);

  const preparedAt = new Date().toISOString();
  return store.updateGit(
    task.id,
    {
      state: "prepared",
      repoRoot,
      baseBranch,
      branchName,
      worktreePath,
      preparedAt,
      mergedAt: "",
      mergeCommit: "",
    },
    { status: "execute" },
  );
}

export async function finalizeGitWorktree(store, taskId, confirmed) {
  if (confirmed !== true) throw new Error("Finalization requires confirmed: true");
  const task = await store.get(taskId);
  if (task.git.state !== "prepared") throw new Error("Task does not have an active Git worktree");
  if (task.verification.outcome !== "passed") {
    throw new Error("Record a passed verification before finalizing Git work");
  }

  const { repoRoot, baseBranch, branchName, worktreePath } = task.git;
  const worktreeStatus = await git(worktreePath, ["status", "--porcelain"]);
  if (worktreeStatus) throw new Error("Task worktree has uncommitted changes; commit or discard them first");

  const baseStatus = await git(repoRoot, ["status", "--porcelain"]);
  if (baseStatus) throw new Error("Base worktree has unrelated changes; clean it before finalizing");
  const currentBranch = await git(repoRoot, ["branch", "--show-current"]);
  if (currentBranch !== baseBranch) {
    throw new Error(`Base worktree must be on ${baseBranch}; it is currently on ${currentBranch || "detached HEAD"}`);
  }

  await git(repoRoot, ["merge", "--ff-only", branchName]);
  const mergeCommit = await git(repoRoot, ["rev-parse", "HEAD"]);
  await git(repoRoot, ["worktree", "remove", worktreePath]);
  await git(repoRoot, ["branch", "-d", branchName]);

  return store.updateGit(
    task.id,
    {
      state: "merged",
      worktreePath: "",
      mergedAt: new Date().toISOString(),
      mergeCommit,
    },
    { status: "verify" },
  );
}

export const gitInternals = { git, chooseBaseBranch, taskBranchName };
