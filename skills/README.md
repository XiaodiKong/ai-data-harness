# 项目内 Skill 开发

本目录是独立 Skill 的开发源目录。用户目录中的副本用于安装和调用，不作为开发源。

## 开发与安装顺序

1. 在 `skills/<skill-name>/` 修改 Skill 及其配套文件。
2. 运行 Skill 校验，并检查本次修改涉及的行为规则；格式校验不等于实际行为验证。
3. 完成开发和验证后，将对应 Skill 同步到 `${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>/`。同步前检查目标是否有未回流到项目的修改，避免覆盖。
4. 比较项目源文件与安装副本，确认一致。后续修改继续从项目目录开始。

## 当前 Skill

- [文档定稿与版本验收](document-finalization/SKILL.md)：整合多轮讨论后的完整正文，分离变更记录，并主动发起具体版本验收。

## 跨 AI 使用与验证

`document-finalization/SKILL.md` 的正文是通用工作规则，可提供给其他 AI；`agents/openai.yaml` 仅用于平台展示。详细示例与交接模板位于该 Skill 的 `references/` 中，附件不可用时仍可依照核心规则工作。

当前版本为 v0.3.1；跨 AI 运行请从 [测试入口](../tests/skills/document-finalization-pilot/RUN-TESTS.md) 开始，入口会选择相应冻结批次。

启动指令和结果回传也已文件化：其他 AI 从 [document-finalization 测试入口](../tests/skills/document-finalization-pilot/AI-START.md) 获取任务，将结果保存为独立运行目录，接收方再读取文件复核，无需复制长提示词或原始对话。此协作约定仅用于该 Skill 的测试，不作为全项目默认规范，也不改变已冻结的 Skill 或测试批次。

行为评估规范见 [文档定稿评估案例](../tests/skills/document-finalization-cases.md)。格式校验通过不代表跨 AI 行为已验证。
