"""Portable application data and atomic records. No studio imports."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path


def default_home() -> Path:
    if os.environ.get("MMV_HOME"):
        return Path(os.environ["MMV_HOME"]).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "mondo-music-video"


def write_json(path: Path, value, *, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".mmv-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600 if private else 0o644) if hasattr(os, "fchmod") else None
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(10):
            try:
                os.replace(name, path)
                break
            except PermissionError:
                if attempt == 9 or os.name != "nt":
                    raise
                time.sleep(0.02)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    for attempt in range(10):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == 9 or os.name != "nt":
                raise
            time.sleep(0.02)
    return default


def _read_or_none(path: Path):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("Use 1–64 lowercase letters, numbers, underscores or hyphens")
    return value


def inside(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()) or result == root.resolve():
        raise ValueError("Path is outside its data directory")
    return result


# The original three-field factory value; a daylight.json equal to this exactly is upgraded.
LEGACY_DEFAULT_STYLE = {
    "id": "daylight", "name": "Daylight Cinema",
    "direction": "Expressive music-video photography, natural light, rich color, "
                 "clear compositions and rhythmic movement. Fully clothed subjects; "
                 "no nudity, sexual imagery, blood or violence.",
}

DEFAULT_STYLE = {
    "id": "daylight", "name": "Daylight Cinema",
    "direction": (
        "Aesthetic directives\n\n"
        "DAYLIGHT CINEMA — expressive music-video photography in natural light. "
        "Every shot must embody all of these simultaneously.\n\n"
        "TONAL STRUCTURE. Blacks are open and gently lifted by ambient daylight, never crushed. "
        "Highlights are held just below clipping, with the sky and bright surfaces keeping detail. "
        "Contrast is moderate and global, with generous, well-separated midtones. "
        "The grade reads as clean, luminous and ungimmicked.\n\n"
        "COLOR AND INK ECONOMY. Rich, honest color: many distinct hues carry real area, "
        "each clearly separated and true to the materials. Saturation is full-bodied but never neon "
        "and never clipped. One deliberate accent color per shot, reserved for the focal point; "
        "everything else stays in harmony around it. Skin tones stay natural and warm.\n\n"
        "SURFACE. Fine, even, organic cinema-film grain over clean, high-resolution detail. "
        "Materials read as tactile — cloth, skin, stone, water, foliage, metal — "
        "with visible texture at every scale. No plastic smoothing, no digital noise.\n\n"
        "EDGE BEHAVIOUR. Edges are crisp where the lens is focused and fall away into soft optical blur "
        "elsewhere. Subjects are unoutlined and separate cleanly from their background. "
        "A touch of natural bloom is allowed where sun meets lens. No halos, fringing or oversharpening.\n\n"
        "LIGHT LOGIC. One dominant natural source: the sun, or open sky acting as a large soft box. "
        "Direction is chosen on purpose — low and raking at golden hour, high and clear at midday, "
        "directional and filtered, with readable falloff. Fill comes from soft reflected illumination. "
        "Falloff is gentle and shadows are soft but shaped. Light is depicted as a physical presence: "
        "visible shafts, rim highlights, lens flare and warm reflected spill. No artificial or colored lighting.\n\n"
        "DEPTH STRATEGY. Layered foreground, middle ground and background, with overlap, "
        "linear perspective and light atmospheric haze. Shallow to moderate depth of field separates the subject. "
        "The image has continuous, physically plausible spatial depth.\n\n"
        "COMPOSITION GRAMMAR. Clear, readable framing with one clear focal grouping and room to breathe. "
        "Use off-centre balance, directional visual lines and open negative space; let the supplied staging determine the forms. "
        "Balance is deliberate, asymmetry is welcome, and the empty-to-occupied ratio stays generous.\n\n"
        "SCALE RELATIONSHIP. The primary form holds a confident share of the frame, "
        "at the supplied shot scale, with readable spatial relationships around it.\n\n"
        "PROVENANCE MARKERS. Gentle lens bloom, a trace of natural vignetting, warm sun-kissed color, "
        "and fine grain. It reads as well-shot cinema photography, not a render.\n\n"
        "MOTION IMPLICATION. Give fine textures a restrained pulse and soft-edged surfaces a gentle, continuous deformation. "
        "Let highlights shift and glint, fine suspended texture drift, and reflected patterns undulate. "
        "Movement is rhythmic and flowing, answering the beat of the music, "
        "with confident motion that is never frantic.\n\n"
        "ANTI-TROPE MANDATE.\n"
        "- NO neon, colored gels or artificial lighting.\n"
        "- NO murky, crushed or muddy shadows.\n"
        "- NO plastic AI skin or digital over-smoothing.\n"
        "- NO centered \"AI poster\" symmetry, cluttered frames or HDR halos.\n\n"
        "CAMERA AND FRAMING.\n\n"
        "The supplied `camera` string is the authoritative motion — use it as written. "
        "Layer the daylight flavor around it: rhythmic, music-driven movement, clear compositions, "
        "natural light moving across the frame. Do not write cut or transition language.\n\n"
        "CONTENT BOUNDARY.\n\n"
        "All human characters are fictional adults. Human characters are fully clothed in opaque clothing. "
        "No nudity, sexual imagery, explicit sexual content, real-person likenesses, blood, gore or violence. "
        "Animals and other non-human subjects are depicted non-sexually."
    ),
    "style_card": (
        "STYLE CARD: Daylight Cinema\n"
        "1 INK ECONOMY: many distinct natural hues with real area; one accent per shot reserved for the focal point; "
        "full-bodied saturation below neon.\n"
        "2 TONAL STRUCTURE: open, gently lifted blacks; highlights held below clipping; moderate global contrast; stretched midtones.\n"
        "3 SURFACE: fine even cinema-film grain over clean tactile detail; no digital smoothing.\n"
        "4 EDGE BEHAVIOUR: crisp at focus, soft optical falloff elsewhere; unoutlined; light natural bloom; no halos.\n"
        "5 LIGHT LOGIC: one dominant natural source, chosen direction, gentle falloff, bounce fill; light is depicted "
        "(shafts, rim, flare).\n"
        "6 DEPTH STRATEGY: layered overlap, linear perspective, light haze, shallow-to-moderate focus; continuous spatial depth.\n"
        "7 COMPOSITION GRAMMAR: clear focal grouping, thirds and leading lines, off-centre balance, generous empty space.\n"
        "8 SCALE RELATIONSHIP: lifelike relative proportions; primary-form size follows the supplied shot scale.\n"
        "9 PROVENANCE MARKERS: gentle bloom, slight vignetting, warm sun-kissed color, fine grain.\n"
        "10 TYPOGRAPHY: none.\n"
        "11 MOTION IMPLICATION: gentle material deformation; shifting and glinting light; drifting fine texture and undulating reflection; "
        "rhythmic texture changes within the supplied camera movement.\n"
        "FREE AXES: natural hue family, daylight direction, placement and primary-form size within the supplied shot scale.\n"
        "BORROWABLE MOTIFS: narrow directional highlights; fine grain shimmer, re-rendered in the target world materials."
    ),
}

DEFAULTS = {
    "writer_api_profile": "", "vision_api_profile": "", "video_api_profile": "",
    "auto_updates": False, "auto_collapse_panels": True, "h3_tag_normalizer": False, "render_timeout_minutes": 120,
    "backend": "local_h3", "comfy_url": "http://127.0.0.1:8188",
    "workflow_map_path": str(Path(__file__).parent / "engine/config/injection_map.json"),
    "comfy_input": "", "comfy_output": "", "comfy_sdk_url": "http://127.0.0.1:8189",
    "writer_url": "http://127.0.0.1:8080/v1", "writer_model": "", "writer_mode": "local", "writer_call_estimate": 0.0,
    "writer_launch": "", "writer_cwd": "", "comfy_launch": "", "comfy_cwd": "",
    "laya_model_dir": "", "laya_device": "cuda",
    "vision_url": "http://127.0.0.1:8080/v1", "vision_model": "", "vision_launch": "",
    "vision_key_env": "MMV_VISION_API_KEY", "vision_call_estimate": 0.0,
    "topaz_executable": "", "topaz_models": "", "topaz_backend": "local",
}


LAYA_OVERRIDES = ("cpu",)


class Storage:
    def __init__(self, home=None):
        self.home = Path(home or default_home()).resolve()
        for name in ("actors", "styles", "vocabularies", "uploads", "runs", "exports", "models", "cache"):
            (self.home / name).mkdir(parents=True, exist_ok=True)
        removed_styles = read_json(self.home / "removed-assets.json", {}).get("styles", [])
        daylight = self.home / "styles/daylight.json"
        if not daylight.exists():
            if "daylight" not in removed_styles:
                write_json(daylight, DEFAULT_STYLE)
        elif _read_or_none(daylight) == LEGACY_DEFAULT_STYLE:
            write_json(daylight, DEFAULT_STYLE)

    def settings(self):
        settings = {**DEFAULTS, **{k:v for k,v in read_json(self.home / "settings.json", {}).items() if k in DEFAULTS}}
        if not settings["workflow_map_path"] or not Path(settings["workflow_map_path"]).is_file():
            settings["workflow_map_path"] = DEFAULTS["workflow_map_path"]
        if not settings["laya_model_dir"]:
            settings["laya_model_dir"] = str(self.home / "models/laya")
        # Per-process override chosen by a worker's GPU hand-off; never read from or written to settings.json.
        if os.environ.get("MMV_LAYA_DEVICE_OVERRIDE") in LAYA_OVERRIDES:
            settings["laya_device"] = os.environ["MMV_LAYA_DEVICE_OVERRIDE"]
        from .api_profiles import resolve
        return resolve(self, settings)

    def key(self, name="WAVESPEED_API_KEY"):
        from .api_profiles import KEYS, selected
        for role, credential in KEYS.items():
            if name == credential:
                profile = selected(self, self.settings(), role)
                if profile is not None:
                    return profile.get("key", "")
        return os.environ.get(name) or read_json(self.home / "secrets.json", {}).get(name, "")

    def save_key(self, name, value):
        if name not in ("WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY", "MMV_COMFY_API_KEY", "MMV_TOPAZ_API_KEY"):
            raise ValueError("Unknown credential")
        from .api_profiles import KEYS, records
        for role, credential in KEYS.items():
            profile_name = self.settings().get(role + "_api_profile")
            if name == credential and profile_name:
                profiles = records(self)
                profiles[profile_name]["key"] = value
                write_json(self.home / "api-profiles.json", profiles, private=True)
                return
        secrets = read_json(self.home / "secrets.json", {})
        if value:
            secrets[name] = value
        else:
            secrets.pop(name, None)
        write_json(self.home / "secrets.json", secrets, private=True)

    def secret_values(self):
        from .api_profiles import records
        values = list(read_json(self.home / "secrets.json", {}).values())
        values.extend(item.get("key", "") for item in records(self).values())
        values.extend(os.environ.get(name, "") for name in
                      ("WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY", "MMV_COMFY_API_KEY",
                       "MMV_TOPAZ_API_KEY"))
        return sorted({v for v in values if isinstance(v, str) and v}, key=len, reverse=True)

    def actor(self, actor_id):
        return read_json(self.home / "actors" / identifier(actor_id) / "actor.json")

    def style(self, style_id):
        result = read_json(self.home / "styles" / (identifier(style_id) + ".json"))
        if result is None:
            raise ValueError("Style not found")
        return result

    def vocabulary(self, vocab_id):
        result = read_json(self.home / "vocabularies" / (identifier(vocab_id) + ".json"))
        if result is None:
            raise ValueError("Unknown visual vocabulary profile")
        return result
