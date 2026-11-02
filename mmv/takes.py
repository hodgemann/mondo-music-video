"""Segment take history, single-passage reroll rendering, and final video re-encoding."""
from __future__ import annotations

import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from .engine.backends.local_h3 import h3_cast_kwargs
from .storage import Storage, identifier, inside, read_json, write_json

TAKES_FILE = "takes.json"
FINAL_TAKES_FILE = "final_takes.json"
SEGMENT_ID_RE = re.compile(r"seg\d{3,4}")
TAKE_ID_RE = re.compile(r"take\d{1,4}")
# Only free renderers may reroll: a paid passage needs its own quote and consent, which reroll does not offer.
REROLL_BACKENDS = ("local_h3",)


PROMPT_TAKES_FILE = "prompt_takes.json"
PROMPT_TAKE_ID_RE = re.compile(r"prompt\d{1,4}")
PROMPT_ARTIFACTS = ("writer-", "validation-", "laya-request-", "laya-response-", "instrument-repair-", "advice", "dance-advice-kept")


def validate_prompt_take_id(prompt_take_id: str) -> str:
    if not PROMPT_TAKE_ID_RE.fullmatch(prompt_take_id or ""):
        raise ValueError("Invalid prompt version ID")
    return prompt_take_id


def prompt_block(request: dict, prepared: dict) -> str | None:
    """Why this production's passage prompts cannot be rewritten or edited, or None when they can."""
    if request.get("kind", "video") not in ("video", "ident"):
        return "Only music videos and idents have passage prompts."
    if not prepared.get("plan") or not prepared.get("settings"):
        return "The production's saved plan or settings are missing."
    return None


def writer_charge(prepared: dict) -> dict:
    """What one passage rewrite may cost: an API writer can charge per call, so it needs the user's acceptance."""
    api = (prepared.get("settings") or {}).get("writer_mode", "local") != "local"
    passages = max(1, len(prepared.get("segments") or (prepared.get("plan") or {}).get("segments") or []))
    return {"api_writer": api, "estimate_usd": round(float(prepared.get("writer_estimate") or 0) / passages, 4) if api else 0}


def _prompt_takes_view(directory: Path, plan: dict, prompts: dict) -> tuple[dict, bool]:
    """Prompt versions per passage with the production's validated prompt as version 1. Pure: returns (versions, changed)."""
    saved = read_json(directory / PROMPT_TAKES_FILE, {})
    segments = saved.get("segments") if isinstance(saved, dict) and isinstance(saved.get("segments"), dict) else {}
    sids = [f"seg{seg['index']:03d}" for seg in (plan.get("segments") or [])] or sorted(prompts)
    changed = not (directory / PROMPT_TAKES_FILE).is_file()
    for sid in sids:
        text = prompts.get(sid)
        if not isinstance(text, str) or not text:
            continue
        entry = segments.get(sid)
        if not isinstance(entry, dict) or not entry.get("takes"):
            segments[sid] = {"active_take": "prompt1", "takes": [{
                "id": "prompt1", "label": "Prompt 1 (original)", "prompt": text, "validated": True,
                "created_at": _mtime(directory / "prompts.json")}]}
            changed = True
            continue
        active = next((t for t in entry["takes"] if t.get("id") == entry.get("active_take")), None)
        matching = next((t["id"] for t in entry["takes"] if t.get("prompt") == text and t.get("validated", True)), None)
        if matching and not (active and active.get("prompt") == text and active.get("validated", True)):
            entry["active_take"] = matching
            changed = True
    return {"segments": segments}, changed


def get_prompt_takes(store: Storage, run_id: str) -> dict:
    """Prompt versions for a run. Read-only: nothing is written."""
    from .score_view import _origin_run, _run_files
    origin = _origin_run(store, run_id)
    plan, prompts, _ = _run_files(store, origin)
    return _prompt_takes_view(inside(store.home / "runs", identifier(origin)), plan, prompts)[0]


def _next_prompt_id(entry: dict) -> tuple[str, int]:
    number = max((int(t["id"][6:]) for t in entry.get("takes") or [] if PROMPT_TAKE_ID_RE.fullmatch(t.get("id", ""))), default=0) + 1
    return f"prompt{number}", number


def new_variation_seed(request: dict) -> int:
    """A random variation seed for one passage's new vocabulary, different from the production's own."""
    base = int(request.get("seed") or 0)
    seed = random.SystemRandom().randint(1, 2147483647)
    return seed if seed != base else (seed % 2147483646) + 1


