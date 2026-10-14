# AI Data Harness

面向 AI 数据研发的控制与执行平台，连接需求、知识、代码、工具、工作流与验收证据。

当前方案以 CLI 访问云端数字人为统一入口，由云端平台承载完整研发事项管理；AI-Data 提供领域知识、Skills、工具适配、流程模板与验收规则，复用现有数据平台的计算、发布和调度。云端自主执行能力已由用户确认，持久流程、恢复和生产控制等能力仍需逐项核验。

当前仓库包含平台技术设计方案和 Taskflow Board 插件，完整平台能力仍处于设计与逐步实现阶段。

## 方案阅读顺序

1. [技术方案 v1.1：云端数字人集成架构与落地路线](docs/architecture/AI-Data-Harness-Technical-Design-v1.1.md)：当前架构基线，说明职责分配、专业能力交付、阶段路线及对 v1.0 的调整。
2. [云端数字人平台能力要求与验收 v1.0](docs/architecture/Cloud-Digital-Human-Platform-Requirements-v1.0.md)：用于云端团队能力盘点、CLI 契约对齐及跨天与故障验收。
3. [技术设计 v1.0](docs/architecture/AI-Data-Harness-Technical-Design-v1.0.md)：保留语义、影响分析、研发验证和生产操作的详细参考；架构归属与实施路线按 v1.1 更新。

## 仓库内容

- `docs/architecture/`：架构方案、平台能力要求与验收设计，阅读顺序见上。
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

## 文档定稿与版本验收 Skill

[Skill 源文件](skills/document-finalization/SKILL.md) 用于多轮文档整合、论据检查、决策记录分离和版本验收。

### 在其他 AI 中测试

统一入口是 [AI-START.md](AI-START.md)。让新 AI 读取并执行该文件即可，启动指令、测试步骤和回传要求均已写入项目，不必复制长提示词。

AI 按 [任务单](ai-collaboration/tasks/document-finalization-evaluation/TASK.md) 执行，将结果写成 `ai-collaboration/runs/<run-id>/` 下的四个交接文件；下一位 AI 直接读取结果并另写复核意见。没有 GitHub 写权限时，返回 ZIP 或可下载文件，用户只需传递附件。

[测试入口](tests/skills/document-finalization-pilot/RUN-TESTS.md) 仍保持有效，当前固定批次为 v0.3.0，旧批次保留回测。文件管理工具不执行模型测试；读取 GitHub 不代表能自动回写，具体能力与执行限制必须记录。完整流程见 [文件协作约定](ai-collaboration/README.md)。
