"""Single-image vision checks; service lifecycle and retry consent belong to the caller."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from .quality import CUT_GUARD

TIMEOUT = 120
PROMPT = '''This is one frame from an AI-generated music video. Answer only with JSON: {"frame_fill": "full"|"bordered"|"unknown", "defects": [short strings, only for clearly visible problems: borders or letterboxing, picture shown as a projected film, photo print or screen, text or watermark, split screen, two images superimposed, severe anatomical distortion]}. "bordered" means the picture does not fill the frame edge to edge.
Also include "framing": "present"|"absent"|"unknown" for borders, letterbox, pillarbox, projected film, photo print, screen within the frame or split screen. Use unknown when the image cannot be judged; do not guess.'''
_FRAMING = re.compile(r'border|letterbox|pillarbox|projected (?:film|image)|photo print|split[- ]screen|'
                       r'screen within|(?:picture|image|video) (?:shown |displayed )?(?:on|as|inside) (?:a )?screen|'
                       r'picture.in.picture', re.I)


_PNG_SIG = b'\x89PNG\r\n\x1a\n'


def _split_pngs(data: bytes) -> list[bytes]:
    if not data:
        return []
    parts = data.split(_PNG_SIG)
    return [_PNG_SIG + part for part in parts[1:] if part]


def _frame_count(video):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                             '-show_entries', 'stream=nb_frames,nb_read_frames', '-of', 'json', str(video)],
                            capture_output=True, check=True, timeout=TIMEOUT)
    stream = json.loads(result.stdout)['streams'][0]
    raw = stream.get('nb_frames') or stream.get('nb_read_frames')
    if raw and str(raw).isdigit() and int(raw) > 0:
        return int(raw)
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                             '-show_entries', 'stream=nb_read_frames', '-of', 'json', str(video)],
                            capture_output=True, check=True, timeout=TIMEOUT)
    return int(json.loads(result.stdout)['streams'][0]['nb_read_frames'])


def sample_frames(video_or_frame_count, trim_frames, shot_starts, budget=8):
    """Spread samples over safe shot interiors, then fill gaps, deterministically.

    Cuts exclude CUT_GUARD frames on each side. Shots without a safe interior
    are skipped; clip endpoints are not cuts. Never sample beyond the trim.
    """
    frames = min(int(trim_frames), video_or_frame_count if isinstance(video_or_frame_count, int)
                 else _frame_count(video_or_frame_count))
    if frames <= 0 or budget <= 0:
        return []
    starts = sorted({int(s) for s in shot_starts if 0 <= int(s) < frames} | {0})
    windows = [(s + (CUT_GUARD if s else 0), e - 1 - (CUT_GUARD if e < frames else 0))
               for s, e in zip(starts, starts[1:] + [frames])]
    windows = [(lo, hi) for lo, hi in windows if lo <= hi]
    if not windows:
        return []
    # First cover shots evenly when there are more shots than the budget.
    chosen = {(windows[i][0] + windows[i][1]) // 2 for i in
              ({round(k * (len(windows) - 1) / (budget - 1)) for k in range(budget)}
               if budget > 1 and len(windows) > budget else
               ([len(windows) // 2] if budget == 1 else range(len(windows))))}
    # Farthest-point sampling over interval endpoints and midpoints of current gaps.
    while len(chosen) < budget:
        candidates = set()
        for lo, hi in windows:
            anchors = [lo] + sorted(x for x in chosen if lo <= x <= hi) + [hi]
            candidates.update(anchors)
            candidates.update((a + b) // 2 for a, b in zip(anchors, anchors[1:]))
        candidates -= chosen
        if not candidates:
            break
        chosen.add(max(candidates, key=lambda x: (min(abs(x - y) for y in chosen), -x)))
    return sorted(chosen)


_JSON_FENCE = re.compile(r'^```(?:json)?\s*|\s*```$', re.I)
_MMPROJ_PREFIX = re.compile(r'^mmproj[-_.]*', re.I)
_QUANT_SUFFIX = re.compile(r'[-_.](?:[qi]q?\d.*|f16|f32|bf16)$', re.I)


def _error(message):
    return {'frame_fill': 'unknown', 'defects': [], 'error': str(message)[:240]}


def judge_frame(base_url, model, png_bytes, timeout=TIMEOUT, max_tokens=None):
    """One request, one image, one fresh user message. Output failures never raise."""
    payload = {'model': model, 'temperature': 0, 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': PROMPT}, {'type': 'image_url', 'image_url': {
            'url': 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')}}]}]}
    if max_tokens:
        payload['max_tokens'] = max_tokens
    try:
        request = urllib.request.Request(base_url.rstrip('/') + '/chat/completions',
                                         data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = json.load(response)['choices'][0]['message']['content']
        content = _JSON_FENCE.sub('', content.strip())
        result = json.loads(content)
        if (not isinstance(result, dict) or result.get('frame_fill') not in ('full', 'bordered', 'unknown')
                or not isinstance(result.get('defects'), list)
                or any(not isinstance(d, str) for d in result['defects'])
                or result.get('framing', 'unknown') not in ('present', 'absent', 'unknown')):
            return _error('invalid frame verdict schema')
        return {k: result[k] for k in ('frame_fill', 'defects', 'framing') if k in result}
    except Exception as exc:
        return _error(f'vision request or output failed: {exc}')


COMPACT_FRAME_WIDTH = 512
COMPACT_MAX_TOKENS = 160


def _select_filter(expr, compact):
    # Full-size frames by default; compact mode caps the width (never enlarges).
    return f"select={expr},scale='min({COMPACT_FRAME_WIDTH},iw)':-2" if compact else f"select={expr}"


def _extract_sampled_pngs(video, indexes, timeout=TIMEOUT, compact=False):
    if not indexes:
        return []
    expr = '+'.join(f'eq(n\\,{i})' for i in indexes)
    out = subprocess.run(
        ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video),
         '-vf', _select_filter(expr, compact), '-fps_mode', 'passthrough',
         '-frames:v', str(len(indexes)), '-f', 'image2pipe', '-vcodec', 'png', '-'],
        capture_output=True, check=True, timeout=timeout).stdout
    return _split_pngs(out)


def judge_clip(video, trim_frames, shot_starts, base_url, model, framing_allowed=False, timeout=TIMEOUT, compact=False):
    """Only repeated unrequested framing can recommend a retry; never submit one."""
    problems, framing_votes, known = [], 0, 0
    try:
        indexes = sample_frames(video, trim_frames, shot_starts)
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
        return {'status': 'error', 'problems': [f'could not sample clip: {exc}'[:240]], 'retry': False}
    if not indexes:
        return {'status': 'error', 'problems': ['no sampled frame could be judged'], 'retry': False}
    try:
        pngs = _extract_sampled_pngs(video, indexes, timeout=timeout, compact=compact)
    except (OSError, subprocess.SubprocessError):
        pngs = []
    for pos, index in enumerate(indexes):
        try:
            if pos < len(pngs):
                png = pngs[pos]
            else:
                png = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video), '-vf',
                                      _select_filter(f'eq(n\\,{index})', compact), '-frames:v', '1', '-f', 'image2pipe',
                                      '-vcodec', 'png', '-'], capture_output=True, check=True, timeout=timeout).stdout
            result = judge_frame(base_url, model, png, timeout, COMPACT_MAX_TOKENS if compact else None) if png else _error('empty decoded frame')
        except (OSError, subprocess.SubprocessError) as exc:
            result = _error(exc)
        if result.get('error'):
            continue
        defects = result['defects']
        framing = result['frame_fill'] == 'bordered' or result.get('framing') == 'present' or any(
            _FRAMING.search(d) for d in defects)
        known += result['frame_fill'] != 'unknown' or bool(defects) or result.get('framing') == 'present'
        if framing and not framing_allowed:
            framing_votes += 1
            problems.append('unrequested framing device')
        problems.extend(d[:160] for d in defects if not _FRAMING.search(d) or not framing_allowed)
    problems = list(dict.fromkeys(problems))
    status = 'fail' if framing_votes >= 2 else 'error' if not known else 'warn' if problems else 'pass'
    if status == 'error':
        problems = ['no sampled frame could be judged']
    return {'status': status, 'problems': problems, 'retry': status == 'fail'}


def vision_command(writer_launch_json, port, alias='mmv-vision', context=16384):
    """Derive a local vision server command, using existing sibling projector files only."""
    try:
        argv = json.loads(writer_launch_json)
    except (ValueError, TypeError) as exc:
        raise ValueError('writer launch must be a JSON argv list') from exc
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
        raise ValueError('writer launch must be a nonempty JSON argv list')
    model = None
    kept = [argv[0]]
    replace = {'-m', '--model', '--mmproj', '--port', '--alias', '-a', '-c', '--ctx-size', '--temp',
               '--temperature', '-np', '--parallel', '--cache-reuse', '--cache-type-k', '--cache-type-v',
               '-ctk', '-ctv'}
    remote = {'--model-url', '-mu', '--mmproj-url', '--hf-repo', '-hf', '-hfr', '--hf-file', '-hff',
              '--hf-repo-v', '-hfrv', '--hf-file-v', '-hffv', '--mmproj-auto'}
    i = 1
    while i < len(argv):
        option, sep, value = argv[i].partition('=')
        if option in remote:
            raise ValueError(f'vision launch cannot use download option {option}; use local model files')
        if option in replace:
            if not sep:
                i += 1
                if i >= len(argv):
                    raise ValueError(f'missing value for {option}')
                value = argv[i]
            if option in ('-m', '--model'):
                model = value
        else:
            kept.append(argv[i])
        i += 1
    if not model:
        raise ValueError('writer launch needs a local -m model')
    path = Path(model).expanduser()
    if not path.is_file() and not path.is_absolute():
        for root in [Path("C:/llamaCPP"), Path("C:/llamaCPP/models")]:
            candidate = root / path
            if candidate.is_file() or candidate.parent.is_dir():
                path = candidate
                model = str(candidate)
                break
    def family(stem):
        stem = _MMPROJ_PREFIX.sub('', stem)
        return _QUANT_SUFFIX.sub('', stem).lower()
    matches = sorted(p for p in path.parent.glob('mmproj*.gguf') if p.is_file() and family(p.stem) == family(path.stem))
    if len(matches) != 1:
        raise ValueError(f'expected one matching sibling mmproj*.gguf for {path.name}; found {len(matches)}')
    return kept + ['-m', model, '--mmproj', str(matches[0]), '--port', str(port), '--alias', alias,
                   '-c', str(context), '--temp', '0']