def _used_segment_vocab(seg) -> dict[str, list[str]]:
    """Vocabulary terms this passage already has, by table, so a rewrite draws different ones. Stacked terms count singly."""
    shot_tables = {
        "setting": "settings",
        "subject_type": "subject_types",
        "mechanism": "mechanisms",
        "lighting": "lighting",
        "tonal_register": "tonal_registers",
        "costume": "costume",
    }
    pairs = [
        ("mechanisms", getattr(seg, "thematic_anchor", None)),
        ("footage_anchors", getattr(seg, "footage_anchor", None)),
        ("practical_effects", getattr(seg, "practical_effects", None)),
    ]
    for shot in getattr(seg, "shots", None) or []:
        for key, table in shot_tables.items():
            value = (getattr(shot, "vocab", None) or {}).get(key)
            if isinstance(value, str):
                pairs += [(table, value), *((table, part.strip()) for part in value.split(", "))]
    used: dict[str, list[str]] = {}
    for table, value in pairs:
        if value and value not in used.setdefault(table, []):
            used[table].append(value)
    return used


def world_custom_vocabulary(store: Storage, world_id: str | None) -> dict[str, dict]:
    """A built-in Thematic World name or saved World ID as custom_vocabulary overrides. An unknown one means the default vocabulary."""
    if not isinstance(world_id, str) or not world_id.strip():
        return {}
    clean = world_id.strip()
    from .world_vectors import BUILTIN_THEMATIC_WORLDS
    builtin = next((pools for name, pools in BUILTIN_THEMATIC_WORLDS.items() if name.casefold() == clean.casefold()), None)
    if builtin:
        return {table: {"mode": "replace", "add": list(terms), "exclude": []}
                for table, terms in builtin.items() if isinstance(terms, (list, tuple)) and terms}
    from . import worlds
    try:
        return worlds.custom_vocabulary(worlds.load(store, clean), mode="replace")
    except Exception:
        return {}


def replan_segment_vocabulary(store: Storage, request: dict, segments: list, index: int, seed: int | None = None,
                              world_id: str | None = None, direction_note: str | None = None) -> int:
    """Draw new vocabulary for segments[index] from the production's pool, with optional World and note steering.

    Timing, cuts, cast and rigging are kept. Other passages are read, never changed. A pool with no other term, or a
    world's own terms, can bring a term back: new terms are likely, not guaranteed. Returns the seed used."""
    from .engine.plan import CHAOTIC, FRAGMENTATION, STANDARD, THEMATIC, VocabSampler
    from .pipeline import load_vocabulary
    from .vocab_select import (
        apply_energy_scaled_vocabulary,
        contextual_vocabulary,
        plan_gaussian_world_dissonance,
        plan_world_departures,
    )

    seg = segments[index]
    actual_seed = seed if seed is not None else new_variation_seed(request)
    used = _used_segment_vocab(seg)
    custom = dict(request.get("custom_vocabulary") or {})
    world_custom = world_custom_vocabulary(store, world_id)
    if world_custom:
        custom = {**custom, **world_custom}

    vocab = load_vocabulary(
        request.get("vocabulary_profile", "full"),
        store=store,
        custom=custom or None,
    )
    contextual = request.get("vocab_selection") == "contextual" or bool(direction_note)
    if contextual:
        vocab = contextual_vocabulary(
            vocab,
            actual_seed,
            (
                request.get("direction", ""),
                str(direction_note or ""),
                request.get("title", ""),
                [t for spec in custom.values() for t in spec.get("add", [])],
            ),
        )

    sampler = VocabSampler(vocab, actual_seed, {table: list(terms) for table, terms in used.items()})
    pick = sampler.pick
    anchor = pick("mechanisms") if getattr(seg, "montage_type", STANDARD) == THEMATIC else None
    seg.thematic_anchor = anchor
    seg.footage_anchor = pick("footage_anchors")
    seg.practical_effects = pick("practical_effects")
    for shot in getattr(seg, "shots", None) or []:
        shot.vocab = (
            {
                "setting": pick("settings"),
                "subject_type": pick("subject_types"),
                "mechanism": anchor or pick("mechanisms"),
                "lighting": pick("lighting"),
                "tonal_register": pick("tonal_registers"),
                "costume": pick("costume"),
            }
            if getattr(seg, "montage_type", STANDARD) in (CHAOTIC, THEMATIC)
            else {"lighting": pick("lighting")}
        )
    if getattr(seg, "montage_type", STANDARD) in (STANDARD, FRAGMENTATION):
        shared = {
            "setting": pick("settings"),
            "subject_type": pick("subject_types"),
            "mechanism": pick("mechanisms"),
            "tonal_register": pick("tonal_registers"),
            "costume": pick("costume"),
        }
        for shot in getattr(seg, "shots", None) or []:
            shot.vocab.update(shared)

    def keep(changes):
        for (s_idx, sh_idx), change in changes.items():
            if s_idx == index:
                seg.shots[sh_idx].vocab = change[1] if isinstance(change, tuple) else change

    if contextual:
        fresh = {
            k: ([t for t in v if t not in set(used.get(k, ()))] or list(v)) if isinstance(v, list) else v
            for k, v in vocab.items()
        }
        keep(apply_energy_scaled_vocabulary(segments, fresh, actual_seed))
        worlds = request.get("thematic_worlds") if isinstance(request.get("thematic_worlds"), dict) else {}
        active = worlds.get("activeWorlds")
        if worlds.get("mode") in ("guided", "strict") and isinstance(active, list) and active and isinstance(active[0], str):
            keep(
                plan_gaussian_world_dissonance(
                    segments,
                    active[0],
                    seed=actual_seed,
                    slider_percent=min(100.0, max(0.0, float(worlds.get("slider", 50)))),
                )
            )
    if request.get("world_departures"):
        keep(
            plan_world_departures(
                segments,
                request["world_departures"],
                actual_seed,
                request.get("world_contrast_strength", 50),
            )
        )

    return actual_seed


