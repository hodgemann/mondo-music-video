"""Mondo Music Video: a focused public server, independent of the private studio."""
from __future__ import annotations

import json
import logging
import math
import os
import secrets
import shutil
import sys
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import oap

class _PollingAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in ("/api/status", "/api/events", "/api/log/", "/api/services"))

logging.getLogger("uvicorn.access").addFilter(_PollingAccessFilter())
from fastapi import HTTPException, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mmv import actors, agreements, instrument_assets, oap_collection, production, props, score_view, worlds
from mmv.jobs import BusyError, Jobs, interrupted_message, job_run_id, upload_name
from mmv import production_queue
from mmv.pipeline import VOCAB_TABLES, apply_vocabulary_overrides, load_vocabulary, render_seed
from mmv.render import CATALOG
from mmv.services import check_services
from mmv.storyboard import Storyboard
from mmv.workflow_presets import map_steps, preset_for_model, preset_path, workflow_presets
from mmv.storage import DEFAULTS, Storage, identifier, inside, read_json, write_json

LOG_FILES = ("operation.log", "writer-service.log", "comfy-service.log")
MGL_APP_VERSION = "1.12.2"
WEB = Path(__file__).parent


H3_MODEL_ROLES = {
    'video_vae': ('VAELoader', 'vae_name', 'vae'),
    'audio_vae': ('VAELoader', 'vae_name', 'vae'),
    'diffusion_model': ('UNETLoader', 'unet_name', 'diffusion_models'),
    'text_encoder': ('CLIPLoader', 'clip_name', 'text_encoders'),
}


def _h3_workflow(settings):
    from mmv.engine.comfy import WorkflowBuilder
    engine = Path(__file__).parent.parent / 'mmv/engine'
    return WorkflowBuilder.load(settings['workflow_map_path'], engine)


def _h3_model_nodes(graph):
    if not isinstance(graph, dict) or any(not isinstance(node, dict) for node in graph.values()):
        raise ValueError('The selected file is not a workflow graph')
    nodes = {}
    for role, (loader, field, _) in H3_MODEL_ROLES.items():
        matches = [key for key, node in graph.items() if node.get('class_type') == loader]
        selected = None
        if role in ('video_vae', 'audio_vae'):
            decoder = 'VAEDecode' if role == 'video_vae' else 'VAEDecodeAudio'
            connected = {node.get('inputs', {}).get('vae', [''])[0] for node in graph.values()
                         if node.get('class_type') == decoder
                         and isinstance(node.get('inputs', {}).get('vae'), list)
                         and node['inputs']['vae']}
            valid = connected.intersection(matches)
            if len(valid) == 1:
                selected = valid.pop()
        if selected is None and len(matches) == 1:
            selected = matches[0]
        if selected is not None and isinstance(graph[selected].get('inputs', {}).get(field), str):
            nodes[role] = selected
    return nodes


def _get_h3_model_info(store, settings=None):
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    settings = settings or store.settings()
    current = {}
    try:
        graph = _h3_workflow(settings).base
        for role, node in _h3_model_nodes(graph).items():
            current[role] = graph[node]['inputs'][H3_MODEL_ROLES[role][1]]
    except (OSError, ValueError, KeyError, TypeError):
        # Settings must remain editable when the selected workflow needs repair.
        pass
    installed = {role: [] for role in H3_MODEL_ROLES}
    comfy_url = settings.get('comfy_url', '').rstrip('/')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    discovered = {}
    loaders = {loader: field for loader, field, _ in H3_MODEL_ROLES.values()}
    if comfy_url and loaders:
        def _probe_loader(item):
            loader, field = item
            try:
                with opener.open(f'{comfy_url}/object_info/{loader}', timeout=.25) as response:
                    data = json.load(response)
                choices = data[loader]['input']['required'][field][0]
                return loader, [name for name in choices if isinstance(name, str)] if isinstance(choices, list) else []
            except (OSError, ValueError, KeyError, TypeError):
                return loader, []
        with ThreadPoolExecutor(max_workers=len(loaders)) as pool:
            discovered = dict(pool.map(_probe_loader, loaders.items()))
    comfy_input = settings.get('comfy_input')
    for role, (loader, _, category) in H3_MODEL_ROLES.items():
        installed[role] = discovered.get(loader, [])
        if not installed[role] and comfy_input:
            folder = Path(comfy_input).expanduser().parent / 'models' / category
            try:
                installed[role] = sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*.safetensors') if p.is_file())
            except OSError:
                pass
    return {'current': current, 'installed': installed}


def _rebase_for_model(store, settings, models):
    """A bundled diffusion model brings its own workflow: choosing the 20-step H3 model on an 8-step
    FastH3 workflow (or the reverse) switches to that model's preset and keeps the other chosen models.
    A custom workflow whose step count already matches is left as it is."""
    current = _get_h3_model_info(store, settings)['current']
    chosen = {**current, **models}
    preset = preset_for_model(chosen.get('diffusion_model'))
    if preset is None or map_steps(preset['path']) == map_steps(settings['workflow_map_path']):
        return models
    settings['workflow_map_path'] = preset['path']
    return chosen


def _update_h3_models(store, settings, models):
    """Derive a private workflow snapshot; never overwrite the source graph/map."""
    models = _rebase_for_model(store, settings, models)
    builder = _h3_workflow(settings)
    nodes = _h3_model_nodes(builder.base)
    info = _get_h3_model_info(store, settings)
    changed = False
    for role, name in models.items():
        if role not in nodes:
            raise ValueError(f'The selected workflow has no unambiguous {role} loader')
        field = H3_MODEL_ROLES[role][1]
        previous = builder.base[nodes[role]]['inputs'][field]
        if name == previous:
            continue
        if name not in info['installed'][role]:
            raise ValueError(f'{role}: choose a model reported installed by ComfyUI or its model folder')
        builder.base[nodes[role]]['inputs'][field] = name
        changed = True
    if changed:
        directory = store.home / 'config'
        name = 'h3-selected-' + uuid.uuid4().hex
        graph_path = directory / (name + '.json')
        map_path = directory / (name + '-map.json')
        write_json(graph_path, builder.base)
        write_json(map_path, {**builder.map, 'workflow': str(graph_path)})
        settings['workflow_map_path'] = str(map_path)


def log_studio(store, message: str, level: str = "INFO"):
    try:
        log_file = store.home / "studio.log"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    except Exception:
        pass


def api_version():
    return {"name": "Mondo Music Video", "version": MGL_APP_VERSION}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class VocabularyTableOverride(StrictModel):
    mode: Literal["append", "replace"] = "append"
    add: list[str] = Field(default_factory=list, max_length=500)
    exclude: list[str] = Field(default_factory=list, max_length=500)


class WorldRequest(StrictModel):
    id: str = Field(max_length=64)
    name: str = Field(min_length=1, max_length=160)
    seed_sentence: str = Field(default="", max_length=400)
    subjects: list[dict[str, str]] = Field(default_factory=list, max_length=worlds.MAX_SUBJECTS)
    pools: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    core_laws: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    locations: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    practices: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    objects: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    factions: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    ecology_rules: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    moral_ambiguities: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    open_threads: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)
    do_not_contradict: list[str] = Field(default_factory=list, max_length=worlds.MAX_LIST)


class WorldEditRequest(WorldRequest):
    id: str = Field(default="", max_length=64)
    base_version: int = Field(ge=1, le=9999)


class WorldRollbackRequest(StrictModel):
    version: int = Field(ge=1, le=9999)


class VocabularyRequest(StrictModel):
    id: str = Field(max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    base_profile: Literal["full", "reduced_flashing"] = "full"
    tables: dict[str, VocabularyTableOverride] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value):
        value = identifier(value)
        if value in ("full", "reduced_flashing"):
            raise ValueError("Cannot overwrite a built-in visual vocabulary profile")
        return value

    @field_validator("tables")
    @classmethod
    def valid_tables(cls, value):
        if any(k not in VOCAB_TABLES for k in value):
            raise ValueError("Unknown vocabulary category")
        return value


class LyricLine(StrictModel):
    start: float = Field(ge=0, le=36000)
    end: float = Field(gt=0, le=36000)
    text: str = Field(min_length=1, max_length=300)
    timing: Literal["manual", "matched", "interpolated", "uncertain"] = "manual"
    section: str | None = Field(default=None, max_length=40)


class ScoreSectionEdit(StrictModel):
    start: float = Field(ge=0, le=36000)
    label: Literal["low", "mid", "high", "peak"]


class ScoreEdits(StrictModel):
    bar_one_beat: int | None = Field(default=None, ge=0, le=100000)
    beat_nudge_ms: int = Field(default=0, ge=-250, le=250)
    muted_beats: list[int] = Field(default_factory=list, max_length=2000)
    sections: list[ScoreSectionEdit] = Field(default_factory=list, max_length=64)


class LyricsRequest(StrictModel):
    song: str = Field(max_length=128)
    model: Literal["tiny", "base", "small", "medium", "large-v3"] = "large-v3"
    beats_per_bar: int = Field(default=4, ge=2, le=12)
    use_vocals: bool = True
    text: str = Field(default="", max_length=16000)


class LyricsPrepareRequest(StrictModel):
    model: Literal["tiny", "base", "small", "medium", "large-v3"] = "large-v3"
    consent: bool = False


class PackageRequest(StrictModel):
    zip: bool = False
    allow_private_actors: bool = False


class StemsPrepareRequest(StrictModel):
    model: Literal["htdemucs", "htdemucs_ft", "htdemucs_6s"] = "htdemucs"
    consent: bool = False


class SubliminalSettings(StrictModel):
    mode: Literal["off", "image", "text"] = "off"
    image: str = Field(default="", max_length=128)
    text: str = Field(default="", max_length=60)
    frames: int = Field(default=2, ge=1, le=12)
    placement: Literal["manual", "downbeats"] = "manual"
    times: list[float] = Field(default_factory=list, max_length=20)
    count: int = Field(default=3, ge=1, le=20)


class CaptionSettings(StrictModel):
    mode: Literal["off", "sidecar", "burned"] = "off"
    style: Literal["classic", "bold", "neon", "box"] = "classic"
    position: Literal["bottom", "middle", "top"] = "bottom"
    size: Literal["small", "medium", "large"] = "medium"
    color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    outline_color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    font: str = Field(default="", max_length=40, pattern=r"^([A-Za-z0-9][A-Za-z0-9 ._+-]*)?$")


