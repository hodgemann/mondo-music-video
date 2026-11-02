"""Portable orchestration around the original Mondo music-video engine.

Analysis, timing, casting, prompt construction/validation, graph injection,
renderer calls and assembly are implemented by the extracted engine modules.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse
from . import actors
from .storage import identifier, inside, read_json, write_json

ENGINE = Path(__file__).parent / 'engine'

VOCAB_TABLES = (
    'settings',
    'subject_types',
    'mechanisms',
    'lighting',
    'tonal_registers',
    'costume',
    'footage_anchors',
    'practical_effects',
    'shot_scales',
)


def apply_vocabulary_overrides(vocab, overrides):
    if not overrides:
        return vocab
    if not isinstance(overrides, dict):
        raise ValueError('Vocabulary overrides must be a dictionary of categories')
    for key, spec in overrides.items():
        if key not in VOCAB_TABLES:
            raise ValueError(f"Unknown vocabulary category '{key}'")
        if not isinstance(spec, dict):
            raise ValueError(f"Invalid vocabulary override for '{key}'")
        mode = spec.get('mode', 'append')
        if mode not in ('append', 'replace'):
            raise ValueError(f"Vocabulary override mode for '{key}' must be 'append' or 'replace'")
        raw_add = spec.get('add', [])
        raw_exclude = spec.get('exclude', [])
        if not isinstance(raw_add, list) or not isinstance(raw_exclude, list):
            raise ValueError(f"Vocabulary 'add' and 'exclude' lists for '{key}' must be arrays")
        added = []
        seen_add = set()
        for item in raw_add:
            if not isinstance(item, str):
                raise ValueError(f"Vocabulary entries in '{key}' must be strings")
            cleaned = item.strip()
            if not cleaned:
                continue
            if len(cleaned) > 240:
                raise ValueError(f"Vocabulary entry in '{key}' exceeds 240 characters")
            if cleaned not in seen_add:
                seen_add.add(cleaned)
                added.append(cleaned)
        excluded = {item.strip() for item in raw_exclude if isinstance(item, str) and item.strip()}
        if mode == 'replace':
            pool = [item for item in added if item not in excluded]
        else:
            pool = [value for value in vocab.get(key, []) if value not in excluded]
            existing = set(pool)
            for item in added:
                if item not in existing and item not in excluded:
                    existing.add(item)
                    pool.append(item)
        if not pool:
            raise ValueError(f"Vocabulary category '{key}' cannot be empty; keep or add at least one entry")
        vocab[key] = pool
    return vocab


def load_vocabulary(profile="full", store=None, custom=None):
    vocab = read_json(ENGINE / 'config/vocab.json')
    if profile and profile != "full":
        profiles = read_json(ENGINE / 'config/vocabulary_profiles.json')
        if profile in profiles:
            for key, excluded in profiles[profile].get('exclude', {}).items():
                if key in vocab and isinstance(vocab[key], list):
                    excluded_set = set(excluded)
                    vocab[key] = [value for value in vocab[key] if value not in excluded_set]
        elif store is not None:
            preset = store.vocabulary(profile)
            base_profile = preset.get('base_profile', 'full')
            if base_profile and base_profile != 'full':
                if base_profile not in profiles:
                    raise ValueError('Unknown base visual vocabulary profile')
                for key, excluded in profiles[base_profile].get('exclude', {}).items():
                    if key in vocab and isinstance(vocab[key], list):
                        excluded_set = set(excluded)
                        vocab[key] = [value for value in vocab[key] if value not in excluded_set]
            apply_vocabulary_overrides(vocab, preset.get('tables', {}))
        else:
            raise ValueError('Unknown visual vocabulary profile')
    if custom:
        apply_vocabulary_overrides(vocab, custom)
    for key in VOCAB_TABLES:
        if not vocab.get(key):
            raise ValueError(f"Vocabulary category '{key}' cannot be empty; keep or add at least one entry")
    return vocab


def references(store, request):
    refs, descriptions = actors.check_cast(store, request.get('actors', []), request['content'])
    for name in request.get('references', []):
        if not name:
            continue
        try:
            path = inside(store.home / 'uploads', name)
        except ValueError:
            raise ValueError(f"Reference image '{name}' is not in the uploads directory")
        if path.suffix != '.png' or not path.is_file():
            raise ValueError(f"Reference image '{name}' not found")
        refs.append(path)
    if len(refs) > 9:
        raise ValueError('Choose at most nine total actor/reference images')
    return refs, descriptions


def roster_for(store, request, refs):
    roster = []
    ids = request.get('actors', [])
    for i, path in enumerate(refs):
        actor_id = ids[i] if i < len(ids) else 'reference_' + str(i + 1)
        record = store.actor(actor_id) if i < len(ids) else {}
        roster.append({'actor_id': actor_id, 'display_name': (record or {}).get('name') or f'Reference subject {i + 1}',
                       'sheet': str(path.name), 'sheet_path': str(path)})
    return roster


def prepare_world_harvest(store, request, settings):
    from . import worlds
    if not settings['vision_model']:
        raise ValueError('Configure your vision model in Settings')
    exists = bool(worlds.versions(store, request['world_id'])) if (worlds.worlds_dir(store) / request['world_id']).is_dir() else False
    if request['world_mode'] == 'create' and exists:
        raise ValueError('That world already exists; grow it or choose a different ID')
    if request['world_mode'] == 'grow' and not exists:
        raise ValueError('World not found; create it first')
    sources = worlds.resolve_sources(store, request)
    files = [*sources['images'], *sources['videos'], *sources['lore'], *(d / 'plan.json' for _, d in sources['runs'] if (d / 'plan.json').is_file()),
             *(worlds.run_video(d) for _, d in sources['runs'])]
    base = worlds.load(store, request['world_id']) if request['world_mode'] == 'grow' else None
    return {'settings': settings, 'segments': [], 'seconds': 0, 'references': files,
            'estimate': settings['vision_call_estimate'], 'world': {'id': request['world_id'], 'mode': request['world_mode'],
                                                                    'base_version': base['version'] if base else 0}}


def render_seed(request):
    """The seed passage N renders with is render_seed + N; productions made before 1.11.1 rendered with seed + N."""
    chosen = request.get('render_seed')
    return request.get('seed') or 0 if chosen is None else chosen


def prepare(store, request, *, saved_prepared=None):
    if request.get('render_seed') is None and saved_prepared is None:
        # Each new production renders with its own random seed unless one was chosen; the variation seed (plan, vocabulary,
        # casting) is separate, so the same song and variation seed still plan the same passages and reuse their prompts.
        # The request records it for start, resume and export; productions made before render seeds keep using `seed`.
        import secrets
        request['render_seed'] = secrets.randbelow(2147483648)
    from .render import get_backend
    from .engine.plan import plan
    from .engine.analyze import ScoreMap, Section
    from .engine.casting import assign
    settings = store.settings()
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Install FFmpeg and FFprobe; run the setup doctor')
    kind = request['kind']
    if kind == 'storyboard':
        from . import storyboard
        return storyboard.prepare(store, request, settings)
    if kind == 'world_harvest':
        return prepare_world_harvest(store, request, settings)
    if kind == 'harvest':
        if not settings['vision_model']:
            raise ValueError('Configure your vision model in Settings')
        if not request.get('references'):
            raise ValueError('Choose images to harvest')
        refs = []
        for x in request['references']:
            if not x:
                continue
            try:
                p = inside(store.home / 'uploads', x)
            except ValueError:
                raise ValueError(f"Harvest reference image '{x}' is not in the uploads directory")
            refs.append(p)
        if not refs or any(p.suffix != '.png' or not p.is_file() for p in refs):
            raise ValueError('Harvest reference image missing')
        identifier(request['style_id'])
        if (store.home / 'styles' / (request['style_id'] + '.json')).exists():
            raise ValueError('That style already exists')
        return {'settings': settings, 'segments': [], 'seconds': 0, 'references': refs,
                'estimate': settings['vision_call_estimate']}
    if not settings['writer_model']:
        raise ValueError('Configure your music-video writer model in Settings first')
    if settings['writer_mode'] == 'api' and settings['writer_call_estimate'] <= 0:
        raise ValueError('Declare an estimated API writer cost per call in Settings before generation')
    if kind == 'video':
        from .engine.validators.laya_semantic import _model_dir_staged
        if not _model_dir_staged(Path(settings['laya_model_dir']).expanduser()):
            raise ValueError('Configure your Laya model folder in Settings before music-video production')
    backend = get_backend(request['backend'])
    clip_quality = request.get('clip_quality') or 'standard'
    if clip_quality != 'standard' and (request['backend'] != 'comfy_sdk_h3' or kind != 'video'):
        raise ValueError('Studio-quality raw clips are available for music videos on the Comfy SDK renderer only. '
                         'Choose Standard, or switch the renderer.')
    refs, descriptions = references(store, request)
    if request['backend'] not in ('local_h3', 'comfy_sdk_h3') and not store.key():
        raise ValueError('Configure your WaveSpeed API key in Settings')
    if request['backend'] == 'local_h3':
        for key in ('comfy_input', 'comfy_output'):
            if not settings[key] or not Path(settings[key]).expanduser().is_dir():
                raise ValueError('Configure your existing ComfyUI ' + key.removeprefix('comfy_') + ' folder in Settings')
        from .engine.comfy import WorkflowBuilder
        WorkflowBuilder.load(settings['workflow_map_path'], ENGINE)
        url = urlparse(settings['comfy_url'])
        if url.scheme != 'http' or url.path not in ('', '/'):
            raise ValueError('The original local H3 adapter needs a direct HTTP ComfyUI host and port')
    if request['backend'] == 'comfy_sdk_h3':
        from .comfy_sdk import require_sdk, validate_proxy_url, check_proxy
        require_sdk()
        validate_proxy_url(settings['comfy_sdk_url'])
        from .engine.comfy import WorkflowBuilder
        builder = WorkflowBuilder.load(settings['workflow_map_path'], ENGINE)
        if clip_quality != 'standard':
            from .comfy_sdk import studio_node_id
            node = builder.base.get(studio_node_id(builder.map) or '')
            if not node or node.get('class_type') != 'VHS_VideoCombine':
                raise ValueError('Studio-quality clips need the workflow\'s VideoHelperSuite save node (VHS_VideoCombine); '
                                 'the active workflow has none. Choose Standard.')
        check_proxy(settings['comfy_sdk_url'], store.key('MMV_COMFY_API_KEY'))
    if kind == 'video' and request.get('vision_quality_check'):
        from .runtime import http_ok, serves_model
        from .vision_check import vision_command
        from .vision_stage import VISION_PORT
        # A matching server that is already running needs no launch command (read-only probe, same as the status card).
        if not (http_ok(f'http://127.0.0.1:{VISION_PORT}/health')
                and serves_model(f'http://127.0.0.1:{VISION_PORT}/v1', 'mmv-vision')):
            try:
                vision_command(settings['writer_launch'], VISION_PORT)
            except ValueError as exc:
                raise ValueError(f'Vision quality check unavailable: {exc} Turn the check off or configure a local '
                                 'vision-capable writer model.') from None
        if request['backend'] in ('local_h3', 'comfy_sdk_h3'):
            if not settings.get('comfy_launch') and not http_ok(settings['comfy_url'].rstrip('/') + '/system_stats'):
                raise ValueError('Start ComfyUI or configure its launch command in Settings for the vision quality check.')
    style = store.style(request['style_id'])
    if kind == 'video':
        if not request.get('song'):
            raise ValueError('Upload a song first')
        try:
            song = inside(store.home / 'uploads', request['song'])
        except ValueError:
            raise ValueError('Upload a song first')
        if not song.is_file():
            raise ValueError('Upload a song first')
        # Cache only original analysis, keyed by the audio bytes and meter.
        song_hash = hashlib.sha256()
        with song.open('rb') as stream:
            hashlib.file_digest(stream, lambda: song_hash)
        song_hash.update(str(request['beats_per_bar']).encode())
        digest = song_hash.hexdigest()
        score_path = store.home / 'analysis' / (digest + '.json')
        score_path.parent.mkdir(exist_ok=True)
        if not score_path.exists():
            result = subprocess.run([sys.executable, '-m', 'mmv.worker', 'analyze', str(song), str(score_path),
                                     str(request['beats_per_bar'])], capture_output=True, text=True, timeout=1800)
            if result.returncode:
                raise ValueError('Original song analysis failed: ' + result.stderr[-1500:])
        score = ScoreMap.from_json(score_path)
        from .score_edit import apply_score_edits, detected_view
        driver = request.get('analysis_driver') or 'mix'
        if driver != 'mix':
            from .stems import drive_score
            score = drive_score(store, song, score_path, digest, driver, request.get('stem_quality') or 'standard')
        detected = detected_view(score)
        score = apply_score_edits(score, request.get('score_edits'))
        attached_sources = {}
        for key in ('start_ident', 'end_ident'):
            if request.get(key):
                try:
                    p = inside(store.home / 'runs', request[key])
                except ValueError:
                    raise ValueError(f"Ident path '{request[key]}' is invalid")
                record = read_json(p.parent / 'output.json', {})
                if not p.is_file() or record.get('kind') not in ('ident', 'video') or record.get('file') != p.name:
                    raise ValueError('Choose a completed ident or video clip')
                from .final_assembly import load_recipe, validate_sources
                attached_sources[key] = load_recipe(store, p.parent)
                validate_sources(attached_sources[key])
    else:
        detected = None
        seconds = request['ident_seconds']
        score = ScoreMap('ident', round(seconds * 24), 22050, 0, 4, sections=[Section(0, round(seconds * 24), 0, .2, 'low')])
    aspect_w, aspect_h = map(int, request['aspect'].split(':'))
    width, height = backend.plan_resolution(aspect_w, aspect_h, megapixels=request['megapixels'],
                                            resolution=request['resolution'] if request['backend'] not in ('local_h3', 'comfy_sdk_h3') else None)
    vocab = load_vocabulary(request.get('vocabulary_profile', 'full'), store=store, custom=request.get('custom_vocabulary'))
    if request.get('vocab_selection') == 'contextual':
        from .vocab_select import contextual_vocabulary
        vocab = contextual_vocabulary(vocab, request['seed'], (
            request.get('direction', ''), request.get('title', ''),
            [t for spec in (request.get('custom_vocabulary') or {}).values() for t in spec.get('add', [])]))
    roster = roster_for(store, request, refs)
    if kind == 'ident' and request.get('ident_all_references'):
        if len(refs) > backend.capabilities()['max_reference_images']:
            raise ValueError('The selected renderer cannot accept all ident reference images')
        request = {**request, 'ref_policy': 'all', 'ensemble_mode': 'always', 'on_screen': max(1, len(refs))}
    p = plan(score, width=width, height=height, vocab=vocab, seed=request['seed'], slug='music-video',
             bars_per_phrase=request['bars_per_phrase'], ref_policy=request['ref_policy'],
             cast_size=len(roster), on_screen=request['on_screen'], ensemble_mode=request['ensemble_mode'], backend=backend)
    if not p.segments:
        raise ValueError('The original planner produced no musical segments for this track')
    if kind == 'video':
        from .score_edit import check_plan_coverage, is_empty
        if not is_empty(request.get('score_edits')):
            check_plan_coverage([{'song_start_frame': s.song_start_frame, 'trim_frames': s.trim_frames}
                                 for s in p.segments], score.duration_frames)
    for s in p.segments:
        if s.gen_frames > backend.max_gen_frames:
            raise ValueError('A detected passage exceeds the renderer limit; the original planner cannot fit this track')
        if s.ref_image_slots < backend.min_reference_images:
            raise ValueError('This renderer needs a reference in every passage. Choose an actor/image and Reference policy: All')
        if s.ref_image_slots > backend.capabilities()['max_reference_images']:
            raise ValueError('The planned cast exceeds this renderer’s reference limit')
    if request.get('vocab_selection') == 'contextual':
        from .vocab_select import apply_energy_scaled_vocabulary, plan_gaussian_world_dissonance
        for (s_idx, sh_idx), vocab_after in apply_energy_scaled_vocabulary(p.segments, vocab, request['seed']).items():
            p.segments[s_idx].shots[sh_idx].vocab = vocab_after
        worlds_ctx = request.get('thematic_worlds')
        worlds_ctx = worlds_ctx if isinstance(worlds_ctx, dict) else {}
        active = worlds_ctx.get('activeWorlds')
        if worlds_ctx.get('mode') in ('guided', 'strict') and isinstance(active, list) and active and isinstance(active[0], str):
            base_world = active[0]
            try:
                slider_pct = min(100.0, max(0.0, float(worlds_ctx.get('slider', 50))))
            except (TypeError, ValueError):
                raise ValueError('Thematic Worlds slider must be a number from 0 to 100')
            for (s_idx, sh_idx), (_, vocab_after) in plan_gaussian_world_dissonance(
                p.segments, base_world, seed=request['seed'], slider_percent=slider_pct
            ).items():
                p.segments[s_idx].shots[sh_idx].vocab = vocab_after
    narrative_acts = request.get('narrative_acts')
    if not narrative_acts and request.get('vocabulary_profile') and store is not None:
        try:
            preset = store.vocabulary(request['vocabulary_profile'])
            narrative_acts = preset.get('acts')
        except Exception:
            pass
    if narrative_acts:
        from .vocab_select import plan_narrative_acts
        for (s_idx, sh_idx), vocab_after in plan_narrative_acts(
            p.segments, narrative_acts, request['seed'], total_frames=score.duration_frames, base_vocab=vocab
        ).items():
            p.segments[s_idx].shots[sh_idx].vocab = vocab_after
    departures = {}
    if request.get('world_departures'):
        from .vocab_select import plan_world_departures
        departures = plan_world_departures(p.segments, request['world_departures'], request['seed'], request.get('world_contrast_strength', 50))
        for (s_idx, sh_idx), (_, vocab_after) in departures.items():
            p.segments[s_idx].shots[sh_idx].vocab = vocab_after
    casting = assign(p, roster, policy=request['casting_policy'], seed=request['seed'],
                     ref_policy=request['ref_policy'], ensemble_mode=request['ensemble_mode'], on_screen=request['on_screen']) if roster else None
    from . import passage_plans
    replay_plans = saved_prepared is not None and passage_plans.verify(saved_prepared)
    lip_sync = saved_prepared.get('lipsync') if replay_plans else None
    if not replay_plans and kind == 'video' and request.get('mouth_mode') == 'lip_sync':
        from . import lipsync
        lip_sync = lipsync.plan_passages(p.segments, casting, lipsync.clean_lines(request.get('lyric_lines')),
                                         request.get('singers') or [], request['seed'])
    voice_note = None
    if lip_sync and kind == 'video':
        from . import voice
        voice_note = voice.voice_check(store, digest, request, lip_sync)
    sub_plan = caption_plan = None
    wants_sub = (request.get('subliminal') or {}).get('mode', 'off') != 'off'
    wants_captions = (request.get('captions') or {}).get('mode', 'off') != 'off'
    if kind == 'video' and (wants_sub or wants_captions):
        from . import captions, subliminal
        fps = p.fps or 24
        opening, closing = (attached_sources[key]['frames'] / attached_sources[key]['fps']
                            if key in attached_sources else 0.0 for key in ('start_ident', 'end_ident'))
        song_seconds = min(p.total_frames, sum(s.trim_frames for s in p.segments)) / fps      # what assembly actually joins
        total_seconds = song_seconds + opening + closing
        if wants_sub:
            sub_plan = subliminal.plan_run(request['subliminal'], fps, p.total_frames + round((opening + closing) * fps),
                                           score.downbeat_frames, round(opening * fps), store.home / 'uploads')
        caption_plan = captions.plan_run(request.get('captions'), request.get('lyric_lines'), opening, song_seconds, total_seconds)
    instrument_plan = saved_prepared.get('instruments') if replay_plans else None
    if instrument_plan:
        from . import instruments
        instruments.check_replay(request, instrument_plan)
    if kind == 'video' and request.get('instrument_mode', 'off') != 'off':
        from . import instruments, instrument_assets
        assignments = instruments.clean(request)
        if not replay_plans:
            prop_ids, prop_uses = instruments.prop_options(request, assignments)
            selected_props = {kind: instrument_assets.locate(store, kind, prop_id=prop_id,
                              use=prop_uses.get(kind, '')) for kind, prop_id in prop_ids.items()}
            part_scores = instruments.cached_scores(store, digest, score_path, assignments,
                                                    request.get('stem_quality') or 'standard', request.get('score_edits'))
            instrument_plan = instruments.plan_passages(p.segments, casting, asdict(score), request, part_scores=part_scores)
            needed = dict.fromkeys(kind for passage in instrument_plan['passages'].values() for kind in passage['references'])
            if set(selected_props) - set(needed):
                raise ValueError('Selected OPP prop has no active instrument reference in this plan')
            instrument_plan['assets'] = {kind: selected_props.get(kind) or instrument_assets.locate(store, kind)
                                         for kind in needed}
        if instrument_plan is None:
            raise ValueError('Saved run has no instrument plan; start a new preview')
        instruments.verify_assets(instrument_plan)
        p = instruments.apply_slots(p, instrument_plan, backend.capabilities()['max_reference_images'])
    dance_plan = saved_prepared.get('dance') if replay_plans else None
    if not replay_plans and kind == 'video' and request.get('dance_mode', 'off') != 'off':
        from . import dance
        part_scores = {}
        if request.get('dance_mode') == 'independent':
            from .stems import cached_dance_scores
            part_scores = cached_dance_scores(store, digest, score_path, request.get('stem_quality') or 'standard', request.get('score_edits'))
        dance_request = request
        if instrument_plan:
            # A player's hands are busy. Other selected actors may still dance.
            chosen = request.get('dancers') or [member['actor_id'] for member in (casting or {}).get('roster', [])]
            dancers = [actor for actor in chosen if actor not in instrument_plan['assignments']]
            dance_request = {**request, 'dancers': dancers, 'dance_mode': request['dance_mode'] if dancers else 'off'}
            if request.get('dance_lead') in instrument_plan['assignments']:
                raise ValueError('An instrument player cannot also be the dance lead')
            dance_request['dance_parts'] = {actor: part for actor, part in request.get('dance_parts', {}).items() if actor in dancers}
        dance_plan = dance.plan_passages(p.segments, casting, asdict(score), dance_request, singer=(lip_sync or {}).get('singer'),
                                        part_scores=part_scores, source={'analysis_driver': request.get('analysis_driver') or 'mix', 'score_edited': any(bool(v) for v in (request.get('score_edits') or {}).values())})
    render_cost = sum(backend.cost_for(s.duration_input, request['resolution'] if request['backend'] not in ('local_h3', 'comfy_sdk_h3') else None,
                                      s.ref_image_slots) for s in p.segments)
    writer_cost = len(p.segments) * settings['writer_call_estimate'] if settings['writer_mode'] == 'api' else 0
    prepared = {'settings': settings, 'segments': [asdict(s) for s in p.segments], 'plan': asdict(p), 'score': asdict(score),
            'detected': detected, 'lipsync': lip_sync, 'subliminal': sub_plan, 'casting': casting, 'style': style, 'references': refs, 'descriptions': descriptions,
            'seconds': score.duration_seconds, 'estimate': round(render_cost + writer_cost, 4),
            'render_estimate': render_cost, 'writer_estimate': writer_cost,
            'analysis': {'tempo_bpm': score.tempo_bpm, 'beats': len(score.beat_frames),
                         'downbeats': len(score.downbeat_frames), 'sections': len(score.sections),
                         'shots': sum(len(s.shots) for s in p.segments), 'width': width, 'height': height}}
    if request.get('storyboard', {}).get('enabled'):
        from . import storyboard
        storyboard.image_paths(store, request['storyboard']['images'])
        prepared['storyboard'] = storyboard.align(request['storyboard'], p.segments, p.fps, kind)
    if departures:
        prepared['world_contrast'] = {'shots': len(departures), 'roles': sorted({role for role, _ in departures.values()})}  # absent when off
    if caption_plan:
        prepared['captions'] = caption_plan          # absent when off, so earlier consent fingerprints stay valid
    if voice_note is not None:
        prepared['voice'] = voice_note             # advisory only: kept out of fingerprints and saved plans
    if instrument_plan is not None:
        prepared['instruments'] = instrument_plan
    if dance_plan is not None:
        prepared['dance'] = dance_plan             # absent when off, so existing fingerprints are unchanged
    if replay_plans and prepared.get('storyboard') != saved_prepared.get('storyboard'):
        raise ValueError('Storyboard differs from the saved prompt alignment; restore the original request or start a new production')
    return passage_plans.restore(prepared, saved_prepared) if replay_plans else prepared


def fingerprint(store, request, prepared):
    payload = {k:v for k,v in prepared.items() if k not in ('references', 'passage_plan_binding', 'voice')}
    digest = hashlib.sha256(json.dumps({'request': request, 'prepared': payload}, sort_keys=True).encode())
    files = list(prepared['references'])
    if request.get('storyboard'):
        from . import storyboard
        files.extend(storyboard.image_paths(store, request['storyboard']['images']))
    files.extend(Path(asset['path']) for asset in (prepared.get('instruments') or {}).get('assets', {}).values())
    files.extend(Path(asset['bundle_path']) for asset in (prepared.get('instruments') or {}).get('assets', {}).values()
                 if asset.get('bundle_path'))
    if request.get('song'): files.append(inside(store.home / 'uploads', request['song']))
    for key in ('start_ident', 'end_ident'):
        if request.get(key): files.append(inside(store.home / 'runs', request[key]))
    if request['backend'] in ('local_h3', 'comfy_sdk_h3') and request['kind'] not in ('harvest', 'world_harvest', 'storyboard'):
        from .engine.comfy import WorkflowBuilder
        builder = WorkflowBuilder.load(prepared['settings']['workflow_map_path'], ENGINE)
        digest.update(json.dumps(builder.base, sort_keys=True).encode())
        files.append(Path(prepared['settings']['workflow_map_path']))
    for actor_id in request.get('actors', []):
        digest.update(json.dumps(store.actor(actor_id), sort_keys=True).encode())
    for file in files:
        digest.update(str(file).encode())
        with Path(file).open('rb') as stream:
            hashlib.file_digest(stream, lambda: digest)
    return digest.hexdigest()


def prepare_resume(store, request, directory):
    from . import passage_plans
    saved = read_json(directory / 'prepared.json', {})
    passage_plans.verify_prompts(directory, saved)
    return prepare(store, request, saved_prepared=saved)


def produce(store, request, prepared, context, *, resume=False):
    from . import vision_service
    with vision_service.for_request(request, prepared, context):
        return _produce(store, request, prepared, context, resume=resume)


def _produce(store, request, prepared, context, *, resume=False):
    from . import passage_plans
    directory = context.log_path.parent
    if resume:
        saved = read_json(directory / 'prepared.json', {})
        passage_plans.verify_prompts(directory, saved)
        if passage_plans.verify(saved):
            if passage_plans.binding(prepared) != saved[passage_plans.KEY]:
                raise ValueError('Resume passage plan digest mismatch; request a new resume preview')
            prepared = passage_plans.restore(prepared, saved)
    elif passage_plans.plans(prepared):
        prepared = {**prepared, passage_plans.KEY: passage_plans.binding(prepared)}
    write_json(directory / 'request.json', request)
    write_json(directory / 'consent.json', prepared['consent'])
    data = {**prepared, 'references': [str(p) for p in prepared['references']]}
    write_json(directory / 'prepared.json', data)
    from .jobs import Cancelled
    if request['kind'] == 'storyboard':
        context.update('Starting storyboard interpretation', 1)
        context.command([sys.executable, '-u', '-m', 'mmv.storyboard', str(store.home), str(directory)],
                        progress_path=directory / 'progress.json')
        return read_json(directory / 'result.json')
    if request['kind'] == 'world_harvest':
        context.update('Starting the world harvest', 1)
        context.command([sys.executable, '-u', '-m', 'mmv.worlds', 'harvest', str(store.home), str(directory)],
                        progress_path=directory / 'progress.json')
        return read_json(directory / 'result.json')
    context.update('Starting original Mondo production pipeline', 1)
    try:
        context.command([sys.executable, '-u', '-m', 'mmv.worker', 'produce', str(store.home), str(directory), *(['resume'] if resume else [])],
                        progress_path=directory / 'progress.json')
    except Cancelled:
        if request['backend'] == 'comfy_sdk_h3':
            from .comfy_sdk import cancel_requests
            try:
                cancel_requests(directory, prepared['settings']['comfy_sdk_url'], store.key('MMV_COMFY_API_KEY'))
            except Exception:
                context.update('Proxy cancellation could not be confirmed; inspect saved Comfy request IDs.')
        if request['backend'] == 'local_h3':
            receipt = read_json(directory / 'local-request.json', {})
            prompt_id = receipt.get('prompt_id')
            if prompt_id:
                from .render import request_json
                base = prepared['settings']['comfy_url'].rstrip('/')
                try:
                    queue = request_json(base + '/queue', timeout=3)
                    request_json(base + '/queue', {'delete':[prompt_id]}, timeout=3)
                    if any(len(item)>1 and item[1]==prompt_id for item in queue.get('queue_running',[])):
                        request_json(base + '/interrupt', {}, timeout=3)
                except ValueError:
                    pass
        raise
    if request['kind'] == 'harvest':
        return read_json(directory / 'result.json')
    result = read_json(directory / 'output.json')
    return {'file': context.record['id'] + '/' + result['file'], 'duration': result['duration']}
