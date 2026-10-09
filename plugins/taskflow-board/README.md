# Taskflow Board

Taskflow Board is a local-first Codex plugin for managing work across four lanes:

- 想法 / Idea
- 方案 / Plan
- 执行 / Execute
- 检验 / Verify

Each task records a stable ID, content, project path, Codex conversation ID, verification evidence, and optional Git worktree metadata. The plugin ships with a dependency-free Node.js MCP server and an interactive MCP Apps board.

## Safety model

Task data is stored outside project repositories under `~/Library/Application Support/Taskflow Board` on macOS. Override this with `TASKFLOW_BOARD_DATA_DIR`.

Git work starts in a dedicated worktree on a `codex/taskflow-*` branch. Finalization requires a passed verification record, an explicit confirmation, clean task and base worktrees, and a fast-forward-only merge. The temporary worktree and branch are removed only after the merge succeeds.

## Local development

```bash
npm test
npm run preview
```

The preview server opens the board with sample data at `http://127.0.0.1:4173`.

## Current Codex UI boundary

Codex plugins can provide skills, MCP tools, and MCP Apps UI rendered with a conversation. The public plugin contract does not currently expose a native third-party left-sidebar page registration point. Taskflow therefore opens as a rich board component from a plugin prompt and can request navigation to linked Codex conversations through the host workflow.
