"""Deterministic contextual vocabulary selection (opt-in, outside the protected planner).

Pure functions only: vocabulary and context in, new vocabulary out. Nothing here
advances a random stream, reads files or mutates its arguments. The protected
planner (mmv/engine/plan.py) is untouched; this module decides which terms the
rotation tables hold before planning. Based on a contribution by hellonearthis.
"""
import hashlib
import math
import re

# Tables whose entries are plain rotation terms. Structured tables are left alone.
ROTATION_TABLES = ('settings', 'lighting', 'mechanisms', 'costume', 'practical_effects')
MIN_KEEP = 4
KEEP_FRACTION = 0.5
MIN_ENERGY_RATIO = 0.20
STACK_ENERGY_THRESHOLD = 0.80
ENERGY_VOCAB_MAP = {
    'setting': 'settings',
    'subject_type': 'subject_types',
    'mechanism': 'mechanisms',
    'lighting': 'lighting',
    'tonal_register': 'tonal_registers',
    'costume': 'costume',
}
STACKABLE_KEYS = ('mechanism', 'lighting')
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOP = frozenset('the and with from for into over under that this a an of in on at to is are as by'.split())


def stable_hash(*parts) -> int:
    """Platform-independent integer hash of the parts (never Python's salted hash)."""
    return int.from_bytes(hashlib.sha256(':'.join(map(str, parts)).encode('utf-8')).digest()[:8], 'big')


def select_term_for_energy(table, energy: float, seed: int, section_idx: int, shot_idx: int,
                           salt: str = "", min_ratio: float = MIN_ENERGY_RATIO) -> str:
    """Select a term where the accessible pool window scales deterministically with audio energy."""
    if not table:
        return ""
    clamped = max(0.0, min(1.0, float(energy)))
    active_ratio = min_ratio + (1.0 - min_ratio) * clamped
    pool_size = max(1, min(len(table), int(math.ceil(len(table) * active_ratio))))
    active_window = table[:pool_size]
    idx = stable_hash(seed, "energy_pick", salt, section_idx, shot_idx) % len(active_window)
    return active_window[idx]


def apply_energy_scaled_vocabulary(segments, vocab: dict, seed: int) -> dict:
    """Pure function: returns {(segment_idx, shot_idx): new_shot_vocab} scaled by audio energy.

    Low energy (< 0.35) draws from a tight top slice (top 20%+ of ranked terms) for visual focus.
    High energy (> 0.75) opens the full table depth and stacks secondary mechanisms/lighting at >= 0.80.
    Preserves held-setting passages and thematic anchors established by the planner.
    """
    result = {}
    for s_idx, seg in enumerate(segments):
        held = len({sh.vocab.get('setting') for sh in seg.shots}) <= 1
        for sh_idx, shot in enumerate(seg.shots):
            shot_energy = float(getattr(shot, 'energy', getattr(seg, 'energy', 0.5)))
            new_vocab = dict(shot.vocab)
            for key, table_name in ENERGY_VOCAB_MAP.items():
                if key not in new_vocab:
                    continue
                if key == 'mechanism' and getattr(seg, 'thematic_anchor', None):
                    continue
                table = vocab.get(table_name)
                if not isinstance(table, list) or not table:
                    continue
                pos = 0 if (held and key != 'lighting') else sh_idx
                eff_energy = float(getattr(seg, 'energy', shot_energy)) if (held and key != 'lighting') else shot_energy
                primary = select_term_for_energy(table, eff_energy, seed, s_idx, pos, salt=key)
                if not primary:
                    continue
                if eff_energy >= STACK_ENERGY_THRESHOLD and key in STACKABLE_KEYS and len(table) > 1:
                    secondary = select_term_for_energy(table, eff_energy, seed, s_idx, pos, salt=f"{key}:stack")
                    if secondary and secondary != primary:
                        new_vocab[key] = f"{primary}, {secondary}"
                    else:
                        new_vocab[key] = primary
                else:
                    new_vocab[key] = primary
            if new_vocab != shot.vocab:
                result[(s_idx, sh_idx)] = new_vocab
    return result


def context_words(*texts) -> frozenset:
    """Lower-cased content words from any mix of strings and string lists."""
    flat = (t for item in texts for t in ([item] if isinstance(item, str) else (item or [])) if isinstance(t, str))
    return frozenset(w for t in flat for w in _WORD.findall(t.lower()) if len(w) > 2 and w not in _STOP)


def affinity(term, words) -> int:
    """How many context words the term shares (whole words and hyphen parts)."""
    parts = {p for w in _WORD.findall(term.lower()) for p in (w, *w.split('-'))}
    return len(parts & words)


