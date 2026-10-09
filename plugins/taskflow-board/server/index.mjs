#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { finalizeGitWorktree, prepareGitWorktree } from "./lib/git-workflow.mjs";
import { TaskStore } from "./lib/store.mjs";

const SERVER_NAME = "taskflow-board";
const SERVER_VERSION = "0.1.0";
const TEMPLATE_URI = "ui://taskflow-board/board-v1.html";
const RESOURCE_MIME_TYPE = "text/html;profile=mcp-app";
const here = dirname(fileURLToPath(import.meta.url));
const uiPath = join(here, "..", "ui", "board.html");
const store = new TaskStore();

const stringProperty = (description, maxLength) => ({ type: "string", description, maxLength });

const taskFields = {
  title: stringProperty("Short task title", 240),
  content: stringProperty("Task description, desired outcome, or notes", 12000),
  status: {
    type: "string",
    enum: ["idea", "plan", "execute", "verify"],
    description: "Board lane: idea, plan, execute, or verify",
  },
  projectPath: stringProperty("Absolute local path of the related project", 4096),
  projectName: stringProperty("Human-readable project name", 160),
  projectId: stringProperty("Optional Codex saved-project ID", 256),
  conversationId: stringProperty("Linked Codex thread/conversation ID", 512),
  conversationHostId: stringProperty("Host ID for the linked Codex conversation", 256),
  conversationTitle: stringProperty("Visible title of the linked Codex conversation", 300),
};

