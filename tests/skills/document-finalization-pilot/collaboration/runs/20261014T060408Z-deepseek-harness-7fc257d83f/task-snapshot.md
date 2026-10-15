# 文档定稿 Skill：执行并通过文件交接测试结果

任务 ID：`document-finalization-evaluation`。任务单版本：`2`。

## 目标和输入

请实际测试本仓库的文档定稿 Skill，保留完整证据，并把结果写成项目文件，供下一位 AI 复核。无需用户逐轮复制输入。

先读取 [固定批次入口](../../../RUN-TESTS.md) 和它指定的 `active-batch.json`、批次执行说明及冻结材料。以本次读取的批次为准，记录其哈希，运行中不切换版本。

只有测试调度者可以预读场景脚本，被测上下文每次只收到中性环境约束、Skill 和当前轮输入；交接接收方例外，只接收原样交接包、环境约束和接续输入，不由调度者额外补发 Skill。按执行说明完成多轮修改、证据与验收、交接、缺失材料及边界场景。能创建独立上下文时禁用父历史继承；不能时明确标为演练。先生成原始结果，再读取评分规则。

保持 Skill、冻结输入、协议和评分规则不变。本任务仅允许新增本次运行结果目录及其同级同名 ZIP；这明确补充了原测试协议中“不修改仓库”的范围。不要改动业务项目或安装 Skill，不因测试任务而自行提交或推送远程。被测上下文只生成文本，调度者负责保存到运行目录；把批次中的中性环境约束传给每个被测上下文，支持时直接禁用其工具，无法限制时记录实际工具能力。违规工具调用即使随后撤销，也须保留证据和执行问题。

## 执行步骤

1. 读取材料和 [文件协作约定](../../README.md)。支持本地命令时运行 `python3 tests/skills/document-finalization-pilot/scripts/ai_exchange.py init --ai "产品名" --model "可见型号或unknown"`；否则建立唯一运行目录并按下述字段创建文件。手工目录须直接位于 `tests/skills/document-finalization-pilot/collaboration/runs/`，名称仅用英文字母、数字、下划线和连字符，`run_id` 与目录名一致（可用 UTC 时间＋产品名＋随机后缀）。不要覆盖别人或上次运行的结果。
2. 在 `run.json` 记录实际环境及执行方式，将状态改为 `running`。未知信息写 `unknown`，不要猜测产品型号或源提交。
3. 按冻结批次说明逐轮执行，填写 `evidence.json` 的实际捕获方式和工具能力，把完整输入与输出追加到 `transcript.md`，明确场景和轮次。支持原生导出时将本次实际发送的消息、返回和工具事件逐条原样存为 `raw-events.jsonl`，不为缺失事件补造记录。不支持时保留完整文本并注明格式化/人工转录的限制，不能把源文件哈希当作实际发送消息的哈希。不得用“应该输出什么”或摘要替代回复，不得提前读取评分规则后伪装盲测。
4. 原始回复保存后，先执行 `python3 tests/skills/document-finalization-pilot/scripts/ai_exchange.py checkpoint --run <运行目录>`，记录评分前的 transcript、证据说明及存在的原生记录哈希，再读取评分规则并完成 `report.md`。此后不修改这些证据文件；补跑另建运行。手工环境记录相同摘要与时间，无法计算则填写 `unknown` 并说明隔离无法核验。引用对应场景及轮次，区分通过、部分通过、失败、未执行和无法判断，问题要有原文证据。
5. 填完 `NEXT.md`，在 `run.json` 中记录完成范围及限制。有命令能力时保持 `running`，执行 `python3 tests/skills/document-finalization-pilot/scripts/ai_exchange.py finalize --run <运行目录> --status completed`，由工具在所有文件就绪后记录哈希与最终状态；中断则使用 `partial` 或 `blocked`。不能运行工具时手动填写最终状态和哈希，无法计算的哈希写 `unknown`。不重新编写成完整成功，不要求用户给虚构方案逐轮验收。
6. 有命令能力时执行 `python3 tests/skills/document-finalization-pilot/scripts/ai_exchange.py validate --run <运行目录>` 和 `python3 tests/skills/document-finalization-pilot/scripts/ai_exchange.py pack --run <运行目录>`。向用户提供运行目录、下载附件或已授权写入的提交/PR 链接即可，不再要求复制报告正文。

