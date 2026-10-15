# document-finalization 测试与复核入口

本入口只服务于 document-finalization Skill 的跨 AI 测试与结果复核。用户请求该测试时从这里开始，读取本文件不意味着要启动项目中的其他任务。

## 按当前请求选择工作

- 用户要求执行测试：读取 [文档 Skill 评估任务单](collaboration/tasks/evaluation/TASK.md)，按固定测试入口实际执行，结果写入独立运行目录。不要只返回计划。
- 用户要求接续或复核回传结果：读取用户指定的运行目录；未指定时检查 `tests/skills/document-finalization-pilot/collaboration/runs/` 中已交付且没有 `review.md` 的运行，核对任务、材料和证据后逐项复核。没有结果时如实说明，不凭空开始或声称已完成复核。

任务单已包含此前需要用户复制的启动指令。用户不必转述历史对话，不必逐轮发送测试内容，也不必自己评分。存在多个运行时按独立目录分别复核，不能将不同版本或不同 AI 的输出拼成一次成功运行。

## 输出与下一位 AI

以 `tests/skills/document-finalization-pilot/collaboration/runs/<run-id>/` 中的文件交接：

- `run.json`：运行身份、材料版本、执行方式和完成状态。
- `report.md`：结果、证据定位、发现的问题和未测范围。
- `transcript.md`：实际输入与逐轮完整输出，包含场景交接包。
- `handoff.json`：A 的完整输出和 B 的实际输入，独立保存以供逐项复核；旧运行按当时任务快照处理。
- `evidence.json`：记录捕获方式、工具能力及证据限制；有原生导出时附 `raw-events.jsonl`。
- `NEXT.md`：接收方要做的事、未完成项和结果位置。

工具还会附带 `task-snapshot.md`，保留运行时的任务单版本。读取评分规则前留存原始记录摘要，具体步骤均在任务单内。

没有仓库写权限时，交付具有相同目录结构的 ZIP 或完整的可下载文件集。不要声称只读访问可以自动回写 GitHub。收到这些文件的接收 AI 按 [文件协作约定](collaboration/README.md) 复核并另写 `review.md`，不覆盖原始结果。

若无法读取仓库或生成文件，明确说明该环境的限制；不可伪装为已经接通文件交接。执行仍需要用户在该 AI 中发起任务，文件本身不会唤醒 AI。