class ProductionRequest(StrictModel):
    kind: Literal["video", "ident", "harvest", "world_harvest", "storyboard"] = "video"
    title: str = Field(default="", max_length=160)
    song: str = Field(default="", max_length=128)
    backend: Literal["local_h3", "comfy_sdk_h3", "wavespeed", "seedance_2", "seedance_2_5"] = "local_h3"
    resolution: Literal["480p", "720p", "768p", "1080p", "2k", "4k"] = "768p"
    aspect: Literal["16:9", "9:16", "1:1", "4:3", "3:4", "5:4", "4:5", "2:1", "1:2", "21:9", "9:21", "3:1", "1:3"] = "16:9"
    direction: str = Field(default="", max_length=6000)
    style_id: str = Field(default="daylight", max_length=64)
    actors: list[str] = Field(default_factory=list, max_length=9)
    references: list[str] = Field(default_factory=list, max_length=9)
    content: dict[str, str] = Field(default_factory=lambda: {key: "none" for key in oap.CONTENT_ENUMS})
    beats_per_bar: int = Field(default=4, ge=2, le=12)
    bars_per_phrase: int = Field(default=8, ge=1, le=32)
    seed: int = Field(default=0, ge=0, le=2147483647)              # variation seed: shot plan, vocabulary and casting
    render_seed: int | None = Field(default=None, ge=0, le=2147483647)   # renderer seed base; None: random, fixed at preview
    megapixels: float = Field(default=.6, ge=.15, le=4)
    conceptual_theme: str = Field(default="", max_length=2000)
    lyrics: str = Field(default="", max_length=16000)
    silent_mouths: bool = True
    mouth_mode: Literal["sealed", "natural", "lip_sync"] | None = None
    lyric_lines: list[LyricLine] = Field(default_factory=list, max_length=500)
    singers: list[str] = Field(default_factory=list, max_length=9)
    dance_mode: Literal["off", "group", "independent"] = "off"
    dancers: list[str] = Field(default_factory=list, max_length=9)
    dance_direction: str = Field("", max_length=200)
    dance_lead: str | None = None
    dance_parts: dict[str, Literal["auto", "beat", "drums", "bass", "vocals"]] = Field(default_factory=dict, max_length=9)
    instrument_mode: Literal["off", "perform"] = "off"
    instrument_assignments: dict[str, Literal["drums", "bass", "guitar", "keyboards"]] = Field(default_factory=dict, max_length=9)
    instrument_references: bool = True
    instrument_props: dict[str, str] = Field(default_factory=dict, max_length=4)
    instrument_prop_uses: dict[str, str] = Field(default_factory=dict, max_length=4)
    ref_policy: Literal["fragmentation", "single_subject", "all"] = "all"
    casting_policy: Literal["random", "rotate", "section"] = "random"
    ensemble_mode: Literal["off", "always", "mixed"] = "off"
    on_screen: int = Field(default=1, ge=1, le=9)
    ident_mode: Literal["standard", "harvest", "scenographic"] = "standard"
    storyboard: Storyboard = Field(default_factory=Storyboard)
    ident_all_references: bool = False
    ident_seconds: float = Field(default=5, ge=4, le=12)
    start_ident: str = Field(default="", max_length=128)
    end_ident: str = Field(default="", max_length=128)
    reuse_prompts: bool = True
    vision_quality_check: bool = False
    clip_quality: Literal["standard", "prores", "lossless"] = "standard"
    subliminal: SubliminalSettings = Field(default_factory=SubliminalSettings)
    captions: CaptionSettings = Field(default_factory=CaptionSettings)
    compact_prompts: bool = False
    strict_prompt_checks: bool = False
    score_edits: ScoreEdits = Field(default_factory=ScoreEdits)
    analysis_driver: Literal["mix", "drums", "bass", "vocals", "other", "guitar", "piano"] = "mix"
    stem_quality: Literal["standard", "high"] = "standard"
    vocabulary_profile: str = Field(default="full", max_length=64)
    custom_vocabulary: dict[str, VocabularyTableOverride] = Field(default_factory=dict)
    thematic_worlds: dict[str, Any] | None = None
    vocab_selection: Literal["legacy", "contextual"] = "legacy"
    world_id: str = Field(default="", max_length=64)
    world_pool_mode: Literal["append", "replace"] = "replace"
    world_contrast: dict[Literal["mirror", "opposite", "tangent"], str] = Field(default_factory=dict)
    world_contrast_strength: int = Field(default=50, ge=0, le=100)
    world_departures: dict[Literal["mirror", "opposite", "tangent"], dict[str, list[str]]] = Field(default_factory=dict)
    world_mode: Literal["", "create", "grow"] = ""
    world_images: list[str] = Field(default_factory=list, max_length=worlds.MAX_IMAGES)
    world_videos: list[str] = Field(default_factory=list, max_length=3)
    world_lore: list[str] = Field(default_factory=list, max_length=worlds.MAX_LORE_FILES)
    world_runs: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("world_id")
    @classmethod
    def valid_world_id(cls, value):
        return identifier(value) if value else ""

    @field_validator("world_contrast")
    @classmethod
    def valid_world_contrast(cls, value):
        return {role: identifier(world) for role, world in value.items() if world}

    @field_validator("world_departures")
    @classmethod
    def valid_world_departures(cls, value):
        """The resolved contrast pools saved with a run, so resume and retry replay the same terms."""
        if any(table not in worlds.WORLD_TABLES or len(terms) > worlds.MAX_POOL or any(len(t) > 300 for t in terms)
               for pools in value.values() for table, terms in pools.items()):
            raise ValueError("Invalid contrast pools")
        return value

    @model_validator(mode="after")
    def contrast_differs_from_world(self):
        if self.world_id and self.world_id in self.world_contrast.values():
            raise ValueError("A contrast world must differ from the main world")
        return self

    @field_validator("vocabulary_profile")
    @classmethod
    def valid_vocabulary_profile(cls, value):
        return identifier(value) if value else "full"

    @field_validator("custom_vocabulary")
    @classmethod
    def valid_custom_vocabulary(cls, value):
        if any(k not in VOCAB_TABLES for k in value):
            raise ValueError("Unknown vocabulary category")
        return value

    @field_validator("content")
    @classmethod
    def valid_content(cls, value):
        if set(value) != set(oap.CONTENT_ENUMS) or any(value[k] not in levels for k, levels in oap.CONTENT_ENUMS.items()):
            raise ValueError("Choose a valid OAP content rating for each category")
        return value


DANCE_FIELDS = ("dance_mode", "dancers", "dance_direction", "dance_lead", "dance_parts")


def request_dict(value):
    """The stored production request. A request without dancing or captions is stored exactly as it was before they existed."""
    request = value.model_dump()
    if request['kind'] != 'storyboard' and not request['storyboard']['enabled']:
        request.pop('storyboard')
    elif request['kind'] not in ('storyboard', 'video', 'ident'):
        raise ValueError('Storyboards are available for music videos and idents')
    if not request['ident_all_references']:
        request.pop('ident_all_references')
    elif request['kind'] != 'ident':
        raise ValueError('Use all ident references is only available for idents')
    if request.get("captions", {}).get("mode", "off") == "off":
        request.pop("captions", None)
    if not request.get("strict_prompt_checks"):
        request.pop("strict_prompt_checks", None)
    if request.get("render_seed") is None:
        request.pop("render_seed", None)       # pipeline.prepare picks it, so earlier requests keep their exact form
    if request["kind"] != "video" or not request.get("world_id") or not request.get("world_contrast") or not request.get("world_contrast_strength"):
        for key in ("world_contrast", "world_contrast_strength", "world_departures"):
            request.pop(key, None)
    elif not request.get("world_departures"):
        request.pop("world_departures", None)
    if request.get("vocab_selection", "legacy") == "legacy":
        request.pop("vocab_selection", None)
    if request.get("dance_mode", "off") == "off":
        for key in DANCE_FIELDS:
            request.pop(key, None)
    if request.get("instrument_mode", "off") == "off":
        for key in ("instrument_mode", "instrument_assignments", "instrument_references", "instrument_props", "instrument_prop_uses"):
            request.pop(key, None)
    elif request["kind"] != "video":
        raise ValueError("Instrument performance is available for music videos only")
    if request["kind"] == "world_harvest":
        if request["world_mode"] not in ("create", "grow") or not request["world_id"]:
            raise ValueError("Choose a world ID and whether to create or grow it")
        request.pop("world_pool_mode")
    else:
        for key in ("world_mode", "world_images", "world_videos", "world_lore", "world_runs"):
            request.pop(key)
        if request["kind"] != "video" or not request["world_id"]:
            request.pop("world_id")
            request.pop("world_pool_mode")
    if request.get("vocab_selection", "legacy") == "legacy":
        request.pop("vocab_selection", None)
    if not request.get("thematic_worlds") or request.get("thematic_worlds", {}).get("mode", "off") == "off":
        request.pop("thematic_worlds", None)
    return request


def with_world(store, request):
    """The request with the chosen world's pools merged into its custom vocabulary (the world wins for tables it describes)."""
    if request.get("kind") != "video" or not request.get("world_id"):
        return request
    ledger = worlds.load(store, request["world_id"])
    merged = {**{k: v for k, v in request.items() if k != "world_departures"}, "custom_vocabulary": {**request["custom_vocabulary"], **worlds.custom_vocabulary(
        ledger, request["world_pool_mode"])}}
    contrast = {role: worlds.load(store, world) for role, world in request.get("world_contrast", {}).items()}
    pools = {role: {table: pool["include"] for table, pool in ledger["pools"].items() if pool.get("include")}
             for role, ledger in contrast.items()}
    return {**merged, "world_departures": {role: terms for role, terms in pools.items() if terms}} if any(pools.values()) else merged


def instrument_preview(plan):
    if not plan:
        return plan
    shown = ('id', 'name', 'description', 'sha256', 'width', 'height', 'license', 'clearance',
             'prop_id', 'sheet_kind', 'sheet_label', 'sheet_tags', 'use')
    return {**plan, 'assets': {kind: {key: asset[key] for key in shown if key in asset}
                               for kind, asset in plan.get('assets', {}).items()}}


class StartRequest(StrictModel):
    quote_id: str
    consent: bool = False


class QueueAddRequest(StrictModel):
    quote_id: str
    consent: bool = False
    replaces: str | None = None


class QueueMoveRequest(StrictModel):
    delta: Literal[-1, 1]


class ResumeRequest(StrictModel):
    run_id: str


class Settings(StrictModel):
    writer_api_profile: str = ""
    vision_api_profile: str = ""
    video_api_profile: str = ""
    auto_updates: bool = False
    auto_collapse_panels: bool = True
    render_timeout_minutes: int = Field(default=120, ge=0, le=1440)
    backend: Literal["local_h3", "comfy_sdk_h3", "wavespeed", "seedance_2", "seedance_2_5"] = "local_h3"
    comfy_url: str = "http://127.0.0.1:8188"
    comfy_sdk_url: str = "http://127.0.0.1:8189"
    comfy_input: str = ""
    comfy_output: str = ""
    workflow_map_path: str = DEFAULTS["workflow_map_path"]
    writer_url: str = "http://127.0.0.1:8080/v1"
    writer_model: str = ""
    writer_mode: Literal["local", "api"] = "local"
    writer_call_estimate: float = Field(default=0, ge=0, le=100)
    writer_launch: str = ""
    writer_cwd: str = ""
    comfy_launch: str = ""
    comfy_cwd: str = ""
    laya_model_dir: str = ""
    laya_device: Literal["cpu", "cuda", "mps", "auto", "cuda_or_cpu", "mps_or_cpu"] = "cuda"
    vision_url: str = "http://127.0.0.1:8080/v1"
    vision_model: str = ""
    vision_launch: str = ""
    vision_key_env: Literal["MMV_VISION_API_KEY"] = "MMV_VISION_API_KEY"
    vision_call_estimate: float = Field(default=0, ge=0, le=100)
    topaz_executable: str = ""
    topaz_models: str = ""
    topaz_backend: Literal["local", "cloud"] = "local"
    h3_models: dict[str, str] = Field(default_factory=dict)
    workflow_preset: str = ""

    @field_validator("writer_api_profile", "vision_api_profile", "video_api_profile")
    @classmethod
    def valid_api_profile(cls, value):
        return identifier(value) if value else ""

    @field_validator("h3_models")
    @classmethod
    def valid_h3_models(cls, models):
        if any(key not in H3_MODEL_ROLES or not value or len(value) > 512
               or value.startswith(('/', '\\')) or ':' in value
               or '..' in value.replace('\\', '/').split('/') for key, value in models.items()):
            raise ValueError('Use known H3 model roles and relative installed model names')
        return models

    @field_validator("comfy_sdk_url")
    @classmethod
    def valid_proxy(cls, value):
        from mmv.comfy_sdk import validate_proxy_url
        return validate_proxy_url(value)

    @field_validator("writer_launch", "comfy_launch", "vision_launch")
    @classmethod
    def valid_launch(cls, value):
        if value:
            import json
            try: command = json.loads(value)
            except (ValueError,TypeError): raise ValueError("Use a JSON array of command arguments")
            if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x for x in command):
                raise ValueError("Use a nonempty JSON array of command arguments")
        return value

    @field_validator("comfy_url", "vision_url", "writer_url")
    @classmethod
    def valid_url(cls, value):
        url = urlparse(value)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("Use an HTTP(S) service URL without embedded credentials")
        return value.rstrip("/")


