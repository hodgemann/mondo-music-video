"""Export one finished production into a self-contained folder for a video editor.

Copies the finished video, every raw per-passage clip, the song, the prompts and the receipts (request, consent,
render IDs, checks, logs) with a README per-passage table and a checksum manifest. Pure file work: no network, no
GPU, no changes to the run. Keys and secrets are never copied, home-folder paths are shortened, and only the four
public starter actors' reference pictures are included.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from . import protected_scheme
from .starter_assets import ACTORS as PUBLIC_ACTORS
from .storage import identifier, inside

TEXT = ('.json', '.txt', '.md', '.log')
SKIP_NAMES = ('api-profiles.json', 'settings.json')
SECRET_NAME = re.compile(r'key|token|secret', re.I)
KEYWORD = r'(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|secret|password|authorization)'
HOME = re.compile(r'(?:[A-Za-z]:[\\/]|/)?(?:home|Users)[\\/][^/\s"\'\\:,;)\]]+')
JSON_SECRET = re.compile(r'("[^"\n]*' + KEYWORD + r'[^"\n]*"\s*:\s*")([^"\n]{8,})(")', re.I)

ASSIGN_SECRET = re.compile(r'(\b[\w-]*' + KEYWORD + r'[\w-]*\s*[=:]\s*[\'"]?)([A-Za-z0-9._~+/=-]{12,})', re.I)
NEAR_TOKEN = re.compile(r'(' + KEYWORD + r'.{0,20}?)([A-Fa-f0-9]{32,}|[A-Za-z0-9+/_-]{40,}={0,2})', re.I)
PLAIN_SECRET = (re.compile(r'\bsk-[A-Za-z0-9_-]{16,}'), re.compile(r'\bBearer\s+[A-Za-z0-9._~+/=-]{12,}', re.I))


def sanitize(text, secrets=()):
    """Return (text with secrets redacted and home paths shortened, redaction count)."""
    count = 0
    for secret in secrets:
        if secret and len(secret) >= 6 and secret in text:
            count += text.count(secret)
            text = text.replace(secret, '[redacted]')

    def json_sub(m):
        nonlocal count
        name = m.group(1).rsplit('"', 2)[-2].lower()
        if name.endswith('_env') or name.endswith('env'):
            return m.group(0)       # the name of an environment variable, not a secret
        count += 1
        return m.group(1) + '[redacted]' + m.group(3)

    def sub(m):
        nonlocal count
        count += 1
        return m.group(1) + '[redacted]' if m.lastindex else '[redacted]'

    text = JSON_SECRET.sub(json_sub, text)
    for pattern in PLAIN_SECRET:
        text = pattern.sub(sub, text)
    text = ASSIGN_SECRET.sub(lambda m: m.group(0) if '[redacted]' in m.group(2) else sub(m), text)
    text = NEAR_TOKEN.sub(sub, text)
    return HOME.sub('~', text), count


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def stamp(seconds):
    return f'{seconds:.2f}'


def public_instrument_receipt(value):
    """Instrument sheets, private import provenance and private world identity never travel in demo receipts."""
    if isinstance(value, list):
        return [public_instrument_receipt(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: public_instrument_receipt(item) for key, item in value.items()}
    if result.get('world_id'):
        for key in ('world_id', 'world_pool_mode', 'custom_vocabulary', 'world_contrast', 'world_contrast_strength', 'world_departures'):
            result.pop(key, None)  # A private world's identity and its derived pools stay out of shared receipts.
    result.pop('storyboard', None)  # Private board text and uploaded source filenames are not demo receipts.
    result.pop('instrument_props', None)
    result.pop('instrument_prop_uses', None)
    if isinstance(result.get('instruments'), dict):
        performance = result['instruments']
        performance.pop('notice', None)  # Old saved plans retain their binding, but internal notes do not travel in demo receipts.
        performance.pop('prop_ids', None)
        performance.pop('prop_uses', None)
        performance['assets'] = {kind: ({key: asset[key] for key in ('id', 'kind', 'version', 'sha256') if key in asset}
                                         if asset.get('prop_id') else
                                         {key: item for key, item in asset.items() if key not in ('path', 'provenance', 'original_sha256')})
                                 for kind, asset in performance.get('assets', {}).items()}
    if isinstance(result.get('reference_identity'), dict):
        result['reference_identity'] = {kind: {'sha256': asset.get('sha256')}
                                         for kind, asset in result['reference_identity'].items()}
    return result


class Package:
    def __init__(self, out, secrets=()):
        self.out, self.secrets, self.redactions, self.skipped, self.absent = out, tuple(secrets), {}, [], []

    def put(self, source, relative):
        """Copy one file (never a link); text is sanitized. Returns the destination or None."""
        source = Path(source)
        if not source.is_file():
            self.absent.append(str(relative))
            return None
        if source.name in SKIP_NAMES or SECRET_NAME.search(source.name):
            self.skipped.append(f'{source.name} (secret-like file name)')
            return None
        target = self.out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in TEXT:
            content = source.read_text(encoding='utf-8', errors='replace')
            if source.suffix.lower() == '.json' and (source.name in ('prepared.json', 'request.json') or source.parent.name == 'writer_jobs'):
                value = json.loads(content)
                public = public_instrument_receipt(value)
                if public != value:
                    content = json.dumps(public, indent=2) + '\n'
            text, count = sanitize(content, self.secrets)
            target.write_text(text, encoding='utf-8')
            if count:
                self.redactions[str(relative)] = count
        else:
            shutil.copyfile(source, target)
        return target

    def write(self, relative, text):
        target = self.out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text, count = sanitize(text, self.secrets)
        target.write_text(text, encoding='utf-8')
        if count:
            self.redactions[str(relative)] = count
        return target


def passages(run):
    """Passage list: id, index, start/end on the song clock, shots, grammar."""
    plan = read_json(run / 'plan.json') or (read_json(run / 'prepared.json') or {}).get('plan') or {}
    fps = plan.get('fps') or 24
    out = []
    for seg in plan.get('segments', []):
        start = seg.get('song_start_frame', 0) / fps
        out.append({'id': f'seg{seg["index"]:03d}', 'index': seg['index'], 'start': start,
                    'start_frame': seg.get('song_start_frame', 0), 'frames': seg.get('trim_frames') or seg.get('musical_frames', 0), 'fps': fps,
                    'end': start + seg.get('musical_frames', 0) / fps, 'shots': len(seg.get('shots', [])),
                    'montage': seg.get('montage_type', ''), 'section': seg.get('section_label', '')})
    if not out and (run / 'renders').is_dir():
        for i, folder in enumerate(sorted(p for p in (run / 'renders').iterdir() if p.is_dir())):
            out.append({'id': folder.name, 'index': i, 'start': 0.0, 'end': 0.0, 'shots': 0, 'montage': '', 'section': ''})
    return out


def actors_of(request, casting):
    names = {m.get('actor_id'): m.get('display_name') or m.get('actor_id') for m in (casting or {}).get('roster', [])}
    ids = list(dict.fromkeys(list(request.get('actors') or []) + list(names)))
    return [(i, names.get(i, i)) for i in ids if i]


_DATE_PREFIX = re.compile(r'\[?(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d)')
_SAFE_SLUG_RE = re.compile(r'[^A-Za-z0-9]+')


def run_seconds(run):
    op = read_json(run / 'operation.json') or {}
    if isinstance(op.get('started'), (int, float)) and isinstance(op.get('finished'), (int, float)):
        return op['finished'] - op['started']
    stamps = []
    for line in (run / 'operation.log').read_text(errors='replace').splitlines() if (run / 'operation.log').is_file() else []:
        m = _DATE_PREFIX.match(line)
        if m:
            stamps.append(datetime.datetime.fromisoformat(m.group(1).replace(' ', 'T')))
    return (stamps[-1] - stamps[0]).total_seconds() if len(stamps) > 1 else None


def probe(path):
    """(video stream, audio stream) dicts from ffprobe, or (None, None) when ffprobe is missing or the file is unreadable."""
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return None, None
    try:
        done = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(path)], capture_output=True, text=True, timeout=120)
        streams = json.loads(done.stdout or '{}').get('streams', [])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None
    pick = lambda kind: next((s for s in streams if s.get('codec_type') == kind), None)
    return pick('video'), pick('audio')


def describe(path):
    """One line an editor can read: codec, size, frame rate and pixel format; audio codec, rate and channels."""
    video, audio = probe(path)
    parts = []
    if video:
        fps = video.get('avg_frame_rate', '')
        steady = ' (constant)' if video.get('r_frame_rate') == fps else ' (variable)'
        rate = fps.split('/')[0] if fps.endswith('/1') else fps
        parts.append(f'{video.get("codec_name", "?").upper()} {video.get("profile", "")}'.replace('  ', ' ').strip()
                     + f', {video.get("width")}x{video.get("height")}, {rate} fps{steady}, {video.get("pix_fmt", "")}')
    if audio:
        layout = {1: 'mono', 2: 'stereo'}.get(audio.get('channels'), f'{audio.get("channels")} ch')
        parts.append(f'{audio.get("codec_name", "?")}, {audio.get("sample_rate")} Hz, {layout}')
    return '; '.join(parts) or 'not readable (ffprobe missing?)'


def editor_wav(source, target):
    """A true 48 kHz 24-bit PCM WAV for the editor. The renderer's 'audio.wav' is FLAC data under a .wav name, which many
    editors refuse to open, so anything that is not already PCM is converted. Falls back to a plain copy."""
    _, audio = probe(source)
    ffmpeg = shutil.which('ffmpeg')
    if audio and str(audio.get('codec_name', '')).startswith('pcm_') and audio.get('sample_rate') == '48000':
        return False
    if not (audio and ffmpeg):
        return False
    done = subprocess.run([ffmpeg, '-y', '-v', 'error', '-i', str(source), '-ar', '48000', '-c:a', 'pcm_s24le', str(target)],
                          capture_output=True, timeout=300)
    return done.returncode == 0 and Path(target).is_file()


def timecode(frame, fps, base_hours=1):
    frame = int(frame) + base_hours * 3600 * fps
    return f'{frame // (3600 * fps):02d}:{frame // (60 * fps) % 60:02d}:{frame // fps % 60:02d}:{frame % fps:02d}'


def edl(title, fps, clips, song_name, total_frames):
    """A CMX 3600 edit decision list (24 fps non-drop, record time starts at 01:00:00:00) that lays each passage clip at its
    place on the song clock with the song as the audio track. Import it in DaVinci Resolve, Premiere, Final Cut or Avid,
    then relink the media from the package folder."""
    lines = [f'TITLE: {title[:60]}', 'FCM: NON-DROP FRAME', '']
    for n, (name, start, frames) in enumerate(clips, 1):
        lines += [f'{n:03d}  AX       V     C        {timecode(0, fps, 0)} {timecode(frames, fps, 0)} '
                  f'{timecode(start, fps)} {timecode(start + frames, fps)}', f'* FROM CLIP NAME: {name}']
    n = len(clips) + 1
    lines += [f'{n:03d}  AX       AA    C        {timecode(0, fps, 0)} {timecode(total_frames, fps, 0)} '
              f'{timecode(0, fps)} {timecode(total_frames, fps)}', f'* FROM CLIP NAME: {song_name}', '']
    return '\n'.join(lines)


def clock(seconds):
    if seconds is None:
        return 'not recorded'
    m, s = divmod(int(round(seconds)), 60)
    return f'{m} min {s} s'


def still(ffmpeg, clip, target, at):
    """Extract one frame at `at` seconds (the first frame when the clip is shorter)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for seek in (at, 0):
        done = subprocess.run([ffmpeg, '-y', '-v', 'error', '-ss', f'{seek:.3f}', '-i', str(clip), '-frames:v', '1', str(target)],
                              capture_output=True, timeout=120)
        if done.returncode == 0 and target.is_file():
            return True
    return False