def passage_vocabulary(segment: dict) -> dict:
    """The vocabulary a prompt version was written from. Pure."""
    return {
        "thematic_anchor": segment.get("thematic_anchor"),
        "footage_anchor": segment.get("footage_anchor"),
        "practical_effects": segment.get("practical_effects"),
        "shots": [shot.get("vocab") for shot in segment.get("shots") or []],
    }


def _with_passage_vocabulary(segments: list, segment_id: str, vocabulary: dict) -> list:
    """The plan's segments with one passage's vocabulary replaced. Pure."""
    def updated(segment):
        fields = {key: vocabulary[key] for key in ("thematic_anchor", "footage_anchor", "practical_effects")}
        shots = [{**shot, "vocab": vocab} for shot, vocab in zip(segment["shots"], vocabulary["shots"])]
        return {**segment, **fields, "shots": shots}
    return [updated(s) if f"seg{s['index']:03d}" == segment_id else s for s in segments]


def save_passage_vocabulary(directory: Path, segment_id: str, vocabulary: dict) -> None:
    """Write one passage's vocabulary to every saved copy of the plan: plan.json, and the plan and segments in prepared.json."""
    prepared = read_json(directory / "prepared.json", {})
    plan = read_json(directory / "plan.json", {}) or prepared.get("plan") or {}
    write_json(directory / "plan.json", {**plan, "segments": _with_passage_vocabulary(plan.get("segments") or [], segment_id, vocabulary)})
    if prepared:
        saved_plan = prepared.get("plan") or {}
        write_json(directory / "prepared.json", {
            **prepared, "segments": _with_passage_vocabulary(prepared.get("segments") or [], segment_id, vocabulary),
            "plan": {**saved_plan, "segments": _with_passage_vocabulary(saved_plan.get("segments") or [], segment_id, vocabulary)}})


def _current_vocabulary(directory: Path, segment_id: str) -> dict | None:
    plan = read_json(directory / "plan.json", {}) or read_json(directory / "prepared.json", {}).get("plan") or {}
    segments = plan.get("segments") or []
    return next((passage_vocabulary(s) for s in segments if f"seg{s['index']:03d}" == segment_id), None)


def begin_prompt_rewrite(directory: Path, segment_id: str) -> str:
    """Save version 1 and move the passage's earlier writer/review files aside, so the new attempt never overwrites them.
    Returns the ID the new version will get."""
    segment_id = validate_segment_id(segment_id)
    plan, prompts = read_json(directory / "plan.json", {}), read_json(directory / "prompts.json", {})
    data, _ = _prompt_takes_view(directory, plan, prompts)
    # Versions from before vocabulary was saved with them were all written from the plan as it still stands.
    vocabulary = _current_vocabulary(directory, segment_id)
    for take in (data["segments"].get(segment_id) or {}).get("takes") or []:
        take.setdefault("vocabulary", vocabulary)
    write_json(directory / PROMPT_TAKES_FILE, data)
    take_id, _ = _next_prompt_id(data["segments"].get(segment_id) or {})
    archive = directory / "prompt_takes" / segment_id / f"before-{take_id}"
    for path in directory.glob(f"{segment_id}.*.json"):
        if any(path.name[len(segment_id) + 1:].startswith(prefix) for prefix in PROMPT_ARTIFACTS):
            archive.mkdir(parents=True, exist_ok=True)
            path.replace(archive / path.name)
    return take_id