class ApiProfileRequest(StrictModel):
    name: str
    role: Literal["writer", "vision", "video"]
    settings: dict | None = None
    key: str | None = Field(default=None, max_length=1000)


class StarterRequest(StrictModel):
    accept_starter_signer: bool = False
    restore_removed: bool = False


class ActorUpdateRequest(StrictModel):
    description: str = Field(max_length=6000)


class CollectionStageRequest(StrictModel):
    actor_id: str
    index_sha256: str


class KeyRequest(StrictModel):
    name: Literal["WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY", "MMV_COMFY_API_KEY", "MMV_TOPAZ_API_KEY"]
    value: str = Field(max_length=1000)


class StyleRequest(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=160)
    direction: str = Field(min_length=1, max_length=8000)
    style_card: str | None = Field(default=None, max_length=16000)
    vocabulary: dict[str, VocabularyTableOverride] = Field(default_factory=dict)


class StyleImportRequest(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=160)
    direction: str = Field(min_length=1, max_length=8000)
    style_card: str | None = Field(default=None, max_length=16000)
    vocabulary: dict[str, VocabularyTableOverride] = Field(default_factory=dict)
    overwrite: bool = False


def style_payload(value, style_id):
    """The stored style card. An optional vocabulary is validated like a custom vocabulary and kept as data only;
    it is never applied unless the user chooses it on the video form."""
    vocabulary = {key: spec.model_dump() for key, spec in value.vocabulary.items()}
    if any(len(term) > 300 for spec in vocabulary.values() for key in ("add", "exclude") for term in spec[key]):
        raise ValueError("Style vocabulary entries must be 300 characters or fewer")
    if vocabulary:
        apply_vocabulary_overrides(load_vocabulary("full"), vocabulary)
    return {"id": style_id, "name": value.name.strip(), "direction": value.direction.strip(),
            **({"style_card": value.style_card} if value.style_card else {}),
            **({"vocabulary": vocabulary} if vocabulary else {})}


class AgreementRequest(StrictModel):
    actor_id: str
    agreement_id: str
    title: str = Field(min_length=1, max_length=160)
    character: str = Field(default="", max_length=160)
    role_description: str = Field(default="", max_length=2000)
    content: dict[str, str] = Field(default_factory=lambda: {key: "none" for key in oap.CONTENT_ENUMS})
    offer: str = Field(pattern=r"^\d{1,12}(\.\d{1,2})?$")
    currency: str = Field(pattern=r"^[A-Z0-9]{3,8}$")
    notes: str = Field(default="", max_length=2000)

    @field_validator("content")
    @classmethod
    def valid_content(cls, value):
        return ProductionRequest.valid_content(value)


class AgreementSignRequest(StrictModel):
    role: Literal["agent", "director"]


class TopazInterpolation(StrictModel):
    model: Literal["apo-8", "apf-2", "chr-2", "chf-3", "aion-1"]
    fps: float | None = Field(default=None, ge=15, le=240)
    slowmo: int | None = Field(default=None, ge=1, le=16)
    duplicate: bool = False


class TopazOptions(StrictModel):
    mode: Literal["Auto", "Relative", "Manual"] = "Auto"
    tuning: dict[str, float] = Field(default_factory=dict)
    interpolation: TopazInterpolation | None = None

    @field_validator("tuning")
    @classmethod
    def known_tuning(cls, value):
        from mmv.topaz_models import TUNING_RANGE
        for key, number in value.items():
            if key not in TUNING_RANGE or not TUNING_RANGE[key][0] <= number <= TUNING_RANGE[key][1]:
                raise ValueError(f"Unknown or out-of-range Topaz tuning value: {key}")
        return value


class UpscaleRequest(StrictModel):
    source: str
    model: str = Field(default="ahq-12", pattern=r"^([a-z][a-z0-9]*-\d+(\.\d+)?|none)$")
    scale: Literal[1, 2, 4] = 2
    options: TopazOptions | None = None
    max_credits: int | None = Field(default=None, ge=1, le=1000000)


class CaptionVideoRequest(StrictModel):
    source: str
    style: Literal["classic", "bold", "neon", "box"] = "classic"
    position: Literal["bottom", "middle", "top"] = "bottom"
    size: Literal["small", "medium", "large"] = "medium"
    color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    outline_color: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    font: str = Field(default="", max_length=40, pattern=r"^([A-Za-z0-9][A-Za-z0-9 ._+-]*)?$")
    lyric_lines: list[LyricLine] = Field(default_factory=list, max_length=500)


class TakeSelectRequest(StrictModel):
    take_id: str = Field(pattern=r"^take\d{1,4}$")


class PromptTakeSelectRequest(StrictModel):
    prompt_take_id: str = Field(pattern=r"^prompt\d{1,4}$")


class PromptRewriteRequest(StrictModel):
    confirm: bool = False
    accept_writer_cost: bool = False
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    world_id: str | None = Field(default=None, max_length=120)
    direction: str | None = Field(default=None, max_length=600)


class PromptEditRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=64000)
    confirm: bool = False


class RerollRequest(StrictModel):
    confirm: bool = False
    seed: int | None = Field(default=None, ge=0, le=2147483647)


class ReassembleRequest(StrictModel):
    selected_takes: dict[str, str] = Field(default_factory=dict)


class ProjectState(StrictModel):
    panel: Literal["video", "vocab", "worlds", "queue", "actors", "styles", "harvest", "idents", "outputs", "settings"] = "video"
    forms: dict[str, dict[str, str | bool | float | int | list[str]]] = Field(default_factory=dict)
    files: dict[str, dict[str, str | list[str]]] = Field(default_factory=dict)
    custom_vocabulary: dict[str, VocabularyTableOverride] = Field(default_factory=dict)
    vocab_random_key: str = Field(default="", max_length=128)
    thematic_worlds: dict[str, Any] | None = None
    details_open: bool = False
    details_sections: dict[str, bool] = Field(default_factory=dict)
    details_reviewed: dict[str, bool] = Field(default_factory=dict)
    details_partial: dict[str, bool] = Field(default_factory=dict)
    log_open: bool = False


