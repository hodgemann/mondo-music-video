"""Cancellable process boundary for the extracted music-video pipeline."""
from __future__ import annotations
from dataclasses import replace
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from .engine.backends.local_h3 import h3_cast_kwargs
from . import writer_usage, storyboard
from .dance import is_blocking as dance_blocking
from .instruments import is_blocking as instrument_blocking


def blocking_for(request, blocking):
    """Which findings force a rewrite: only integrity problems, or every finding when the request asks for strict dance/instrument checks."""
    return (lambda problem: True) if request.get('strict_prompt_checks') else blocking


from .workflow_presets import map_steps
from .writer_json import MAX_FREE_RETRIES, draft_feedback, escape_control_characters, is_broken_json, laya_style_feedback
from .storage import Storage, inside, read_json, write_json


def require_renderer_handoff(settings):
    """Do not load the local renderer alongside a known external model we cannot unload."""
    from . import gpu_memory, runtime
    from .vision_stage import VISION_PORT
    if runtime.serves_model(f'http://127.0.0.1:{VISION_PORT}/v1', 'mmv-vision'):
        raise ValueError('A vision model started outside this production is still running. '
                         'Local rendering was held to avoid overlapping GPU models. '
                         'Let Mondo launch the vision model when its quality stage runs.')
    if settings.get('writer_mode') == 'local' and runtime.http_ok(settings['writer_url'].rstrip('/') + '/models'):
        try:
            cpu_only = gpu_memory.gguf_need_bytes(json.loads(settings.get('writer_launch') or '[]')) == 0
        except (ValueError, TypeError, AttributeError):
            cpu_only = False
        if not cpu_only:
            raise ValueError('The local writer is still running outside this production. '
                             'Local rendering was held to avoid overlapping GPU models. '
                             'Mondo can start and stop the writer automatically using writer_launch in Settings.')


def render_timeout(backend, minutes=120):
    """Seconds to wait for one local clip; 0 minutes means no limit (the adapter needs a number, so infinity)."""
    if backend != 'local_h3': return None
    return minutes * 60.0 if minutes else float('inf')


def passage_cache_key(system, job, validators_version=''):
    # Empty version deliberately preserves every existing cache identity.
    prefix = "validated-v2\n" + ("validators:" + validators_version + "\n" if validators_version else "")
    return hashlib.sha256((prefix + system + "\n---\n" + json.dumps(job, sort_keys=True)).encode('utf-8')).hexdigest()


def cached_shot_bodies(prompt):
    """Recover assembled shot clauses for opt-in cache validators (never writer prose)."""
    detailed = prompt.partition('\ndetailed_description:\n')[2].partition('\noverall_soundscape:')[0]
    return re.split(r'\[Shot \d+\]', detailed)[1:]