def record_prompt_take(directory: Path, segment_id: str, prompt: str, how: str, *, problems=None, variation_seed=None) -> dict:
    """Add a prompt version. A validated one becomes active (prompts.json already holds it); a hand edit that failed the
    checks is kept for further editing but never becomes the passage's prompt."""
    data = read_json(directory / PROMPT_TAKES_FILE, {"segments": {}})
    entry = data["segments"].setdefault(segment_id, {"active_take": "", "takes": []})
    take_id, number = _next_prompt_id(entry)
    take = {"id": take_id, "label": f"Prompt {number} ({how}{'' if problems is None else ', not passed'})", "prompt": prompt,
            "validated": problems is None, "created_at": time.time(), "vocabulary": _current_vocabulary(directory, segment_id),
            **({"variation_seed": variation_seed} if variation_seed is not None else {}),
            **({"problems": problems} if problems is not None else {})}
    entry["takes"].append(take)
    if problems is None:
        entry["active_take"] = take_id
    write_json(directory / PROMPT_TAKES_FILE, data)
    return take


def select_prompt_take(store: Storage, run_id: str, segment_id: str, prompt_take_id: str) -> dict:
    """Make a validated prompt version the passage's prompt. Clips already rendered are unchanged; reroll the clip to use it."""
    from .score_view import _origin_run, _run_files
    from . import passage_plans
    segment_id, prompt_take_id = validate_segment_id(segment_id), validate_prompt_take_id(prompt_take_id)
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, prompts, _ = _run_files(store, origin)
    data, _ = _prompt_takes_view(directory, plan, prompts)
    entry = data["segments"].get(segment_id) or {}
    chosen = next((t for t in entry.get("takes") or [] if t.get("id") == prompt_take_id), None)
    if chosen is None:
        raise ValueError(f"Prompt version {prompt_take_id} not found for passage {segment_id}")
    if not chosen.get("validated", True):
        raise ValueError(f"{chosen['label']} did not pass the Mondo checks and Laya review; edit it and check it again")
    entry["active_take"] = prompt_take_id
    prompts = {**prompts, segment_id: chosen["prompt"]}
    prepared = read_json(directory / "prepared.json", {})
    if prepared:                # binding first: if it fails, the prompt in use is unchanged
        passage_plans.bind_prompts(directory, prepared, prompts)
    if chosen.get("vocabulary"):    # the version and the vocabulary it was written from stay a pair
        save_passage_vocabulary(directory, segment_id, chosen["vocabulary"])
    write_json(directory / "prompts.json", prompts)
    write_json(directory / PROMPT_TAKES_FILE, data)
    return {"run_id": origin, "segment_id": segment_id, "active_prompt_take": prompt_take_id, "prompt_take": chosen}


def reroll_block(request: dict) -> str | None:
    """Why this production's passages cannot be rerolled, or None when they can."""
    if request.get("backend", "local_h3") not in REROLL_BACKENDS:
        return "Reroll is available for the local H3 renderer only; other renderers can submit paid jobs and need a new preview and consent."
    return None


def validate_segment_id(segment_id: str) -> str:
    if not SEGMENT_ID_RE.fullmatch(segment_id or ""):
        raise ValueError("Invalid passage ID")
    return segment_id


def validate_take_id(take_id: str) -> str:
    if not TAKE_ID_RE.fullmatch(take_id or ""):
        raise ValueError("Invalid take ID")
    return take_id


def _takes_view(directory: Path, plan: dict, request: dict, renders: dict) -> tuple[dict, bool]:
    """Recorded takes with each rendered passage's original clip as take 1. Pure: returns (takes, changed)."""
    takes = read_json(directory / TAKES_FILE, {})
    if not isinstance(takes, dict):
        takes = {}
    segments = takes.get("segments")
    if not isinstance(segments, dict):
        segments = {}
    attempts = read_json(directory / "quality.json", {})
    changed = False

    by_id = {f"seg{seg['index']:03d}": seg for seg in (plan.get("segments") or [])}
    all_sids = list(by_id.keys()) or sorted(renders.keys())

    for sid in all_sids:
        entry = segments.get(sid)
        got = renders.get(sid)
        if not isinstance(got, dict) or not got.get("video"):
            continue
        seg = by_id.get(sid, {"index": int(sid[3:]) if sid[3:].isdigit() else 0})
        if not isinstance(entry, dict) or not isinstance(entry.get("takes"), list) or not entry["takes"]:
            take1 = {
                "id": "take1",
                "label": "Take 1 (original)",
                "seed": got.get("seed", _original_seed(got, attempts.get(sid) or {}, request, seg["index"])),
                "video": got["video"],
                "audio": got.get("audio", ""),
                "created_at": got.get("created_at") or _mtime(directory / "renders.json"),
                "render": got,
            }
            segments[sid] = {"active_take": "take1", "takes": [take1]}
            changed = True
        else:
            # Take 1 records saved before its seed was derived from the render (1.11.0 showed 42 + index) are corrected.
            first = entry["takes"][0]
            if first.get("id") == "take1" and (first.get("render") or {}).get("seed") is None:
                seed = _original_seed(first.get("render") or first, attempts.get(sid) or {}, request, seg["index"])
                if first.get("seed") != seed:
                    first["seed"] = seed
                    changed = True
            # Ensure active_take points to a valid take or matches renders.json
            current_video = got.get("video")
            matching = next((t["id"] for t in entry["takes"] if t.get("video") == current_video), None)
            if matching and entry.get("active_take") != matching:
                entry["active_take"] = matching
                changed = True
            elif not entry.get("active_take"):
                entry["active_take"] = entry["takes"][-1]["id"]
                changed = True

    return {"segments": segments}, changed or not (directory / TAKES_FILE).is_file()


