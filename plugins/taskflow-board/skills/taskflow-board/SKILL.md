---
name: taskflow-board
description: Manage local Codex tasks in a four-lane Taskflow Board, link tasks to Codex conversations, and prepare or finalize task-scoped Git worktrees. Use when the user asks to open the task board, capture an idea, plan or execute a tracked task, link a conversation, record verification, or merge and clean up a Taskflow branch.
---

# Taskflow Board

Use the Taskflow MCP tools as the authoritative task store. The four active statuses are `idea`, `plan`, `execute`, and `verify`.

## Open and edit the board

- When the user asks to open, show, or view the board, call `taskflow_open_board`.
- Use `taskflow_create_task` for a new card and `taskflow_update_task` for edits or lane changes.
- Preserve task IDs. Never invent or rewrite an existing ID.
- Archive completed cards with `taskflow_archive_task`; archived cards stay recoverable.
- Store an absolute project path when the task belongs to a local project.

## Link Codex conversations

- A task can store `conversationId`, `conversationHostId`, and `conversationTitle`.
- When a board action asks to open a linked conversation, get the task with `taskflow_get_task`. If it has a conversation ID, use the Codex app navigation capability to open that task. If navigation is unavailable, report the ID and keep working in the current conversation.
- Create a separate Codex task only when the user explicitly asks to start a new task or conversation. After creation, save the returned thread ID and host ID with `taskflow_update_task`.
- If a card has no conversation ID, offer to continue in the current task or create a new one; do not silently create a user-owned task.

## Git lifecycle

Use the plugin Git tools only for a task whose project path is a Git repository.

1. Before implementation, call `taskflow_prepare_git` after the user agrees to create a task branch. It creates a `codex/taskflow-*` branch in a dedicated Git worktree and moves the card to `execute`.
2. Make project changes only inside the returned `worktreePath`.
3. Run the project's relevant checks in that worktree. Record the result with `taskflow_record_verification`; include concise evidence.
4. Call `taskflow_finalize_git` only after verification passed and the user explicitly asks to merge/finish. The tool requires `confirmed: true`, performs a safe fast-forward-only merge into the recorded base branch, removes the worktree, and deletes the temporary branch.
5. If fast-forward merge is not possible, stop and explain that the base branch advanced. Do not rebase, force-delete, or resolve conflicts without a separate user request.

Never claim a branch was merged or deleted unless the tool result confirms both. Preserve unrelated changes: Git lifecycle tools reject dirty base or task worktrees.

## Board interaction messages

The UI may send a follow-up message such as `Taskflow action: open conversation for TF-...` or `prepare Git for TF-...`. Treat it as the user's request for that card, fetch the current task first, and follow the rules above.
