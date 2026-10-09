# AI Data Harness

面向 AI 数据研发的控制与执行平台，连接需求、知识、代码、工具、工作流与验收证据。

当前仓库包含平台技术设计方案和 Taskflow Board 插件，完整平台能力仍处于设计与逐步实现阶段。

## 仓库内容

- [技术设计方案](docs/architecture/AI-Data-Harness-Technical-Design-v1.0.md)：平台架构、核心对象、工作流与实施路线。
- [Taskflow Board](plugins/taskflow-board/README.md)：本地四泳道任务面板，提供任务管理、Codex 对话关联和 Git worktree 工作流。
- `.agents/plugins/marketplace.json`：本地插件目录配置。

## 开发与验证

Taskflow Board 使用 Node.js 18 或更新版本，无第三方运行依赖。

```bash
cd plugins/taskflow-board
npm test
npm run preview
```

预览地址为 `http://127.0.0.1:4173`。