def _original_seed(got: dict, quality_entry: dict, request: dict, index: int) -> int:
    """The seed that produced a production's kept clip: a quality retry's own seed, else the production seed plus the
    passage index, as the worker renders it."""
    from .worker import RETRY_SEED_OFFSET
    name = Path(got.get("video", "")).name
    retried = [a for a in quality_entry.get("attempts") or []
               if "-r" in str(a.get("segment_id", "")) and a["segment_id"] in name and a.get("seed") is not None]
    if retried:
        return int(retried[-1]["seed"])
    from .pipeline import render_seed
    base = int(render_seed(request) or 0) + index
    # A kept retry clip is named segNNN-r1; its seed is fixed by the worker even when quality.json was rewritten on resume.
    return base + RETRY_SEED_OFFSET if f"seg{index:03d}-r1" in name else base


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else time.time()


def _ensure_takes_initialized(directory: Path, plan: dict, request: dict, renders: dict) -> dict:
    """The takes record, saved when it was missing or stale. Only actions that change takes call this."""
    takes, changed = _takes_view(directory, plan, request, renders)
    if changed:
        write_json(directory / TAKES_FILE, takes)
    return takes


def get_segment_takes(store: Storage, run_id: str) -> dict:
    """Takes for a run (derived outputs resolve to their origin run). Read-only: nothing is written."""
    from .score_view import _origin_run, _run_files
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, _, renders = _run_files(store, origin)
    request = read_json(directory / "request.json", {})
    return _takes_view(directory, plan, request, renders)[0]


def get_final_takes(store: Storage, run_id: str) -> dict:
    """Final assembled video versions for a run. Read-only: the original is listed until a re-encode saves it."""
    from .score_view import _origin_run
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    output = read_json(directory / "output.json", {})
    final_file = output.get("file") or ("ident.mp4" if output.get("kind") == "ident" else "music-video.mp4")
    records = read_json(directory / FINAL_TAKES_FILE, {})
    if not isinstance(records, dict) or not isinstance(records.get("takes"), list) or not records["takes"]:
        if (directory / final_file).is_file():
            initial = {
                "id": "final1",
                "label": "Version 1 (original)",
                "file": final_file,
                "created_at": (directory / final_file).stat().st_mtime,
            }
            records = {"active": final_file, "takes": [initial]}
        else:
            records = {"active": final_file, "takes": []}
    return records


def select_segment_take(store: Storage, run_id: str, segment_id: str, take_id: str) -> dict:
    """Select an existing take for a segment and update renders.json to point to it."""
    from .score_view import _origin_run, _run_files, _clip_roots, _recorded_clip
    segment_id = validate_segment_id(segment_id)
    take_id = validate_take_id(take_id)
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, _, renders = _run_files(store, origin)
    request = read_json(directory / "request.json", {})
    takes_data = _ensure_takes_initialized(directory, plan, request, renders)
    seg_entry = takes_data["segments"].get(segment_id)
    if not seg_entry or not seg_entry.get("takes"):
        raise ValueError(f"No takes recorded for passage {segment_id}")
    chosen = next((t for t in seg_entry["takes"] if t.get("id") == take_id), None)
    if not chosen:
        raise ValueError(f"Take {take_id} not found for passage {segment_id}")
    roots = _clip_roots(store)
    clip_path = _recorded_clip({"temp": chosen}, "temp", roots)
    if clip_path is None:
        raise ValueError(f"The video file for {take_id} is no longer available on disk")
    seg_entry["active_take"] = take_id
    write_json(directory / TAKES_FILE, takes_data)
    # The take's own render record replaces the passage entry, so no seed or receipt of another take lingers.
    renders[segment_id] = chosen.get("render") or {"video": chosen["video"], "audio": chosen.get("audio", ""), "seed": chosen.get("seed")}
    write_json(directory / "renders.json", renders)
    return {
        "run_id": origin,
        "segment_id": segment_id,
        "active_take": take_id,
        "take": chosen,
        "clip_url": f"/api/outputs/{origin}/clips/{segment_id}?take={take_id}",
    }