def find_cached_passage_prompt(cache_dir, runs_dir, system, job, seg, tags, cleared_at=0.0,
                               *, extra_validators=(), validators_version=''):
    cache_key = passage_cache_key(system, job, validators_version)
    def acceptable(prompt):
        return all(not validate(prompt) for validate in extra_validators)
    cache_file = cache_dir / f"{cache_key}.json"
    if cache_file.exists() and (cleared_at <= 0 or cache_file.stat().st_mtime >= cleared_at):
        try:
            cached = read_json(cache_file)
            if cached and isinstance(cached.get("prompt"), str) and cached["prompt"] and acceptable(cached["prompt"]):
                return cached["prompt"]
        except Exception:
            pass

    if runs_dir and runs_dir.exists():
        for run_dir in sorted(runs_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            if not run_dir.is_dir() or (cleared_at > 0 and run_dir.stat().st_mtime < cleared_at):
                continue
            job_file = run_dir / "writer_jobs" / f"{seg.segment_id}.json"
            if not job_file.exists():
                continue
            try:
                if not any(path.read_text(encoding="utf-8") == system for path in run_dir.glob("writer_system*.md")) or read_json(job_file) != job:
                    continue
            except Exception:
                continue

            run_prompts = run_dir / "prompts.json"
            if run_prompts.exists():
                try:
                    p_dict = read_json(run_prompts, {})
                    if seg.segment_id in p_dict and isinstance(p_dict[seg.segment_id], str):
                        prompt = p_dict[seg.segment_id]
                        if not acceptable(prompt):
                            continue
                        write_json(cache_file, {"prompt": prompt, "segment_id": seg.segment_id})
                        return prompt
                except Exception:
                    pass

    return None


def save_cached_passage_prompt(cache_dir, system, job, prompt, seg_id, *, validators_version=''):
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = passage_cache_key(system, job, validators_version)
        write_json(cache_dir / f"{cache_key}.json", {"prompt": prompt, "segment_id": seg_id})
    except Exception:
        pass


def _compact_writer_job(job: dict) -> str:
    """Serialize writer job without indentation or empty dialogue stubs to minimize LLM tokens."""
    payload = dict(job)
    if isinstance(payload.get("cast"), list):
        compact_cast = []
        for entry in payload["cast"]:
            if isinstance(entry, dict):
                cleaned = {k: v for k, v in entry.items() if not (k in ("lines", "direction", "part") and not v)}
                compact_cast.append(cleaned)
            else:
                compact_cast.append(entry)
        payload["cast"] = compact_cast
    return json.dumps(payload, separators=(",", ":"))


def _compact_ident_prompt(prompt: str, mode: str = "standard") -> str:
    """Prune mode-irrelevant sections and future-only i2v specs from the 64 KB ident prompt."""
    mode = str(mode or "standard").strip().lower()
    # Always omit the unused future IMAGE-TO-VIDEO IDENT template block.
    i2v_start = prompt.find("\nIMAGE-TO-VIDEO IDENT (SCENOGRAPHIC)")
    i2v_end = prompt.find("\nFailure modes\n", i2v_start if i2v_start != -1 else 0)
    if i2v_start != -1 and i2v_end != -1:
        prompt = prompt[:i2v_start] + prompt[i2v_end:]
    if mode != "scenographic":
        # Omit the 155-line Scenographic mode essay and Scenographic boxes when not in scenographic mode.
        sceno_start = prompt.find("\nScenographic mode\n")
        sceno_end = prompt.find("\nThe law of fresh starts\n", sceno_start if sceno_start != -1 else 0)
        if sceno_start != -1 and sceno_end != -1:
            prompt = prompt[:sceno_start] + prompt[sceno_end:]
        boxes_start = prompt.find("\nScenographic boxes\n")
        boxes_end = prompt.find("\nFailure modes\n", boxes_start if boxes_start != -1 else 0)
        if boxes_start != -1 and boxes_end != -1:
            prompt = prompt[:boxes_start] + prompt[boxes_end:]
    if mode == "standard":
        # In standard mode, vision harvesting has not been requested; omit the forensic reference-reading essay.
        ref_start = prompt.find("\nReading a reference image\n")
        ref_end = prompt.find("\nFailure modes\n", ref_start if ref_start != -1 else 0)
        if ref_start != -1 and ref_end != -1:
            prompt = prompt[:ref_start] + prompt[ref_end:]
    return prompt



def finished_clip(got, frames):
    """True when a saved render entry points at an existing clip with at least the passage's frames."""
    from .engine.assemble import probe_frames
    video = got.get('video') if isinstance(got, dict) else None
    return bool(video) and Path(video).is_file() and probe_frames(video) >= frames


def harvest_text(value):
    """Some vision models return the style card or directives as JSON objects or lists; store them as text."""
    if isinstance(value, dict):
        return '\n'.join(f'{k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}' for k, v in value.items())
    if isinstance(value, list):
        return '\n'.join(str(x) for x in value)
    return str(value or '')


def run(home, directory, *, resume=False, rewrite=None):
    """Produce a video or ident. rewrite={'segment': id, 'candidate': text or None, 'seed': variation seed or None} instead prepares one passage of a finished
    production through this same prompt stage (a fresh writer prompt, or a hand-edited candidate given only the checks) and stops
    before rendering; other passages keep their saved prompts and the prompt cache is neither read nor written."""
    os.environ['MMV_HOME'] = str(home)
    store = Storage(home)
    request = read_json(directory / 'request.json')
    prepared = read_json(directory / 'prepared.json')
    from . import passage_plans
    if resume:
        passage_plans.verify_prompts(directory, prepared)
    settings = prepared['settings']
    from .engine import style, actor, casting, assemble
    from .engine.plan import ShotPlan
    from .engine.schema import WriterResponse, build_writer_request, assemble_prompt, validate_prompt, ValidationError, RIGGING_TAIL
    from . import quality
    from .engine.writer import call_llm
    from .render import get_backend
    from .pipeline import ENGINE, render_seed
    from .render import request_json
    def progress(message, value):
        print(message, flush=True)
        write_json(directory / 'progress.json', {'message': message, 'progress': value})
    ctx_size = writer_usage.launch_context(settings)
    def llm(system, user, label=None):
        captured = {}
        ok, text, error = writer_usage.observe(
            lambda: call_llm(None, system, user, .7, 4096, 900, profile=(settings, store.key('MMV_WRITER_API_KEY'))), captured)
        if not ok:
            mode = "local llama.cpp" if settings.get('writer_mode') == 'local' else "API writer"
            endpoint = runtime.safe_endpoint(settings.get('writer_url', ''))
            err_str = str(error or '')
            if any(term in err_str.lower() for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "connection error", "target machine actively refused")):
                raise ValueError(f"Prompt Writer is offline or unreachable ({mode} at {endpoint}): {error}. Please ensure the writer service is running.")
            raise ValueError(f"Writer ({mode} at {endpoint}) failed: {error or 'Writer returned no output'}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Writer ({settings.get('writer_model') or 'llama.cpp'}) returned empty text")
        if line := writer_usage.usage_line(captured, ctx_size, label):
            print(line, flush=True)
        return text
    if request['kind'] == 'harvest':
        progress('Harvesting visual style with the original style contract', 10)
        try:
            response = request_json(settings['vision_url'].rstrip('/') + '/chat/completions',
                 {'model': settings['vision_model'], 'messages': [{'role':'user', 'content': style.build_harvest_payload([Path(p) for p in prepared['references']])}],
                  'max_tokens':4096, 'temperature':.4}, key=store.key('MMV_VISION_API_KEY'), timeout=900)
        except Exception as exc:
            err_str = str(exc).lower()
            endpoint = runtime.safe_endpoint(settings.get('vision_url', ''))
            if any(term in err_str for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "target machine actively refused")):
                raise ValueError(f"Vision engine is offline or unreachable at {endpoint}: {exc}. Please ensure your vision model service is running.") from exc
            raise ValueError(f"Vision service ({endpoint}) failed during style harvest: {exc}") from exc
        card, aesthetic = style.parse_harvest_response(response['choices'][0]['message']['content'])
        card, aesthetic = harvest_text(card), harvest_text(aesthetic)
        if not card.strip() or not aesthetic.strip(): raise ValueError('Harvest did not return a style card and aesthetic directives')
        record = {'id':request['style_id'], 'name':request['title'] or request['style_id'], 'direction':aesthetic.strip(), 'style_card':card.strip()}
        write_json(store.home / 'styles' / (request['style_id'] + '.json'), record)
        write_json(directory / 'result.json', {'style':record['id']})
        return
    plan_path = directory / 'plan.json'
    write_json(plan_path, prepared['plan'])
    write_json(directory / 'score.json', prepared['score'])
    write_json(directory / 'casting.json', prepared['casting'])
    plan = ShotPlan.from_json(plan_path)
    plan.slug = 'mmv-' + directory.name
    plan.to_json(plan_path)
    backend = get_backend(request['backend'])
    prompt_limit = backend.capabilities().get('max_prompt_chars')    # None: the renderer reports no ceiling
    style_dir = directory / 'style';style_dir.mkdir(exist_ok=True)
    (style_dir / 'aesthetic.md').write_text(prepared['style']['direction'], encoding='utf-8')
    (style_dir / 'style_card.md').write_text(prepared['style'].get('style_card', prepared['style']['direction']), encoding='utf-8')
    # Public records are adapted to the original visual-contract reader in this process only.
    roster = (prepared['casting'] or {}).get('roster', [])
    actor_records = {}
    for member in roster:
        record = store.actor(member['actor_id']) or {}
        actor_records[member['actor_id']] = {**record, 'display_name':member['display_name'],
            'reference_sheets':[member['sheet']], 'visual_contract':record.get('visual_contract') or {'default_sheet':member['sheet'],
            'sheets':{member['sheet']:{'canonical_summary':record.get('description','')}}}}
    actor.load_actor_meta = lambda actor_id: actor_records[actor_id]
    # Sealed-lips rigging applies to every production unless the operator picks natural
    # expressions; lyrics text no longer switches it off (a lip-sync mode will own that).
    mouth_mode = request.get('mouth_mode') or ('sealed' if request.get('silent_mouths', True) else 'natural')
    # Lip sync keeps every passage sealed except those the approved plan marks as singing.
    effective_silent_mouths = mouth_mode in ('sealed', 'lip_sync')
    singing_plan = ((prepared.get('lipsync') or {}).get('passages') or {}) if mouth_mode == 'lip_sync' else {}
    from . import instruments
    instrument_plan = prepared.get('instruments') or None
    instrument_passages = (instrument_plan or {}).get('passages', {})
    if instrument_plan:
        instruments.check_replay(request, instrument_plan)
        instruments.verify_assets(instrument_plan)
    dance_plan = prepared.get('dance') or None
    dance_passages = ((dance_plan or {}).get('passages') or {}) if request['kind'] == 'video' else {}
    cast_block = actor.cast_writer_block([a['actor_id'] for a in roster], silent_mouths=effective_silent_mouths)
    restrictions = [name for name in ('nudity','blood','violence','sexual') if request['content'].get({'blood':'blood_gore','sexual':'sexual_content'}.get(name,name), 'none') == 'none']
    # OAP's own category names are enforced independently by check_cast.
    if all(value == 'none' for value in request['content'].values()): restrictions = ['nudity','blood','violence','sexual']
    from . import runtime
    vision_wanted = request['kind'] == 'video' and request.get('vision_quality_check')
    if not resume:
        # Confirm cached renderer models have left the GPU before loading prompt models.
        if (request['backend'] in ('local_h3', 'comfy_sdk_h3') and (request['backend'] == 'local_h3' or vision_wanted)
                and settings.get('comfy_url') and runtime.http_ok(settings['comfy_url'].rstrip('/') + '/system_stats')):
            from .comfy_memory import release_cached_models
            progress('Releasing ComfyUI model memory for prompt preparation', 1)
            release_cached_models(settings['comfy_url'])
        from . import gpu_memory
        gpu_before_writer = gpu_memory.gpu_memory()
        writer_process = None
        candidate = (rewrite or {}).get('candidate')
        if settings['writer_mode'] == 'local' and candidate is None:
            if not runtime.http_ok(settings['writer_url'].rstrip('/') + '/models'):
                try:
                    command = json.loads(settings['writer_launch'])
                    need = gpu_memory.gguf_need_bytes(command) if isinstance(command, list) else None
                except (ValueError, TypeError, AttributeError):
                    need = None  # start_service supplies the configuration diagnostic.
                if need and gpu_before_writer and gpu_before_writer[0] < need:
                    raise ValueError(f'Not enough free GPU memory to start the writer: '
                                     f'{gpu_memory.gib(gpu_before_writer[0])} free, about '
                                     f'{gpu_memory.gib(need)} needed. Another model may still be using the GPU.')
            progress('Starting music-video writer', 2)
            writer_process = runtime.start_service(settings['writer_launch'],settings['writer_cwd'],
                             settings['writer_url'].rstrip('/')+'/models',service_logs(directory)/'writer-service.log',
                             name='llama.cpp (Writer)', launch_setting='writer_launch')
        prompts = read_json(directory / 'prompts.json', {}) if rewrite else {}
        validator = None
        if request['kind'] == 'video':
            from .engine.validators import LayaSemanticValidator
            validator = LayaSemanticValidator()
            # Measured after the writer is up, so what it holds is already subtracted. Never rewrites settings.
            override, why = gpu_memory.laya_device_choice(
                settings.get('laya_device', 'cuda'), gpu_memory.laya_need_bytes(settings.get('laya_model_dir') or ''),
                gpu_memory.gpu_memory())
            if override:
                os.environ['MMV_LAYA_DEVICE_OVERRIDE'] = override
            progress(why, 3)
            progress('Loading Laya prompt reviewer', 3)
            try:
                validator._load_agent()
                if getattr(validator, "device", None):
                    progress(f'Laya prompt reviewer loaded on {validator.device}', 3)
            except Exception as exc:
                raise ValueError(f"Laya semantic validator failed to load: {exc}") from exc

        if request['kind'] == 'ident':
            system = style.compose_ident_prompt()
            if request.get('compact_prompts'):
                system = _compact_ident_prompt(system, request['ident_mode'])
            message = style.build_ident_writer_message(request['title'], request['ident_seconds'], request['ident_mode'],
                       style_card=prepared['style'].get('style_card', prepared['style']['direction']), ident_notes=storyboard.ident_notes(request['direction'], prepared.get('storyboard'), plan.segments[0].segment_id))
            (directory / 'writer_system.md').write_text(system, encoding='utf-8')
            cache_dir = store.home / 'cache' / 'prompts'
            cache_key = hashlib.sha256((system + "\n---\n" + message).encode('utf-8')).hexdigest()
            cache_file = cache_dir / f"ident_{cache_key}.json"
            cleared_info = read_json(store.home / 'cache_cleared.json', {})
            cleared_at = float(cleared_info.get('cleared_at', 0))
            reuse_prompts = request.get('reuse_prompts', True) and not rewrite
            if rewrite:
                prompts.pop(plan.segments[0].segment_id, None)
            if candidate is not None:
                if request['title'] not in candidate: raise ValueError('The edited ident prompt must contain the exact requested title')
                if too_long := length_problems(candidate, prompt_limit): raise ValueError(too_long[0])
                prompts[plan.segments[0].segment_id] = candidate
            if reuse_prompts and cache_file.exists() and (cleared_at <= 0 or cache_file.stat().st_mtime >= cleared_at):
                try:
                    cached = read_json(cache_file)
                    if cached and "prompt" in cached and not length_problems(cached["prompt"], prompt_limit):
                        prompts[plan.segments[0].segment_id] = cached["prompt"]
                        write_json(directory / 'prompts.json', prompts)
                        progress('Ident prompt resumed from cache', 30)
                except Exception:
                    pass
            if plan.segments[0].segment_id not in prompts:
                progress('Writing ident with the original ident prompt', 10)
                raw = llm(system, message, label='ident').strip()
                if raw.startswith('```'): raw = '\n'.join(raw.splitlines()[1:-1]).strip()
                if request['title'] not in raw: raise ValueError('Ident writer omitted the exact requested title')
                if too_long := length_problems(raw, prompt_limit): raise ValueError('Ident ' + too_long[0])
                prompts[plan.segments[0].segment_id] = raw
                write_json(directory / 'prompts.json', prompts)
                try:
                    if not rewrite:                     # a rewrite never replaces the cached prompt
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        write_json(cache_file, {"prompt": raw})
                except Exception:
                    pass
        else:
            system = style.compose_writer_prompt(str(style_dir), actor_block=cast_block, restrictions=restrictions,
                        silent_mouths=effective_silent_mouths, lyrics=request['lyrics'] or None, direction=request['direction'] or None)
            system += quality.WRITER_RULES
            (directory / 'writer_system.md').write_text(system, encoding='utf-8')
            system_singing = cast_block_singing = None
            if any(item.get('singing') for item in singing_plan.values()):
                from . import lipsync
                cast_block_singing = actor.cast_writer_block([a['actor_id'] for a in roster], silent_mouths=False)
                system_singing = style.compose_writer_prompt(str(style_dir), actor_block=cast_block_singing, restrictions=restrictions,
                        silent_mouths=False, lyrics=request['lyrics'] or None, direction=request['direction'] or None)
                system_singing += '\n\n' + lipsync.SINGING_RULES + quality.WRITER_RULES
                (directory / 'writer_system_singing.md').write_text(system_singing, encoding='utf-8')
            system_dance = system_singing_dance = None
            if any(item.get('dancing') for item in dance_passages.values()):
                from . import dance
                tail = quality.WRITER_RULES            # the quality rules stay last: base, singing rules, dance rules, quality rules
                system_dance = system[:-len(tail)] + '\n\n' + dance.writer_rules(dance_plan) + tail
                (directory / 'writer_system_dance.md').write_text(system_dance, encoding='utf-8')
                if system_singing is not None:
                    system_singing_dance = system_singing[:-len(tail)] + '\n\n' + dance.writer_rules(dance_plan) + ' ' + dance.DANCE_SINGER_SENTENCE + tail
                    (directory / 'writer_system_singing_dance.md').write_text(system_singing_dance, encoding='utf-8')
            jobs_dir = directory / 'writer_jobs';jobs_dir.mkdir(exist_ok=True)
            cache_dir = store.home / 'cache' / 'prompts'
            cache_dir.mkdir(parents=True, exist_ok=True)
            cleared_info = read_json(store.home / 'cache_cleared.json', {})
            cleared_at = float(cleared_info.get('cleared_at', 0))
            reuse_prompts = request.get('reuse_prompts', True) and not rewrite
            for index, seg in enumerate(plan.segments):
                if rewrite and seg.segment_id != rewrite['segment']:
                    continue
                tags = backend.ref_tags(seg.ref_image_slots, 0, 1)
                sing = singing_plan.get(seg.segment_id) or {}
                singing = bool(sing.get('singing')) and system_singing is not None
                seg_silent = effective_silent_mouths and not singing
                dpass = dance_passages.get(seg.segment_id) or {}
                dancing = bool(dpass.get('dancing')) and system_dance is not None
                seg_system = (system_singing_dance if dancing else system_singing) if singing else (system_dance if dancing else system)
                ipass = instrument_passages.get(seg.segment_id) or {}
                performing = bool(ipass.get('performers'))
                if performing:
                    tail = quality.WRITER_RULES
                    seg_system = seg_system[:-len(tail)] + '\n\n' + instruments.RULES + tail
                    (directory / f'writer_system_instruments_{seg.segment_id}.md').write_text(seg_system, encoding='utf-8')
                seg_cast_block = cast_block_singing if singing else cast_block
                cast_entries = casting.cast_for(prepared['casting'], seg.segment_id)
                if singing:
                    from . import lipsync
                    cast_entries = lipsync.with_singer_lines(cast_entries, sing['actor_id'], sing['lines'])
                if rewrite and candidate is None:
                    from . import takes
                    seed_val = rewrite.get('seed')
                    takes.replan_segment_vocabulary(
                        store,
                        request,
                        plan.segments,
                        index,
                        seed=seed_val,
                        world_id=rewrite.get('world_id'),
                        direction_note=rewrite.get('direction'),
                    )
                job = build_writer_request(plan, seg, tags, cast_entries, silent_mouths=seg_silent)
                if singing:
                    job['singing'] = {'actor_id': sing['actor_id'], 'picture_tag': sing['picture_tag'], 'lines': sing['lines'],
                                      'shots': lipsync.shot_lyrics(seg, sing['lines'])}
                if dancing:
                    job['dance'] = dance.job(dpass, dance_plan)
                if performing:
                    job['instrument_performance'] = instruments.job(ipass, instrument_plan, tags)
                if prepared.get('storyboard'):
                    job['storyboard'] = storyboard.writer_context(prepared['storyboard'], seg.segment_id)
                if request['conceptual_theme']: job['conceptual_theme'] = request['conceptual_theme']
                if rewrite and candidate is None and rewrite.get('direction'):
                    steer = str(rewrite['direction']).strip()
                    if steer:
                        base_theme = str(job.get('conceptual_theme') or '').strip()
                        job['conceptual_theme'] = f"{base_theme} | Passage creative direction: {steer}" if base_theme else f"Passage creative direction: {steer}"
                write_json(jobs_dir / (seg.segment_id+'.json'), job)

                dance_blocks, instrument_blocks = blocking_for(request, dance_blocking), blocking_for(request, instrument_blocking)
                cache_validators = []
                if singing:
                    cache_validators = [
                        lambda prompt: validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=False),
                        lambda prompt: lipsync.lipsync_problems(prompt, cached_shot_bodies(prompt), seg, sing,
                                                              *lipsync.cast_refs(cast_entries, sing['actor_id']))]
                dance_version = ''
                if dancing:
                    if not singing:
                        cache_validators.append(lambda prompt: validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent))
                    dance_version = f"dance-v{dance_plan.get('version', dance.VERSION)}"
                    cache_validators.append(lambda prompt: list(filter(dance_blocks, dance.dance_problems(prompt, cached_shot_bodies(prompt), seg, dpass, dance_plan))))
                if performing:
                    if not singing and not dancing:
                        cache_validators.append(lambda prompt: validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent))
                    dance_version += f'instruments-v{instrument_plan["version"]}'
                    cache_validators.append(lambda prompt: list(filter(instrument_blocks, instruments.problems(prompt, cached_shot_bodies(prompt), seg, ipass, instrument_plan, tags))))
                if request.get('strict_prompt_checks'):
                    dance_version += '-strict'
                if prompt_limit:
                    cache_validators.append(lambda prompt: length_problems(prompt, prompt_limit))
                if reuse_prompts:
                    cached = find_cached_passage_prompt(cache_dir, store.home / 'runs', seg_system, job, seg, tags,
                                                        cleared_at=cleared_at, extra_validators=cache_validators, validators_version=dance_version)
                    if cached and not quality.prompt_problems(cached, seg, request['direction']):
                        if seg_silent and RIGGING_TAIL.rstrip(".").lower() not in cached.lower():
                            soundscape_pos = cached.find("\noverall_soundscape:")
                            if soundscape_pos > 0:
                                cached = cached[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + cached[soundscape_pos:]
                            else:
                                cached = cached.rstrip() + f" {RIGGING_TAIL}\n"
                        prompts[seg.segment_id] = cached
                        write_json(directory / 'prompts.json', prompts)
                        progress(f'Musical passage {index+1} of {len(plan.segments)} (resumed from cache)', 5 + int(25*(index+1)/len(plan.segments)))
                        continue

                if candidate is not None:
                    # A hand-edited prompt gets the same Mondo checks and Laya review as a written one, never a rewrite.
                    prompt = candidate
                    if seg_silent and RIGGING_TAIL.rstrip(".").lower() not in prompt.lower():
                        soundscape_pos = prompt.find("\noverall_soundscape:")
                        if soundscape_pos > 0:
                            prompt = prompt[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + prompt[soundscape_pos:]
                        else:
                            prompt = prompt.rstrip() + f" {RIGGING_TAIL}\n"
                    bodies = cached_shot_bodies(prompt)
                    problems = (validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent)
                                + quality.prompt_problems(prompt, seg, request['direction'])
                                + (lipsync.lipsync_problems(prompt, bodies, seg, sing, *lipsync.cast_refs(cast_entries, sing['actor_id'])) if singing else [])
                                + (list(filter(dance_blocks, dance.dance_problems(prompt, bodies, seg, dpass, dance_plan))) if dancing else [])
                                + (list(filter(instrument_blocks, instruments.problems(prompt, bodies, seg, ipass, instrument_plan, tags))) if performing else [])
                                + length_problems(prompt, prompt_limit))
                    if not problems:
                        progress(f'Laya reviewing the edited prompt for passage {index+1}', 20)
                        state = {'slug':plan.slug, 'backend':request['backend'], 'restrictions':{x:True for x in restrictions},
                                 'lyrics_flavor':(' / '.join(item['text'] for item in sing['lines']) if singing else request['lyrics']), 'director_direction':request['direction'],
                                 'style_digest':prepared['style'].get('style_card',prepared['style']['direction']), 'cast_digest':seg_cast_block}
                        response, problems = validator.run_clipboard(prompt,seg,tags,silent_mouths=seg_silent,state=state)
                        write_json(directory / f'{seg.segment_id}.laya-response-edit.json', response)
                    if problems:
                        write_json(directory / f'{seg.segment_id}.validation-edit.json', problems)
                        raise ValueError(f'{seg.segment_id}: the edited prompt did not pass the Mondo checks and Laya review: '
                                         + '; '.join(map(str, problems))[:600])
                    prompts[seg.segment_id] = prompt
                    write_json(directory / 'prompts.json', prompts)
                    continue
                progress(f'Writing musical passage {index+1} of {len(plan.segments)}', 5 + int(25*index/len(plan.segments)))
                feedback, soft_fallback = '', None
                compact = bool(request.get('compact_prompts'))
                attempts = (4 if singing or dancing or performing else 3) if settings['writer_mode'] == 'local' else 1
                attempt = call = free_retries = 0          # attempt counts real tries; call also counts replies that were not JSON
                while attempt < attempts:
                    tag = f"{seg.segment_id} (attempt {call + 1})" if call else seg.segment_id
                    if compact:
                        raw = llm(seg_system, _compact_writer_job(job) + feedback, label=tag)
                    else:
                        raw = llm(seg_system + feedback, json.dumps(job, indent=2), label=tag)
                    (directory / f'{seg.segment_id}.writer-{call+1}.json').write_text(raw, encoding='utf-8')
                    instrument_problems, advice, draft_bodies = [], [], None
                    try:
                        response = WriterResponse.parse(escape_control_characters(raw), seg.segment_id)
                        if performing:
                            bodies, repaired_shots = instruments.repair_shot_bodies(
                                response.shot_bodies, seg, ipass, instrument_plan, tags)
                            if repaired_shots:
                                response = replace(response, shot_bodies=bodies)
                                write_json(directory / f'{seg.segment_id}.instrument-repair-{call+1}.json',
                                           {'shots': repaired_shots, 'action': instruments.GUITAR_CONTACT})
                                print(f'{seg.segment_id}: corrected guitar hand contact in shots '
                                      + ', '.join(map(str, repaired_shots)) + '; checking the complete prompt', flush=True)
                        draft_bodies = response.shot_bodies
                        prompt = assemble_prompt(seg, response, tags)
                        if singing:
                            prompt = lipsync.swap_audio_sentence(prompt, tags.music_tag)
                        if seg_silent and RIGGING_TAIL.rstrip(".").lower() not in prompt.lower():
                            soundscape_pos = prompt.find("\noverall_soundscape:")
                            if soundscape_pos > 0:
                                prompt = prompt[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + prompt[soundscape_pos:]
                            else:
                                prompt = prompt.rstrip() + f" {RIGGING_TAIL}\n"
                        found_instruments = instruments.problems(prompt, response.shot_bodies, seg, ipass, instrument_plan, tags) if performing else []
                        found_dance = dance.dance_problems(prompt, response.shot_bodies, seg, dpass, dance_plan) if dancing else []
                        # Word-list findings about dancing and playing are advice: only integrity problems force a rewrite, Laya reviews the rest.
                        instrument_problems = list(filter(instrument_blocks, found_instruments))
                        advice = [x for x in found_instruments if not instrument_blocks(x)] + [x for x in found_dance if not dance_blocks(x)]
                        problems = (validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent)
                                    + quality.prompt_problems(prompt, seg, request['direction'])
                                    + (lipsync.lipsync_problems(prompt, response.shot_bodies, seg, sing, *lipsync.cast_refs(cast_entries, sing['actor_id'])) if singing else [])
                                    + list(filter(dance_blocks, found_dance))
                                    + instrument_problems
                                    + length_problems(prompt, prompt_limit))
                    except (ValidationError, TypeError, AttributeError, KeyError) as exc:
                        prompt = None
                        problems = [str(exc)]
                    if dancing and prompt is not None and problems and all(dance.is_soft(x) for x in problems) and soft_fallback is None:
                        soft_fallback = (prompt, problems)          # only style advice left: keep the first such draft as the fallback
                    if dancing and problems and attempt == attempts - 1 and soft_fallback is not None:
                        prompt, kept = soft_fallback                # a later try got worse; use the best draft and record its advice
                        write_json(directory / f'{seg.segment_id}.dance-advice-kept.json', kept)
                        problems = []
                    if not problems:
                        progress(f'Laya reviewing musical passage {index+1} of {len(plan.segments)}', 5 + int(25*index/len(plan.segments)))
                        state = {'slug':plan.slug, 'backend':request['backend'], 'restrictions':{x:True for x in restrictions},
                                 'lyrics_flavor':(' / '.join(item['text'] for item in sing['lines']) if singing else request['lyrics']), 'director_direction':request['direction'],
                                 'style_digest':prepared['style'].get('style_card',prepared['style']['direction']), 'cast_digest':seg_cast_block}
                        response, problems = validator.run_clipboard(prompt,seg,tags,silent_mouths=seg_silent,state=state)
                        style_advice, style_problems = laya_style_feedback(response, strict=bool(request.get('strict_prompt_checks')))
                        advice = advice + style_advice
                        problems = list(problems) + style_problems
                        clip = validator.last_clipboard_request if hasattr(validator, 'last_clipboard_request') else validator.build_clipboard_request(prompt,seg,tags,silent_mouths=seg_silent,state=state)
                        write_json(directory / f'{seg.segment_id}.laya-request-{call+1}.json', clip)
                        write_json(directory / f'{seg.segment_id}.laya-response-{call+1}.json', response)
                    if not problems:
                        if advice:
                            write_json(directory / f'{seg.segment_id}.advice.json', {'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'advice': advice})
                            print(f'{seg.segment_id}: accepted with {len(advice)} dance/instrument wording notes (no rewrite); see {seg.segment_id}.advice.json', flush=True)
                        prompts[seg.segment_id] = prompt
                        write_json(directory / 'prompts.json', prompts)
                        if not rewrite:
                            save_cached_passage_prompt(cache_dir, seg_system, job, prompt, seg.segment_id, validators_version=dance_version)
                        break
                    write_json(directory / f'{seg.segment_id}.validation-{call+1}.json', problems)
                    call += 1
                    if prompt is None and is_broken_json(problems) and free_retries < MAX_FREE_RETRIES:
                        free_retries += 1                   # the reply was not JSON: ask again with the same feedback, without spending an attempt
                        continue
                    attempt += 1
                    if instrument_problems:
                        others = [x for x in problems if x not in instrument_problems]
                        feedback = (('\n\nCorrect these validation failures in your next response:\n' + validator.format_retry_feedback(others)) if others else '') \
                                   + instruments.retry_feedback(instrument_problems)
                    else:
                        feedback = '\n\nCorrect these validation failures in your next response:\n' + validator.format_retry_feedback(problems)
                    if draft_bodies is not None and (dancing or performing):
                        feedback += draft_feedback(draft_bodies)
                else:
                    raise ValueError(f'{seg.segment_id}: prompt validation failed after {attempts} attempts (Mondo prompt checks first, then Laya; the validation file lists which check failed). See {directory / f"{seg.segment_id}.validation-{call}.json"}. Nothing rendered.')
            write_json(directory / 'prompts.json', prompts)
        if validator is not None:
            validator._agent = None
            del validator
            import gc
            gc.collect()
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available(): torch.cuda.empty_cache()
            # Freed CPU memory stays with this process until handed back; nothing else may hold RAM while ComfyUI renders.
            if sys.platform.startswith('linux'):
                import ctypes
                ctypes.CDLL('libc.so.6').malloc_trim(0)
        if writer_process is not None:
            progress('Stopping the music-video writer to free the GPU for rendering', 31)
        runtime.stop_confirmed(writer_process, 'Music-video writer')
        if gpu_memory.wait_released(gpu_before_writer) is False:
            raise ValueError('GPU memory was not released after the writer and Laya stopped, so rendering was not started. '
                             'Close other programs using the GPU, then resume this production.')
    else:
        prompts = read_json(directory / 'prompts.json', {})
        if any(not isinstance(prompts.get(seg.segment_id), str) or not prompts[seg.segment_id] for seg in plan.segments):
            raise ValueError('Resume requires saved validated prompts for every passage')
    if not resume:
        passage_plans.bind_prompts(directory, prepared, prompts)
    if rewrite:
        if candidate is None and request.get('kind', 'video') != 'ident':
            from dataclasses import asdict
            from . import takes
            segment = next(s for s in plan.segments if s.segment_id == rewrite['segment'])
            takes.save_passage_vocabulary(directory, rewrite['segment'], takes.passage_vocabulary(asdict(segment)))
        progress(f"Prompt for {rewrite['segment']} validated", 100)
        return prompts[rewrite['segment']]
    progress('All prompts validated; opening renderer', 32)
    def start_comfy():
        # Returns a handle only when this production launched ComfyUI; None means it was already running.
        return runtime.start_service(settings['comfy_launch'],settings['comfy_cwd'],
                                     settings['comfy_url'].rstrip('/')+'/system_stats',service_logs(directory)/'comfy-service.log',
                                     name='ComfyUI', launch_setting='comfy_launch')
    comfy_process = None
    if request['backend'] == 'local_h3' or (request['backend'] == 'comfy_sdk_h3' and vision_wanted):
        require_renderer_handoff(settings)
        comfy_process = start_comfy()
    # A resumed run keeps passages whose original clip is already complete; only the rest are rendered.
    rendered = read_json(directory / 'renders.json', {}) if resume else {}
    sheets = casting.sheet_paths(prepared['casting']) if prepared['casting'] else {}
    if instrument_plan:
        instruments.verify_assets(instrument_plan)
        sheets = {**sheets, **{'__instrument_' + kind: asset['path'] for kind, asset in instrument_plan['assets'].items()}}
    url = urlparse(settings['comfy_url'])
    if request['backend'] == 'local_h3':
        from .engine.comfy import ComfyClient
        original_queue = ComfyClient.queue
        def record_queue(client, graph):
            write_json(directory / 'render-graph.json', graph)
            prompt_id = original_queue(client, graph)
            write_json(directory / 'local-request.json', {'prompt_id':prompt_id})
            return prompt_id
        ComfyClient.queue = record_queue
    backend.open_render(slug=plan.slug, out_dir=directory / 'renders', cast_sheets=list(sheets.items()), subject_image=None,
                        song=None, steps=map_steps(settings['workflow_map_path']), timeout_s=render_timeout(request['backend'], settings.get('render_timeout_minutes', 120)), comfy_host=url.hostname, comfy_port=url.port or 8188,
                        comfy_input=settings['comfy_input'], comfy_output=settings['comfy_output'],
                        map_path=settings['workflow_map_path'], root=ENGINE,
                        comfy_sdk_url=settings['comfy_sdk_url'], comfy_sdk_key=store.key('MMV_COMFY_API_KEY'),
                        clip_quality=request.get('clip_quality') or 'standard')
    try:
        song = inside(store.home / 'uploads', request['song']) if request['kind'] == 'video' else directory / 'silence.wav'
        if request['kind'] == 'ident':
            subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','anullsrc=r=44100:cl=stereo','-t',str(plan.segments[0].gen_frames/24),str(song)],check=True)
        rss = next((line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                    if line.startswith('VmRSS:')), None) if Path('/proc/self/status').exists() else None
        if rss: print(f'Mondo worker memory before rendering: {int(rss) / 1048576:.2f} GiB', flush=True)
        def render_passage(seg, segment_id, seed):
            cast_members = casting.cast_for(prepared['casting'], seg.segment_id)
            images = [(member['actor_id'], sheets[member['actor_id']]) for member in cast_members]
            if instrument_plan:
                instruments.verify_assets(instrument_plan)
                images += instruments.images(instrument_passages[seg.segment_id], instrument_plan)
            if len(images) != seg.ref_image_slots: raise ValueError('Original cast/reference-slot contract disagrees; refusing render')
            try:
                result = backend.render_segment(segment_id=segment_id,index=seg.index,slug=plan.slug,
                    prompt=prompts[seg.segment_id],duration_input=seg.duration_input,gen_frames=seg.gen_frames,
                    width=plan.width,height=plan.height,seed=seed,images=images,song=str(song),
                    audio_start_s=seg.audio_slice_start_s,audio_end_s=seg.audio_slice_end_s,
                    **h3_cast_kwargs(settings, request['backend'], cast_members))
            except Exception as exc:
                err_str = str(exc).lower()
                if any(term in err_str for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "target machine actively refused")):
                    endpoint = runtime.safe_endpoint(settings.get('comfy_url', 'http://127.0.0.1:8188'))
                    raise ValueError(f"ComfyUI video renderer is offline or unreachable at {endpoint}: {exc}. Please check that ComfyUI is running.") from exc
                raise
            video = result.get('video')
            if not video or not Path(video).is_file() or assemble.probe_frames(video) < seg.trim_frames:
                raise ValueError('Renderer returned a missing or short clip; refusing an incomplete final video')
            return result
        for index, seg in enumerate(plan.segments):
            if finished_clip(rendered.get(seg.segment_id), seg.trim_frames):
                progress(f'Musical passage {index+1} of {len(plan.segments)} already rendered; keeping it', 35+int(40*index/len(plan.segments)))
                continue
            progress(f'Rendering musical passage {index+1} of {len(plan.segments)}', 35+int(40*index/len(plan.segments)))
            rendered[seg.segment_id] = render_passage(seg, seg.segment_id, render_seed(request)+seg.index)
            write_json(directory / 'renders.json', rendered)
        if request['kind'] == 'video':
            vision, vision_note = None, None
            if vision_wanted:
                from . import quality
                from .vision_stage import VisionStage
                uses_comfy = request['backend'] in ('local_h3', 'comfy_sdk_h3')
                vision = VisionStage(settings, directory, plan, quality.framing_requested(request.get('direction')),
                                     comfy_process, start_comfy if uses_comfy else None, progress,
                                     compact=bool(request.get('compact_prompts')))
            quality_completed = False
            try:
                # All passages exist before model swaps; vision retries share one further swap batch.
                rendered = run_quality_stage(directory, backend, request, plan, rendered, render_passage, progress, vision)
                quality_completed = True
            finally:
                if vision is not None:
                    vision.close()
                    vision_note = vision.note()
                write_json(directory / 'vision.json', {'requested': True, 'ran': quality_completed and vision is not None and not vision_note,
                                                       'note': vision_note, 'rerender_skipped': vision and vision.skipped}
                           if vision_wanted else {'requested': False})
            write_json(directory / 'renders.json', rendered)
    finally:
        backend.close_render()
    progress('Assembling frame-exact music video', 85)
    from . import final_assembly
    output = final_assembly.assemble(store, directory, request, read_json(directory / 'plan.json'), rendered)
    sub_result = sub_error = None
    if request['kind'] == 'video' and prepared.get('subliminal'):
        progress('Assembling the subliminal version from original clips', 96)
        from . import subliminal
        try:
            sub_result = subliminal.apply_to_run(store, directory, prepared['subliminal'])
        except Exception as exc:                  # a bonus effect never fails the production: the clean video stays
            sub_error = str(exc)
    caption_result = caption_error = None
    if request['kind'] == 'video' and (prepared.get('captions') or {}).get('cues'):
        progress('Assembling the captioned version from original clips', 97)
        from . import captions
        try:
            caption_result = captions.apply_to_run(directory, prepared['captions'])
        except Exception as exc:                  # captions never fail the production: the finished video stays as it was
            caption_error = str(exc)
    from .media import duration
    warnings = [entry['warning'] for entry in read_json(directory / 'quality.json', {}).values() if entry.get('warning')]
    vision_note = read_json(directory / 'vision.json', {}).get('note')
    if vision_note:
        warnings.insert(0, vision_note)
    if skipped := read_json(directory / 'vision.json', {}).get('rerender_skipped'):
        warnings.insert(0, skipped)
    if sub_error:
        warnings.insert(0, 'The subliminal flashes could not be added, so the finished video is the clean one: ' + sub_error[:200])
    caption_error = caption_error or (caption_result or {}).get('burn_error')
    if caption_error:
        warnings.insert(0, 'The lyric captions could not be burned in, so the finished video has none: ' + caption_error[:200])
    # Studio-quality clips: say plainly when the requested master was not delivered (never resubmitted automatically).
    lost = sorted(sid for sid, got in rendered.items() if isinstance(got, dict) and got.get('clip_quality_note'))
    if lost:
        warnings.insert(0, 'Studio-quality clip not delivered for ' + ', '.join(lost) + '; the standard clip was used for the final video and the export.')
    delivered = request.get('clip_quality') or 'standard'
    if lost and len(lost) == len(rendered):
        delivered = 'standard'
    write_json(directory/'output.json',{'file':output.name,'duration':duration(output),'kind':request['kind'],
                                       'title':request['title'] or 'Music video',
                                       **({'clip_quality': delivered, 'clip_quality_requested': request.get('clip_quality')}
                                          if (request.get('clip_quality') or 'standard') != 'standard' else {}),
                                       **({'subliminal': sub_result} if sub_result else {}),
                                       **({'captions': caption_result} if caption_result else {}),
                                       **({'quality_warnings': warnings} if warnings else {})})
    progress('Complete',100)


# Seeds for the single automatic re-render stay distinct from every passage's first seed.
RETRY_SEED_OFFSET = 7919
# Only these free local renderers may re-render a passage automatically; paid
# renderers are never resubmitted, whatever their price card says.
QUALITY_RETRY_BACKENDS = ('local_h3', 'comfy_sdk_h3')
# Passing beats a measured failure, which beats an unmeasurable clip.
_PIXEL = {'pass': 0, 'fail': 1}
_VISION = {'fail': 1, 'error': 2}


def _rank(attempt):
    vision = attempt.get('vision') or {}
    return (_PIXEL.get(attempt['status'], 2), _VISION.get(vision.get('status'), 0),
            len(attempt['problems']) + len(vision.get('problems', [])))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run_quality_stage(directory, backend, request, plan, rendered, render_passage, progress, vision=None):
    """Check every rendered passage, then re-render failures once as a batch; record outcomes.

    Only completed, structurally valid clips reach this stage: renderer errors,
    including ambiguous SDK submissions, have already stopped the run. Each passage
    has one retry budget, used only on free local renderers, under a deterministic
    segment ID and seed, so SDK receipts stay exact. Every attempt records its clip
    hash; a resumed run reuses saved verdicts for unchanged clips and recovers
    spent retries instead of discarding them.

    `vision`, when supplied, has `judge(items)` and `prepare_render()`. `judge`
    receives [(segment_id, attempt, result)] and returns {attempt_segment_id:
    {'status': 'pass'|'warn'|'fail'|'error', 'problems': [...], 'retry': bool}}.
    It is called for the chosen attempts, then once more for vision retries, so a
    production swaps renderer -> vision -> renderer -> vision at most.
    `prepare_render()` runs before rendering vision retries; False means a re-render
    would share the GPU with a vision model, so the retries are skipped.
    """
    from . import quality
    borders = not quality.framing_requested(request.get('direction'))
    free = request['backend'] in QUALITY_RETRY_BACKENDS and all(
        backend.cost_for(seg.duration_input) == 0 for seg in plan.segments)
    by_id = {seg.segment_id: seg for seg in plan.segments}
    total = len(plan.segments)
    saved = read_json(directory / 'quality.json', {})
    report, results = {}, {}

    def inspect(seg, result, segment_id, seed):
        digest = _sha256(result['video'])
        previous = next((a for a in saved.get(seg.segment_id, {}).get('attempts', [])
                         if a.get('segment_id') == segment_id and a.get('sha256') == digest
                         and a.get('status') in ('pass', 'fail')), None)
        if previous is not None:
            return dict(previous)
        found = quality.inspect_clip(result['video'], seg.trim_frames, [s.start_frame for s in seg.shots], borders)
        return dict(found, segment_id=segment_id, seed=seed, sha256=digest)

    def save():
        write_json(directory / 'quality.json', report)

    from .pipeline import render_seed
    progress('Checking every passage for motion and framing', 76)
    for seg in plan.segments:
        attempt = inspect(seg, rendered[seg.segment_id], seg.segment_id, render_seed(request) + seg.index)
        report[seg.segment_id] = {'attempts': [attempt],
                                  'retry_used': bool(saved.get(seg.segment_id, {}).get('retry_used'))}
        results[seg.segment_id] = [rendered[seg.segment_id]]
    save()

    def retry(candidates, label):
        for number, segment_id in enumerate(candidates):
            seg, entry = by_id[segment_id], report[segment_id]
            progress(f"Re-rendering passage {seg.index+1} of {total} once with a new seed ({label}; "
                     f"{number+1} of {len(candidates)})", 78)
            retry_id, retry_seed = segment_id + '-r1', entry['attempts'][0]['seed'] + RETRY_SEED_OFFSET
            entry['retry_used'] = True
            save()
            result = render_passage(seg, retry_id, retry_seed)
            entry['attempts'].append(inspect(seg, result, retry_id, retry_seed))
            results[segment_id].append(result)
            save()

    def best(segment_id):
        attempts = report[segment_id]['attempts']
        # The original wins ties; min returns the first of equal ranks.
        return min(range(len(attempts)), key=lambda i: _rank(attempts[i]))

    if free:
        # A crash after a retry was spent recovers it through its receipt instead of skipping it.
        recover = [s for s, e in report.items() if e['retry_used']]
        failing = [s for s, e in report.items() if e['attempts'][0]['status'] == 'fail' and not e['retry_used']]
        if recover:
            retry(recover, 'recovering an earlier retry')
        if failing:
            # Pixel failures are retried before any vision swap, while the renderer's models are loaded.
            retry(failing, 'motion/framing check')

    def judge(segment_ids, which):
        items = [(s, report[s]['attempts'][i], results[s][i]) for s in segment_ids for i in which(s)]
        pending = [item for item in items if not item[1].get('vision')]
        verdicts = vision.judge(pending) if pending else {}
        for segment_id, attempt, _ in pending:
            attempt['vision'] = verdicts.get(attempt['segment_id']) or {
                'status': 'error', 'problems': ['vision check returned no verdict'], 'retry': False}
        save()

    if vision is not None:
        progress('Vision check of every passage', 80)
        judge(list(report), lambda s: [best(s)])
        candidates = [s for s, e in report.items() if not e['retry_used'] and
                      (e['attempts'][best(s)].get('vision') or {}).get('retry')]
        if free and candidates and vision.prepare_render() is not False:
            retry(candidates, 'vision check')
            judge(candidates, lambda s: [len(report[s]['attempts']) - 1])

    chosen = {}
    for segment_id, entry in report.items():
        index, pick = by_id[segment_id].index, best(segment_id)
        used = entry['attempts'][pick]
        chosen[segment_id] = results[segment_id][pick]
        entry['used'] = used['segment_id']
        vision_verdict = used.get('vision') or {}
        details = ([] if used['status'] == 'pass' else list(used['problems']))
        details += [a['error'] for a in entry['attempts'] if a.get('error')]
        if vision_verdict.get('status') in ('warn', 'fail', 'error'):
            details += ['vision: ' + p for p in vision_verdict.get('problems', [])]
        clean = used['status'] == 'pass' and vision_verdict.get('status') not in ('fail', 'error')
        entry['status'] = ('ok' if clean and pick == 0 else 'retried_ok' if clean else
                           used['status'] if used['status'] != 'pass' else 'vision_' + vision_verdict['status'])
        entry.pop('warning', None)
        if details:
            entry['warning'] = (f"Passage {index+1}: {'; '.join(details)}"
                                + ('' if free or used['status'] == 'pass' else
                                   ' (not re-rendered automatically on this renderer)'))
    save()
    return chosen


def length_problems(prompt, limit):
    """The renderer's own prompt ceiling (max_prompt_chars from its capabilities, e.g. a rate card), checked before
    anything is submitted. No ceiling means no check; no number lives here."""
    if limit and len(prompt) > int(limit):
        return [f'prompt is {len(prompt)} characters; this renderer accepts at most {int(limit)}. '
                f'Shorten the shot bodies so the whole prompt fits.']
    return []


def service_logs(directory):
    """Where writer and ComfyUI output goes: the production folder, or the folder of the operation redoing one of its
    passages (MMV_SERVICE_LOG_DIR), so the log view of that operation shows the render as it happens."""
    return Path(os.environ.get('MMV_SERVICE_LOG_DIR') or directory)


def _guarded(home, call):
    """Run one worker phase: stop on SIGTERM, print a redacted error and exit 1 on failure, always clean up services."""
    import signal
    from . import runtime
    def terminate(signum, frame): raise SystemExit(130)
    signal.signal(signal.SIGTERM, terminate)
    try:
        call()
    except Exception as exc:
        message = str(exc)
        for value in Storage(home).secret_values():
            message = message.replace(value, '[redacted]')
        print(type(exc).__name__ + ': ' + message, flush=True)
        raise SystemExit(1)
    finally:
        runtime.cleanup()


def main():
    if sys.argv[1] == 'analyze':
        from .engine.analyze import analyze
        path=Path(sys.argv[3]); temp=path.with_suffix('.tmp')
        analyze(sys.argv[2],beats_per_bar=int(sys.argv[4])).to_json(temp)
        temp.replace(path)
    elif sys.argv[1] == 'drive':
        from .engine.analyze import ScoreMap
        from .stems import driven_score
        driven_score(ScoreMap.from_json(sys.argv[2]), sys.argv[3]).to_json(sys.argv[4])
    elif sys.argv[1] == 'voice':
        from .voice import estimate_voice
        Path(sys.argv[3]).write_text(json.dumps(estimate_voice(sys.argv[2])), encoding='utf-8')
    elif sys.argv[1] == 'produce':
        home,directory=Path(sys.argv[2]),Path(sys.argv[3])
        import signal
        from . import runtime
        def terminate(signum, frame): raise SystemExit(130)
        signal.signal(signal.SIGTERM,terminate)
        try:run(home,directory,resume=len(sys.argv)>4 and sys.argv[4]=='resume')
        except Exception as exc:
            message=str(exc)
            for value in Storage(home).secret_values():
                message=message.replace(value,'[redacted]')
            print(type(exc).__name__+': '+message,flush=True)
            raise SystemExit(1)
        finally:
            runtime.cleanup()
    elif sys.argv[1] == 'reroll':
        home, directory, segment_id = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
        seed = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else None
        from . import takes
        _guarded(home, lambda: takes.reroll_segment_worker(home, directory, segment_id, seed=seed))
    elif sys.argv[1] == 'rewrite_prompt':
        # One passage of a finished production through the normal prompt stage; an optional file holds a hand-edited candidate.
        home, directory, segment_id = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
        candidate = Path(sys.argv[5]).read_text(encoding='utf-8') if len(sys.argv) > 5 and sys.argv[5] else None
        seed = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else None
        world_id = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
        direction = sys.argv[8] if len(sys.argv) > 8 and sys.argv[8] else None
        _guarded(home, lambda: run(home, directory, rewrite={
            'segment': segment_id,
            'candidate': candidate,
            'seed': seed,
            'world_id': world_id,
            'direction': direction,
        }))
    else: raise SystemExit('Unknown worker phase')

if __name__=='__main__':main()
