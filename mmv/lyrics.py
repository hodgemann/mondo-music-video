"""Optional lyrics detection: transcribe the vocals (or the mix) to timed words, group them into lines,
and align pasted lyrics to what was heard. The speech model is an optional add-on that is never
installed or downloaded automatically; detection and alignment are free local analysis.
"""
from __future__ import annotations

import difflib
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from .storage import read_json, write_json

WORKER = Path(__file__).with_name('lyrics_worker.py')
INSTALL_HINT = 'pip install openai-whisper'
# File names are whisper's own; large-v3 was measured at 3,087,371,615 bytes. The others are approximate.
MODELS = {
    'tiny': {'file': 'tiny.pt', 'download': 'about 75 MB'},
    'base': {'file': 'base.pt', 'download': 'about 145 MB'},
    'small': {'file': 'small.pt', 'download': 'about 470 MB'},
    'medium': {'file': 'medium.pt', 'download': 'about 1.5 GB'},
    'large-v3': {'file': 'large-v3.pt', 'download': 'about 3.1 GB'},
}
DEFAULT_MODEL = 'large-v3'
# GPU memory each model needs: large-v3 measured at about 10.2 GB; the others are the figures in Whisper's own README.
VRAM_GB = {'tiny': 1.0, 'base': 1.0, 'small': 2.0, 'medium': 5.0, 'large-v3': 10.3}
VRAM_HEADROOM_GB = 1.0
GAP_SECONDS = 0.9
MIN_MATCH = 0.5               # below this share of recognised words a line's timing is only a guess
GUESS_SECONDS = 3.0           # a line with no recognised words is given at most this window, never the whole gap
CLUSTER_GAP = 3.0             # recognised words of one line must sit within this many seconds of each other
MAX_SPAN = 12.0               # ... and within this span in total
MAX_LINE_WORDS = 10
MAX_LINE_SECONDS = 8.0
_PROBE = {'python': None, 'at': 0.0, 'ok': False}


def python_exe():
    """The interpreter that runs Whisper: MMV_LYRICS_PYTHON (an existing Whisper environment) or this one."""
    return os.environ.get('MMV_LYRICS_PYTHON') or sys.executable


def model_dir():
    return Path(os.environ.get('MMV_WHISPER_DIR') or Path.home() / '.cache' / 'whisper')


def available():
    exe = python_exe()
    if _PROBE['python'] != exe or time.time() - _PROBE['at'] > 60:
        try:
            ok = subprocess.run([exe, '-c', 'import whisper'], capture_output=True, timeout=120).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        _PROBE.update(python=exe, at=time.time(), ok=ok)
    return _PROBE['ok']


def pick_device(model):
    """The GPU only when the model fits in the memory free right now (with headroom), otherwise the CPU."""
    from . import stems
    return 'cuda' if stems._gpu()['free'] / 1024 ** 3 >= VRAM_GB[model] + VRAM_HEADROOM_GB else 'cpu'


def recommend(hw):
    """Plain-language advice for an installer or agent. Measured: large-v3 about 10.2 GB VRAM and 46 s (GPU) or
    164 s (CPU) for a 60 s clip. Smaller models were not tested on singing, so none is recommended for accuracy."""
    free = hw['vram_free_gb']
    fits = [name for name in MODELS if free >= VRAM_GB[name] + VRAM_HEADROOM_GB]
    notes = []
    if 'large-v3' in fits:
        notes.append(f"The most accurate model (large-v3, 3.1 GB) fits on this GPU ({hw['gpu']}, {free} GB free): about 46 s per minute "
                     'of song including loading. It needs about 10 GB of VRAM, so close or unload ComfyUI models first.')
        model, device = 'large-v3', 'cuda'
    else:
        model, device = 'large-v3', 'cpu'
        notes.append('large-v3 needs about 10 GB of free VRAM, which this machine does not have free, so it would run on the '
                     'CPU: about 3 minutes per minute of song, with no VRAM use. That is slow but is the accurate option measured.')
        if fits:
            notes.append(f"Smaller models fit the free GPU memory (up to {fits[-1]}) and are much faster, but their accuracy "
                         'on singing has not been measured; offer them only if the wait matters.')
    if hw.get('ram_gb') is not None and hw['ram_gb'] < 8:
        notes.append(f"System RAM is {hw['ram_gb']} GB; large-v3 on CPU needs several GB.")
    notes.append('Detection is optional and free; run it on the isolated vocals when the stems add-on is installed '
                 '(it was correct on stems and wrong on one full mix in testing).')
    return {'model': model, 'device': device, 'notes': notes}