def reroll_segment_worker(home: Path, directory: Path, segment_id: str, seed: int | None = None) -> dict:
    """Render a single passage with a fresh seed in the worker process, preserving all previous takes."""
    import os
    os.environ["MMV_HOME"] = str(home)
    store = Storage(home)
    segment_id = validate_segment_id(segment_id)
    request = read_json(directory / "request.json", {})
    prepared = read_json(directory / "prepared.json", {})
    prompts = read_json(directory / "prompts.json", {})
    plan_dict = read_json(directory / "plan.json", {}) or prepared.get("plan") or {}
    renders = read_json(directory / "renders.json", {})

    if not request or not prepared or not plan_dict:
        raise ValueError("Saved production plan or request is missing; cannot reroll passage")
    if not prompts.get(segment_id):
        raise ValueError(f"No saved prompt for passage {segment_id}")
    if blocked := reroll_block(request):
        raise ValueError(blocked)

    from .engine import actor, casting, assemble
    from .engine.plan import ShotPlan
    from . import instruments, runtime
    from .render import get_backend
    from .pipeline import ENGINE
    from .worker import require_renderer_handoff, render_timeout, map_steps, service_logs

    plan_path = directory / "plan.json"
    if not plan_path.is_file():
        write_json(plan_path, plan_dict)
    plan = ShotPlan.from_json(plan_path)
    plan.slug = "mmv-" + directory.name

    seg = next((s for s in plan.segments if s.segment_id == segment_id), None)
    if seg is None:
        raise ValueError(f"Passage {segment_id} is not in this production's plan")

    def progress(message: str, value: int):
        print(message, flush=True)
        write_json(directory / "progress.json", {"message": message, "progress": value})

    # Replay the production's own prepared settings, as the original render did; later setting changes do not apply.
    settings = prepared.get("settings") or {}
    if not settings.get("workflow_map_path"):
        raise ValueError("Saved production settings are missing; cannot reroll passage")
    backend_name = request.get("backend", "local_h3")
    backend = get_backend(backend_name)

    roster = (prepared.get("casting") or {}).get("roster", [])
    actor_records = {}
    for member in roster:
        record = store.actor(member["actor_id"]) or {}
        actor_records[member["actor_id"]] = {
            **record,
            "display_name": member["display_name"],
            "reference_sheets": [member["sheet"]],
            "visual_contract": record.get("visual_contract") or {
                "default_sheet": member["sheet"],
                "sheets": {member["sheet"]: {"canonical_summary": record.get("description", "")}},
            },
        }
    actor.load_actor_meta = lambda actor_id: actor_records[actor_id]

    instrument_plan = prepared.get("instruments") or None
    instrument_passages = (instrument_plan or {}).get("passages", {})
    if instrument_plan:
        instruments.check_replay(request, instrument_plan)
        instruments.verify_assets(instrument_plan)

    takes_data = _ensure_takes_initialized(directory, plan_dict, request, renders)
    seg_takes = takes_data["segments"].setdefault(segment_id, {"active_take": "", "takes": []})
    existing_takes = seg_takes["takes"]
    used_seeds = {t.get("seed") for t in existing_takes if t.get("seed") is not None}

    if seed is None:
        candidate = random.randint(100000, 2147483000)
        while candidate in used_seeds:
            candidate = random.randint(100000, 2147483000)
        seed = candidate

    next_num = max((int(t["id"][4:]) for t in existing_takes if TAKE_ID_RE.fullmatch(t.get("id", ""))), default=0) + 1
    take_id = f"take{next_num}"
    render_seg_id = f"{segment_id}_{take_id}"

    progress(f"Preparing renderer for {segment_id} ({take_id}, seed {seed})", 10)
    if backend_name == "local_h3":
        require_renderer_handoff(settings)
        runtime.start_service(
            settings["comfy_launch"],
            settings["comfy_cwd"],
            settings["comfy_url"].rstrip("/") + "/system_stats",
            service_logs(directory) / "comfy-service.log",
            name="ComfyUI",
            launch_setting="comfy_launch",
        )

    sheets = casting.sheet_paths(prepared["casting"]) if prepared.get("casting") else {}
    if instrument_plan:
        sheets = {**sheets, **{"__instrument_" + kind: asset["path"] for kind, asset in instrument_plan["assets"].items()}}

    url = urlparse(settings["comfy_url"])
    if backend_name == "local_h3":
        from .engine.comfy import ComfyClient
        original_queue = ComfyClient.queue
        # The original run's render-graph.json and local-request.json stay as recovery records; each take keeps its own.
        def record_queue(client, graph):
            write_json(directory / f"render-graph-{render_seg_id}.json", graph)
            prompt_id = original_queue(client, graph)
            write_json(directory / f"local-request-{render_seg_id}.json", {"prompt_id": prompt_id})
            return prompt_id
        ComfyClient.queue = record_queue

    backend.open_render(
        slug=plan.slug,
        out_dir=directory / "renders",
        cast_sheets=list(sheets.items()),
        subject_image=None,
        song=None,
        steps=map_steps(settings["workflow_map_path"]),
        timeout_s=render_timeout(backend_name, settings.get("render_timeout_minutes", 120)),
        comfy_host=url.hostname,
        comfy_port=url.port or 8188,
        comfy_input=settings["comfy_input"],
        comfy_output=settings["comfy_output"],
        map_path=settings["workflow_map_path"],
        root=ENGINE,
        comfy_sdk_url=settings["comfy_sdk_url"],
        comfy_sdk_key=store.key("MMV_COMFY_API_KEY"),
        clip_quality=request.get("clip_quality") or "standard",
    )
    try:
        song = inside(store.home / "uploads", request["song"]) if request.get("kind", "video") == "video" else directory / "silence.wav"
        if request.get("kind") == "ident" and not song.is_file():
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(seg.gen_frames / 24), str(song)],
                check=True,
            )
        cast_members = casting.cast_for(prepared.get("casting"), seg.segment_id)
        images = [(member["actor_id"], sheets[member["actor_id"]]) for member in cast_members]
        if instrument_plan:
            images += instruments.images(instrument_passages[seg.segment_id], instrument_plan)
        if len(images) != seg.ref_image_slots:
            raise ValueError("Original cast/reference-slot contract disagrees; refusing render")

        progress(f"Rendering {segment_id} take {next_num} (seed {seed})", 35)
        result = backend.render_segment(
            segment_id=render_seg_id,
            index=seg.index,
            slug=plan.slug,
            prompt=prompts[seg.segment_id],
            duration_input=seg.duration_input,
            gen_frames=seg.gen_frames,
            width=plan.width,
            height=plan.height,
            seed=seed,
            images=images,
            **h3_cast_kwargs(settings, backend_name, cast_members),
            song=str(song),
            audio_start_s=seg.audio_slice_start_s,
            audio_end_s=seg.audio_slice_end_s,
        )
        video = result.get("video")
        if not video or not Path(video).is_file() or assemble.probe_frames(video) < seg.trim_frames:
            raise ValueError("Renderer returned a missing or short clip; refusing incomplete take")
    finally:
        backend.close_render()

    prompt_take = (read_json(directory / PROMPT_TAKES_FILE, {}).get("segments", {}).get(segment_id) or {}).get("active_take")
    render = {**result, "seed": seed, "take_id": take_id, **({"prompt_take": prompt_take} if prompt_take else {})}
    new_take = {
        "id": take_id,
        "label": f"Take {next_num} (seed {seed})",
        "seed": seed,
        "video": result["video"],
        "audio": result.get("audio", ""),
        "created_at": time.time(),
        "render": render,
        **({"prompt_take": prompt_take} if prompt_take else {}),
    }
    existing_takes.append(new_take)
    seg_takes["active_take"] = take_id
    write_json(directory / TAKES_FILE, takes_data)
    renders[segment_id] = render
    write_json(directory / "renders.json", renders)
    progress(f"Completed {segment_id} {take_id}", 100)
    return {
        "run_id": directory.name,
        "segment_id": segment_id,
        "active_take": take_id,
        "take": new_take,
    }


