---
name: review
description: "对课程逐字稿做法律审查（依据律师审定的法规清单，风险分刑事、治安、网络信息内容、广告宣传、民事五类），输出问题片段标红、审查意见红黄标注的审查报告 docx，无问题时附合规审查意见。输入是视频时先经 transcribe skill 转写。仅在用户明确引用本 skill 时使用。legal review of course transcript, docx report."
disable-model-invocation: true
---

# 课程法律审查

审查对象是**逐字稿**（带时间戳的转写文本），产物是**审查报告**（逐字稿全文 + 内嵌审查意见的 docx）。法律判断由当前主模型自己完成，不派子 agent、不降级模型。

## 输入分流

- **视频文件或含视频的目录**：按此顺序查找 transcribe skill：`./.claude/skills/transcribe/SKILL.md`、`./.agents/skills/transcribe/SKILL.md`、`./.codex/skills/transcribe/SKILL.md`，再查用户主目录下同名三个位置。找到就完整执行它（输出目录用用户指定的，未指定则放视频旁的 `转写结果`），拿到每份 `transcript.md` 后回到本流程。找不到就停止，告诉用户安装地址 https://github.com/f4de01/transcribe-and-review ，不自行转写。
- **逐字稿（.md）、字幕（.srt）或含它们的目录**：执行 `PYTHON SCRIPT normalize INPUT`。SRT 会先转成同目录的 `transcript.md`。每份逐字稿输出一行 JSON，含 `path`、`title`、`segments`、`chunks`、`findings_path`、`report_path`；`warnings` 里的 “no format marker” 是旧逐字稿，照常审查；`error` 行（无时间戳文本、格式不认识）向用户说明原因并跳过该份。

首次运行时按 [references/setup.md](references/setup.md) 建环境。下文 `PYTHON` 指该环境 Python 的绝对路径，`SCRIPT` 指本 skill 的 `scripts/review_tool.py`；调用时替换成真实路径。

## 三遍审查

每份逐字稿独立走完三遍，审查依据只用 [references/legal-standards.md](references/legal-standards.md)（先完整读一遍再开始）。

1. **通读**：读完整份 `transcript.md`，记下课程主题与性质、讲师自述的身份和资质、收费项目及其承诺、目标受众，以及有无劝学员以迷信手段替代法律程序、医疗或法定义务的内容。这些是后两遍判断语境的依据。
2. **逐块**：`PYTHON SCRIPT chunk TRANSCRIPT --index N`（N 从 0 到 `chunks - 1`）逐块打印，上下文段只供理解。对本块每一段按 legal-standards.md 的每一章逐条比对构成要件，清单上的章节全部过完，不因已有发现而略过后面的章节；有嫌疑就记一条候选：起止段落的起始时间戳、风险类型、风险提示、法规依据、处理意见。
3. **回看**：每条候选过三问，任一答否就删除。行为要件是否由原话满足，而不是只出现了关键词？第 1 遍记下的全文语境是否支持这个判断？依据是法律、法规、规章或规范性文件，而不是平台规则？通过的条目中，相邻且同一事由的合并为一个问题片段。条数不设上下限，有多少标多少。

## 写 review.json 并出报告

把结果写到 normalize 给出的 `findings_path`（与逐字稿同目录的 `review.json`）：

```json
{"findings": [{"start": "00:12:03.200", "end": "00:12:19.800",
  "risk_type": "刑事", "risk": "…", "basis": "…", "advice": "…"}]}
```

- `start`、`end`：问题片段第一段和最后一段的**起始**时间戳，原样复制；单段片段两者相同。片段之间不得重叠。
- `risk_type`：`刑事`、`治安`、`网络信息内容`、`广告宣传`、`民事` 五选一；一个片段触及多个依据时按 legal-standards.md 的优先规则取最重的。
- `risk`：讲了什么行为、已满足和尚缺哪些要件、语境如何支持，一段话，单行。
- `basis`：法名 + 条号 + 一句话要件要点，不整条引用；多个依据用"；"并列。
- `advice`：自然语言的处理建议，写明删除、改口、补充说明或保留，具体到可以照着改，单行。
- 没有问题片段时 `findings` 为空列表，并加一个 `conclusion` 字段写通过意见：单行一段话，按 legal-standards.md"通过意见"一节的顺序写课程性质、讲师资质陈述、收费与承诺、结论。有问题片段时不得出现 `conclusion`。

```json
{"findings": [], "conclusion": "本课程为……。讲师……。课程收费……。经审查，本课程内容未发现……的法律风险。"}
```

然后 `PYTHON SCRIPT validate TRANSCRIPT`；报错就改 `review.json` 再验，直到输出 `valid`。再 `PYTHON SCRIPT render TRANSCRIPT`，生成 `<视频名>-审查报告.docx`（与逐字稿同目录）。报告版式由脚本固定：逐字稿标题行加粗，正文宋体小四 1.5 倍行距；问题片段连同时间戳整体红字；片段后另起一行，一个全角括号内先是红字的风险提示与依据，再是黄字的处理意见。有 `conclusion` 时，报告末尾由脚本加上加粗的"合规审查意见"标题、结论段，以及从 legal-standards.md 章节标题自动生成的"审查依据"一行。

## 交付

向用户报告每份报告的路径和问题片段数量；零条的说明报告末尾已附合规审查意见。不在对话里粘贴逐字稿全文，不描述审查过程。目录输入逐份完成、逐份报告，最后说明完成和跳过的数量。`review.json` 与报告同目录保留，改了它可以只重跑 `render`。

## 检验边界

报告按交付标准写，不加免责或复核提示。脚本只校验结构（时间戳存在、片段不重叠、字段齐全、零条时有 `conclusion`），不校验法律判断。审查依据以 `legal-standards.md` 为准，法规文本变化时先改它。
