# 使用文档

本文面向使用者：怎么装、怎么配、遇到什么情况调用哪个 skill、结果在哪里、出错怎么办。

## 1. 两个 skill 各管什么

- **transcribe**：把本地课程视频转成逐字稿 `transcript.md`。语音识别在本机完成，之后由固定模型的子 agent 修复错字和标点，只交付修复稿。
- **review**：对逐字稿做法律审查，产出 `review.json` 和 `<视频名>-审查报告.docx`。输入是视频时，它会自己找 transcribe 先转写。

两者独立安装、独立运行。只装 review 也能审查已有的逐字稿；只装 transcribe 也能单独转写。

## 2. 安装

### 2.1 复制 skill 文件夹

把仓库里的 `transcribe` 和 `review` 两个文件夹整个复制到宿主的 skill 目录。文件夹内所有文件都要，不能只复制 `SKILL.md`。

| 宿主 | 用户级目录 | 项目级目录 |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | 项目根 `.claude/skills/` |
| Codex | `~/.codex/skills/` 或 `~/.agents/skills/` | 项目根 `.agents/skills/` |
| 其他 agent | 其文档指定的 skill 目录 | 同上 |

Windows 的 `~` 是 `C:\Users\<用户名>`。复制后新开一次会话，或按宿主要求重启，让 skill 列表刷新。

### 2.2 Python 环境

每个 skill 在自己文件夹里建一个 `.venv`，互不共享。首次调用时 agent 会按 `references/setup.md` 自动建立；也可以手动先建好：

```powershell
# transcribe（Windows PowerShell，在 transcribe 文件夹内）
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts/transcribe.py prepare --model base --model-dir models/base

# review（在 review 文件夹内）
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS 把 `py -3.11` 换成 `python3.11`，把 `.\.venv\Scripts\python.exe` 换成 `.venv/bin/python`。`prepare` 需要联网下载语音模型（base 约 150 MB）；之后转写完全离线。

### 2.3 修复模型（transcribe）

修复模型按宿主固定在 `transcribe/config.json` 的 `repair` 表里：

| 宿主 | 模型 | 推理强度 |
| --- | --- | --- |
| Claude Code | sonnet（Claude Sonnet 5.5） | low |
| Codex | gpt-5.6-luna | low |
| 其他 | 宿主默认 | 最低 |

要换模型就改这张表。agent 在派子 agent 前会检查宿主是否真的提供该模型；不提供时会列出候选让你选，不会悄悄换。

### 2.4 法律依据（review）

`review/references/legal-standards.md` 是审查的唯一依据清单，已由律师审定。要增减审查范围或更新法规文本就改这个文件。

## 3. 调用方式

两个 skill 都**不会自动触发**，必须在对话里点名：

- Claude Code：`/review …`、`/transcribe …`
- Codex：`$review …`、`$transcribe …`
- 其他 agent：按其引用 skill 的语法写名字

路径写你电脑上真实存在的路径。Windows 示例用 `D:\…`，macOS 用 `~/…`。

## 4. 各种情况调用什么

### 4.1 只有课程视频，要审查报告

调用 **review**，给视频路径。它会找到 transcribe 先转写，再审查：

```text
/review 审查 "D:\课程\第一讲.mp4"，转写结果放 "D:\转写结果"
```

结果在 `D:\转写结果\video-第一讲-<哈希>\` 下：`transcript.md`、`review.json`、`第一讲-审查报告.docx`。没装 transcribe 时 review 会停下并给出安装地址。

### 4.2 已有逐字稿，要审查报告

调用 **review**，给 `transcript.md` 路径：

```text
/review 审查 "D:\转写结果\video-第一讲-3f9a1c2b7d4e5f60\transcript.md"
```

旧版 transcribe 产出的逐字稿（首行没有 `<!-- transcript-format: v1 -->`）同样可用。

### 4.3 只有 SRT 字幕

同样调用 **review**，给 `.srt` 路径。它会在同目录生成 `transcript.md`（标题取字幕文件名）再审查；SRT 原件不动。

### 4.4 只要逐字稿，不审查

调用 **transcribe**：

```text
/transcribe 转写 "D:\课程\第一讲.mp4"，输出到 "D:\转写结果"
```

转写完成后它只报告逐字稿路径，不会接着审查。之后要审查再按 4.2 调用 review。

### 4.5 一个目录里有很多视频或逐字稿

- 视频目录：`/review 审查 "D:\课程" 下的视频`（默认不含子目录，需要时说“包含子目录”）。
- 逐字稿目录：`/review 审查 "D:\转写结果" 下所有逐字稿`。会递归找出每份 `transcript.md` 和 `.srt`，逐份出报告。

### 4.6 不要修复，只要离线原始转写

`/transcribe 仅本地离线转写 "D:\课程\第一讲.mp4"，关闭修复`。结果标为未修复，不是修复稿；同样可以送审。

## 5. 结果说明

- **transcript.md**：首行格式标记，然后 `# 视频名`，每段一行 `[00:00:01.200 --> 00:00:04.500] 文字`。
- **changes.json / complete.json**：修复记录和完成标记，不用动。
- **review.json**：审查结果，每条含起止时间戳、风险类型（刑事 / 治安 / 网络信息内容 / 广告宣传 / 民事）、风险提示、法规依据、处理意见。没有问题片段时 `findings` 为空，另有一个 `conclusion` 字段是通过意见。改了它可以让 agent 重新 `render`，不必重审。
- **<视频名>-审查报告.docx**：逐字稿全文。问题片段连同时间戳红字；片段后另起一行，括号内红字是风险提示和依据，黄字是处理意见。无问题时末尾附"合规审查意见"：一段结论和一行审查依据，依据名单从 `legal-standards.md` 的章节标题自动生成。

