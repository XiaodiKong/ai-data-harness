import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { execFile } from "node:child_process";
import { TaskStore } from "../server/lib/store.mjs";
import { finalizeGitWorktree, prepareGitWorktree } from "../server/lib/git-workflow.mjs";

const execFileAsync = promisify(execFile);
const here = dirname(fileURLToPath(import.meta.url));
const pluginRoot = join(here, "..");

async function git(cwd, args) {
  const result = await execFileAsync("git", args, { cwd, encoding: "utf8" });
  return result.stdout.trim();
}

function createMcpClient(dataDir) {
  const child = spawn(process.execPath, [join(pluginRoot, "server", "index.mjs")], {
    cwd: pluginRoot,
    env: { ...process.env, TASKFLOW_BOARD_DATA_DIR: dataDir },
    stdio: ["pipe", "pipe", "pipe"],
  });
  let buffer = "";
  let nextId = 1;
  const pending = new Map();
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    while (buffer.includes("\n")) {
      const index = buffer.indexOf("\n");
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (!line) continue;
      const response = JSON.parse(line);
      const waiter = pending.get(response.id);
      if (!waiter) continue;
      pending.delete(response.id);
      response.error ? waiter.reject(new Error(response.error.message)) : waiter.resolve(response.result);
    }
  });

  return {
    request(method, params = {}) {
      const id = nextId++;
      child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    },
    close() {
      child.stdin.end();
      child.kill();
    },
  };
}

async function run() {
  const root = await mkdtemp(join(tmpdir(), "taskflow-board-test-"));
  try {
    const store = new TaskStore(join(root, "data"));
    const created = await store.create({
      title: "Implement safe branch workflow",
      content: "Create, verify, merge, and clean up a task worktree.",
      projectName: "fixture",
      projectPath: join(root, "repo"),
      conversationId: "thread_test_001",
    });
    assert.match(created.id, /^TF-\d{8}-001$/);
    assert.equal(created.status, "idea");

    const updated = await store.update(created.id, { status: "plan", title: "Implement tested branch workflow" });
    assert.equal(updated.status, "plan");
    assert.equal((await store.board()).counts.plan, 1);

    const repo = join(root, "repo");
    await execFileAsync("mkdir", ["-p", repo]);
    await git(repo, ["init", "-b", "main"]);
    await git(repo, ["config", "user.email", "taskflow@example.test"]);
    await git(repo, ["config", "user.name", "Taskflow Test"]);
    await writeFile(join(repo, "README.md"), "# Fixture\n");
    await git(repo, ["add", "README.md"]);
    await git(repo, ["commit", "-m", "Initial commit"]);

    const prepared = await prepareGitWorktree(store, created.id);
    assert.equal(prepared.git.state, "prepared");
    assert.equal(prepared.git.branchName, `codex/taskflow-${created.id.toLowerCase()}`);
    assert.equal(await git(prepared.git.worktreePath, ["branch", "--show-current"]), prepared.git.branchName);

    await writeFile(join(prepared.git.worktreePath, "result.txt"), "verified\n");
    await git(prepared.git.worktreePath, ["add", "result.txt"]);
    await git(prepared.git.worktreePath, ["commit", "-m", "Complete Taskflow fixture"]);
    await store.recordVerification(created.id, "passed", "Fixture assertions passed.");

    const finalized = await finalizeGitWorktree(store, created.id, true);
    assert.equal(finalized.git.state, "merged");
    assert.equal(finalized.git.worktreePath, "");
    assert.equal(await readFile(join(repo, "result.txt"), "utf8"), "verified\n");
    const branches = await git(repo, ["branch", "--format=%(refname:short)"]);
    assert.equal(branches, "main");

    await store.archive(created.id, true);
    assert.equal((await store.board()).tasks.length, 0);
    assert.equal((await store.board({ includeArchived: true })).tasks.length, 1);
    await store.archive(created.id, false);

    const client = createMcpClient(join(root, "mcp-data"));
    try {
      const initialized = await client.request("initialize", { protocolVersion: "2025-06-18" });
      assert.equal(initialized.serverInfo.name, "taskflow-board");
      const listedTools = await client.request("tools/list");
      assert.ok(listedTools.tools.some((tool) => tool.name === "taskflow_open_board"));
      const resource = await client.request("resources/read", { uri: "ui://taskflow-board/board-v1.html" });
      assert.equal(resource.contents[0].mimeType, "text/html;profile=mcp-app");
      assert.match(resource.contents[0].text, /Taskflow Board/);
      const toolCreate = await client.request("tools/call", {
        name: "taskflow_create_task",
        arguments: { title: "MCP smoke test" },
      });
      assert.equal(toolCreate.structuredContent.task.title, "MCP smoke test");
      const opened = await client.request("tools/call", { name: "taskflow_open_board", arguments: {} });
      assert.equal(opened.structuredContent.board.tasks.length, 1);
      assert.equal(opened._meta.ui.resourceUri, "ui://taskflow-board/board-v1.html");
    } finally {
      client.close();
    }

    process.stdout.write("✓ Task store CRUD and archive\n");
    process.stdout.write("✓ Git worktree prepare, verify, fast-forward merge, and cleanup\n");
    process.stdout.write("✓ MCP tools and UI resource protocol\n");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