def reassemble_final_video(store: Storage, run_id: str, context, selected_takes: dict | None = None) -> dict:
    """Re-encode the final music video using the active (or specified) takes from original clips, preserving all previous final videos."""
    from .score_view import _origin_run, _run_files, _clip_roots, _recorded_clip
    from . import final_assembly, subliminal, captions
    from .media import duration

    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    request = read_json(directory / "request.json", {})
    prepared = read_json(directory / "prepared.json", {})
    plan, _, renders = _run_files(store, origin)
    if not plan.get("segments") or not renders:
        raise ValueError("Original assembly sources are unavailable; cannot reassemble video")

    # Every choice is checked first and saved only after the new video is assembled, so a refusal or failure changes nothing.
    takes_data = _takes_view(directory, plan, request, renders)[0]
    renders = dict(renders)
    for sid, tid in (selected_takes or {}).items():
        seg_entry = takes_data["segments"].get(validate_segment_id(sid)) or {}
        chosen = next((t for t in seg_entry.get("takes") or [] if t.get("id") == validate_take_id(tid)), None)
        if chosen is None:
            raise ValueError(f"Take {tid} not found for passage {sid}")
        if _recorded_clip({"t": chosen}, "t", _clip_roots(store)) is None:
            raise ValueError(f"The video file for {tid} is no longer available on disk")
        seg_entry["active_take"] = tid
        renders[sid] = chosen.get("render") or {"video": chosen["video"], "audio": chosen.get("audio", ""), "seed": chosen.get("seed")}

    output_record = read_json(directory / "output.json", {})
    final_name = output_record.get("file") or ("ident.mp4" if request.get("kind") == "ident" else "music-video.mp4")
    final_path = directory / final_name
    if not final_path.is_file() and not (directory / FINAL_TAKES_FILE).is_file():
        raise ValueError(f"The finished video {final_name} is missing; restore it so the original version is kept before re-encoding")

    # Preserve existing final video takes before re-encoding
    final_takes = get_final_takes(store, origin)
    if final_path.is_file():
        # Ensure Take 1 is backed up as a dedicated file if not already archived
        if len(final_takes["takes"]) == 1 and final_takes["takes"][0]["file"] == final_name:
            backup_v1 = f"{Path(final_name).stem}-v1.mp4"
            if not (directory / backup_v1).is_file():
                shutil.copy2(final_path, directory / backup_v1)
            final_takes["takes"][0]["file"] = backup_v1

    # Each FFmpeg encode runs through the operation, so Cancel stops it; a cancel between encodes keeps the records true.
    from .jobs import Cancelled
    run = lambda argv, cwd: context.command(argv, cwd=cwd)
    context.update("Re-assembling frame-exact final video from selected passage takes", 25)
    output = final_assembly.assemble(store, directory, request, plan, renders, run=run)
    write_json(directory / TAKES_FILE, takes_data)
    write_json(directory / "renders.json", renders)

    # Each variant is assembled from the original clips, as in the first production; a failed effect is reported, not hidden.
    warnings, effects, cancelled = [], {}, None
    if request.get("kind") == "video" and prepared.get("subliminal"):
        context.update("Applying subliminal version from selected passage clips", 75)
        try:
            effects["subliminal"] = subliminal.apply_to_run(store, directory, prepared["subliminal"], run=run)
        except Cancelled as exc:
            cancelled = exc
            warnings.append("Cancelled before the subliminal flashes were added, so this version is the clean one.")
        except Exception as exc:
            warnings.append("The subliminal flashes could not be added, so this version is the clean one: " + str(exc)[:200])

    if cancelled is None and request.get("kind") == "video" and (prepared.get("captions") or {}).get("cues"):
        context.update("Applying lyric captions from selected passage clips", 85)
        try:
            effects["captions"] = captions.apply_to_run(directory, prepared["captions"], run=run)
        except Cancelled as exc:
            cancelled = exc
            warnings.append("Cancelled before the lyric captions were burned in, so this version has none.")
        except Exception as exc:
            effects["captions"] = {"burn_error": str(exc)}
        if burn_error := (effects.get("captions") or {}).get("burn_error"):
            warnings.append("The lyric captions could not be burned in, so this version has none: " + burn_error[:200])

    next_v = len(final_takes["takes"]) + 1
    version_file = f"{Path(final_name).stem}-v{next_v}.mp4"
    shutil.copy2(output, directory / version_file)

    active_summary = {
        sid: entry.get("active_take", "take1")
        for sid, entry in takes_data.get("segments", {}).items()
    }
    new_final_take = {
        "id": f"final{next_v}",
        "label": f"Version {next_v} ({time.strftime('%H:%M:%S')})",
        "file": version_file,
        "created_at": time.time(),
        "segment_takes": active_summary,
        **({"warnings": warnings} if warnings else {}),
    }
    final_takes["takes"].append(new_final_take)
    final_takes["active"] = final_name
    write_json(directory / FINAL_TAKES_FILE, final_takes)

    measured = duration(output)
    for key in ("subliminal", "captions", "reassembly_warnings"):
        output_record.pop(key, None)
    output_record.update({
        "file": output.name,
        "duration": measured,
        "final_takes": [t["file"] for t in final_takes["takes"] if t.get("file")],
        **{key: value for key, value in effects.items() if value},
        **({"reassembly_warnings": warnings} if warnings else {}),
    })
    write_json(directory / "output.json", output_record)
    if cancelled is not None:      # the version that was built is recorded truthfully; the operation still ends cancelled
        raise cancelled
    context.update("Re-assembly complete", 100)
    return {
        "file": f"{origin}/{output.name}",
        "version_file": f"{origin}/{version_file}",
        "duration": measured,
        "final_take": new_final_take,
        "final_takes": final_takes["takes"],
        "warnings": warnings,
    }