const toolDefinitions = [
  {
    name: "taskflow_open_board",
    title: "Open Taskflow Board",
    description: "Render the current four-lane Taskflow board. Use this when the user asks to open or show the task panel.",
    inputSchema: {
      type: "object",
      properties: {
        includeArchived: { type: "boolean", description: "Include archived tasks in the result" },
      },
      additionalProperties: false,
    },
    _meta: {
      ui: { resourceUri: TEMPLATE_URI },
      "openai/outputTemplate": TEMPLATE_URI,
      "openai/toolInvocation/invoking": "正在打开 Taskflow…",
      "openai/toolInvocation/invoked": "Taskflow 已打开",
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "taskflow_list_tasks",
    title: "List Taskflow tasks",
    description: "Return the authoritative Taskflow task snapshot without rendering UI.",
    inputSchema: {
      type: "object",
      properties: {
        includeArchived: { type: "boolean", description: "Include archived tasks" },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "taskflow_get_task",
    title: "Get Taskflow task",
    description: "Get one task by its stable Taskflow ID, including project, conversation, Git, and verification metadata.",
    inputSchema: {
      type: "object",
      required: ["taskId"],
      properties: { taskId: stringProperty("Stable task ID such as TF-20260826-001", 64) },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "taskflow_create_task",
    title: "Create Taskflow task",
    description: "Create a local task card. A stable Taskflow ID is assigned automatically.",
    inputSchema: {
      type: "object",
      required: ["title"],
      properties: taskFields,
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "taskflow_update_task",
    title: "Update Taskflow task",
    description: "Edit task content, move it between lanes, or link a project and Codex conversation.",
    inputSchema: {
      type: "object",
      required: ["taskId"],
      properties: {
        taskId: stringProperty("Stable Taskflow task ID", 64),
        ...taskFields,
        rank: { type: "number", description: "Sort rank inside the lane" },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "taskflow_archive_task",
    title: "Archive Taskflow task",
    description: "Archive or restore a task card. Active Git worktree tasks cannot be archived.",
    inputSchema: {
      type: "object",
      required: ["taskId"],
      properties: {
        taskId: stringProperty("Stable Taskflow task ID", 64),
        archived: { type: "boolean", description: "True to archive, false to restore", default: true },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "taskflow_prepare_git",
    title: "Prepare task Git worktree",
    description: "Create a codex/taskflow-* branch in a dedicated worktree for a tracked task and move it to Execute.",
    inputSchema: {
      type: "object",
      required: ["taskId"],
      properties: {
        taskId: stringProperty("Stable Taskflow task ID", 64),
        baseBranch: stringProperty("Optional local base branch; defaults to main, master, or current branch", 256),
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "taskflow_record_verification",
    title: "Record task verification",
    description: "Record passed or failed verification evidence and move the task to Verify.",
    inputSchema: {
      type: "object",
      required: ["taskId", "outcome", "summary"],
      properties: {
        taskId: stringProperty("Stable Taskflow task ID", 64),
        outcome: { type: "string", enum: ["passed", "failed"] },
        summary: stringProperty("Concise checks and evidence", 8000),
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "taskflow_finalize_git",
    title: "Merge and clean up task Git work",
    description: "After passed verification and explicit confirmation, fast-forward merge the task branch, remove its worktree, and delete the temporary branch.",
    inputSchema: {
      type: "object",
      required: ["taskId", "confirmed"],
      properties: {
        taskId: stringProperty("Stable Taskflow task ID", 64),
        confirmed: { type: "boolean", description: "Must be true after the user explicitly asks to merge and finish" },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
  },
];

function textResult(message, structuredContent = undefined, meta = undefined) {
  const result = { content: [{ type: "text", text: message }] };
  if (structuredContent !== undefined) result.structuredContent = structuredContent;
  if (meta !== undefined) result._meta = meta;
  return result;
}

async function mutationResult(action, task) {
  const board = await store.board();
  return textResult(`${action}: ${task.id} — ${task.title}`, { action, task, board });
}

async function callTool(name, input = {}) {
  switch (name) {
    case "taskflow_open_board": {
      const board = await store.board({ includeArchived: Boolean(input.includeArchived) });
      return textResult(
        `Taskflow Board: ${board.tasks.length} active task${board.tasks.length === 1 ? "" : "s"}.`,
        { board },
        {
          ui: { resourceUri: TEMPLATE_URI },
          "openai/outputTemplate": TEMPLATE_URI,
        },
      );
    }
    case "taskflow_list_tasks": {
      const board = await store.board({ includeArchived: Boolean(input.includeArchived) });
      return textResult(`Found ${board.tasks.length} Taskflow tasks.`, { board });
    }
    case "taskflow_get_task": {
      const task = await store.get(input.taskId);
      return textResult(`${task.id}: ${task.title}`, { task });
    }
    case "taskflow_create_task":
      return mutationResult("Created", await store.create(input));
    case "taskflow_update_task": {
      const { taskId, ...patch } = input;
      return mutationResult("Updated", await store.update(taskId, patch));
    }
    case "taskflow_archive_task":
      return mutationResult(input.archived === false ? "Restored" : "Archived", await store.archive(input.taskId, input.archived !== false));
    case "taskflow_prepare_git":
      return mutationResult("Prepared Git worktree", await prepareGitWorktree(store, input.taskId, input.baseBranch || ""));
    case "taskflow_record_verification":
      return mutationResult("Recorded verification", await store.recordVerification(input.taskId, input.outcome, input.summary));
    case "taskflow_finalize_git":
      return mutationResult("Merged and cleaned up Git work", await finalizeGitWorktree(store, input.taskId, input.confirmed));
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

async function handleRequest(request) {
  const { method, params = {} } = request;
  switch (method) {
    case "initialize":
      return {
        protocolVersion: params.protocolVersion || "2025-06-18",
        capabilities: { tools: { listChanged: false }, resources: { subscribe: false, listChanged: false } },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      };
    case "ping":
      return {};
    case "tools/list":
      return { tools: toolDefinitions };
    case "tools/call":
      return callTool(params.name, params.arguments || {});
    case "resources/list":
      return {
        resources: [
          {
            uri: TEMPLATE_URI,
            name: "Taskflow four-lane board",
            description: "Interactive local-first Kanban board for Taskflow tasks",
            mimeType: RESOURCE_MIME_TYPE,
          },
        ],
      };
    case "resources/templates/list":
      return { resourceTemplates: [] };
    case "resources/read":
      if (params.uri !== TEMPLATE_URI) throw new Error(`Unknown resource: ${params.uri}`);
      return {
        contents: [
          {
            uri: TEMPLATE_URI,
            mimeType: RESOURCE_MIME_TYPE,
            text: await readFile(uiPath, "utf8"),
            _meta: {
              ui: {
                prefersBorder: false,
                csp: { connectDomains: [], resourceDomains: [] },
              },
              "openai/widgetPrefersBorder": false,
            },
          },
        ],
      };
    default:
      throw Object.assign(new Error(`Method not found: ${method}`), { code: -32601 });
  }
}

let inputBuffer = Buffer.alloc(0);
let transportMode = "jsonl";

function send(message) {
  const json = JSON.stringify(message);
  if (transportMode === "headers") {
    const bytes = Buffer.byteLength(json);
    process.stdout.write(`Content-Length: ${bytes}\r\n\r\n${json}`);
  } else {
    process.stdout.write(`${json}\n`);
  }
}

async function dispatch(request) {
  if (!request || request.jsonrpc !== "2.0" || !request.method) return;
  if (request.id === undefined) return;
  try {
    send({ jsonrpc: "2.0", id: request.id, result: await handleRequest(request) });
  } catch (error) {
    send({
      jsonrpc: "2.0",
      id: request.id,
      error: {
        code: error.code || -32000,
        message: error.message || "Taskflow request failed",
      },
    });
  }
}

function parseInput() {
  while (inputBuffer.length) {
    const asString = inputBuffer.toString("utf8");
    if (/^Content-Length:/i.test(asString)) {
      transportMode = "headers";
      const headerEnd = asString.indexOf("\r\n\r\n");
      if (headerEnd < 0) return;
      const header = asString.slice(0, headerEnd);
      const match = header.match(/Content-Length:\s*(\d+)/i);
      if (!match) throw new Error("Invalid Content-Length header");
      const length = Number(match[1]);
      const bodyStart = Buffer.byteLength(asString.slice(0, headerEnd + 4));
      if (inputBuffer.length < bodyStart + length) return;
      const body = inputBuffer.subarray(bodyStart, bodyStart + length).toString("utf8");
      inputBuffer = inputBuffer.subarray(bodyStart + length);
      void dispatch(JSON.parse(body));
      continue;
    }

    const newline = inputBuffer.indexOf(0x0a);
    if (newline < 0) return;
    const line = inputBuffer.subarray(0, newline).toString("utf8").trim();
    inputBuffer = inputBuffer.subarray(newline + 1);
    if (line) void dispatch(JSON.parse(line));
  }
}

process.stdin.on("data", (chunk) => {
  inputBuffer = Buffer.concat([inputBuffer, chunk]);
  try {
    parseInput();
  } catch (error) {
    process.stderr.write(`[taskflow-board] ${error.message}\n`);
  }
});

process.stdin.on("end", () => process.exit(0));