def status(store):
    from . import stems
    hw = stems.hardware()
    cached = {name: (model_dir() / info['file']).is_file() for name, info in MODELS.items()}
    return {'available': available(), 'python': python_exe(), 'install_command': INSTALL_HINT,
            'models': {name: {'cached': cached[name], 'download': info['download'], 'vram_gb': VRAM_GB[name]}
                       for name, info in MODELS.items()},
            'hardware': hw, 'recommendation': recommend(hw),
            'note': 'Optional add-on (openai-whisper, MIT). Detection works best on the isolated vocals stem. '
                    'Nothing is installed or downloaded automatically; you can edit every detected line.'}


def require_ready(model):
    if model not in MODELS:
        raise ValueError('Unknown speech model')
    if not available():
        raise ValueError(f'Lyrics detection needs the optional Whisper add-on. Install it with "{INSTALL_HINT}" '
                         'or point MMV_LYRICS_PYTHON at a Python that already has it.')
    if not (model_dir() / MODELS[model]['file']).is_file():
        raise ValueError(f'The {model} speech model is not downloaded yet ({MODELS[model]["download"]}); approve its '
                         'one-time download first.')


def _cache(store):
    folder = store.home / 'analysis' / 'lyrics'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def transcribe(store, song, digest, model, context=None, use_vocals=True):
    """Timed words for a song (cached). Uses the vocals stem when the stems add-on is ready."""
    require_ready(model)
    source, audio = 'mix', Path(song)
    if use_vocals:
        from . import stems
        if stems.installed() and read_json(stems._root(store) / 'htdemucs.ready', None):
            if context:
                context.update('Separating the vocals…', 10)
            audio, source = stems.separate(store, song, digest, 'htdemucs') / 'vocals.wav', 'vocals stem'
    cache = _cache(store) / f'{digest}-{source.split()[0]}-{model}.json'
    if not cache.is_file():
        if context:
            context.update(f'Listening to the {source} with {model}…', 40)
        temp = cache.with_suffix('.tmp')
        result = subprocess.run([python_exe(), str(WORKER), str(audio), str(temp), model, str(model_dir()), pick_device(model)],
                                capture_output=True, text=True, timeout=3600)
        if result.returncode:
            raise ValueError('Lyrics detection failed: ' + result.stderr[-600:])
        temp.replace(cache)
    data = read_json(cache, {})
    return {**data, 'source': source, 'lines': group_lines(data.get('words', []))}


def group_lines(words):
    """Group timed words into lyric lines at pauses, sentence ends and length limits; drop hallucinated blips."""
    lines, current = [], []

    def close():
        if current:
            lines.append({'start': round(current[0]['start'], 2), 'end': round(current[-1]['end'], 2),
                          'text': ' '.join(w['word'] for w in current), 'words': len(current)})
            current.clear()

    for word in words:
        if current and (word['start'] - current[-1]['end'] >= GAP_SECONDS or len(current) >= MAX_LINE_WORDS
                        or word['end'] - current[0]['start'] > MAX_LINE_SECONDS):
            close()
        current.append(word)
        if word['word'].endswith(('.', '!', '?')) and len(current) >= 3:
            close()
    close()
    kept = []
    for line in lines:
        span = round(line['end'] - line['start'], 3)
        # A blip is too short to be speech: under 0.15 s, or faster than 0.1 s per word. A short real shout ("Hey!") stays.
        if span < 0.15 or span / line['words'] < 0.1 or not _norm(line['text']):
            continue
        kept.append({k: v for k, v in line.items() if k != 'words'})
    return kept


_NORM_WORDS = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def _norm(text):
    """Lower-cased word tokens in any script: apostrophes inside words stay, curly quotes count as apostrophes, hyphens split."""
    text = unicodedata.normalize('NFKC', text).casefold().replace('\u2019', "'").replace('\u2018', "'")
    return _NORM_WORDS.findall(text)


STOPWORDS = frozenset('the a an and or of to i you it in on my me we is so but at be am are was for with oh la na yeah'.split())
SECTION = re.compile(r"\b(verse|chorus|bridge|intro|outro|hook|refrain|pre-?chorus|post-?chorus|interlude|solo|instrumental\w*|break|drop|"
                     r"spoken|rap|vocals?|tag|coda|ad-?lib|beat|silence|pause|fade|piano|guitar|drums?|bass|synth|strings|sax\w*|trumpet|violin|keys|organ|flute)\b")
INSTRUMENTAL = re.compile(r"\b(instrumental\w*|solo|interlude|break(?!\s*down)|drop|beat|silence|pause|fade|piano|guitar|drums?|bass|synth|strings|"
                          r"sax\w*|trumpet|violin|keys|organ|flute)\b")
