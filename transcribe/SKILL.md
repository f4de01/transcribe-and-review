---
name: transcribe
description: "将本地课程视频转成带时间戳的 Markdown 逐字稿：本地语音识别（faster-whisper），再由按宿主固定的模型修复，只交付修复稿。仅在用户明确引用本 skill 时使用。transcribe video to timestamped transcript."
disable-model-invocation: true
---

# 视频转写

## 运行约定

两阶段：本地语音识别 → 子 agent 修复。默认多语种 base、CPU INT8、beam_size=1，优先速度；中文转简体，英文保留英文，不翻译、不总结、不区分讲话人。轻量识别的漏听不能靠文字修复可靠补回。

修复模型按宿主固定，写在 `config.json` 的 `repair` 表里，脚本用 `--host` 选取：

| 宿主 | `--host` | 修复模型 | 推理强度 |
| --- | --- | --- | --- |
| Claude Code | `claude` | `sonnet`（Claude Sonnet 5.5） | `low` |
| Codex | `codex` | `gpt-5.6-luna` | `low` |
| 其他 agent | `other` | 宿主默认模型 | 宿主最低档 |

派子 agent 前先确认宿主的子 agent 工具能指定该模型和推理强度。不能明确匹配时，列出实际可用候选让用户选择；不得静默替换、不得用主模型冒充指定模型、不得改走 API。用户可以临时覆盖（`--repair-model`、`--repair-effort`）。宿主没有子 agent 工具时，由当前 agent 自己按 [references/repair.md](references/repair.md) 逐块修复，并在交付说明中写明修复由主 agent 完成。

语音识别完全本地；修复只发送转写文字及时间轴给子 agent。首次可联网安装依赖和下载模型。用户可以关闭修复（`--no-repair`），改为仅离线转写；这时结果标为未修复，不能称作修复稿。

## 工作流程

1. 确认当前操作系统和宿主，使用用户提供的实际输入路径和输出目录。Windows 盘符示例只适用于 Windows；macOS 使用本机路径（如 `~/Movies/课程.mp4`），展开 `~` 并验证文件存在，不能照抄示例盘符或虚构用户名。未指定输出目录时使用当前工作区的 `转写结果` 子目录。默认不扫描子目录；需要时加 `--recursive`。支持格式由脚本的 `EXTENSIONS` 定义。只读取源视频，不移动或改名。先完成上述修复模型检查，避免长时间识别后才发现无法修复。
2. 首次运行或环境缺失时读 [references/setup.md](references/setup.md)，创建隔离环境并准备本地模型。运行脚本 `--help` 了解参数。以下 `PYTHON` 指环境中 Python 的绝对路径，`SCRIPT` 指本 skill 的 `scripts/transcribe.py`；调用时替换成真实路径，不把占位符直接交给 shell。
3. 执行：`PYTHON SCRIPT transcribe INPUT --model-dir MODEL_DIR --output OUTPUT --host HOST`。关闭修复则加 `--no-repair`。脚本输出 JSON 行：`pending` 包含 job 路径；`skipped` 表示相同输入和配置已经完成；`error` 表示该视频失败，其余视频继续。非零退出码时也处理已经生成的 pending job。
4. 对每个 pending job，读取其中 `job.json` 和 `chunk-*.json`。按 [references/repair.md](references/repair.md) 派出子 agent，显式传入表中的模型和推理强度。每个任务只分配具体的 chunk 输入和 repair 输出路径；不要继承整场对话或视频路径。并行数不超过宿主额度，默认至多两个修复子 agent；多个块可由同一个 agent 顺序完成。
5. 所有块完成后执行 `PYTHON SCRIPT finalize JOB_PATH`。脚本校验每块的段落 ID、数量、文字及修改理由，时间轴始终从原始段落取；任一块失败则整件不发布。允许让子 agent 按具体校验错误修正一次；再次失败就报告并保留待处理状态，不无限重试。
6. 最终逐字稿为 `transcript.md`：首行是格式标记 `<!-- transcript-format: v1 -->`，然后 `# 视频名`，之后每段一行 `[HH:MM:SS.mmm --> HH:MM:SS.mmm] 文字`，按原讲话顺序分段，不添加总结或改写内容；不生成 TXT 或 SRT。结果目录中的 `changes.json` 和 `complete.json` 用于疑点记录与完成校验。修改记录只记录段落 ID、时间和修改理由，不存原文或逐字差异。原始段落及修复分块在成功发布后自动删除。只有全部输出落盘且校验完成才算成功；批量结果须说明完成、跳过、失败数量。

## 中断、重新处理与清理

中间文件位于输出目录 `.work/`，用于修复和中断恢复，不是交付物。识别时中断会在下次重新识别该视频；识别完成后中断则复用 job，继续缺失的修复块。报告失败时明确临时文件还在，并给出 `PYTHON SCRIPT clean JOB_PATH` 的清理命令。用户要求立即不保留中间文件时执行该命令，之后重试须重新识别。

完成标记绑定视频内容、源路径、识别参数、宿主和修复模型配置，并校验交付文件哈希；视频、配置变化会创建新结果目录。同名但不同路径的视频不会互相覆盖。若已完成文件被用户修改，脚本拒绝覆盖并报告冲突；选另一个输出目录重跑。

## 交接

转写完成后向用户报告每份 `transcript.md` 的路径。本 skill 只做转写，不做法律审查，也不自动调用其他 skill。用户要审查时，告知可用 review skill 处理该 `transcript.md`（Claude Code 输入 `/review`，Codex 输入 `$review`）。

## 检验边界

JSON 结构校验不是内容正确率验证。首次在目标设备上跑一段含中文、英文、静音的真实视频，检查是否漏转、专名是否正确；Windows 和 macOS 分别验证才可声称两端实测。宿主工具不支持指定子 agent 模型时直接说明限制。
