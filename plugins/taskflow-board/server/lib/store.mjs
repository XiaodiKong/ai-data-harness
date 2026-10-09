import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

export const STATUSES = Object.freeze(["idea", "plan", "execute", "verify"]);
export const STATUS_LABELS = Object.freeze({
  idea: "想法",
  plan: "方案",
  execute: "执行",
  verify: "检验",
});

const EMPTY_STORE = Object.freeze({
  schemaVersion: 1,
  revision: 0,
  counters: {},
  tasks: [],
});

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function text(value, field, maxLength = 8000) {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new Error(`${field} must be a string`);
  const normalized = value.trim();
  if (normalized.length > maxLength) {
    throw new Error(`${field} must be ${maxLength} characters or fewer`);
  }
  return normalized;
}

function optionalAbsolutePath(value, field = "projectPath") {
  const normalized = text(value, field, 4096);
  if (!normalized) return "";
  if (!normalized.startsWith("/")) throw new Error(`${field} must be an absolute path`);
  return resolve(normalized);
}

function status(value) {
  const normalized = value || "idea";
  if (!STATUSES.includes(normalized)) {
    throw new Error(`status must be one of: ${STATUSES.join(", ")}`);
  }
  return normalized;
}

function now() {
  return new Date().toISOString();
}

function todayKey() {
  return new Date().toISOString().slice(0, 10).replaceAll("-", "");
}

function nextTaskId(data) {
  const key = todayKey();
  const sequence = (data.counters[key] || 0) + 1;
  data.counters[key] = sequence;
  return `TF-${key}-${String(sequence).padStart(3, "0")}`;
}

function projectFrom(input = {}) {
  const projectPath = optionalAbsolutePath(input.projectPath);
  const suppliedName = text(input.projectName, "projectName", 160);
  const fallbackName = projectPath ? projectPath.split("/").filter(Boolean).at(-1) || projectPath : "";
  return {
    path: projectPath,
    name: suppliedName || fallbackName,
    id: text(input.projectId, "projectId", 256),
  };
}

function conversationFrom(input = {}) {
  return {
    threadId: text(input.conversationId, "conversationId", 512),
    hostId: text(input.conversationHostId, "conversationHostId", 256),
    title: text(input.conversationTitle, "conversationTitle", 300),
  };
}

function publicBoard(data, includeArchived = false) {
  const tasks = data.tasks
    .filter((task) => includeArchived || !task.archived)
    .sort((left, right) => {
      const lane = STATUSES.indexOf(left.status) - STATUSES.indexOf(right.status);
      if (lane !== 0) return lane;
      const rank = (left.rank ?? 0) - (right.rank ?? 0);
      return rank || right.updatedAt.localeCompare(left.updatedAt);
    });
  const counts = Object.fromEntries(STATUSES.map((lane) => [lane, tasks.filter((task) => task.status === lane).length]));
  return {
    schemaVersion: data.schemaVersion,
    revision: data.revision,
    statuses: STATUSES.map((id) => ({ id, label: STATUS_LABELS[id] })),
    counts,
    tasks,
  };
}

export function defaultDataDir() {
  if (process.env.TASKFLOW_BOARD_DATA_DIR) return resolve(process.env.TASKFLOW_BOARD_DATA_DIR);
  if (process.platform === "darwin") {
    return join(homedir(), "Library", "Application Support", "Taskflow Board");
  }
  return join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "taskflow-board");
}

export class TaskStore {
  constructor(dataDir = defaultDataDir()) {
    this.dataDir = resolve(dataDir);
    this.filePath = join(this.dataDir, "tasks.json");
    this.writeQueue = Promise.resolve();
  }

  async read() {
    try {
      const raw = await readFile(this.filePath, "utf8");
      const data = JSON.parse(raw);
      if (data.schemaVersion !== 1 || !Array.isArray(data.tasks)) {
        throw new Error("Unsupported or invalid Taskflow data file");
      }
      data.counters ||= {};
      data.revision ||= 0;
      return data;
    } catch (error) {
      if (error.code === "ENOENT") return clone(EMPTY_STORE);
      throw error;
    }
  }

  async write(data) {
    await mkdir(dirname(this.filePath), { recursive: true });
    const tempPath = `${this.filePath}.${process.pid}.tmp`;
    await writeFile(tempPath, `${JSON.stringify(data, null, 2)}\n`, { mode: 0o600 });
    await rename(tempPath, this.filePath);
  }