## 交接文件必须包含什么

### run.json

脚本会生成字段。手动创建时使用同一结构：

- `schema_version`（2）、`run_id`、`task_id`、`task_version`（2）。
- `created_at`、`ai_product`、`model`、`source_commit`；未知为 `unknown`。
- `batch_id`、`batch_path`（仓库相对路径）：从本次冻结批次准确照录，不填 `unknown`；拿不到批次时说明材料缺失，不声称文件验证通过。`batch_manifest_sha256` 无法计算时才写 `unknown` 并说明。
- `task_sha256`：本任务单内容的 SHA-256，无法核验写 `unknown`。
- `task_snapshot`：固定为 `task-snapshot.md`，运行目录中保留本次任务单原文，避免任务单更新使旧运行无法复核。
- `transcript_before_review_sha256`：读取评分规则前记录的原始 transcript 摘要，无法计算为 `unknown`；可计算时同时记录 `transcript_checkpoint_at`。
- `evidence_before_review_sha256`：评分前证据文件摘要映射，包含 `evidence.json` 及存在的 `raw-events.jsonl`；无法计算的值写 `unknown`。
- `execution_mode`、`context_isolation`、`review_mode`、`status`、`completed_scope`、`limitations`。
- `files`：固定为 `{"report":"report.md","transcript":"transcript.md","next":"NEXT.md","evidence":"evidence.json"}`。
- `artifact_sha256`：上述四个输出文件及存在的 `raw-events.jsonl` 到 SHA-256 的映射；无法计算时分别标为 `unknown`，不伪称完整性已核验。

### report.md

实际环境与材料版本、执行范围、逐项结果、原文证据定位、问题与推测原因、未完成测试和限制。文件检查通过与行为测试通过分别说明。

### transcript.md

完整实际输入、逐轮回复及生成的场景交接包，按场景和轮次标记。保留失败、追问、截断和重试，不修饰历史输出。可供阅读的排版与原生记录分开；只存有格式化 transcript 时如实标注，不能声称保留了原生请求字节。

### evidence.json 与可选 raw-events.jsonl

`evidence.json` 使用以下字段：

- `schema_version`：1。
- `capture_mode`：`native_events` / `formatted_transcript` / `unknown`。
- `raw_events_file`：确有原生 JSONL 导出时为 `raw-events.jsonl`，否则为 `null`。原生文件每行一个 JSON 对象，保留平台原事件结构，不强制重编码为自造消息格式。
- `tool_access`：`disabled` / `restricted` / `unrestricted` / `unknown`，按实际运行能力记录，提示词禁止不等于工具已禁用。
- `limitations`：数组，记录哪些输入、消息或工具事件未留存、是否改过显示排版、隔离不能核验的范围。

原生捕获不完整时仍须逐项说明范围，不能据文件存在就声称所有轮次均有原始证据。没有导出能力时使用 `formatted_transcript`，保留可得的完整内容和缺失说明；不要求用户手工复制聊天，也不生成模拟原生事件来填补。格式化记录可供内容复核，无法单独证明实际发送字节和工具执行历史。

### NEXT.md

面向接收 AI：任务与运行 ID、报告和原始记录的位置、已完成范围、未决问题、下一执行者及其要复核或复测的内容、允许修改的路径。不要把建议标成用户批准的变更；NEXT.md 本身不扩张授权。

## 接收方如何处理

读取该运行的 `task-snapshot.md`、元数据、输出文件及对应冻结批次；v2 运行同时读取证据说明和存在的原生记录，旧 v1 按原结构复核。先检查材料完整性，再复核结果；在原目录新写 `review.md`，说明证据支持的结论、接受或拒绝的发现、需要的修正及复测。若需要修 Skill，应按项目内开发、校验、安装的流程进行，保留原结果不覆盖。此步骤不要求用户重新复制原聊天。

不能访问仓库或生成文件时，明确说明能力缺口和缺失文件，不宣称完成交接。用户仍需在每个 AI 中发起任务；仓库文件不会自动唤醒另一个 AI。