## 6. 中断与重跑

- 转写时中断：下次重新识别该视频。识别完、修复中中断：复用中间文件，只补缺的块。中间文件在输出目录的 `.work/` 下。
- 同一视频、同一配置再跑会直接跳过；视频或配置变了会生成新的结果目录，不覆盖旧的。
- 已完成的 `transcript.md` 被手工改过后，再跑会报冲突；换一个输出目录。
- 审查可以随时重跑：删掉或改写 `review.json` 后再调用 review，报告会被重新生成。

## 7. 改报告样式

字体、字号、行距、红黄颜色都是 `review/scripts/review_tool.py` 顶部的常量。改完让 agent 对该逐字稿再执行一次 `render` 即可，不需要重审。

## 8. 常见错误

| 提示 | 原因 | 处理 |
| --- | --- | --- |
| `not a timestamped segment` | 给的 .md 不是逐字稿格式（没有时间戳） | 用 transcribe 重新转写，或提供 SRT |
| `unsupported transcript format` | 格式标记版本不认识 | 更新 review skill |
| `is not a segment start timestamp` | review.json 里的时间戳和逐字稿对不上 | agent 会自行修正；手工改过 review.json 时核对时间戳 |
| `findings overlap` | 两个问题片段重叠 | 合并成一条 |
| `conclusion must be a non-empty string` | 没有问题片段但 review.json 缺通过意见 | agent 会补写 `conclusion`；手工改过 review.json 时补上 |
| `conclusion is only allowed when findings is empty` | 有问题片段却带了 `conclusion` | 删掉 `conclusion` |
| `exists with different content` | SRT 旁已有不同内容的 transcript.md | 移走旧文件，或直接审查那份 .md |
| `Incomplete local model` | 语音模型没下载完 | 重新执行 `prepare` |
| 子 agent 模型不可用 | 宿主不提供表中模型 | 从 agent 列出的候选里选一个，或改 config.json |

## 9. 更新 skill

重新复制整个文件夹覆盖旧版即可。`.venv` 和 `models/` 在 skill 文件夹内，覆盖时保留它们就不用重装。