VOICE = re.compile(r"\b(vocals?|voice|sing\w*|choir|spoken|rap|whisper\w*|chant\w*)\b")
REPEAT = re.compile(r"\(?\s*(?:x|\u00d7)\s*\d+\s*\)?\s*$", re.I)
BRACKETS = re.compile(r'\[([^\[\]]*)\]')
SECTION_PAREN = re.compile(r'\(\s*' + SECTION.pattern + r'[^()]*\)', re.I)
BACKING_PARENS = re.compile(r'(\s*\([^()]*\)\s*)+')
PARENS = re.compile(r'[()]')
MAX_TOKENS = 8000


def _is_instrumental(label):
    return bool(INSTRUMENTAL.search(label)) and not VOICE.search(label)


def parse_lyrics(text):
    """Read Suno sections and backing vocals; instrumental entries are kept but never timed.

    A section marker on its own line, or at the start of a line, applies from there on; one after words on a line applies from the next
    line; brackets that are not section words ("[laughs]") are stage directions and are dropped. Several markers on a line combine:
    the block is instrumental if any marker is. "(x2)" repeats and "(Chorus)" directions are ignored."""
    if len(text) > 16000:
        raise ValueError('Lyrics must be at most 16000 characters')
    text = (text.replace('\u3010', '[').replace('\u3011', ']').replace('\uff3b', '[').replace('\uff3d', ']')
            .replace('\u2019', "'").replace('\u2018', "'").replace('*', ''))
    entries, section, kind = [], None, 'sung'
    for raw in text.splitlines():
        labels = [' '.join(label.strip().lower().split()) for label in BRACKETS.findall(raw)]
        rest = BRACKETS.sub(' ', raw).replace('[', ' ').replace(']', ' ')
        rest = ' '.join(rest.split())
        accepted = [label for label in labels if label and (not rest or SECTION.search(label))]
        lead = raw.lstrip().startswith('[') or not rest
        next_section, next_kind = section, kind
        if accepted:
            next_section = accepted[-1][:40]
            next_kind = 'instrumental' if any(_is_instrumental(label) for label in accepted) else 'sung'
        if lead:
            section, kind = next_section, next_kind
        rest = REPEAT.sub('', rest).strip()
        if rest and SECTION_PAREN.fullmatch(rest):
            rest = ''                                       # "(Chorus)" is a direction, not words
        if rest:
            flat = rest
            while '((' in flat or '))' in flat:
                flat = flat.replace('((', '(').replace('))', ')')
            backing = bool(BACKING_PARENS.fullmatch(flat))
            inner = ' '.join(PARENS.sub(' ', rest).split())
            if inner:
                entries.append({'text': inner, 'section': section, 'kind': kind, 'backing': backing})
        if not lead:
            section, kind = next_section, next_kind
    if not entries:
        raise ValueError('Paste at least one line of lyrics')
    return entries