def rank_table(table, seed, name, words, keep=None) -> list:
    """Most in-context terms first, ties broken by a seeded hash; keep a coherent subset."""
    keep = keep if keep is not None else max(MIN_KEEP, math.ceil(len(table) * KEEP_FRACTION))
    ranked = sorted(dict.fromkeys(table), key=lambda t: (-affinity(t, words), stable_hash(seed, name, t)))
    return ranked[:max(1, min(keep, len(ranked)))]


def contextual_vocabulary(vocab, seed, context=(), tables=ROTATION_TABLES) -> dict:
    """A new vocabulary whose rotation tables are narrowed to the context and ordered by hash."""
    words = context_words(*context)
    return {**vocab, **{name: rank_table(vocab[name], seed, name, words)
                        for name in tables if isinstance(vocab.get(name), list) and vocab[name]}}


# World juxtaposition: on high-energy shots, borrow terms from a contrast world. Adapted from a contribution by
# hellonearthis (mirror / opposite / tangent departures); the contrast worlds are the owner's own Worlds, not fixed archetypes.
ROLES = ('mirror', 'opposite', 'tangent')
DEPARTURE_KEYS = {'setting': 'settings', 'lighting': 'lighting', 'mechanism': 'mechanisms', 'tonal_register': 'tonal_registers'}
# The role a draw lands on may have no world chosen; the next configured role takes it, so the chance of staying home is unchanged.
ROLE_FALLBACK = {'mirror': ('mirror', 'tangent', 'opposite'), 'tangent': ('tangent', 'opposite', 'mirror'),
                 'opposite': ('opposite', 'tangent', 'mirror')}
DEPARTURE_THRESHOLD = 0.65
PEAK_THRESHOLD = 0.85


def departure_score(shot_energy, segment_energy, strength) -> float:
    """Half the shot's own energy, half the passage's energy scaled by the strength slider (50 = unscaled)."""
    return 0.5 * shot_energy + 0.5 * max(0.0, min(1.0, segment_energy * strength / 50.0))


def pick_role(score, draw):
    """The contrast role for a draw in 0-99, or None to stay in the main world. Calm passages never depart."""
    if score < DEPARTURE_THRESHOLD:
        return None
    if score >= PEAK_THRESHOLD:
        return 'tangent' if draw < 55 else 'opposite' if draw < 85 else 'mirror'
    return 'mirror' if draw < 60 else 'tangent' if draw < 90 else None


def _borrowed(vocab, terms, role, seed, segment_idx, position, held) -> dict:
    """The shot vocabulary with this role's terms swapped into slots the shot already has (no keys are added)."""
    def term(key, table):
        pos = 0 if held and key != 'lighting' else position
        return terms[table][stable_hash(seed, 'world', role, key, segment_idx, pos) % len(terms[table])]
    return {**vocab, **{key: term(key, table) for key, table in DEPARTURE_KEYS.items()
                        if key in vocab and terms.get(table)}}


def plan_world_departures(segments, departures, seed, strength=50) -> dict:
    """{(segment index, shot index): (role, new shot vocab)} for shots that depart. Pure: reads the plan, changes nothing.

    `departures` maps role -> {table: [terms]} (a role with no world is absent). A passage whose shots share one setting
    (the planner holds it steady) decides once for the whole passage, so that setting stays steady; a passage anchored to
    a thematic mechanism keeps that mechanism."""
    def decide(s_idx, sh_idx, shot_energy, seg):
        role = pick_role(departure_score(shot_energy, seg.energy, strength),
                         stable_hash(seed, 'juxtaposition', s_idx, sh_idx) % 100)
        return next((r for r in ROLE_FALLBACK[role] if r in departures), None) if role else None
    result = {}
    for s_idx, seg in enumerate(segments):
        held = len({sh.vocab.get('setting') for sh in seg.shots}) <= 1
        role_once = decide(s_idx, 0, seg.energy, seg) if held else None
        for sh_idx, shot in enumerate(seg.shots):
            role = role_once if held else decide(s_idx, sh_idx, shot.energy, seg)
            if role:
                terms = departures[role]
                if seg.thematic_anchor:
                    terms = {t: v for t, v in terms.items() if t != 'mechanisms'}
                new = _borrowed(shot.vocab, terms, role, seed, s_idx, sh_idx, held)
                if new != shot.vocab:
                    result[(s_idx, sh_idx)] = (role, new)
    return result