def export(run, out, zip_it=False, allow_private=False, log=print, secrets=()):
    run = Path(run).resolve()
    out = Path(out).expanduser().resolve()
    if not (run / 'request.json').is_file():
        raise ValueError(f'{run.name} is not a finished production folder (no request.json).')
    if out == run or run in out.parents:
        raise ValueError('Refusing to write the package inside the production folder.')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f'Refusing to overwrite: {out} already exists and is not empty.')
    request = read_json(run / 'request.json', {})
    casting = read_json(run / 'casting.json', {})
    prepared = read_json(run / 'prepared.json', {}) or {}
    cast = actors_of(request, casting)
    private = [(i, n) for i, n in cast if i not in PUBLIC_ACTORS]
    if private and not allow_private:
        listing = ', '.join(f'{n} ({i})' for i, n in private)
        raise ValueError('PRIVATE_ACTORS: this production uses actors that are not public starter actors: ' + listing +
                         '. Nothing was exported. Confirm to export anyway for a private edit (their reference images are '
                         'never copied, but prompts and receipts still describe them, so do not publish the package).')
    data = run.parent.parent
    pack = Package(out, secrets)
    out.mkdir(parents=True, exist_ok=True)
    pas = passages(run)
    label = {p['id']: f'{p["id"]}_{stamp(p["start"])}-{stamp(p["end"])}s' for p in pas}

    # 01_final
    for file in sorted(run.glob('*.mp4')) + sorted(run.glob('*.mov')) + sorted(run.glob('lyrics.srt')):
        pack.put(file, f'01_final/{file.name}')
    for file in sorted((run / 'assembly').glob('*.mp4')):
        pack.put(file, f'01_final/assembly_{file.name}')
    for file in sorted((run / 'assembly').glob('*.wav')):
        pack.put(file, f'01_final/assembly_{file.name}')
    if (run / 'assembly' / 'work' / 'picture.mp4').is_file():
        pack.put(run / 'assembly' / 'work' / 'picture.mp4', '01_final/picture_only_no_audio_mix.mp4')
    if not list((out / '01_final').glob('music-video.mp4')):
        pack.absent.append('01_final/music-video.mp4 (run has no finished video)')

    # 02_raw_clips: raw renders and the trimmed assembly inputs, named by passage and song-clock times
    receipts = read_json(run / 'renders.json', {}) or {}

    def recorded(sid, key, default):
        """The per-passage file: the SDK layout keeps it in renders/<id>/; other renderers record its path in renders.json."""
        if default.is_file():
            return default
        path = (receipts.get(sid) or {}).get(key)
        return Path(path) if isinstance(path, str) and Path(path).is_file() else default

    for p in pas:
        raw, work = run / 'renders' / p['id'], run / 'assembly' / 'work'
        source = recorded(p['id'], 'video', raw / 'video.mp4')
        pack.put(source, f'02_raw_clips/{label[p["id"]]}_raw{source.suffix.lower() if source.suffix else ".mp4"}')
        audio = pack.put(recorded(p['id'], 'audio', raw / 'audio.wav'), f'02_raw_clips/{label[p["id"]]}_raw_audio.wav')
        if audio and editor_wav(audio, audio.with_suffix('.pcm.tmp.wav')):
            audio.with_suffix('.pcm.tmp.wav').replace(audio)           # same name, now a real PCM WAV
        pack.put(raw / 'passage.wav', f'02_raw_clips/{label[p["id"]]}_song_slice.wav')
        pack.put(work / f'{p["id"]}.mp4', f'02_raw_clips/{label[p["id"]]}_trimmed_for_edit.mp4')
        pack.put(work / f'{p["id"]}.wav', f'02_raw_clips/{label[p["id"]]}_trimmed_for_edit.wav')
    idents = [(k, request.get(k)) for k in ('start_ident', 'end_ident') if request.get(k)]
    for key, value in idents:
        pack.put(run.parent / value, f'02_raw_clips/{key}_{Path(value).name}')

    # 03_audio
    song = request.get('song')
    song_target = None
    if song:
        slug = _SAFE_SLUG_RE.sub('_', request.get('title') or run.name).strip('_')[:40] or 'song'
        song_target = pack.put(data / 'uploads' / Path(song).name, f'03_audio/{slug}_song{Path(song).suffix.lower()}')
    else:
        pack.absent.append('03_audio/song (request has no song)')

    # 04_prompts
    prompts = read_json(run / 'prompts.json', {}) or {}
    for sid, text in prompts.items():
        pack.write(f'04_prompts/{label.get(sid, sid)}_prompt.txt', text if isinstance(text, str) else json.dumps(text, indent=2))
    pack.put(run / 'prompts.json', '04_prompts/prompts.json')
    for file in sorted((run / 'writer_jobs').glob('*.json')):
        pack.put(file, f'04_prompts/writer_jobs/{file.name}')
    for file in sorted(run.glob('writer_system*.md')):
        pack.put(file, f'04_prompts/{file.name}')

    # 05_receipts
    for name in ('request.json', 'consent.json', 'renders.json', 'quality.json', 'vision.json', 'operation.log', 'prepared.json',
                 'plan.json', 'score.json', 'casting.json', 'operation.json', 'output.json', 'passage-plan-prompts.json'):
        pack.put(run / name, f'05_receipts/{name}')
    for file in sorted(run.glob('seg*.json')) + sorted(run.glob('*.log')):
        if not (out / '05_receipts' / file.name).exists():
            pack.put(file, f'05_receipts/{file.name}')
    for file in sorted((run / 'renders').glob('*/*.json')):
        pack.put(file, f'05_receipts/renders/{file.parent.name}/{file.name}')
    # Clip, prompt and final-video versions, and the writer/review files of earlier prompt versions, when a passage was redone.
    for name in ('takes.json', 'prompt_takes.json', 'final_takes.json'):
        if (run / name).is_file():
            pack.put(run / name, f'05_receipts/{name}')
    for file in sorted((run / 'prompt_takes').rglob('*.json')):
        pack.put(file, f'05_receipts/{file.relative_to(run).as_posix()}')
    for file in sorted((run / 'style').glob('*')):
        pack.put(file, f'05_receipts/style/{file.name}')
    pack.put(run / 'assembly' / 'assembly_report.json', '05_receipts/assembly_report.json')
    pack.put(run / 'assembly' / 'work' / 'concat_video.txt', '05_receipts/concat_video.txt')

    # 06_stills
    ffmpeg = shutil.which('ffmpeg')
    stills = 0
    if ffmpeg:
        for p in pas:
            clip = recorded(p['id'], 'video', run / 'renders' / p['id'] / 'video.mp4')
            if clip.is_file() and still(ffmpeg, clip, out / '06_stills' / f'{label[p["id"]]}_mid.png', max(p['end'] - p['start'], 0) / 2):
                stills += 1
    else:
        pack.absent.append('06_stills (ffmpeg is not installed)')

    # 07_actor_references: allowlisted public actors only
    for actor_id, _ in cast:
        if actor_id in PUBLIC_ACTORS:
            sheets = [Path(m['sheet_path']) for m in (casting or {}).get('roster', []) if m.get('actor_id') == actor_id and m.get('sheet_path')]
            sheets.append(data / 'actors' / actor_id / 'reference.png')
            sheet = next((s for s in sheets if s.is_file() and data / 'actors' in s.resolve().parents), None)
            if sheet:
                pack.put(sheet, f'07_actor_references/{actor_id}{sheet.suffix}')

    # Studio-quality raw clips (ProRes / FFV1, both intra-coded) are cut to the exact passage length without re-encoding.
    studio = {}
    ffmpeg_bin = shutil.which('ffmpeg')
    for p in pas:
        raw_clip = next(iter(sorted((out / '02_raw_clips').glob(f'{label[p["id"]]}_raw.*'))), None)
        video, _ = probe(raw_clip) if raw_clip and raw_clip.suffix.lower() in ('.mov', '.mkv') else (None, None)
        if ffmpeg_bin and video and video.get('codec_name') in ('prores', 'ffv1') and p['frames']:
            target = out / '02_raw_clips' / f'{label[p["id"]]}_studio_trimmed{raw_clip.suffix.lower()}'
            done = subprocess.run([ffmpeg_bin, '-y', '-v', 'error', '-i', str(raw_clip), '-t', f'{p["frames"] / p["fps"]:.6f}',
                                   '-c', 'copy', str(target)], capture_output=True, timeout=600)
            if done.returncode == 0 and target.is_file():
                studio[p['id']] = target.name
    # 08_timeline: an EDL that places the trimmed passage clips on the song clock (studio copies when they exist)
    clips = [(studio.get(p['id']) or f'{label[p["id"]]}_trimmed_for_edit.mp4', p['start_frame'], p['frames']) for p in pas
             if p['id'] in studio or (out / '02_raw_clips' / f'{label[p["id"]]}_trimmed_for_edit.mp4').is_file()]
    if clips and song_target is not None and pas:
        fps = pas[0]['fps']
        total = (read_json(run / 'plan.json') or {}).get('total_frames') or max(s + f for _, s, f in clips)
        slug = _SAFE_SLUG_RE.sub('_', request.get('title') or run.name).strip('_')[:40] or 'production'
        pack.write(f'08_timeline/{slug}.edl', edl(request.get('title') or run.name, fps, clips, song_target.name, total))
    readme = readme_text(run, request, casting, prepared, pas, label, cast, private, pack, stills, idents, bool(studio))
    (out / 'README.md').write_text(readme, encoding='utf-8')
    files = {}
    for file in sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'):
        files[file.relative_to(out).as_posix()] = {'sha256': sha256(file), 'bytes': file.stat().st_size}
    (out / 'MANIFEST.json').write_text(json.dumps({'run': run.name, 'files': files}, indent=2) + '\n', encoding='utf-8')
    log(f'Exported {len(files)} files')
    if zip_it:
        archive = out.parent / (out.name + '.zip')
        if archive.exists():
            raise ValueError(f'Refusing to overwrite {archive}')
        shutil.make_archive(str(out), 'zip', out.parent, out.name)
        log(f'Wrote {archive}')
    return {'path': str(out), 'files': len(files), 'bytes': sum(f['bytes'] for f in files.values()), 'private_actors': [i for i, _ in private],
            'redactions': sum(pack.redactions.values()), 'skipped': pack.skipped, 'absent': pack.absent,
            'zip': str(out.parent / (out.name + '.zip')) if zip_it else None}


