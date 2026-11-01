# 环境准备

只需 python-docx，Python 3.9 以上均可；建议 3.11。不要修改全局 Python 包。先定位安装后的 skill 目录并从该目录执行。

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts/review_tool.py --help
```

macOS：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/review_tool.py --help
```

脚本子命令：`normalize`（接受 .md、.srt 或目录，SRT 转成 transcript.md，输出统计）、`chunk`（打印第 N 块，前后各带两段上下文）、`validate`（校验 review.json）、`render`（校验并生成 docx）。Windows 上脚本输出中文时设置 `PYTHONUTF8=1` 可避免编码问题。

报告样式（字体、字号、行距、红黄颜色）是脚本顶部的常量；改完重新 `render` 即可，不需要改 review.json。