def plan_gaussian_world_dissonance(
    segments,
    base_world: str,
    world_pools: dict | None = None,
    seed: int = 0,
    slider_percent: float = 50.0,
) -> dict:
    """Apply percentile-calibrated Gaussian dissonance (kappa) and dimensional binding across segments.

    Pure function: returns {(segment_idx, shot_idx): (target_world, new_shot_vocab)} for shots whose
    effective dissonance kappa_eff > 0.20 triggers Soft Accent, Motivated Tension, Surreal Juxtaposition,
    or Hot Bars (Maximal Collision) while respecting Montage Grammar rules (Standard holds setting steady;
    Thematic preserves thematic_anchor mechanism).
    """
    from .world_vectors import (
        BUILTIN_CALIBRATED_MATRIX,
        BUILTIN_THEMATIC_WORLDS,
        calibrate_distance_matrix,
        compute_cluster_centroid,
        compute_effective_kappa,
        dimensional_binding_for_kappa,
        gaussian_cluster_weights,
    )

    catalog = dict(world_pools) if world_pools else dict(BUILTIN_THEMATIC_WORLDS)
    if base_world not in catalog or len(catalog) < 2:
        return {}

    if not world_pools:
        calibrated_dists = BUILTIN_CALIBRATED_MATRIX["calibrated"]
    else:
        centroids = {name: compute_cluster_centroid(pools) for name, pools in catalog.items()}
        cal = calibrate_distance_matrix(centroids)
        calibrated_dists = cal["calibrated"]

    weights_cache = {}

    def pick_cluster_for_tier(tier: str, kappa_eff: float, s_idx: int, pos: int, key: str) -> str:
        if tier == "base":
            return base_world
        target_k = {
            "adjacent": 0.15,
            "tension": max(0.55, kappa_eff),
            "opposite": 0.85,
            "maximal": 1.00,
        }.get(tier, kappa_eff)
        if target_k not in weights_cache:
            weights_cache[target_k] = gaussian_cluster_weights(
                base_world, calibrated_dists, target_k, d_max=1.0, exclude_base=True
            )
        weights = weights_cache[target_k]
        if not weights:
            return base_world
        ranked = sorted(weights.items())
        point = stable_hash(seed, "gaussian_pick", tier, key, s_idx, pos) / 2 ** 64 * sum(w for _, w in ranked)
        for name, weight in ranked:
            point -= weight
            if point < 0:
                return name
        return ranked[-1][0]

    result = {}
    for s_idx, seg in enumerate(segments):
        held = len({sh.vocab.get('setting') for sh in seg.shots}) <= 1
        seg_energy = float(getattr(seg, 'energy', 0.5))
        for sh_idx, shot in enumerate(seg.shots):
            shot_energy = float(getattr(shot, 'energy', seg_energy))
            base_k = 0.5 * shot_energy + 0.5 * seg_energy
            kappa_eff = compute_effective_kappa(base_k, slider_percent)
            draw = stable_hash(seed, "dim_bind", s_idx, 0 if held else sh_idx)
            binding = dimensional_binding_for_kappa(kappa_eff, list(shot.vocab.keys()), seed_draw=draw)

            new_vocab = dict(shot.vocab)
            chosen_worlds = set()
            for key, tier in binding.items():
                if tier == "base":
                    continue
                if key == "mechanism" and getattr(seg, "thematic_anchor", None):
                    continue
                if held and key in ("setting", "subject_type", "costume") and kappa_eff < 0.90:
                    pos = 0
                else:
                    pos = sh_idx
                table_name = ENERGY_VOCAB_MAP.get(key)
                if not table_name:
                    continue
                target_world = pick_cluster_for_tier(tier, kappa_eff, s_idx, pos, key)
                terms = catalog.get(target_world, {}).get(table_name)
                if terms:
                    term_idx = stable_hash(seed, "dissonance_term", target_world, key, s_idx, pos) % len(terms)
                    new_vocab[key] = terms[term_idx]
                    chosen_worlds.add(target_world)

            if new_vocab != shot.vocab and chosen_worlds:
                primary_target = sorted(chosen_worlds)[0]
                result[(s_idx, sh_idx)] = (primary_target, new_vocab)
    return result


# ---------------------------------------------------------------------------
# Preset-driven Narrative Palettes (Chronological Act 1 / Act 2 / Act 3)
# ---------------------------------------------------------------------------