def cell(value):
    return str(value).replace('|', '/').replace('\n', ' ')


def readme_text(run, request, casting, prepared, pas, label, cast, private, pack, stills, idents, studio=False):
    out = pack.out
    plan = read_json(run / 'plan.json') or prepared.get('plan') or {}
    output = read_json(run / 'output.json', {}) or {}
    lip = prepared.get('lipsync') or {}
    sing = lip.get('passages', {}) if isinstance(lip, dict) else {}
    names = dict(cast)
    modes = []
    mode = request.get('mouth_mode') or ('sealed' if request.get('silent_mouths', True) else 'natural')
    if any(v.get('singing') for v in sing.values()):
        modes.append('lip sync (main singer: %s)' % names.get(lip.get('singer'), lip.get('singer')))
    elif mode == 'lip_sync':
        modes.append('lip sync requested, no passage was sung')
    dance = prepared.get('dance') or {}
    dancing = [sid for sid, v in (dance.get('passages') or {}).items() if v.get('dancing')]
    if dancing:
        modes.append('dancing in %d passage(s): "%s"' % (len(dancing), dance.get('direction', '')))
    if prepared.get('instruments'):
        modes.append('instrument performance: ' + ', '.join(f'{actor}: {kind}' for actor, kind in prepared['instruments']['assignments'].items()))
    if (request.get('analysis_driver') or 'mix') != 'mix':
        modes.append(f'instrument driver: {request["analysis_driver"]}')
    if request.get('vision_quality_check'):
        modes.append('vision quality check')
    modes.append({'sealed': 'silent (sealed) mouths', 'natural': 'natural expressions',
                  'lip_sync': 'sealed mouths except the singing passages (HONK lip sync)'}.get(mode, mode))
    width, height = plan.get('width'), plan.get('height')
    lines = [f'# {request.get("title") or run.name}: demo package', '',
             f'Exported {datetime.date.today()} from run `{run.name}`. Contents are copies; nothing was moved.', '']
    if private:
        lines += ['## PRIVATE_ACTORS_WARNING', '',
                  'This run uses actors that are NOT on the public allowlist. Do not publish this package.',
                  'Their reference images were not copied, but the receipts (casting.json, prepared.json) may still describe them:', '']
        lines += [f'- {n} (`{i}`)' for i, n in private] + ['']
    lines += ['## The production', '',
              f'- Title: {request.get("title", "")}', f'- Song file: `{request.get("song", "")}` (folder 03_audio)',
              f'- Video length: {output.get("duration", plan.get("total_frames", 0) / (plan.get("fps") or 24) if plan else "unknown")} s',
              f'- Backend: {request.get("backend", "")}',
              f'- Resolution setting: {request.get("resolution", "")}, aspect {request.get("aspect", "")}, '
              f'megapixels {request.get("megapixels", "")}' + (f', frame {width}x{height} at {plan.get("fps")} fps' if width else ''),
              f'- Variation seed: {request.get("seed", "")}', f'- Render seed: {request.get("render_seed", request.get("seed", ""))} (+ passage number)', f'- Tempo: {plan.get("tempo_bpm", "unknown")} BPM',
              f'- Direction: {request.get("direction", "")}', f'- Style: {request.get("style_id", "")}',
              '- Actors: ' + (', '.join(f'{n} (`{i}`)' for i, n in cast) or 'none'),
              '- Mode: ' + ('; '.join(modes) or 'standard'),
              f'- Production time: {clock(run_seconds(run))} (from operation.json / operation.log)',
              *(['- Subliminal flashes: %d frame(s) each at %s s (the untouched video is `music-video-clean.mp4` in 01_final)' % (
                  output['subliminal']['frames'], ', '.join(str(t) for t in output['subliminal']['times']))] if output.get('subliminal') else []),
              *(['- Lyric captions: %d line(s), %s (`lyrics.srt`%s)' % (output['captions']['cues'], output['captions']['mode'],
                  ' in 01_final; the video without captions is `music-video-uncaptioned.mp4`' if output['captions'].get('uncaptioned_copy') else '')] if output.get('captions') else []),
              '- Prompting scheme: ' + (protected_scheme.notice() or 'unmodified (the protected prompts, sealed-lips scheme and checks match the released Mondo scheme)'), '',
              '## Passages (times are on the song clock)', '',
              '| # | Start-end (s) | Shots | Montage grammar | Cast | Sings | Clip | Prompt |', '|---|---|---|---|---|---|---|---|']
    for p in pas:
        members = ((casting or {}).get('segments', {}).get(p['id'], {}) or {}).get('cast', [])
        who = ', '.join(m.get('display_name') or m.get('actor_id') for m in members) or '-'
        s = sing.get(p['id'], {})
        sings = (names.get(s.get('actor_id'), s.get('actor_id')) if s.get('singing') else '-')
        clip = next((f.name for f in (out / '02_raw_clips').glob(label[p['id']] + '_raw.mp4')), 'absent')
        prompt = next((f.name for f in (out / '04_prompts').glob(label[p['id']] + '_prompt.txt')), 'absent')
        lines.append(f'| {p["index"]} | {stamp(p["start"])}-{stamp(p["end"])} | {p["shots"]} | {cell(p["montage"])} | {cell(who)} | '
                     f'{cell(sings)} | {clip} | {prompt} |')
    lyric_lines = request.get('lyric_lines') or []
    if lyric_lines:
        lines += ['', '## Lyric lines used (seconds on the song clock)', '', '| Start-end | Section | Words |', '|---|---|---|']
        lines += [f'| {stamp(l["start"])}-{stamp(l["end"])} | {cell(l.get("section") or "")} | {cell(l["text"])} |' for l in lyric_lines]
    final = next(iter(sorted((out / '01_final').glob('music-video.mp4'))), None)
    raw = next(iter(sorted((out / '02_raw_clips').glob('*_raw.*'))), None)
    studio_clip = next(iter(sorted((out / '02_raw_clips').glob('*_studio_trimmed.*'))), None)
    trimmed = next(iter(sorted((out / '02_raw_clips').glob('*_trimmed_for_edit.mp4'))), None)
    master = next(iter(sorted((out / '03_audio').glob('*'))), None)
    lines += ['', '## Media format (for your editor)', '',
              'Set the project to match: the timeline frame rate below, the frame size below and 48 kHz audio. ' +
              ('The finished video and the `_trimmed_for_edit` clips are H.264 at a constant frame rate, which every editor opens directly; the studio clips are ProRes or FFV1 '
               '(intra-coded masters). ' if studio else 'All video is H.264 at a constant frame rate, which every editor opens directly; transcode to ProRes or DNxHR only if you '
               'prefer an intermediate codec. ') +
              'Separate audio files in this package are true PCM WAV (the renderer\'s own audio is converted from FLAC), so none of them depend on a codec your editor may lack.', '']
    for label_, item in (('Finished video', final), ('Raw passage clip', raw), ('Studio trimmed clip (exact length, not re-encoded)', studio_clip),
                         ('Trimmed passage clip (H.264, as used in the final video)', trimmed), ('Song (master audio)', master)):
        if item:
            lines.append(f'- {label_} (`{item.name}`): {describe(item)}')
    lines += ['- Raw clips are slightly longer than the passage and carry the video model\'s own audio; the H.264 `_trimmed_for_edit` clips are exact length and picture-only.']
    if studio:
        lines += ['- This production saved **studio-quality raw clips**. The `_studio_trimmed` files are the exact passage lengths cut from them '
                  'without re-encoding (the timeline file points at them) and keep the video model\'s own audio inside; the H.264 `_trimmed_for_edit` files are what the '
                  'finished video was built from.']
    lines += ['']
    lines += ['', '## What is in each folder', '',
              '- `01_final`: the finished music video (`music-video.mp4`), the assembler copy, the picture-only cut and the mixed diegetic audio.',
              '- `02_raw_clips`: every passage clip as the video model produced it (`_raw`, a little longer than needed, with its own audio), '
              'the trimmed version the assembler used (`_trimmed_for_edit`) and the slice of the song for that passage. File names carry the passage '
              'number and its start/end seconds on the song, so clips drop onto a timeline at the right place.' +
              (' Start/end ident clips are included.' if idents else ''),
              '- `03_audio`: the original song file the video was built on. Lay it under the clips as the master track.',
              '- `04_prompts`: the text prompt for each passage, the writer jobs and the writer system prompt.',
              '- `05_receipts`: the request, consent, render request IDs, quality and vision checks, logs, plan, score and casting: the proof of how it was made.',
              f'- `06_stills`: one PNG per passage taken at its midpoint ({stills} made).',
              '- `07_actor_references`: reference sheets for public starter actors only.',
              '- `08_timeline`: an `.edl` (CMX 3600, 24 fps non-drop, starts at 01:00:00:00) that lays each trimmed passage clip on the '
              'song clock with the song underneath. Import it in DaVinci Resolve, Premiere, Final Cut or Avid and relink the media to this folder.',
              '- `MANIFEST.json`: sha256 and size of every file.', '']
    if pack.redactions:
        lines += ['## Redactions', ''] + [f'- `{k}`: {v} secret-looking value(s) replaced with [redacted]' for k, v in sorted(pack.redactions.items())] + ['']
    lines += ['Home-folder paths in text files were shortened to `~`.', '']
    if pack.skipped:
        lines += ['## Skipped for safety', ''] + [f'- {s}' for s in pack.skipped] + ['']
    lines += ['## Absent from this run', ''] + ([f'- {a}' for a in pack.absent] or ['- nothing missing']) + ['']
    return '\n'.join(lines)