def _clean_words(words):
    """Heard words with finite times; an end before its start is treated as a point."""
    clean = []
    for word in words or []:
        try:
            start, end = float(word['start']), float(word['end'])
            text = str(word['word'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Each recognised word needs word, start and end') from None
        if not (math.isfinite(start) and math.isfinite(end)):
            continue
        clean.append({'word': text, 'start': start, 'end': max(end, start)})
    return clean


def _best_cluster(heard_words):
    """The densest run of heard words that sit together in time (a gap over CLUSTER_GAP or a span over MAX_SPAN starts a new run)."""
    runs, current = [], []
    for word in sorted(heard_words, key=lambda w: (w['start'], w['end'])):
        if current and (word['start'] - current[-1]['end'] > CLUSTER_GAP or word['end'] - current[0]['start'] > MAX_SPAN):
            runs.append(current)
            current = []
        current.append(word)
    if current:
        runs.append(current)
    return max(runs, key=len) if runs else []


def align_lines(text, words):
    """Time pasted lyric lines against recognised words.

    A line is 'matched' only when at least half its words were heard close together in time (including at least two when it has
    two or more, and one that is not a filler word); a weaker match is 'uncertain' and a line never heard is 'interpolated' with a
    short guessed window. Matched and uncertain lines keep the real times of the words heard."""
    entries = [entry for entry in parse_lyrics(text) if entry['kind'] == 'sung']
    rows = [entry['text'] for entry in entries]
    if not rows:
        raise ValueError('Paste at least one line of lyrics')
    words = _clean_words(words)
    heard = [(token, word) for word in words for token in _norm(word['word'])]
    wanted = [(i, token) for i, row in enumerate(rows) for token in _norm(row)]
    if not heard or not wanted:
        raise ValueError('No words were recognised in the song, so the lyrics cannot be timed')
    if len(heard) > MAX_TOKENS or len(wanted) > MAX_TOKENS:
        raise ValueError(f'Too much text to time at once: at most {MAX_TOKENS} words')
    matcher = difflib.SequenceMatcher(None, [t for _, t in wanted], [t for t, _ in heard], autojunk=False)
    hits = {}
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            hits.setdefault(wanted[a + k][0], []).append((wanted[a + k][1], heard[b + k][1]))
    if sum(len(v) for v in hits.values()) / len(wanted) < 0.3:
        raise ValueError('The pasted lyrics do not match what was heard in the song; check the text or the song.')
    result = []
    for i, row in enumerate(rows):
        total = len(_norm(row))
        cluster = _best_cluster({id(word): word for _, word in hits.get(i, [])}.values())
        members = {id(word) for word in cluster}
        tokens = [token for token, word in hits.get(i, []) if id(word) in members]
        if cluster:
            ratio = len(tokens) / total
            solid = (ratio >= MIN_MATCH and len(tokens) >= min(2, total) and any(t not in STOPWORDS for t in tokens))
            start, end = min(w['start'] for w in cluster), max(w['end'] for w in cluster)
            result.append({'start': round(start, 3), 'end': round(max(end, start + 0.2), 3), 'text': row,
                           'timing': 'matched' if solid else 'uncertain', 'matched': round(ratio, 2)})
        else:
            result.append({'start': None, 'end': None, 'text': row, 'timing': 'interpolated', 'matched': 0.0})
    _place_guesses(result)
    for item, entry in zip(result, entries):
        item.update(section=entry['section'], backing=entry['backing'])
    return result


def _place_guesses(result):
    """Give never-heard lines a short window in the gap where they probably sit: before the next heard line when leading, in the
    middle of the gap between two heard lines, or after the last heard line when trailing."""
    i = 0
    while i < len(result):
        if result[i]['start'] is not None:
            i += 1
            continue
        j = i
        while j < len(result) and result[j]['start'] is None:
            j += 1
        count = j - i
        low = result[i - 1]['end'] if i > 0 else None
        high = result[j]['start'] if j < len(result) else None
        if low is None and high is None:
            low, high = 0.0, GUESS_SECONDS * count
        if low is None:                                           # leading: end at the first heard line
            width = min(GUESS_SECONDS, high / count)
            slots = [(max(high - width * (count - n), 0.0), max(high - width * (count - n - 1), 0.0)) for n in range(count)]
        elif high is None:                                        # trailing: start after the last heard line
            slots = [(low + GUESS_SECONDS * n, low + GUESS_SECONDS * (n + 1)) for n in range(count)]
        else:                                                     # middle: centred in each slot of the gap
            slot = max(high - low, 0.1 * count) / count
            width = min(GUESS_SECONDS, slot)
            slots = [(low + slot * n + (slot - width) / 2, low + slot * n + (slot + width) / 2) for n in range(count)]
        for n, (start, end) in enumerate(slots):
            result[i + n]['start'], result[i + n]['end'] = round(start, 2), round(max(end, start + 0.1), 2)
        i = j


def song_digest(path, beats_per_bar=4):
    """The same key the analysis and stems caches use for a song, so cached stems are reused."""
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        hashlib.file_digest(stream, lambda: digest)
    digest.update(str(beats_per_bar).encode())
    return digest.hexdigest()


def cached_words(store, digest, model):
    """Words from an earlier detection (vocals stem preferred), or None."""
    for source in ('vocals', 'mix'):
        data = read_json(_cache(store) / f'{digest}-{source}-{model}.json', None)
        if data and data.get('words'):
            return {**data, 'source': 'vocals stem' if source == 'vocals' else 'mix'}
    return None


def prepare_model(store, model, context):
    """Download one speech model once (explicit approval is the caller's responsibility)."""
    if model not in MODELS:
        raise ValueError('Unknown speech model')
    if not available():
        raise ValueError(f'Install the optional Whisper add-on first: {INSTALL_HINT}')
    context.update(f'Downloading the {model} speech model (one time)…', 5)
    context.command([python_exe(), '-c',
                     'import sys, whisper; whisper.load_model(sys.argv[1], device="cpu", download_root=sys.argv[2])',
                     model, str(model_dir())])
    if not (model_dir() / MODELS[model]['file']).is_file():
        raise ValueError('The speech model did not download')
    return {'model': model}