  async mutate(callback) {
    const operation = this.writeQueue.then(async () => {
      const data = await this.read();
      const result = await callback(data);
      data.revision += 1;
      await this.write(data);
      return result;
    });
    this.writeQueue = operation.catch(() => undefined);
    return operation;
  }

  async board({ includeArchived = false } = {}) {
    return publicBoard(await this.read(), includeArchived);
  }

  async get(taskId) {
    const id = text(taskId, "taskId", 64);
    const task = (await this.read()).tasks.find((candidate) => candidate.id === id);
    if (!task) throw new Error(`Task not found: ${id}`);
    return task;
  }

  async create(input) {
    return this.mutate(async (data) => {
      const title = text(input.title, "title", 240);
      if (!title) throw new Error("title is required");
      const createdAt = now();
      const lane = status(input.status);
      const laneTasks = data.tasks.filter((task) => task.status === lane && !task.archived);
      const task = {
        id: nextTaskId(data),
        title,
        content: text(input.content, "content", 12000) || title,
        status: lane,
        rank: laneTasks.reduce((max, task) => Math.max(max, task.rank || 0), 0) + 1000,
        project: projectFrom(input),
        conversation: conversationFrom(input),
        git: {
          state: "none",
          repoRoot: "",
          baseBranch: "",
          branchName: "",
          worktreePath: "",
          preparedAt: "",
          mergedAt: "",
          mergeCommit: "",
        },
        verification: {
          outcome: "pending",
          summary: "",
          checkedAt: "",
        },
        archived: false,
        createdAt,
        updatedAt: createdAt,
      };
      data.tasks.push(task);
      return task;
    });
  }

  async update(taskId, input) {
    return this.mutate(async (data) => {
      const task = data.tasks.find((candidate) => candidate.id === text(taskId, "taskId", 64));
      if (!task) throw new Error(`Task not found: ${taskId}`);

      if (input.title !== undefined) {
        const title = text(input.title, "title", 240);
        if (!title) throw new Error("title cannot be empty");
        task.title = title;
      }
      if (input.content !== undefined) task.content = text(input.content, "content", 12000);
      if (input.status !== undefined) task.status = status(input.status);
      if (input.rank !== undefined) {
        if (!Number.isFinite(input.rank)) throw new Error("rank must be a finite number");
        task.rank = input.rank;
      }
      if (input.projectPath !== undefined || input.projectName !== undefined || input.projectId !== undefined) {
        task.project = projectFrom({
          projectPath: input.projectPath ?? task.project.path,
          projectName: input.projectName ?? task.project.name,
          projectId: input.projectId ?? task.project.id,
        });
      }
      if (
        input.conversationId !== undefined ||
        input.conversationHostId !== undefined ||
        input.conversationTitle !== undefined
      ) {
        task.conversation = conversationFrom({
          conversationId: input.conversationId ?? task.conversation.threadId,
          conversationHostId: input.conversationHostId ?? task.conversation.hostId,
          conversationTitle: input.conversationTitle ?? task.conversation.title,
        });
      }
      task.updatedAt = now();
      return task;
    });
  }

  async archive(taskId, archived = true) {
    return this.mutate(async (data) => {
      const task = data.tasks.find((candidate) => candidate.id === text(taskId, "taskId", 64));
      if (!task) throw new Error(`Task not found: ${taskId}`);
      if (archived && task.git.state === "prepared") {
        throw new Error("Cannot archive a task with an active Git worktree");
      }
      task.archived = Boolean(archived);
      task.updatedAt = now();
      return task;
    });
  }

  async recordVerification(taskId, outcome, summary) {
    if (!["passed", "failed"].includes(outcome)) {
      throw new Error("outcome must be passed or failed");
    }
    return this.mutate(async (data) => {
      const task = data.tasks.find((candidate) => candidate.id === text(taskId, "taskId", 64));
      if (!task) throw new Error(`Task not found: ${taskId}`);
      task.verification = {
        outcome,
        summary: text(summary, "summary", 8000),
        checkedAt: now(),
      };
      task.status = "verify";
      task.updatedAt = now();
      return task;
    });
  }

  async updateGit(taskId, gitPatch, taskPatch = {}) {
    return this.mutate(async (data) => {
      const task = data.tasks.find((candidate) => candidate.id === text(taskId, "taskId", 64));
      if (!task) throw new Error(`Task not found: ${taskId}`);
      task.git = { ...task.git, ...gitPatch };
      Object.assign(task, taskPatch);
      task.updatedAt = now();
      return task;
    });
  }
}
