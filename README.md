# transcribe&review

两个可独立安装的 agent skill，把课程视频变成带时间戳的逐字稿，再对逐字稿做法律审查并出具审查报告 docx。适用于 Claude Code、Codex 和其他读取 `SKILL.md` 的 agent。

| skill | 作用 | 输入 | 输出 |
| --- | --- | --- | --- |
| [`transcribe/`](transcribe/) | 本地语音识别 + 固定模型修复 | 视频文件或目录 | `transcript.md`（逐字稿） |
| [`review/`](review/) | 三遍法律审查 + 渲染报告 | 逐字稿、SRT，或视频（自动先转写） | `review.json` + `<视频名>-审查报告.docx` |

两者靠逐字稿文件格式串联（见 [docs/adr/0001](docs/adr/0001-transcript-file-as-skill-contract.md)）：只有视频时调用 `review`，它会找到 `transcribe` 先转写；已有逐字稿时直接调用 `review`；只要逐字稿就调用 `transcribe`。

## 安装

把 `transcribe` 和 `review` 两个文件夹整个复制到宿主的 skill 目录（必须含 `SKILL.md`、`scripts/`、`references/` 等全部文件）。两者独立，可以只装一个。

| 宿主 | 目录 | 调用方式 |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` 或项目 `.claude/skills/` | `/review …`、`/transcribe …` |
| Codex | `~/.codex/skills/` 或 `~/.agents/skills/`，或项目 `.agents/skills/` | `$review …`、`$transcribe …` |
| 其他 agent | 其读取 `SKILL.md` 的目录 | 按名字引用 |

PowerShell 示例（Claude Code）：

```powershell
git clone https://github.com/f4de01/transcribe-and-review.git
Copy-Item -Recurse .\transcribe-and-review\transcribe "$HOME\.claude\skills\transcribe"
Copy-Item -Recurse .\transcribe-and-review\review "$HOME\.claude\skills\review"
```

两个 skill 都不会被 agent 自动触发，只在用户明确引用时运行。首次运行时 agent 会按各自 `references/setup.md` 建立独立的 Python 环境；`transcribe` 另需下载本地语音模型。

完整的安装、配置、各种情况下调用哪个 skill，见 [docs/usage.md](docs/usage.md)。

## 法律依据

审查依据是 [review/references/legal-standards.md](review/references/legal-standards.md) 中律师审定的法规清单，风险分刑事、治安、网络信息内容、广告宣传、民事五类；每份逐字稿对整份清单审一遍，没有问题片段时报告末尾附合规审查意见。增减审查范围或法规文本变化时在该文件修改。

## 开发

- 术语：[GLOSSARY.md](GLOSSARY.md)。决策：[docs/adr/](docs/adr/)。
- 测试：`transcribe/scripts/test_transcribe.py`（文件协议，不需要模型）、`review/scripts/test_review_tool.py`（解析、校验、渲染）。在各 skill 的 `scripts/` 目录下用 `python -m unittest` 运行，review 的测试需要 python-docx。
- 渲染样例：`review/examples/sample/` 是有问题片段的虚构课程，`review/examples/clean/` 是零条、附合规审查意见的虚构课程，各有逐字稿和 `review.json`，`render` 后可直接打开 docx 核对版式。
- 真实视频的实测记录放 `docs/testing/`。
