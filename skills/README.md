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

当前版本为 v0.3.3；跨 AI 测试请从 [测试入口](../tests/skills/document-finalization-pilot/RUN-TESTS.md) 开始，入口会选择相应冻结批次。

## 离线安装与使用

在可访问项目的环境取得完整的 `skills/document-finalization/` 文件夹，通过内网或移动介质传到目标机器，再按目标 AI 的 Skill 安装方式放置。Codex 的用户级目标为 `${CODEX_HOME:-$HOME/.codex}/skills/document-finalization/`；保留 `SKILL.md`、`references/` 和 `agents/` 的相对结构，无需复制本项目的 `tests/`，无需运行联网安装脚本或下载方法网站。

核心规则和方法操作说明均在包内；外链只供可选溯源。没有 Skill 加载功能时，将 `SKILL.md` 的全文提供给 AI，需要时再提供本地参考文件。仅发送仓库链接不能满足离线读取要求。

这里的离线支持指 Skill 资料不依赖外网；目标环境仍需具备可用的 AI 推理和材料读取能力。任务若要求核验当前外部事实，需要可用的本地证据或后续补充材料，不能因断网跳过核验并声称完成。

本次修改及验证范围见 [v0.3.3 离线资料支持记录](../tests/skills/reports/2026-10-15-document-finalization-v0.3.3-offline/REPORT.md)。

## 测试与结果交接

启动指令和结果回传也已文件化：其他 AI 从 [document-finalization 测试入口](../tests/skills/document-finalization-pilot/AI-START.md) 获取任务，将结果保存为独立运行目录，接收方再读取文件复核，无需复制长提示词或原始对话。此协作约定仅用于该 Skill 的测试，不作为全项目默认规范，也不改变已冻结的 Skill 或测试批次。

行为评估规范见 [文档定稿评估案例](../tests/skills/document-finalization-cases.md)。格式校验通过不代表跨 AI 行为已验证。
