"""Transcript normalisation, review.json validation and docx rendering (Python 3.9+).

Input contract (transcript format v1, produced by the transcribe skill):
    <!-- transcript-format: v1 -->      optional marker; absent on older transcripts
    # <title>
    [HH:MM:SS.mmm --> HH:MM:SS.mmm] text   one paragraph per segment

review.json contract (written by the agent):
    {"findings": [{"start": "HH:MM:SS.mmm", "end": "HH:MM:SS.mmm",
                   "risk_type": "刑事|治安|网络信息内容",
                   "risk": "...", "basis": "...", "advice": "..."}]}
start/end are the START timestamps of the first and last segment of the span.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FORMAT_MARKER = '<!-- transcript-format: v1 -->'
MARKER_RE = re.compile(r'^<!--\s*transcript-format:\s*(\S+)\s*-->$')
SUPPORTED_FORMATS = {'v1'}
SEGMENT_RE = re.compile(r'^\[(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\] (.*)$')
SRT_TIME_RE = re.compile(r'^(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})')
NO_SPEECH = '（未检测到语音）'
RISK_TYPES = ('刑事', '治安', '网络信息内容')
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.mpeg', '.mpg', '.wmv', '.ts'}
WORK_DIRS = {'.work', '.venv', 'node_modules', '.git'}
REPORT_SUFFIX = '-审查报告.docx'
FINDINGS_FILE = 'review.json'
CHUNK_CHARS = 6000
CONTEXT_SEGMENTS = 2

# Report style: change here, re-run render.
FONT_EAST_ASIAN = '宋体'
FONT_LATIN = 'Times New Roman'
BODY_SIZE_PT = 12        # 小四
TITLE_SIZE_PT = 15       # 小三
LINE_SPACING = 1.5
COLOR_PROBLEM = 'FF0000'  # 问题片段与风险提示
COLOR_ADVICE = 'FFFF00'   # 处理意见


def emit(status, **kwargs):
    print(json.dumps(dict(status=status, **kwargs), ensure_ascii=False), flush=True)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def parse_transcript(path):
    """Return dict(title, segments=[dict(index,start,end,text)], marker, warnings)."""
    path = Path(path)
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    title, marker, segments, warnings = None, None, [], []
    for number, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if not line:
            continue
        found = MARKER_RE.match(line)
        if found and marker is None and title is None:
            marker = found.group(1)
            if marker not in SUPPORTED_FORMATS:
                raise ValueError(f'{path.name}: unsupported transcript format {marker!r}; this tool reads {sorted(SUPPORTED_FORMATS)}')
            continue
        if title is None and line.startswith('# '):
            title = line[2:].strip()
            continue
        if line == NO_SPEECH:
            continue
        found = SEGMENT_RE.match(line)
        if not found:
            raise ValueError(f'{path.name} line {number}: not a timestamped segment; input must be transcript format v1 or SRT')
        start, end, text = found.groups()
        if segments and start < segments[-1]['start']:
            raise ValueError(f'{path.name} line {number}: timestamps go backwards')
        segments.append(dict(index=len(segments), start=start, end=end, text=text))
    if title is None:
        raise ValueError(f'{path.name}: missing "# title" line')
    if marker is None:
        warnings.append('no format marker; accepted as v1 by line format')
    return dict(title=title, segments=segments, marker=marker, warnings=warnings, path=str(path))


def srt_to_transcript(srt_path):
    srt_path = Path(srt_path)
    blocks = re.split(r'\n\s*\n', srt_path.read_text(encoding='utf-8-sig').strip())
    paragraphs = []
    for block in blocks:
        rows = [r.strip() for r in block.splitlines() if r.strip()]
        if not rows:
            continue
        if rows and rows[0].isdigit():
            rows = rows[1:]
        if not rows:
            continue
        found = SRT_TIME_RE.match(rows[0])
        if not found:
            raise ValueError(f'{srt_path.name}: block without a timestamp line: {rows[0][:40]!r}')
        start, end = (x.replace(',', '.') for x in found.groups())
        text = ' '.join(rows[1:]).strip()
        if text:
            paragraphs.append(f'[{start} --> {end}] {text}')
    body = '\n\n'.join(paragraphs) + '\n' if paragraphs else NO_SPEECH + '\n'
    return FORMAT_MARKER + '\n# ' + srt_path.stem + '\n\n' + body


def normalize_one(path):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() == '.srt':
        target = path.with_name('transcript.md')
        text = srt_to_transcript(path)
        if target.exists() and target.read_text(encoding='utf-8-sig') != text:
            raise ValueError(f'{target} exists with different content; move it aside or review it directly')
        target.write_text(text, encoding='utf-8')
        path = target
    data = parse_transcript(path)
    data['chunks'] = len(list(chunk_ranges(data['segments'])))
    data['chars'] = sum(len(s['text']) for s in data['segments'])
    return path, data


def discover(root):
    root = Path(root).expanduser().resolve()
    if root.is_file():
        return [root]
    found = []
    for p in sorted(root.rglob('*')):
        if any(part in WORK_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file() and p.suffix.lower() in {'.md', '.srt'} and not p.name.endswith('.review.md'):
            if p.suffix.lower() == '.md':
                head = p.read_text(encoding='utf-8-sig', errors='replace')[:4000]
                if not re.search(SEGMENT_RE.pattern, head, re.M) and NO_SPEECH not in head:
                    continue
            found.append(p)
    return found


def chunk_ranges(segments, limit=CHUNK_CHARS):
    start, size = 0, 0
    for i, seg in enumerate(segments):
        length = len(seg['text'])
        if i > start and size + length > limit:
            yield start, i
            start, size = i, 0
        size += length
    if segments:
        yield start, len(segments)


def format_segment(seg):
    return f"[{seg['start']} --> {seg['end']}] {seg['text']}"


def show_chunk(data, index, limit=CHUNK_CHARS):
    ranges = list(chunk_ranges(data['segments'], limit))
    if not 0 <= index < len(ranges):
        raise ValueError(f'chunk index out of range: 0..{len(ranges) - 1}')
    lo, hi = ranges[index]
    segs = data['segments']
    out = [f'# {data["title"]}  (chunk {index + 1}/{len(ranges)}, segments {lo}-{hi - 1})']
    before = segs[max(0, lo - CONTEXT_SEGMENTS):lo]
    after = segs[hi:hi + CONTEXT_SEGMENTS]
    if before:
        out.append('--- 上文（仅供理解，不在本块审查范围）---')
        out.extend(format_segment(s) for s in before)
    out.append('--- 本块 ---')
    out.extend(format_segment(s) for s in segs[lo:hi])
    if after:
        out.append('--- 下文（仅供理解，不在本块审查范围）---')
        out.extend(format_segment(s) for s in after)
    return '\n\n'.join(out)


def validate_findings(data, findings):
    """Return findings sorted, each with resolved lo/hi segment indexes. Raise on any defect."""
    if not isinstance(findings, dict) or set(findings) != {'findings'}:
        raise ValueError('review.json must be an object with exactly one key: findings')
    rows = findings['findings']
    if not isinstance(rows, list):
        raise ValueError('findings must be a list')
    by_start = {}
    for seg in data['segments']:
        by_start.setdefault(seg['start'], seg['index'])
    resolved = []
    required = {'start', 'end', 'risk_type', 'risk', 'basis', 'advice'}
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError(f'finding {n}: fields must be exactly {sorted(required)}')
        for key in ('risk', 'basis', 'advice'):
            value = row[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'finding {n}: {key} must be a non-empty string')
            if '\n' in value or '\r' in value:
                raise ValueError(f'finding {n}: {key} must be a single line')
        if row['risk_type'] not in RISK_TYPES:
            raise ValueError(f'finding {n}: risk_type must be one of {RISK_TYPES}')
        if row['start'] not in by_start:
            raise ValueError(f'finding {n}: start {row["start"]} is not a segment start timestamp in the transcript')
        if row['end'] not in by_start:
            raise ValueError(f'finding {n}: end {row["end"]} is not a segment start timestamp in the transcript')
        lo, hi = by_start[row['start']], by_start[row['end']]
        if hi < lo:
            raise ValueError(f'finding {n}: end comes before start')
        resolved.append(dict(row, lo=lo, hi=hi))
    resolved.sort(key=lambda r: (r['lo'], r['hi']))
    for prev, cur in zip(resolved, resolved[1:]):
        if cur['lo'] <= prev['hi']:
            raise ValueError(f'findings overlap: {prev["start"]}..{prev["end"]} and {cur["start"]}..{cur["end"]}; merge them')
    return resolved


def report_path(transcript_path, title):
    name = re.sub(r'[\\/:*?"<>|\r\n]', '_', title).strip() or 'transcript'
    return Path(transcript_path).with_name(name + REPORT_SUFFIX)


def render_docx(data, resolved, target):
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = FONT_LATIN
    style.font.size = Pt(BODY_SIZE_PT)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_EAST_ASIAN)
    style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    style.paragraph_format.line_spacing = LINE_SPACING

    def run(paragraph, text, color=None, bold=False, size=None):
        r = paragraph.add_run(text)
        r.font.name = FONT_LATIN
        r._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_EAST_ASIAN)
        if size:
            r.font.size = Pt(size)
        if bold:
            r.font.bold = True
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        return r

    run(doc.add_paragraph(), data['title'], bold=True, size=TITLE_SIZE_PT)
    if not data['segments']:
        run(doc.add_paragraph(), NO_SPEECH)
    by_lo = {f['lo']: f for f in resolved}
    active = None
    for seg in data['segments']:
        if seg['index'] in by_lo:
            active = by_lo[seg['index']]
        colored = active is not None and active['lo'] <= seg['index'] <= active['hi']
        run(doc.add_paragraph(), format_segment(seg), color=COLOR_PROBLEM if colored else None)
        if active is not None and seg['index'] == active['hi']:
            p = doc.add_paragraph()
            run(p, f"（风险提示：【{active['risk_type']}】{active['risk']} 依据：{active['basis']}；", color=COLOR_PROBLEM)
            run(p, f"处理意见：{active['advice']}", color=COLOR_ADVICE)
            run(p, '）', color=COLOR_PROBLEM)
            active = None
    doc.save(str(target))
    return target


def cmd_normalize(args):
    source = Path(args.input).expanduser().resolve()
    if not source.exists():
        raise ValueError('Input does not exist: ' + str(source))
    if source.is_file() and source.suffix.lower() in VIDEO_EXTENSIONS:
        emit('video', path=str(source), hint='run the transcribe skill first, then review its transcript.md')
        return 2
    paths = discover(source)
    if not paths:
        raise ValueError('No transcript (.md with timestamped segments) or .srt found under ' + str(source))
    failures = 0
    for p in paths:
        try:
            path, data = normalize_one(p)
            emit('transcript', path=str(path), title=data['title'], segments=len(data['segments']),
                 chars=data['chars'], chunks=data['chunks'], marker=data['marker'], warnings=data['warnings'],
                 findings_path=str(path.with_name(FINDINGS_FILE)),
                 report_path=str(report_path(path, data['title'])))
        except Exception as exc:
            failures += 1
            emit('error', path=str(p), error=str(exc))
    return 1 if failures else 0


def cmd_chunk(args):
    data = parse_transcript(Path(args.transcript).expanduser().resolve())
    if args.index is None:
        emit('chunks', count=len(list(chunk_ranges(data['segments']))))
        return 0
    print(show_chunk(data, args.index))
    return 0


def load_valid(args):
    transcript = Path(args.transcript).expanduser().resolve()
    data = parse_transcript(transcript)
    findings_path = Path(args.findings).expanduser().resolve() if args.findings else transcript.with_name(FINDINGS_FILE)
    resolved = validate_findings(data, read_json(findings_path))
    return resolved, data, transcript, findings_path


def cmd_validate(args):
    resolved, data, transcript, findings_path = load_valid(args)
    emit('valid', transcript=str(transcript), findings=str(findings_path), count=len(resolved))
    return 0


def cmd_render(args):
    resolved, data, transcript, findings_path = load_valid(args)
    target = Path(args.output).expanduser().resolve() if args.output else report_path(transcript, data['title'])
    render_docx(data, resolved, target)
    emit('rendered', report=str(target), findings=len(resolved), segments=len(data['segments']))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('normalize', help='Accept a transcript.md, an .srt, or a directory; convert SRT; report stats as JSON lines')
    p.add_argument('input')
    p = sub.add_parser('chunk', help='Print chunk N of a transcript with 2 context segments each side; omit --index to count chunks')
    p.add_argument('transcript')
    p.add_argument('--index', type=int)
    p = sub.add_parser('validate', help='Check review.json against the transcript; non-zero exit on any defect')
    p.add_argument('transcript')
    p.add_argument('--findings')
    p = sub.add_parser('render', help='Validate, then write <title>-审查报告.docx beside the transcript')
    p.add_argument('transcript')
    p.add_argument('--findings')
    p.add_argument('--output')
    args = parser.parse_args()
    try:
        if args.command == 'normalize':
            return cmd_normalize(args)
        if args.command == 'chunk':
            return cmd_chunk(args)
        if args.command == 'validate':
            return cmd_validate(args)
        return cmd_render(args)
    except Exception as exc:
        emit('error', error=str(exc))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