def create_app(home=None, *, test_hosts=False):
    store = Storage(home)
    jobs = Jobs(store)
    quotes = {}
    queue_control = production_queue.new_control()
    production_queue.recover_tickets(store, interrupted_message)
    jobs.on_settled = lambda record: production_queue.settle_operation(store, jobs, queue_control, record)
    jobs.on_idle = lambda record: production_queue.start_dispatch(store, jobs, queue_control)
    from mmv.final_assembly import remove_interrupted_encodes
    for leftover in remove_interrupted_encodes(store.home / "runs"):   # no operation runs yet
        log_studio(store, f"Removed an interrupted encode's work folder: {leftover.parent.name}/{leftover.name}")
    try:
        props.install_starter_props(store)
    except (OSError, ValueError) as error:
        logging.getLogger("uvicorn.error").warning("Starter props were not installed: %s", error)
    @asynccontextmanager
    async def lifespan(app):
        yield
        queue_control.update(running=False, closing=True)   # closing the app must not launch the next ticket
        await asyncio.to_thread(jobs.shutdown)

    app = FastAPI(title="Mondo Music Video", version=MGL_APP_VERSION, lifespan=lifespan)
    app.state.store, app.state.jobs = store, jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"] +
                       (["testserver"] if test_hosts else []))

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin changes are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; " \
            "media-src 'self' blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        log_studio(store, f"{request.method} {request.url.path} error: {exc}", level="ERROR")
        return JSONResponse({"detail": str(exc)}, status_code=409 if isinstance(exc, BusyError) else 400)

    @app.exception_handler(Exception)
    async def general_error(request, exc):
        log_studio(store, f"{request.method} {request.url.path} unexpected error: {exc}", level="ERROR")
        return JSONResponse({"detail": str(exc)}, status_code=500)

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/app.js")
    def javascript():
        return FileResponse(WEB / "app.js", media_type="text/javascript")

    @app.get("/js/{module_name}")
    def js_module(module_name: str):
        path = inside(WEB / "js", module_name)
        if not path.is_file() or path.suffix != ".js":
            raise ValueError("Module not found")
        return FileResponse(path, media_type="text/javascript")

    @app.get("/vendor/{asset_path:path}")
    def vendor_asset(asset_path: str):
        path = inside(WEB / "vendor", asset_path)
        if not path.is_file() or path.suffix not in (".js", "") or (path.suffix == "" and path.name != "LICENSE"):
            raise ValueError("Asset not found")
        return FileResponse(path, media_type="text/javascript" if path.suffix == ".js" else "text/plain")

    @app.get("/style.css")
    def css():
        return FileResponse(WEB / "style.css", media_type="text/css")

    @app.get("/favicon.ico")
    def favicon_ico():
        return FileResponse(WEB / "favicon.ico", media_type="image/x-icon")

    @app.get("/favicon.svg")
    def favicon_svg():
        return FileResponse(WEB / "favicon.svg", media_type="image/svg+xml")

    app.get("/api/version")(api_version)

    @app.get("/api/update")
    def update_status():
        from mmv.updates import public_status
        return public_status(store)

    def get_full_status(snapshot=None):
        result = dict(snapshot) if snapshot is not None else jobs.status()
        previous = read_json(store.home / 'runs' / identifier(result['id']) / 'request.json', {}) if result.get('id') else {}
        result['can_retry_prompts'] = retryable_prompt_run(result, previous)
        if result['can_retry_prompts'] and ' Note: Incomplete responses, JSON formatting errors,' in result.get('message', ''):
            result['message'] = (result['message'].split(' Note: Incomplete responses, JSON formatting errors,', 1)[0]
                                 + ' Nothing rendered.')
        result['can_resume'] = (result.get('state') in ('failed', 'cancelled', 'interrupted')
                                and previous.get('backend') == 'comfy_sdk_h3'
                                and not result['can_retry_prompts'])
        result['services'] = check_services(store, result)
        result['queue'] = queue_view()
        return result

    def queue_view():
        tickets = production_queue.read_tickets(store)
        return {"running": queue_control["running"], "waiting": production_queue.waiting_count(tickets),
                "tickets": [production_queue.public_ticket(t) for t in tickets]}

    def retryable_prompt_run(snapshot, previous):
        """Only an unrendered, failed prompt attempt may offer a fresh quote."""
        if (snapshot.get('state') != 'failed' or snapshot.get('kind') != 'video'
                or 'prompt validation failed after' not in snapshot.get('message', '')
                or previous.get('kind') != 'video' or not snapshot.get('id')):
            return False
        directory = store.home / 'runs' / identifier(snapshot['id'])
        return (read_json(directory / 'consent.json', {}).get('accepted') is True
                and (directory / 'prepared.json').is_file()
                and not (directory / 'output.json').exists()
                and not any((directory / 'renders').glob('*'))
                and any(directory.glob('seg*.validation-*.json')))

    @app.get("/api/status")
    def status():
        return get_full_status()

    @app.get("/api/services/status")
    def services_status(force: bool = False):
        return check_services(store, jobs.status(), force=force)

    @app.get("/api/events")
    async def events(request: Request, once: bool = False):
        queue = asyncio.Queue(maxsize=32)
        loop = asyncio.get_running_loop()
        closed = False

        def enqueue(data):
            if closed:
                return
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(data)

        def on_event(status_dict, log_line=None):
            if not closed:
                loop.call_soon_threadsafe(enqueue, {"status": get_full_status(status_dict), "log": log_line})

        unsubscribe = jobs.subscribe(on_event)

        async def event_generator():
            nonlocal closed
            try:
                initial = await asyncio.to_thread(get_full_status)
                yield f"event: status\ndata: {json.dumps(initial)}\n\n"
                if once:
                    while not queue.empty():
                        data = queue.get_nowait()
                        if "status" in data:
                            yield f"event: status\ndata: {json.dumps(data['status'])}\n\n"
                        if data.get("log"):
                            yield f"event: log\ndata: {json.dumps({'message': data['log']})}\n\n"
                    return
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=15.0)
                        if "status" in data:
                            yield f"event: status\ndata: {json.dumps(data['status'])}\n\n"
                        if data.get("log"):
                            yield f"event: log\ndata: {json.dumps({'message': data['log']})}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                closed = True
                unsubscribe()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    @app.post("/api/cancel")
    def cancel():
        return jobs.cancel()

    @app.get("/api/catalog")
    def catalog():
        return {"backends": CATALOG, "ratings": oap.CONTENT_ENUMS, "price_checked": "2026-10-15",
                "oap_version": oap.OAP_VERSION,
                "instruments": {"kinds": instrument_assets.KINDS, "mode": ["off", "perform"]},
                "opp_version": props.protocol_version(), "opp_accepts": ["0.1.x", "0.2.x"], "props": {"import": True, "instrument_selection": True}}

    @app.get("/api/project")
    def get_project():
        project = read_json(store.home / "project.json", {})
        uploads = store.home / "uploads"
        for state in project.get("files", {}).values():
            if not isinstance(state, dict):
                continue
            song = state.get("song")
            if isinstance(song, str) and song:
                try:
                    if not inside(uploads, song).is_file():
                        state.pop("song", None)
                        state.pop("songName", None)
                except ValueError:
                    state.pop("song", None)
                    state.pop("songName", None)
            refs = state.get("references")
            names = state.get("referenceNames")
            if isinstance(refs, list):
                valid_refs, valid_names = [], []
                for idx, ref in enumerate(refs):
                    try:
                        if isinstance(ref, str) and ref and inside(uploads, ref).is_file():
                            valid_refs.append(ref)
                            if isinstance(names, list) and idx < len(names):
                                valid_names.append(names[idx])
                    except ValueError:
                        pass
                state["references"] = valid_refs
                state["referenceNames"] = valid_names
        return project

    @app.put("/api/project")
    def put_project(value: ProjectState):
        write_json(store.home / "project.json", value.model_dump())
        return {"ok": True}

    @app.get("/api/settings")
    def get_settings():
        from mmv.api_profiles import public_profiles
        s = store.settings()
        info = _get_h3_model_info(store)
        s["h3_models"] = info["current"]
        return {"settings": s, "h3_models_installed": info["installed"],
                "workflow_presets": workflow_presets(), "workflow_steps": map_steps(s["workflow_map_path"]),
                "api_profiles": public_profiles(store),
                "keys": {name: bool(store.key(name)) for name in
                ("WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY", "MMV_COMFY_API_KEY",
                 "MMV_TOPAZ_API_KEY")}}

    @app.put("/api/settings")
    def settings(value: Settings):
        with jobs.lock:
            jobs.require_idle()
            dump = value.model_dump()
            from mmv.api_profiles import resolve, save_settings
            dump = Settings(**resolve(store, dump)).model_dump()
            if dump.pop("workflow_preset", ""):
                dump["workflow_map_path"] = preset_path(value.workflow_preset)
            h3_models = dump.pop("h3_models", None)
            if h3_models:
                _update_h3_models(store, dump, h3_models)
            save_settings(store, dump)
        return {"ok": True}

    @app.post("/api/api-profiles")
    def save_api_profile(value: ApiProfileRequest):
        from mmv.api_profiles import FIELDS, KEYS, save_profile
        with jobs.lock:
            jobs.require_idle()
            current = store.settings()
            config = value.settings if value.settings is not None else {k: current[k] for k in FIELDS[value.role]}
            credential = value.key if value.key is not None else (store.key(KEYS[value.role]) if value.settings is None else "")
            return save_profile(store, value.name, value.role, config, credential)

    @app.post("/api/api-profiles/{name}/activate")
    def activate_api_profile(name: str):
        from mmv.api_profiles import activate
        with jobs.lock:
            jobs.require_idle()
            return activate(store, identifier(name))

    @app.delete("/api/api-profiles/{name}")
    def delete_api_profile(name: str):
        from mmv.api_profiles import remove_profile
        with jobs.lock:
            jobs.require_idle()
            result = remove_profile(store, identifier(name))
            quotes.clear()
            return result

    @app.patch("/api/settings")
    def patch_settings(changes: dict):
        with jobs.lock:
            jobs.require_idle()
            return settings(Settings(**{**store.settings(), **changes}))

    @app.post("/api/starter-assets")
    def install_starter_assets(value: StarterRequest):
        from mmv.starter_assets import install
        with jobs.lock:
            jobs.require_idle()
            result = install(store, accept_signer=value.accept_starter_signer, restore=value.restore_removed)
            quotes.clear()
            return result

    @app.get("/api/fs/browse")
    def browse_fs(path: str = "", mode: Literal["folder", "file"] = "folder", ext: str = ""):
        import string
        drives = []
        if os.name == "nt":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        else:
            drives = ["/"]

        home = Path.home()
        target = None
        if path:
            try:
                candidate = Path(path).expanduser().resolve()
                if candidate.is_file():
                    target = candidate.parent
                elif candidate.is_dir():
                    target = candidate
                elif candidate.parent.is_dir():
                    target = candidate.parent
            except Exception:
                target = None

        if not target or not target.is_dir():
            target = home

        folders = []
        files = []
        allowed_exts = [e.strip().lower() for e in ext.split(",") if e.strip()]
        try:
            for item in sorted(target.iterdir(), key=lambda x: x.name.lower()):
                try:
                    if item.name.startswith((".", "$")) or item.name in ("System Volume Information", "Recovery"):
                        continue
                    if item.is_dir():
                        folders.append({"name": item.name, "path": str(item)})
                    elif mode == "file" and item.is_file():
                        if not allowed_exts or item.suffix.lower() in allowed_exts:
                            files.append({"name": item.name, "path": str(item)})
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

        return {
            "current": str(target),
            "parent": str(target.parent) if target.parent != target else None,
            "drives": drives,
            "home": str(home),
            "folders": folders,
            "files": files,
        }

    @app.put("/api/key")
    def key(value: KeyRequest):
        with jobs.lock:
            jobs.require_idle()
            store.save_key(value.name, value.value)
        return {"configured": bool(store.key(value.name))}

    @app.post("/api/upload/{kind}")
    def upload(kind: Literal["song", "reference", "oap", "opp", "agreement", "video", "lore"], file: UploadFile = File(...)):
        limit = {"song": 256, "reference": 25, "oap": 128, "opp": 128, "agreement": 2, "video": 512, "lore": 1}[kind] * 1024 * 1024
        suffix = Path(file.filename or "").suffix.lower()
        if kind == "song" and suffix not in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff"):
            raise ValueError("Choose a supported audio file")
        if kind == "opp" and suffix != ".opp":
            raise ValueError("Choose an .opp package")
        if kind == "video" and suffix not in worlds.VIDEO_SUFFIXES:
            raise ValueError("Choose a supported video file")
        if kind == "lore" and suffix not in worlds.LORE_SUFFIXES:
            raise ValueError("Choose a .txt or .md text file")
        name = uuid.uuid4().hex + (suffix if kind in ("song", "video", "lore") else ".png" if kind == "reference"
                                   else ".json" if kind == "agreement" else ".opp" if kind == "opp" else ".oap")
        target = store.home / "uploads" / name
        # Serialize mutations with operation startup so quoted inputs remain stable.
        with jobs.lock:
            if kind not in ("song", "reference"):   # these get new names, so they cannot disturb a running production
                jobs.require_idle()
            if kind == "reference":
                data = file.file.read(limit + 1)
                actors.clean_image(data, target)
            else:
                size = 0
                try:
                    with target.open("xb") as stream:
                        while chunk := file.file.read(1024 * 1024):
                            size += len(chunk)
                            if size > (worlds.LORE_BYTES if kind == "lore" else limit):
                                raise ValueError("File exceeds upload size limit")
                            stream.write(chunk)
                    if not size:
                        raise ValueError("File is empty")
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
        if kind in ("song", "video", "lore"):
            write_json(target.with_name(name + ".metadata.json"), {"name": Path((file.filename or kind).replace("\\", "/")).name})
        return {"file": name, "name": file.filename}

    @app.get("/api/uploads/reference/{filename}")
    def uploaded_reference(filename: str):
        path = inside(store.home / 'uploads', filename)
        if path.suffix != '.png' or not path.is_file():
            raise HTTPException(404, 'Reference image not found')
        return FileResponse(path, media_type='image/png')

    @app.get("/api/uploads/song/{filename}")
    def get_uploaded_song(filename: str):
        path = inside(store.home / "uploads", filename)
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff"):
            raise ValueError("Uploaded song not found")
        media_types = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".aiff": "audio/aiff",
        }
        return FileResponse(path, media_type=media_types.get(suffix, "application/octet-stream"))

    @app.get("/api/instruments")
    def list_instruments():
        return instrument_assets.catalog(store)

    @app.get("/api/props")
    def list_props():
        return props.catalog(store)

    @app.get("/api/props/{prop_id}/reference")
    def prop_reference(prop_id: str, use: str = ""):
        return FileResponse(props.select(store, prop_id, use)["path"], media_type="image/png")

    @app.get("/api/props/{prop_id}/selection")
    def prop_selection(prop_id: str, use: str = ""):
        selected = props.select(store, prop_id, use)
        return {key: selected[key] for key in ('prop_id', 'name', 'description', 'license', 'clearance', 'sheet_kind',
                                                'sheet_label', 'sheet_tags', 'use', 'sha256', 'source_sha256')}

    @app.get("/api/opp/inspect/{filename}")
    def inspect_opp(filename: str, allow_unsigned: bool = False):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".opp" or not path.is_file():
            raise ValueError("OPP upload not found")
        return props.inspection(path, allow_unsigned=allow_unsigned)

    @app.post("/api/opp/import")
    def import_opp(filename: str = Form(...), allow_unsigned: bool = Form(False),
                   accept_signer: str = Form("")):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".opp" or not path.is_file():
            raise ValueError("OPP upload not found")
        with jobs.lock:
            jobs.require_idle()
            return props.import_package(store, path, allow_unsigned=allow_unsigned, accept_signer=accept_signer)

    @app.get("/api/actors")
    def list_actors():
        return [read_json(path) for path in sorted((store.home / "actors").glob("*/actor.json"))]

    @app.post("/api/actors")
    def add_actor(actor_id: str = Form(...), name: str = Form(...), description: str = Form(""),
                  reference: UploadFile = File(...)):
        if len(name) > 160 or len(description) > 6000:
            raise ValueError("Actor name or description is too long")
        with jobs.lock:
            jobs.require_idle()
            return actors.create_actor(store, actor_id, name, description, reference.file.read(25 * 1024 * 1024 + 1))

    @app.patch("/api/actors/{actor_id}")
    def update_actor(actor_id: str, value: ActorUpdateRequest):
        with jobs.lock:
            jobs.require_idle()
            actor_id = identifier(actor_id)
            target = inside(store.home / "actors", actor_id)
            json_path = target / "actor.json"
            if not target.is_dir() or not json_path.is_file():
                raise ValueError("Actor not found")
            record = read_json(json_path)
            if record.get("oap") or (target / "original.oap").exists():
                raise ValueError("Imported OAP actors keep their signed identity; request a revised package from its signer")
            if not value.description.strip():
                raise ValueError("Visual description cannot be empty")
            record["description"] = value.description
            write_json(json_path, record)
            quotes.clear()
        return record

    @app.get("/api/actors/{actor_id}/reference")
    def actor_reference(actor_id: str):
        record = store.actor(actor_id)
        if not record:
            raise ValueError("Actor not found")
        return FileResponse(inside(store.home / "actors" / actor_id, record["reference"]), media_type="image/png")

    @app.delete("/api/actors/{actor_id}")
    def delete_actor(actor_id: str):
        from mmv.starter_assets import mark_removed
        with jobs.lock:
            jobs.require_idle()
            actor_id = identifier(actor_id)
            if (store.home / "actors" / actor_id).is_symlink():
                raise ValueError("Cannot delete a linked actor directory")
            target = inside(store.home / "actors", actor_id)
            if not target.is_dir() or not (target / "actor.json").is_file():
                raise ValueError("Actor not found")
            mark_removed(store, "actors", actor_id)
            shutil.rmtree(target)
            quotes.clear()
        return {"deleted": actor_id}

    @app.post("/api/actors/{actor_id}/export")
    def export_actor(actor_id: str, tier: Literal["full", "audition"] = "full",
                     reference_clearance: Literal["cast", "audition"] = "cast"):
        with jobs.lock:
            jobs.require_idle()
            path = actors.export_actor(store, actor_id, tier=tier, reference_clearance=reference_clearance)
        suffix = "-audition.oap" if tier == "audition" else ".oap"
        return FileResponse(path, filename=actor_id + suffix, media_type="application/octet-stream")

    @app.get("/api/oap/inspect/{filename}")
    def inspect_package(filename: str, allow_unsigned: bool = False):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".oap" or not path.is_file():
            raise ValueError("OAP upload not found")
        manifest, verification = actors.package_info(path, allow_unsigned=allow_unsigned)
        return {"manifest": manifest, "verification": verification}

    @app.get("/api/oap/recipient-key")
    def oap_recipient_key():
        return {"public_key": actors.recipient_identity(store)["public_key"]}

    @app.post("/api/oap/import")
    def import_package(filename: str = Form(...), actor_id: str = Form(""),
                       allow_unsigned: bool = Form(False), accept_unknown: bool = Form(False)):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".oap" or not path.is_file():
            raise ValueError("OAP upload not found")
        with jobs.lock:
            jobs.require_idle()
            return actors.import_actor(store, path, actor_id, allow_unsigned=allow_unsigned, accept_unknown=accept_unknown)

    @app.get("/api/oap-collection")
    def check_oap_collection():
        return oap_collection.check(store)

    @app.post("/api/oap-collection/stage")
    def stage_oap_collection(value: CollectionStageRequest):
        with jobs.lock:
            jobs.require_idle()

        def publish(source, destination):
            with jobs.lock:
                jobs.require_idle()
                source.replace(destination)

        return oap_collection.stage(store, value.actor_id, value.index_sha256, publish=publish)

    @app.get("/api/agreements")
    def list_agreements():
        return agreements.list_agreements(store)

    @app.post("/api/agreements")
    def create_agreement(value: AgreementRequest):
        with jobs.lock:
            jobs.require_idle()
            return agreements.create_agreement(
                store, value.actor_id, value.agreement_id, title=value.title, character=value.character,
                role_description=value.role_description, content=value.content, offer=value.offer,
                currency=value.currency, notes=value.notes)

    @app.post("/api/agreements/{agreement_id}/sign")
    def sign_agreement(agreement_id: str, value: AgreementSignRequest):
        with jobs.lock:
            jobs.require_idle()
            return agreements.sign(store, agreement_id, value.role)

    @app.get("/api/agreements/{agreement_id}/verify")
    def verify_agreement(agreement_id: str):
        return agreements.verify(store, agreement_id)

    @app.post("/api/agreements/{agreement_id}/bundle")
    def agreement_bundle(agreement_id: str):
        path = agreements.bundle(store, agreement_id)
        return FileResponse(path, filename=identifier(agreement_id) + "-agreement.zip", media_type="application/zip")

    @app.post("/api/agreements/import")
    def import_agreement(filename: str = Form(...)):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".json" or not path.is_file():
            raise ValueError("Agreement upload not found")
        with jobs.lock:
            jobs.require_idle()
            return agreements.import_signed(store, path)

    @app.get("/api/styles")
    def styles():
        return [read_json(path) for path in sorted((store.home / "styles").glob("*.json"))]

    @app.get("/api/styles/{style_id}")
    def get_style(style_id: str):
        style_id = identifier(style_id)
        target = inside(store.home / "styles", style_id + ".json")
        if not target.is_file():
            raise ValueError("Style not found")
        return read_json(target)

    @app.get("/api/styles/{style_id}/export")
    def export_style(style_id: str):
        style_id = identifier(style_id)
        target = inside(store.home / "styles", style_id + ".json")
        if not target.is_file():
            raise ValueError("Style not found")
        return FileResponse(target, filename=f"{style_id}.json", media_type="application/json")

    @app.post("/api/styles")
    def add_style(value: StyleRequest):
        style_id = identifier(value.id)
        path = store.home / "styles" / (style_id + ".json")
        with jobs.lock:
            jobs.require_idle()
            if path.exists():
                raise ValueError("Style already exists; use a different ID")
            payload = style_payload(value, style_id)
            write_json(path, payload)
        return payload

    @app.post("/api/styles/import")
    def import_style(value: StyleImportRequest):
        style_id = identifier(value.id)
        path = store.home / "styles" / (style_id + ".json")
        with jobs.lock:
            jobs.require_idle()
            if path.exists() and not value.overwrite:
                raise ValueError(f"Style '{style_id}' already exists; choose a different ID or enable overwrite")
            payload = style_payload(value, style_id)
            write_json(path, payload)
        return payload

    @app.delete("/api/styles/{style_id}")
    def delete_style(style_id: str):
        from mmv.starter_assets import mark_removed
        with jobs.lock:
            jobs.require_idle()
            style_id = identifier(style_id)
            if (store.home / "styles" / (style_id + ".json")).is_symlink():
                raise ValueError("Cannot delete a linked style file")
            target = inside(store.home / "styles", style_id + ".json")
            if not target.is_file():
                raise ValueError("Style not found")
            mark_removed(store, "styles", style_id)
            target.unlink()
            quotes.clear()
        return {"deleted": style_id}

    def world_or_error(world_id, version=None):
        return worlds.load(store, identifier(world_id), version)

    @app.get("/api/worlds")
    def list_worlds():
        return worlds.listing(store)

    @app.post("/api/worlds")
    def add_world(value: WorldRequest):
        with jobs.lock:
            jobs.require_idle()
            ledger = worlds.create(store, value.id, value.model_dump(exclude={"id"}))
            quotes.clear()
        return ledger

    @app.get("/api/worlds/proposals")
    def list_world_proposals():
        return worlds.list_proposals(store)

    @app.get("/api/worlds/proposals/{proposal_id}")
    def get_world_proposal(proposal_id: str):
        return worlds.read_proposal(store, proposal_id)

    @app.post("/api/worlds/proposals/{proposal_id}/accept")
    def accept_world_proposal(proposal_id: str):
        with jobs.lock:
            jobs.require_idle()
            ledger = worlds.accept(store, proposal_id)
            quotes.clear()
        return ledger

    @app.delete("/api/worlds/proposals/{proposal_id}")
    def reject_world_proposal(proposal_id: str):
        with jobs.lock:
            jobs.require_idle()
            worlds.reject(store, proposal_id)
        return {"rejected": proposal_id}

    @app.get("/api/worlds/{world_id}")
    def get_world(world_id: str, version: int | None = None):
        return world_or_error(world_id, version)

    def edit_fields(world_id, value):
        if value.id and identifier(value.id) != identifier(world_id):
            raise ValueError("The edit names a different world")
        return value.model_dump(exclude={"id", "base_version"})

    @app.post("/api/worlds/{world_id}/edit-preview")
    def preview_world_edit(world_id: str, value: WorldEditRequest):
        return worlds.preview_edit(store, identifier(world_id), edit_fields(world_id, value))

    @app.put("/api/worlds/{world_id}")
    def edit_world(world_id: str, value: WorldEditRequest):
        with jobs.lock:
            jobs.require_idle()
            ledger = worlds.edit(store, identifier(world_id), edit_fields(world_id, value), value.base_version)
            quotes.clear()
        return ledger

    @app.get("/api/worlds/{world_id}/versions")
    def get_world_versions(world_id: str):
        return worlds.versions(store, world_id)

    @app.get("/api/worlds/{world_id}/export")
    def export_world(world_id: str):
        return JSONResponse(world_or_error(world_id), headers={"Content-Disposition": f'attachment; filename="{identifier(world_id)}.world.json"'})

    @app.post("/api/worlds/{world_id}/rollback")
    def rollback_world(world_id: str, value: WorldRollbackRequest):
        with jobs.lock:
            jobs.require_idle()
            ledger = worlds.rollback(store, world_id, value.version)
            quotes.clear()
        return ledger

    @app.delete("/api/worlds/{world_id}")
    def delete_world(world_id: str):
        with jobs.lock:
            jobs.require_idle()
            worlds.delete(store, world_id)
            quotes.clear()
        return {"deleted": world_id}

    @app.get("/api/vocabulary")
    def get_vocabulary():
        engine_cfg = Path(__file__).parent.parent / "mmv/engine/config"
        base = read_json(engine_cfg / "vocab.json", {})
        profiles = read_json(engine_cfg / "vocabulary_profiles.json", {})
        presets = [read_json(path) for path in sorted((store.home / "vocabularies").glob("*.json"))]
        return {
            "categories": list(VOCAB_TABLES),
            "base": {k: base.get(k, []) for k in VOCAB_TABLES},
            "profiles": profiles,
            "vocabularies": presets,
        }

    @app.get("/api/vocabulary/guide")
    def get_vocabulary_guide():
        guide_path = Path(__file__).parent.parent / "docs" / "VOCABULARY_GUIDE.md"
        if not guide_path.exists():
            return {"title": "Vocabulary Architecture Guide", "markdown": "Guide not found on disk."}
        return {"title": "Visual Vocabulary Architecture & Customization Guide", "markdown": guide_path.read_text(encoding="utf-8")}

    @app.get("/api/props/guide")
    def get_props_guide():
        guide_path = Path(__file__).parent.parent / "docs" / "OPEN_PROP_PROTOCOL.md"
        if not guide_path.exists():
            guide_path = Path(sys.prefix) / "share/mondo-music-video/docs/OPEN_PROP_PROTOCOL.md"
        if not guide_path.exists():
            raise HTTPException(status_code=404, detail="Open Prop Protocol guide is not installed")
        return {"title": "What is Open Prop Protocol", "markdown": guide_path.read_text(encoding="utf-8")}

    @app.get("/api/vision/guide")
    def get_vision_guide():
        guide_path = Path(__file__).parent.parent / "docs" / "QUALITY_VISION_SETUP.md"
        if not guide_path.exists():
            guide_path = Path(sys.prefix) / "share/mondo-music-video/docs/QUALITY_VISION_SETUP.md"
        if not guide_path.exists():
            raise HTTPException(status_code=404, detail="Vision setup guide is not installed")
        return {"title": "Style Harvest and Quality Vision guide", "markdown": guide_path.read_text(encoding="utf-8")}

    @app.get("/api/vocabularies")
    def list_vocabularies():
        return [read_json(path) for path in sorted((store.home / "vocabularies").glob("*.json"))]

    @app.post("/api/vocabularies")
    def save_vocabulary(value: VocabularyRequest):
        vocab_id = identifier(value.id)
        path = store.home / "vocabularies" / (vocab_id + ".json")
        payload = value.model_dump()
        with jobs.lock:
            jobs.require_idle()
            if path.is_symlink():
                raise ValueError("Cannot overwrite a linked vocabulary file")
            load_vocabulary(value.base_profile, store=store, custom=payload["tables"])
            write_json(path, payload)
            quotes.clear()
        return payload

    @app.delete("/api/vocabularies/{vocab_id}")
    def delete_vocabulary(vocab_id: str):
        with jobs.lock:
            jobs.require_idle()
            vocab_id = identifier(vocab_id)
            if vocab_id in ("full", "reduced_flashing"):
                raise ValueError("Cannot delete a built-in visual vocabulary profile")
            if (store.home / "vocabularies" / (vocab_id + ".json")).is_symlink():
                raise ValueError("Cannot delete a linked vocabulary file")
            target = inside(store.home / "vocabularies", vocab_id + ".json")
            if not target.is_file():
                raise ValueError("Vocabulary preset not found")
            target.unlink()
            quotes.clear()
        return {"deleted": vocab_id}

    def build_quote(value: ProductionRequest, *, resume_directory=None):
        request = with_world(store, request_dict(value))   # pipeline.prepare picks a random render seed if none was chosen
        kind = request.get("kind", "video")
        log_studio(store, f"Preview requested: kind='{kind}' backend='{request.get('backend')}' title='{request.get('title', '')}'")
        try:
            with queue_control["prepare_lock"], production_queue.preview_gpu_gate(store, jobs, queue_control):
                # One at a time: previews of a new song share its analysis file. Stem work waits for a free GPU.
                prepared = (production.prepare_resume(store, request, resume_directory) if resume_directory is not None
                            else production.prepare(store, request))
        except Exception as exc:
            log_studio(store, f"Preview failed ({kind}): {exc}", level="ERROR")
            raise
        quote_fingerprint = production.fingerprint(store, request, prepared)
        quote_id = secrets.token_urlsafe(24)
        with jobs.lock:   # the plan itself is worked out unlocked: a running production keeps reporting meanwhile
            busy = jobs.active is not None
            for expired in [key for key, item in quotes.items() if item["expires"] < time.time()]:
                quotes.pop(expired)
            if len(quotes) > 100:
                quotes.clear()
            quotes[quote_id] = {"request": request, "fingerprint": quote_fingerprint, "estimate": production_queue.cost(prepared),
                                "expires": time.time() + 600}
        from mmv.services import check_required_services
        # Engines swap in and out during an operation, so "offline" only means something when idle; the ticket checks again.
        offline_engines = [] if busy else check_required_services(store, request, resume=bool(resume_directory))
        return {"id": quote_id, "seed": request["seed"], "render_seed": render_seed(request), "estimate_usd": prepared["estimate"], "clips": len(prepared["segments"]),
                "seconds": prepared["seconds"], "analysis": prepared.get("analysis"),
                "segments": prepared["segments"], "writer_estimate_usd": prepared.get("writer_estimate", 0),
                "score": score_view.build_score(prepared["score"], prepared["plan"]) if kind == "video" else None,
                "detected": prepared.get("detected"), "lipsync": prepared.get("lipsync"), "subliminal": prepared.get("subliminal"), "captions": prepared.get("captions"), "dance": prepared.get("dance"), "instruments": instrument_preview(prepared.get("instruments")), "voice": prepared.get("voice"), "world_contrast": prepared.get("world_contrast"), "storyboard": prepared.get("storyboard"),
                "offline_engines": offline_engines,
                "paid": prepared["estimate"] > 0 if request["kind"] != "harvest"
                else prepared["estimate"] > 0,
                "note": "Estimate only. Check provider pricing. Uploaded references/audio are sent to your chosen provider. "
                "Cancellation cannot undo charges for submitted work."}

    @app.get("/api/quick-start")
    def quick_start_plan():
        from mmv import quick_start
        return quick_start.plan([a["id"] for a in list_actors()], [s["id"] for s in styles()])

    @app.get("/api/storyboards")
    def storyboard_results():
        paths = {p.parent: p for name in ('storyboard-response.txt', 'storyboard.json')
                 for p in (store.home / 'runs').glob('*/' + name)}
        return [{'run_id': p.parent.name} for p in sorted(paths.values(), key=lambda p: p.stat().st_mtime, reverse=True)]

    @app.get("/api/storyboards/{run_id}/response")
    def storyboard_response(run_id: str):
        path = inside(store.home / 'runs', identifier(run_id)) / 'storyboard-response.txt'
        if not path.is_file():
            raise HTTPException(404, 'No saved vision response for this operation')
        return {'response': path.read_text(encoding='utf-8')}

    @app.get("/api/storyboards/{run_id}")
    def storyboard_result(run_id: str):
        directory = inside(store.home / 'runs', identifier(run_id))
        result = read_json(directory / 'storyboard.json') if (directory / 'storyboard.json').is_file() else None
        if result is None:
            raise HTTPException(404, 'Storyboard result not found; inspect operation status and logs')
        return Storyboard(**result).model_dump()

    @app.post("/api/quote")
    def quote(value: ProductionRequest):
        return build_quote(value)

    @app.post("/api/retry-prompts/quote")
    def retry_prompts_quote(value: ResumeRequest):
        with jobs.lock:
            jobs.require_idle()
            run_id = identifier(value.run_id)
            snapshot = jobs.status()
            if snapshot.get('id') != run_id:
                raise ValueError('Choose the latest failed prompt run')
            directory = store.home / 'runs' / run_id
            request = read_json(directory / 'request.json', {})
            if not retryable_prompt_run(snapshot, request):
                raise ValueError('Only an unrendered production stopped by prompt validation can be tried again')
            result = build_quote(ProductionRequest(**request))
            result.update(kind='video', request={key: value for key, value in request.items() if key != 'world_departures'})
            return result

    @app.get("/api/lyrics")
    def lyrics_status():
        from mmv import lyrics
        return lyrics.status(store)

    @app.post("/api/lyrics/prepare")
    def lyrics_prepare(value: LyricsPrepareRequest):
        from mmv import lyrics
        if value.consent is not True:
            raise ValueError("Approve the one-time speech model download first")
        return jobs.start("lyrics", lambda context: lyrics.prepare_model(store, value.model, context),
                          run_id=job_run_id(store, "lyrics model", value.model))

    @app.post("/api/lyrics/detect")
    def lyrics_detect(value: LyricsRequest):
        from mmv import lyrics
        song = inside(store.home / "uploads", value.song)
        if not song.is_file():
            raise ValueError("Upload your song first")
        lyrics.require_ready(value.model)
        digest = lyrics.song_digest(song, value.beats_per_bar)

        def detect(context):
            found = lyrics.transcribe(store, song, digest, value.model, context, value.use_vocals)
            return {"lines": found["lines"], "source": found["source"], "language": found.get("language"), "model": value.model}
        return jobs.start("lyrics", detect, run_id=job_run_id(store, "lyrics", upload_name(store, value.song)))

    @app.post("/api/lyrics/align")
    def lyrics_align(value: LyricsRequest):
        from mmv import lyrics
        song = inside(store.home / "uploads", value.song)
        if not song.is_file():
            raise ValueError("Upload your song first")
        found = lyrics.cached_words(store, lyrics.song_digest(song, value.beats_per_bar), value.model)
        if not found:
            raise ValueError("Detect the lyrics first: the song is listened to once, then your pasted words are timed against it")
        return {"lines": lyrics.align_lines(value.text, found["words"]), "source": found["source"]}

    @app.get("/api/stems")
    def stems_status():
        from mmv import stems
        return stems.status(store)

    @app.post("/api/stems/prepare")
    def stems_prepare(value: StemsPrepareRequest):
        from mmv import stems
        if value.consent is not True:
            raise ValueError("Approve the one-time stem model download first")
        return jobs.start("stems", lambda context: stems.prepare_model(store, value.model, context),
                          run_id=job_run_id(store, "stems model", value.model))

    @app.get("/api/waveform")
    def waveform(song: str):
        from mmv.waveform import waveform_peaks
        return waveform_peaks(inside(store.home / "uploads", song))

    @app.post("/api/resume/quote")
    def resume_quote(value: ResumeRequest):
        with jobs.lock:
            jobs.require_idle()
            run_id = identifier(value.run_id)
            directory = store.home / 'runs' / run_id
            request = read_json(directory / 'request.json', {})
            consent = read_json(directory / 'consent.json', {})
            if request.get('backend') not in ('comfy_sdk_h3', 'local_h3') or not consent.get('accepted'):
                raise ValueError('Choose a previously authorized local Comfy production')
            if (directory / 'output.json').exists():
                raise ValueError('This production is already complete')
            # Recheck OAP, files, workflow and settings before offering recovery.
            prepared = production.prepare_resume(store, request, directory)
            fingerprint_now = production.fingerprint(store, request, prepared)
            if fingerprint_now != consent.get('fingerprint'):
                raise ValueError('Original inputs or settings changed; restore them before resuming')
            prompts = read_json(directory / 'prompts.json', {})
            if any(not prompts.get(f"seg{seg['index']:03d}") for seg in prepared['segments']):
                raise ValueError('Only productions with every prompt validated can resume')
            blocker = production_queue.resume_blocker(directory, fingerprint_now, consent)
            if blocker:
                raise ValueError(blocker)
            result = build_quote(ProductionRequest(**request), resume_directory=directory)
            quotes[result['id']]['resume_run'] = run_id
            result.update(kind=request['kind'], estimate_usd=0, writer_estimate_usd=0, paid=False,
                          note='Resume this local Comfy SDK production using saved validated prompts and request IDs. '
                               'Completed jobs are downloaded again; remaining passages may be submitted. No writer calls.')
            return result

    @app.post("/api/start")
    def start(value: StartRequest):
        with jobs.lock:
            jobs.require_idle()
            quoted = quotes.get(value.quote_id)
            if not quoted or quoted["expires"] < time.time():
                msg = "Preview expired. Request a new preview"
                log_studio(store, f"Start failed: {msg}", level="ERROR")
                raise ValueError(msg)
            if not value.consent:
                msg = "Review and accept the preview before starting"
                log_studio(store, f"Start failed: {msg}", level="ERROR")
                raise ValueError(msg)
            request = quoted["request"]
            from mmv.services import check_required_services
            missing_errors = check_required_services(store, request, resume=bool(quoted.get("resume_run")))
            if missing_errors:
                msg = f"Cannot start: {missing_errors[0]}"
                log_studio(store, f"Start rejected (engine offline): {msg}", level="ERROR")
                raise ValueError(msg)
            kind = request.get("kind", "video")
            try:
                prepared = (production.prepare_resume(store, request, store.home / 'runs' / quoted['resume_run'])
                            if quoted.get('resume_run') else production.prepare(store, request))
            except Exception as exc:
                log_studio(store, f"Start preparation failed ({kind}): {exc}", level="ERROR")
                raise
            if production.fingerprint(store, request, prepared) != quoted["fingerprint"]:
                msg = "Inputs or settings changed. Request a new preview"
                log_studio(store, f"Start failed: {msg}", level="ERROR")
                raise ValueError(msg)
            prepared["consent"] = {"accepted": True, "accepted_at": time.time(),
                                   "estimate_usd": 0 if quoted.get("resume_run") else prepared["estimate"], "quote_id": value.quote_id,
                                   "fingerprint": quoted["fingerprint"]}
            quotes.pop(value.quote_id)
            write_json(store.home / "log_cleared.json", {"cleared_at": time.time()})
            studio_log = store.home / "studio.log"
            if studio_log.exists():
                try:
                    studio_log.write_text("", encoding="utf-8")
                except Exception:
                    pass
            log_studio(store, f"Starting production for kind='{request.get('kind', 'video')}'")
            from mmv.jobs import output_run_id
            return jobs.start(request["kind"], lambda context: production.produce(
                store, request, prepared, context, resume=bool(quoted.get("resume_run"))),
                run_id=quoted.get("resume_run") or output_run_id(store, request))

    @app.get("/api/queue")
    def queue_list():
        return queue_view()

    @app.post("/api/queue")
    def queue_add(value: QueueAddRequest):
        with jobs.lock:
            quoted = quotes.get(value.quote_id)
            if not quoted or quoted["expires"] < time.time():
                raise ValueError("Preview expired. Request a new preview")
            request = quoted["request"]
            if quoted.get("resume_run") or request["kind"] not in production_queue.QUEUEABLE_KINDS:
                raise ValueError("Only a new music video or ident can be queued")
            if quoted["estimate"] > 0 and value.consent is not True:
                raise ValueError("Accept the estimated charges before queueing this paid production")
            tickets = production_queue.read_tickets(store)
            replaced = production_queue.get_ticket(store, value.replaces) if value.replaces else None
            if replaced and replaced["state"] not in production_queue.TERMINAL_STATES:
                raise ValueError("Only a stopped ticket can be replaced")
            label = upload_name(store, request.get("song")) or request.get("title") or request["kind"]
            ticket = production_queue.new_ticket(
                request, label, replaced["position"] if replaced else production_queue.next_position(tickets),
                estimate=quoted["estimate"], fingerprint=quoted["fingerprint"])
            quotes.pop(value.quote_id)
            production_queue.save_ticket(store, ticket)
            if replaced:
                production_queue.remove_ticket(store, replaced["id"])
            return production_queue.public_ticket(ticket)

    @app.post("/api/queue/start")
    def queue_start():
        with jobs.lock:
            production_queue.resume_interrupted(store)
            queue_control["running"] = True
        production_queue.start_dispatch(store, jobs, queue_control)
        return queue_view()

    @app.post("/api/queue/pause")
    def queue_pause():
        with jobs.lock:
            queue_control["running"] = False
            return queue_view()

    @app.post("/api/queue/clear-finished")
    def queue_clear_finished():
        with jobs.lock:
            for ticket in production_queue.read_tickets(store):
                if ticket["state"] in production_queue.TERMINAL_STATES:
                    production_queue.remove_ticket(store, ticket["id"])
            return queue_view()

    @app.post("/api/queue/{ticket_id}/move")
    def queue_move(ticket_id: str, value: QueueMoveRequest):
        with jobs.lock:
            for ticket in production_queue.moved(production_queue.read_tickets(store), ticket_id, value.delta):
                production_queue.save_ticket(store, ticket)
            return queue_view()

    @app.post("/api/queue/{ticket_id}/preview")
    def queue_preview(ticket_id: str):
        """A fresh quote for a stopped ticket. Add it with `replaces` to put the ticket back in line."""
        ticket = production_queue.get_ticket(store, ticket_id)
        if ticket["state"] not in production_queue.TERMINAL_STATES:
            raise ValueError("Only a stopped ticket can be previewed again")
        return {**build_quote(ProductionRequest(**ticket["request"])), "replaces": ticket["id"],
                "request": {key: value for key, value in ticket["request"].items() if key != "world_departures"}}

    @app.post("/api/queue/{ticket_id}/resume")
    def queue_resume(ticket_id: str):
        """Put a stopped local ticket back in line to continue from its saved work."""
        with jobs.lock:
            production_queue.resume_ticket(store, production_queue.get_ticket(store, ticket_id))
            return queue_view()

    @app.delete("/api/queue/{ticket_id}")
    def queue_remove(ticket_id: str):
        with jobs.lock:
            production_queue.remove_ticket(store, ticket_id)
            return queue_view()

    @app.get("/api/outputs")
    def outputs():
        result = []
        for path in sorted((store.home / "runs").glob("*/output.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            record = read_json(path)
            result.append({**record, "file": path.parent.name + "/" + record["file"]})
        return result

    @app.post("/api/outputs/{run_id}/package")
    def output_package(run_id: str, value: PackageRequest):
        from mmv import package_export
        package_export.check_package(store, run_id, value.allow_private_actors)
        return jobs.start("export", lambda context: package_export.export_package(
            store, run_id, zip_it=value.zip, allow_private=value.allow_private_actors, context=context),
            run_id=job_run_id(store, "export", run_id))

    @app.get("/api/integrity")
    def integrity():
        from mmv import protected_scheme
        changed = protected_scheme.check()
        return {"intact": not changed, "changed": protected_scheme.describe(changed), "notice": protected_scheme.notice() if changed else None}

    _run_size_cache: dict[str, tuple[float, float]] = {}

    @app.delete("/api/outputs/{run_id}")
    def delete_output(run_id: str):
        with jobs.lock:
            jobs.require_idle()
            run_id = identifier(run_id)
            target = inside(store.home / "runs", run_id)
            if not target.is_dir() or not (target / "output.json").is_file():
                raise ValueError("Output not found")
            shutil.rmtree(target, ignore_errors=True)
            _run_size_cache.pop(run_id, None)
            quotes.clear()
        return {"deleted": run_id}

    def run_folder_size_mb(path: Path) -> float:
        now = time.monotonic()
        cached = _run_size_cache.get(path.name)
        if cached and now - cached[0] < 5:
            return cached[1]
        total = 0
        stack = [path]
        while stack:
            try:
                with os.scandir(stack.pop()) as entries:
                    for entry in entries:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
            except OSError:
                continue
        size_mb = round(total / (1024 * 1024), 2)
        _run_size_cache[path.name] = (now, size_mb)
        return size_mb

    def rendered_clips(path):
        return sum(1 for _ in (path / "renders").glob("*.mp4"))

    @app.get("/api/runs/unfinished")
    def list_unfinished_runs():
        results = []
        runs_dir = store.home / "runs"
        if not runs_dir.is_dir():
            return []
        entries = []
        with os.scandir(runs_dir) as candidates:
            for entry in candidates:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        entries.append((entry.stat(follow_symlinks=False).st_mtime, entry.name, Path(entry.path)))
                except OSError:
                    continue
        for mtime, run_id, path in sorted(entries, reverse=True):
            if (path / "output.json").is_file():
                continue
            request = read_json(path / "request.json", {}) or {}
            title = request.get("title") or "Untitled Draft"
            backend = request.get("backend") or ""
            kind = request.get("kind") or "video"
            prompts = read_json(path / "prompts.json", {}) or {}
            plan = read_json(path / "plan.json", {}) or (read_json(path / "prepared.json", {}) or {}).get("plan") or {}
            segments = plan.get("segments", [])
            total_segments = len(segments)
            validated_prompts = sum(1 for seg in segments if bool(prompts.get(f"seg{seg['index']:03d}")))
            can_finish = (total_segments > 0 and validated_prompts == total_segments and (backend in ("comfy_sdk_h3", "local_h3")))
            results.append({
                "id": run_id,
                "title": title.strip().strip('"'),
                "backend": backend,
                "kind": kind,
                "mtime": mtime,
                "created_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
                "segments": total_segments,
                "validated_prompts": validated_prompts,
                "can_finish": can_finish,
                "rendered_clips": rendered_clips(path),
                "size_mb": run_folder_size_mb(path)
            })
        if len(_run_size_cache) > 512:
            _run_size_cache.clear()
        return results

    @app.delete("/api/runs/unfinished/{run_id}")
    def delete_unfinished_run(run_id: str, confirm_rendered: bool = False):
        with jobs.lock:
            jobs.require_idle()
            run_id = identifier(run_id)
            target = inside(store.home / "runs", run_id)
            if not target.is_dir():
                raise ValueError("Run directory not found")
            if (target / "output.json").is_file():
                raise ValueError("Cannot purge a finished production with this endpoint")
            if rendered_clips(target) and not confirm_rendered:
                raise ValueError("This run holds rendered clips that may have been paid for; confirm to delete them")
            shutil.rmtree(target, ignore_errors=True)
            _run_size_cache.pop(run_id, None)
            quotes.clear()
        return {"deleted": run_id}

    @app.post("/api/runs/unfinished/purge")
    def purge_all_unfinished():
        with jobs.lock:
            jobs.require_idle()
            runs_dir = store.home / "runs"
            if not runs_dir.is_dir():
                return {"purged_count": 0, "kept_with_clips": 0}
            purgeable = [path for path in runs_dir.iterdir() if path.is_dir() and not (path / "output.json").is_file()]
            kept = [path for path in purgeable if rendered_clips(path)]
            for path in purgeable:
                if path not in kept:
                    shutil.rmtree(path, ignore_errors=True)
                    _run_size_cache.pop(path.name, None)
            quotes.clear()
        return {"purged_count": len(purgeable) - len(kept), "kept_with_clips": len(kept)}

    @app.get("/api/outputs/{run_id}/score")
    def output_score(run_id: str):
        return score_view.music_score(store, run_id)

    @app.get("/api/outputs/{run_id}/prompts")
    def output_prompts(run_id: str):
        return score_view.passage_breakdown(store, run_id)

    @app.get("/api/outputs/{run_id}/clips/{segment_id}")
    def output_clip(run_id: str, segment_id: str, take: str | None = None):
        path, media_type = score_view.passage_clip(store, run_id, segment_id, take_id=take)
        # inline: Firefox will not play a <video> source served as an attachment; the name still applies when saved.
        return FileResponse(path, media_type=media_type, filename=segment_id + path.suffix.lower(), content_disposition_type="inline")

    @app.post("/api/outputs/{run_id}/takes/{segment_id}")
    def select_output_take(run_id: str, segment_id: str, value: TakeSelectRequest):
        from mmv import takes
        with jobs.lock:
            jobs.require_idle()
            return takes.select_segment_take(store, run_id, segment_id, value.take_id)

    def prompt_job(run_id, segment_id, kind, how, candidate=None, seed=None, world_id=None, direction=None):
        """Rewrite or check one passage prompt of a finished production through the worker's own prompt stage."""
        from mmv import takes
        origin = score_view._origin_run(store, run_id)
        directory = inside(store.home / "runs", identifier(origin))
        takes.validate_segment_id(segment_id)
        request, prepared = read_json(directory / "request.json", {}), read_json(directory / "prepared.json", {})
        if blocked := takes.prompt_block(request, prepared):
            raise ValueError(blocked)
        if segment_id not in read_json(directory / "prompts.json", {}):
            raise ValueError(f"No saved prompt for passage {segment_id}")
        # A written (not hand-edited) video prompt gets new vocabulary; ident prompts are not written from vocabulary.
        variation = None if candidate is not None or request.get("kind") == "ident" else (
            takes.new_variation_seed(request) if seed is None else seed)
        def run_prompt(context):
            takes.begin_prompt_rewrite(directory, segment_id)
            argv = [sys.executable, "-u", "-m", "mmv.worker", "rewrite_prompt", str(store.home), str(directory), segment_id]
            if candidate is not None:
                draft = directory / "prompt_takes" / segment_id / "candidate.txt"
                draft.parent.mkdir(parents=True, exist_ok=True)
                draft.write_text(candidate, encoding="utf-8")
                argv.append(str(draft))
            elif variation is not None or world_id or direction:
                argv.extend([
                    "",
                    str(variation) if variation is not None else "",
                    str(world_id).strip() if world_id else "",
                    str(direction).strip() if direction else "",
                ])
            context.update(f"{'Checking the edited' if candidate is not None else 'Writing a new'} prompt for {segment_id}", 5)
            # The worker saves the prompt before its last checks finish; a failure anywhere restores the prompt, its binding and plan.
            kept = {name: (directory / name).read_bytes()
                    for name in ("prompts.json", "passage-plan-prompts.json", "plan.json", "prepared.json", f"writer_jobs/{segment_id}.json")
                    if (directory / name).is_file()}
            try:
                context.command(argv, progress_path=directory / "progress.json",
                                env={"MMV_SERVICE_LOG_DIR": str(context.log_path.parent)})
            except BaseException as exc:
                for name, content in kept.items():
                    (directory / name).write_bytes(content)
                if candidate is not None:       # keep the user's text to edit again, marked as not passed
                    takes.record_prompt_take(directory, segment_id, candidate, how,
                                             problems=read_json(directory / f"{segment_id}.validation-edit.json", None) or [str(exc)[:600]])
                raise
            takes.record_prompt_take(directory, segment_id, read_json(directory / "prompts.json", {})[segment_id], how, variation_seed=variation)
            return score_view.passage_breakdown(store, origin)
        return jobs.start(kind, run_prompt, run_id=job_run_id(store, kind, f"{origin}_{segment_id}"))

    @app.post("/api/outputs/{run_id}/prompts/{segment_id}/rewrite")
    def rewrite_output_prompt(run_id: str, segment_id: str, value: PromptRewriteRequest):
        from mmv import takes
        if value.confirm is not True:
            raise ValueError("Confirm writing a new prompt for this passage")
        with jobs.lock:
            jobs.require_idle()
            origin = score_view._origin_run(store, run_id)
            charge = takes.writer_charge(read_json(inside(store.home / "runs", identifier(origin)) / "prepared.json", {}))
            if charge["api_writer"] and value.accept_writer_cost is not True:
                raise ValueError(f"This production's writer is an API service that may charge for the call "
                                 f"(estimate about ${charge['estimate_usd']:.2f}); accept the writer cost to continue")
            return prompt_job(
                run_id,
                segment_id,
                "prompt_rewrite",
                "rewritten",
                seed=value.seed,
                world_id=value.world_id,
                direction=value.direction,
            )

    @app.post("/api/outputs/{run_id}/prompts/{segment_id}/edit")
    def edit_output_prompt(run_id: str, segment_id: str, value: PromptEditRequest):
        if value.confirm is not True:
            raise ValueError("Confirm checking the edited prompt with the Mondo checks and Laya review")
        with jobs.lock:
            jobs.require_idle()
            return prompt_job(run_id, segment_id, "prompt_check", "edited", candidate=value.prompt.strip())

    @app.post("/api/outputs/{run_id}/prompts/{segment_id}/select")
    def select_output_prompt(run_id: str, segment_id: str, value: PromptTakeSelectRequest):
        from mmv import takes
        with jobs.lock:
            jobs.require_idle()
            return takes.select_prompt_take(store, run_id, segment_id, value.prompt_take_id)

    @app.post("/api/outputs/{run_id}/reroll/{segment_id}")
    def reroll_output_segment(run_id: str, segment_id: str, value: RerollRequest):
        from mmv import takes
        from mmv.services import check_required_services
        if value.confirm is not True:
            raise ValueError("Confirm the local GPU render of one passage before rerolling")
        with jobs.lock:
            jobs.require_idle()
            origin = score_view._origin_run(store, run_id)
            directory = inside(store.home / "runs", identifier(origin))
            request = read_json(directory / "request.json", {})
            takes.validate_segment_id(segment_id)
            if blocked := takes.reroll_block(request):
                raise ValueError(blocked)
            missing_errors = check_required_services(store, request, resume=True)
            if missing_errors:
                raise ValueError(f"Cannot reroll clip: {missing_errors[0]}")
            seed_arg = [str(value.seed)] if value.seed is not None else []
            def run_reroll(context):
                context.update(f"Starting reroll for {segment_id}", 5)
                context.command(
                    [sys.executable, "-u", "-m", "mmv.worker", "reroll", str(store.home), str(directory), segment_id, *seed_arg],
                    progress_path=directory / "progress.json", env={"MMV_SERVICE_LOG_DIR": str(context.log_path.parent)},
                )
                return score_view.passage_breakdown(store, origin)
            return jobs.start("reroll", run_reroll, run_id=job_run_id(store, "reroll", f"{origin}_{segment_id}"))

    @app.post("/api/outputs/{run_id}/reassemble")
    def reassemble_output_video(run_id: str, value: ReassembleRequest | None = None):
        from mmv import takes
        with jobs.lock:
            jobs.require_idle()
            origin = score_view._origin_run(store, run_id)
            selected = value.selected_takes if value else None
            return jobs.start(
                "reassemble",
                lambda context: takes.reassemble_final_video(store, origin, context, selected_takes=selected),
                run_id=job_run_id(store, "reassemble", origin),
            )

    @app.get("/api/media/{run_id}/{filename}")
    def media_file(run_id: str, filename: str, download: bool = False):
        directory = store.home / "runs" / identifier(run_id)
        record = read_json(directory / "output.json", {})
        from mmv import captions
        if filename not in [record.get("file"), *captions.downloads(record)] or Path(filename).suffix not in (".mp4", ".srt"):
            raise ValueError("Output not found")
        kind = "application/x-subrip" if filename.endswith(".srt") else "video/mp4"
        return FileResponse(inside(directory, filename), media_type=kind, filename=filename if download or filename.endswith(".srt") else None)

    @app.post("/api/log/clear")
    def clear_log():
        cleared_offsets = {}
        try:
            status = jobs.status()
            active_id = status.get("id") if status.get("state") in ("running", "cancelling") else None
            if active_id:
                active_dir = store.home / "runs" / identifier(active_id)
                cleared_offsets = {f"{active_dir.name}/{name}": (active_dir / name).stat().st_size
                                   for name in LOG_FILES if (active_dir / name).exists()}
        except Exception:
            pass

        write_json(store.home / "log_cleared.json", {"cleared_at": time.time(), "offsets": cleared_offsets})
        studio_log = store.home / "studio.log"
        if studio_log.exists():
            try:
                studio_log.write_text("", encoding="utf-8")
            except Exception:
                pass
        return {"status": "cleared"}

    @app.post("/api/cache/clear")
    def clear_cache():
        write_json(store.home / "cache_cleared.json", {"cleared_at": time.time()})
        cache_dir = store.home / "cache" / "prompts"
        count = 0
        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
        log_studio(store, f"Prompt cache cleared ({count} cached prompts removed)")
        return {"status": "cleared", "count": count}

    @app.get("/api/log/{run_id}")
    def operation_log(run_id: str):
        cleared_info = read_json(store.home / "log_cleared.json", {})
        cleared_at = float(cleared_info.get("cleared_at", 0))
        cleared_offsets = cleared_info.get("offsets", {})

        active_id = None
        try:
            status = jobs.status()
            if status.get("state") in ("running", "cancelling"):
                active_id = status.get("id")
        except Exception:
            pass

        sections = []
        if run_id == "latest" or not run_id:
            runs = [p for p in sorted((store.home / "runs").glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if p.name == active_id or p.stat().st_mtime >= cleared_at]
            directory = runs[0] if runs else None
        else:
            directory = store.home / "runs" / identifier(run_id)
            if not directory.exists() or ((not active_id or directory.name != active_id) and directory.stat().st_mtime < cleared_at):
                directory = None

        if directory and directory.is_dir():
            def tail(name, limit):
                """The last `limit` bytes of a run log, never reaching back before the last clear."""
                path = directory / name
                if not path.exists():
                    return ""
                offset, size = int(cleared_offsets.get(f"{directory.name}/{name}", 0)), path.stat().st_size
                if size <= offset:
                    return ""
                with path.open("rb") as stream:
                    stream.seek(max(offset, size - limit))
                    return stream.read().decode(errors="replace")
            content_chunk = tail("operation.log", 64000)
            if content_chunk.strip():
                sections.append(f"=== Operation Output (Run: {directory.name}) ===\n" + content_chunk)
            # Include any validation failure reports
            validations = sorted(directory.glob("*.validation-*.json"))
            for v in validations:
                if v.stat().st_mtime >= cleared_at:
                    try:
                        data = json.loads(v.read_text(encoding="utf-8"))
                        sections.append(f"\n--- Validation Details ({v.name}) ---\n" + json.dumps(data, indent=2))
                    except Exception:
                        pass
            # Include writer service output if present
            if writer_text := tail("writer-service.log", 16000):
                sections.append("\n--- Writer Service Output (llama.cpp) ---\n" + writer_text)
            # Include ComfyUI service output if present
            if comfy_text := tail("comfy-service.log", 16000):
                sections.append("\n--- ComfyUI Service Output ---\n" + comfy_text)
            # Include final operation status
            op_info = read_json(directory / "operation.json", {})
            if op_info.get("state") == "failed" and op_info.get("message"):
                sections.append(f"\nStatus: FAILED - {op_info['message']}")
            elif op_info.get("state"):
                sections.append(f"\nStatus: {op_info['state'].upper()}")

        # Include recent studio event log
        studio_log = store.home / "studio.log"
        if studio_log.exists() and studio_log.stat().st_size > 0:
            with studio_log.open("rb") as stream:
                stream.seek(max(0, studio_log.stat().st_size - 16000))
                sections.append("\n=== Studio Server Event Log ===\n" + stream.read().decode(errors="replace"))

        content = "\n\n".join(filter(None, sections)).strip()
        for secret in store.secret_values():
            content = content.replace(secret, "[redacted]")
        return {"log": content or "No operation or server log recorded yet."}

    quoted_upscales = {}

    def upscale_options(value):
        return value.options.model_dump(exclude_none=True) if value.options else None

    def upscale_key(value):
        return (value.source, value.model, value.scale, json.dumps(upscale_options(value), sort_keys=True))

    @app.post("/api/upscale/estimate")
    def upscale_estimate(value: UpscaleRequest):
        """Free Topaz cloud quote (credits and time). Reserves nothing and starts no job."""
        if store.settings().get("topaz_backend") != "cloud":
            raise ValueError("Choose the Topaz cloud service in Settings to get an estimate")
        quote = production.upscale_estimate(store, value.source, value.model, value.scale, upscale_options(value))
        quoted_upscales[upscale_key(value)] = quote["credits"][1]
        return quote

    @app.get("/api/upscale/models")
    def upscale_models():
        """Topaz cloud models and frame-rate/tuning options (free; narrowed to what Topaz accepts now)."""
        return production.upscale_models()

    @app.post("/api/upscale")
    def upscale(value: UpscaleRequest):
        with jobs.lock:
            jobs.require_idle()
            if (store.settings().get("topaz_backend") == "cloud"
                    and quoted_upscales.get(upscale_key(value)) != value.max_credits):
                raise ValueError("Get a Topaz estimate for these exact settings and approve its credits first")
            title = read_json(inside(store.home / "runs", value.source).parent / "output.json", {}).get("title") or ""
            return jobs.start("upscale", lambda context: production.upscale(store, value.source, value.model, value.scale,
                                                                              context, value.max_credits, options=upscale_options(value)),
                              run_id=job_run_id(store, "upscale", title))

    @app.get("/api/captions/fonts")
    def caption_fonts():
        from mmv import captions
        return {"fonts": list(captions.installed_fonts())}

    @app.post("/api/captions")
    def caption_video(value: CaptionVideoRequest):
        from mmv import captions
        with jobs.lock:
            jobs.require_idle()
            looks = value.model_dump(include={"style", "position", "size", "color", "outline_color", "font"})
            return jobs.start("captions", lambda context: captions.caption_finished(
                store, value.source, [line.model_dump(exclude_none=True) for line in value.lyric_lines], context, looks),
                run_id=captions.run_name(store, value.source, looks))

    return app