def resolve_act_span(act_index: int, total_acts: int, custom_span: list | tuple | None = None) -> tuple[float, float]:
    """Return (start_ratio, end_ratio) for an act along the [0.0, 1.0] timeline.

    If custom_span is provided as [start, end] with 0.0 <= start < end <= 1.0, it is used.
    Otherwise, evenly partitions the timeline across the number of acts.
    """
    if custom_span and isinstance(custom_span, (list, tuple)) and len(custom_span) == 2:
        try:
            start, end = float(custom_span[0]), float(custom_span[1])
            if 0.0 <= start < end <= 1.0:
                return (round(start, 4), round(end, 4))
        except (TypeError, ValueError):
            pass
    total = max(1, total_acts)
    span_len = 1.0 / total
    return (round(act_index * span_len, 4), round(min(1.0, (act_index + 1) * span_len), 4))


def resolve_act_for_progress(progress: float, acts: list[dict]) -> tuple[int, dict]:
    """Find the active act for a progress ratio (0.0 to 1.0).

    Returns (act_index, act_dict).
    """
    total = len(acts)
    if total <= 0:
        return 0, {}
    clamped = max(0.0, min(1.0, float(progress)))
    for idx, act in enumerate(acts):
        start, end = resolve_act_span(idx, total, act.get("span"))
        if (start <= clamped < end) or (idx == total - 1 and clamped >= start):
            return idx, act
    return total - 1, acts[-1]


def _extract_act_table(table_spec, base_list: list | None = None) -> list[str]:
    """Extract list of available terms from either a list of strings or a VocabularyTableOverride dict."""
    if isinstance(table_spec, list):
        return [str(t).strip() for t in table_spec if str(t).strip()]
    if isinstance(table_spec, dict):
        mode = table_spec.get("mode", "append")
        adds = [str(t).strip() for t in table_spec.get("add", []) if str(t).strip()]
        excludes = {str(t).strip() for t in table_spec.get("exclude", []) if str(t).strip()}
        if mode == "replace":
            return [t for t in adds if t not in excludes]
        base = [t for t in (base_list or []) if t not in excludes]
        seen = set(base)
        for t in adds:
            if t not in seen and t not in excludes:
                seen.add(t)
                base.append(t)
        return base
    return []


def plan_narrative_acts(
    segments,
    acts: list[dict],
    seed: int = 0,
    total_frames: int | None = None,
    base_vocab: dict | None = None,
) -> dict:
    """Pure function: returns {(segment_idx, shot_idx): new_shot_vocab} for shots mapped to narrative acts.

    Each act in `acts` defines custom vocabulary pools for specific tables (settings, lighting,
    mechanisms, costume, tonal_registers, subject_types). The segment's midpoint progress along the
    song timeline activates its corresponding Act.

    Preserves:
    - Standard & Type 1 montage: held setting is chosen once per passage so shots stay visually cohesive.
    - Type 3 Thematic montage: thematic_anchor mechanism is preserved.
    - Determinism: exact same seed, acts, and timeline produce identical assignments.
    """
    if not acts or not segments:
        return {}
    base_vocab = base_vocab or {}
    if not total_frames or total_frames <= 0:
        total_frames = max(
            (getattr(s, "song_start_frame", 0) + getattr(s, "musical_frames", 0)) for s in segments
        ) or 1

    result = {}
    for s_idx, seg in enumerate(segments):
        start_f = getattr(seg, "song_start_frame", 0)
        dur_f = getattr(seg, "musical_frames", 0)
        mid_f = start_f + (dur_f / 2.0)
        progress = max(0.0, min(1.0, mid_f / total_frames))

        act_idx, active_act = resolve_act_for_progress(progress, acts)
        act_tables = active_act.get("tables") or {}

        held = len({sh.vocab.get("setting") for sh in seg.shots}) <= 1

        for sh_idx, shot in enumerate(seg.shots):
            new_vocab = dict(shot.vocab)
            for key in ("setting", "lighting", "mechanism", "costume", "tonal_register", "subject_type"):
                if key not in new_vocab:
                    continue
                if key == "mechanism" and getattr(seg, "thematic_anchor", None):
                    continue

                table_name = ENERGY_VOCAB_MAP.get(key)
                if not table_name:
                    continue

                table_spec = act_tables.get(table_name) or act_tables.get(key)
                if table_spec is None:
                    continue

                pool = _extract_act_table(table_spec, base_vocab.get(table_name))
                if not pool:
                    continue

                pos = 0 if (held and key in ("setting", "costume", "subject_type")) else sh_idx
                idx = stable_hash(seed, "narrative_act", act_idx, key, s_idx, pos) % len(pool)
                new_vocab[key] = pool[idx]

            if new_vocab != shot.vocab:
                result[(s_idx, sh_idx)] = new_vocab

    return result