def package_folder(store, run):
    """A human-friendly folder: the video's title and the date and time it was made, e.g. halp_fren_2026-10-19_0409."""
    request = read_json(run / 'request.json', {}) or {}
    slug = _SAFE_SLUG_RE.sub('_', request.get('title') or '').strip('_')[:40] or run.name[:8]
    done = (read_json(run / 'operation.json', {}) or {}).get('finished')
    if not isinstance(done, (int, float)):
        done = (run / 'output.json').stat().st_mtime
    base = f'{slug}_{time.strftime("%Y-%m-%d_%H%M", time.localtime(done))}'
    out, count = store.home / 'exports' / base, 2
    while out.exists() or out.with_name(out.name + '.zip').exists():
        out = store.home / 'exports' / f'{base}-{count}'
        count += 1
    return out


def export_package(store, run_id, *, zip_it=False, allow_private=False, context=None):
    """Export one finished run of this installation into MMV_HOME/exports/<run id>[-timestamp]."""
    run = inside(store.home / 'runs', identifier(run_id))
    if not (run / 'output.json').is_file():
        raise ValueError('Only a finished production can be exported.')
    out = package_folder(store, run)
    if context:
        context.update('Copying the production into an editing package…', 20)
    return export(run, out, zip_it, allow_private, log=lambda *_: None, secrets=store.secret_values())


def check_package(store, run_id, allow_private=False):
    """Refuse early (before any job starts): the run must be finished, and non-public actors need an explicit yes."""
    run = inside(store.home / 'runs', identifier(run_id))
    if not (run / 'output.json').is_file() or not (run / 'request.json').is_file():
        raise ValueError('Only a finished production can be exported.')
    request, casting = read_json(run / 'request.json', {}), read_json(run / 'casting.json', {})
    private = [(i, n) for i, n in actors_of(request, casting) if i not in PUBLIC_ACTORS]
    if private and not allow_private:
        raise ValueError('PRIVATE_ACTORS: this production uses actors that are not public starter actors: '
                         + ', '.join(f'{n} ({i})' for i, n in private) + '. Their reference images are never copied, but prompts and '
                         'receipts still describe them, so do not publish the package. Confirm to export it for a private edit.')
    return run.name
