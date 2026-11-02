"""Deterministic contextual vocabulary selection: pure, no services, no real data."""
import copy

from mmv import vocab_select as vs
from mmv.pipeline import load_vocabulary


def test_contextual_vocabulary_is_pure_stable_and_narrowed():
    vocab = {'settings': ['archive stairwell', 'beach at noon', 'records annex', 'forest glade',
                          'carceral cell', 'desert road', 'harbor pier', 'office cubicle'],
             'camera_by_energy': {'0': 'static'}}
    before = copy.deepcopy(vocab)
    first = vs.contextual_vocabulary(vocab, 3, ['a clerk in an archive records office'])
    assert vocab == before
    assert first == vs.contextual_vocabulary(vocab, 3, ['a clerk in an archive records office'])
    assert len(first['settings']) == 4 and set(first['settings']) <= set(vocab['settings'])
    assert {'archive stairwell', 'records annex', 'office cubicle'} <= set(first['settings'])
    assert first['camera_by_energy'] == vocab['camera_by_energy']


def test_seed_changes_tiebreaks_but_never_empties_a_table():
    vocab = load_vocabulary('full')
    assert vocab is not None
    a, b = vs.contextual_vocabulary(vocab, 1), vs.contextual_vocabulary(vocab, 2)
    for name in vs.ROTATION_TABLES:
        if isinstance(vocab.get(name), list):
            assert a[name] and b[name] and len(a[name]) <= len(vocab[name])
    assert any(a[n] != b[n] for n in vs.ROTATION_TABLES if isinstance(vocab.get(n), list))


def _segment(index, energy, montage, shot_vocabs, anchor=None):
    from mmv.engine.plan import Segment, Shot
    shots = [Shot(n=i + 1, start_frame=0, frames=24, cut_time=None, camera='', shot_scale='', energy=energy, vocab=dict(v))
             for i, v in enumerate(shot_vocabs)]
    return Segment(index=index, song_start_frame=0, musical_frames=0, gen_frames=0, trim_frames=0, duration_input=0.0,
                   montage_type=montage, section_index=0, section_label='', energy=energy, thematic_anchor=anchor,
                   ref_image_slots=0, footage_anchor='', practical_effects='', rigging='', audio_slice_start_s=0.0,
                   audio_slice_end_s=0.0, shots=shots)


DEPARTURES = {role: {'settings': [f'{role} place {i}' for i in range(6)], 'lighting': [f'{role} light {i}' for i in range(6)],
                     'mechanisms': [f'{role} device {i}' for i in range(6)]} for role in vs.ROLES}


def test_pick_role_calm_stays_home_and_peak_departs():
    assert all(vs.pick_role(vs.departure_score(0.3, 0.4, 50), d) is None for d in range(100))
    assert {vs.pick_role(0.95, d) for d in range(100)} == {'tangent', 'opposite', 'mirror'}
    assert {vs.pick_role(0.7, d) for d in range(100)} == {'mirror', 'tangent', None}
    assert vs.departure_score(0.9, 0.9, 0) < vs.departure_score(0.9, 0.9, 100)


def test_departures_are_pure_deterministic_and_keep_slots():
    rotating = [{'setting': 'a', 'subject_type': 's', 'mechanism': 'm', 'lighting': 'l', 'costume': 'c'},
                {'setting': 'b', 'subject_type': 's', 'mechanism': 'm', 'lighting': 'l', 'costume': 'c'}]
    segments = [_segment(0, 0.95, 'chaotic', rotating), _segment(1, 0.2, 'chaotic', rotating)]
    before = copy.deepcopy(segments)
    first = vs.plan_world_departures(segments, DEPARTURES, 5, 100)
    assert segments == before and first == vs.plan_world_departures(segments, DEPARTURES, 5, 100)
    assert first and all(s_idx == 0 for s_idx, _ in first)           # the calm passage never departs
    for (s_idx, sh_idx), (role, vocab) in first.items():
        assert set(vocab) == set(rotating[0])                           # no keys added
        assert vocab['subject_type'] == 's' and vocab['costume'] == 'c' # cast-facing slots untouched
        assert vocab['setting'].startswith(role)
    assert vs.plan_world_departures(segments, {}, 5, 100) == {}


def test_held_passage_keeps_one_setting_and_anchor_mechanism():
    held = [{'setting': 'a', 'mechanism': 'm', 'lighting': f'l{i}'} for i in range(4)]
    result = vs.plan_world_departures([_segment(0, 1.0, 'standard', held, anchor='clock')], DEPARTURES, 9, 100)
    assert len(result) == 4 and len({v['setting'] for _, v in result.values()}) == 1
    assert {v['mechanism'] for _, v in result.values()} == {'m'}


def test_single_configured_role_still_departs_at_moderate_energy():
    shots = [{'setting': f's{i}', 'lighting': 'l'} for i in range(8)]
    segments = [_segment(i, 0.75, 'chaotic', shots) for i in range(6)]
    result = vs.plan_world_departures(segments, {'opposite': DEPARTURES['opposite']}, 3, 50)
    assert result and {role for role, _ in result.values()} == {'opposite'}


def test_select_term_for_energy_scales_pool_depth():
    table = [f'term_{i}' for i in range(20)]
    low_picks = {vs.select_term_for_energy(table, 0.0, seed=7, section_idx=0, shot_idx=i) for i in range(50)}
    high_picks = {vs.select_term_for_energy(table, 1.0, seed=7, section_idx=0, shot_idx=i) for i in range(50)}
    # At energy 0.0, min_ratio=0.20 confines choices to the first 4 terms (20% of 20)
    assert low_picks <= set(table[:4])
    # At energy 1.0, full pool is accessible, including terms beyond index 4
    assert any(p in set(table[4:]) for p in high_picks)
    assert vs.select_term_for_energy([], 0.5, 7, 0, 0) == ''


def test_apply_energy_scaled_vocabulary_stacks_at_high_energy_and_preserves_anchors():
    vocab = {
        'settings': [f'place_{i}' for i in range(10)],
        'mechanisms': [f'mech_{i}' for i in range(10)],
        'lighting': [f'light_{i}' for i in range(10)],
    }
    calm_shots = [{'setting': 's0', 'mechanism': 'm0', 'lighting': 'l0'},
                  {'setting': 's1', 'mechanism': 'm1', 'lighting': 'l1'}]
    peak_shots = [{'setting': 's0', 'mechanism': 'm0', 'lighting': 'l0'},
                  {'setting': 's1', 'mechanism': 'm1', 'lighting': 'l1'}]
    anchored_shots = [{'setting': 's0', 'mechanism': 'anchor_mech', 'lighting': 'l0'}]

    segments = [
        _segment(0, 0.15, 'chaotic', calm_shots),
        _segment(1, 0.90, 'chaotic', peak_shots),
        _segment(2, 0.90, 'standard', anchored_shots, anchor='anchor_mech'),
    ]
    before = copy.deepcopy(segments)
    updates = vs.apply_energy_scaled_vocabulary(segments, vocab, seed=42)
    assert segments == before  # Pure: does not mutate input segments

    # Calm segment (index 0) draws single terms from the top 20-35% slice (no comma stacking)
    assert ',' not in updates[(0, 0)]['mechanism']
    assert updates[(0, 0)]['setting'] in vocab['settings'][:4]

    # High-energy segment (index 1, energy 0.90 >= 0.80) stacks secondary mechanism/lighting tags
    assert ',' in updates[(1, 0)]['mechanism'] or ',' in updates[(1, 1)]['mechanism']
    assert ',' in updates[(1, 0)]['lighting'] or ',' in updates[(1, 1)]['lighting']

    # Anchored segment (index 2) preserves its thematic_anchor mechanism
    assert updates[(2, 0)]['mechanism'] == 'anchor_mech'


def test_resolve_act_span_and_progress_mapping():
    # 3 acts equal partition
    assert vs.resolve_act_span(0, 3) == (0.0, 0.3333)
    assert vs.resolve_act_span(1, 3) == (0.3333, 0.6667)
    assert vs.resolve_act_span(2, 3) == (0.6667, 1.0)

    # Custom span
    assert vs.resolve_act_span(0, 3, [0.0, 0.25]) == (0.0, 0.25)
    assert vs.resolve_act_span(1, 3, [0.25, 0.70]) == (0.25, 0.7)

    acts = [
        {"act": 1, "title": "Act I", "span": [0.0, 0.35]},
        {"act": 2, "title": "Act II", "span": [0.35, 0.70]},
        {"act": 3, "title": "Act III", "span": [0.70, 1.0]},
    ]
    assert vs.resolve_act_for_progress(0.10, acts)[0] == 0
    assert vs.resolve_act_for_progress(0.35, acts)[0] == 1
    assert vs.resolve_act_for_progress(0.69, acts)[0] == 1
    assert vs.resolve_act_for_progress(0.70, acts)[0] == 2
    assert vs.resolve_act_for_progress(1.00, acts)[0] == 2


def test_plan_narrative_acts_chronological_progression():
    acts = [
        {
            "act": 1,
            "title": "Confinement",
            "span": [0.0, 0.33],
            "tables": {
                "settings": ["basement archive", "tenement stairwell"],
                "lighting": ["flickering fluorescent"],
                "mechanisms": ["sorting", "weighing"],
            },
        },
        {
            "act": 2,
            "title": "The Flight",
            "span": [0.33, 0.66],
            "tables": {
                "settings": ["subway tunnel", "fire escape"],
                "lighting": ["sodium vapor lamp"],
                "mechanisms": ["unspooling", "accelerating"],
            },
        },
        {
            "act": 3,
            "title": "Transcendence",
            "span": [0.66, 1.0],
            "tables": {
                "settings": ["salt flat", "open cliff"],
                "lighting": ["blinding noon sun"],
                "mechanisms": ["combustion", "levitation"],
            },
        },
    ]

    shots_act1 = [{"setting": "old_s", "lighting": "old_l", "mechanism": "old_m"}]
    shots_act2 = [{"setting": "old_s", "lighting": "old_l", "mechanism": "old_m"}]
    shots_act3 = [{"setting": "old_s", "lighting": "old_l", "mechanism": "old_m"}]

    from mmv.engine.plan import Segment, Shot

    def _timed_segment(idx, start_f, dur_f, shots, montage="chaotic", anchor=None):
        s_objs = [
            Shot(n=i + 1, start_frame=0, frames=24, cut_time=None, camera="", shot_scale="", energy=0.5, vocab=dict(v))
            for i, v in enumerate(shots)
        ]
        return Segment(
            index=idx,
            song_start_frame=start_f,
            musical_frames=dur_f,
            gen_frames=dur_f,
            trim_frames=dur_f,
            duration_input=dur_f / 24.0,
            montage_type=montage,
            section_index=idx,
            section_label="",
            energy=0.5,
            thematic_anchor=anchor,
            ref_image_slots=0,
            footage_anchor="",
            practical_effects="",
            rigging="",
            audio_slice_start_s=start_f / 24.0,
            audio_slice_end_s=(start_f + dur_f) / 24.0,
            shots=s_objs,
        )

    # 3 segments spanning 300 frames total (100 frames each)
    segments = [
        _timed_segment(0, 0, 100, shots_act1),      # mid=50 (16.7% progress -> Act 1)
        _timed_segment(1, 100, 100, shots_act2),    # mid=150 (50.0% progress -> Act 2)
        _timed_segment(2, 200, 100, shots_act3),    # mid=250 (83.3% progress -> Act 3)
    ]
    before = copy.deepcopy(segments)

    updates = vs.plan_narrative_acts(segments, acts, seed=123, total_frames=300)
    assert segments == before  # Pure: does not mutate inputs

    # Segment 0 must draw from Act 1 tables
    assert updates[(0, 0)]["setting"] in acts[0]["tables"]["settings"]
    assert updates[(0, 0)]["lighting"] == "flickering fluorescent"
    assert updates[(0, 0)]["mechanism"] in acts[0]["tables"]["mechanisms"]

    # Segment 1 must draw from Act 2 tables
    assert updates[(1, 0)]["setting"] in acts[1]["tables"]["settings"]
    assert updates[(1, 0)]["lighting"] == "sodium vapor lamp"
    assert updates[(1, 0)]["mechanism"] in acts[1]["tables"]["mechanisms"]

    # Segment 2 must draw from Act 3 tables
    assert updates[(2, 0)]["setting"] in acts[2]["tables"]["settings"]
    assert updates[(2, 0)]["lighting"] == "blinding noon sun"
    assert updates[(2, 0)]["mechanism"] in acts[2]["tables"]["mechanisms"]


def test_plan_narrative_acts_held_passages_and_thematic_anchors():
    acts = [
        {
            "act": 1,
            "title": "Act I",
            "tables": {
                "settings": ["vault room", "steel hangar", "sub-level chamber"],
                "lighting": ["dim worklight", "overhead neon"],
            },
        }
    ]
    from mmv.engine.plan import Segment, Shot

    # Standard montage passage with 3 shots that share one setting (held)
    shots = [
        Shot(n=1, start_frame=0, frames=24, cut_time=None, camera="", shot_scale="", energy=0.5, vocab={"setting": "hold", "lighting": "l1", "mechanism": "anchor_m"}),
        Shot(n=2, start_frame=24, frames=24, cut_time=None, camera="", shot_scale="", energy=0.5, vocab={"setting": "hold", "lighting": "l2", "mechanism": "anchor_m"}),
        Shot(n=3, start_frame=48, frames=24, cut_time=None, camera="", shot_scale="", energy=0.5, vocab={"setting": "hold", "lighting": "l3", "mechanism": "anchor_m"}),
    ]
    seg = Segment(
        index=0,
        song_start_frame=0,
        musical_frames=72,
        gen_frames=72,
        trim_frames=72,
        duration_input=3.0,
        montage_type="standard",
        section_index=0,
        section_label="",
        energy=0.5,
        thematic_anchor="anchor_m",
        ref_image_slots=0,
        footage_anchor="",
        practical_effects="",
        rigging="",
        audio_slice_start_s=0.0,
        audio_slice_end_s=3.0,
        shots=shots,
    )

    updates = vs.plan_narrative_acts([seg], acts, seed=777, total_frames=72)
    # The setting must be updated to an Act 1 setting, and all 3 shots must share the EXACT SAME setting!
    chosen_setting = updates[(0, 0)]["setting"]
    assert chosen_setting in acts[0]["tables"]["settings"]
    assert updates[(0, 1)]["setting"] == chosen_setting
    assert updates[(0, 2)]["setting"] == chosen_setting

    # The thematic anchor mechanism must be preserved
    assert updates.get((0, 0), {}).get("mechanism", "anchor_m") == "anchor_m"


def test_pipeline_prepare_video_with_narrative_acts(tmp_path):
    from mmv import pipeline
    from mmv.storage import Storage, DEFAULT_STYLE, write_json
    from mmv.api_profiles import save_settings

    store = Storage(tmp_path)
    (tmp_path / "styles").mkdir(parents=True, exist_ok=True)
    write_json(tmp_path / "styles/daylight.json", DEFAULT_STYLE)
    (tmp_path / "in").mkdir(exist_ok=True)
    (tmp_path / "out").mkdir(exist_ok=True)
    save_settings(store, {
        "writer_model": "qwen",
        "vision_model": "qwen",
        "comfy_input": str(tmp_path / "in"),
        "comfy_output": str(tmp_path / "out"),
    })
    request = {
        "kind": "ident",
        "style_id": "daylight",
        "backend": "local_h3",
        "aspect": "16:9",
        "megapixels": 0.6,
        "ident_seconds": 6.0,
        "seed": 42,
        "bars_per_phrase": 8,
        "ref_policy": "all",
        "on_screen": 1,
        "ensemble_mode": "off",
        "ident_all_references": False,
        "content": {"violence": "none", "nudity": "none", "sexual": "none", "substances": "none"},
        "narrative_acts": [
            {
                "act": 1,
                "title": "Opening",
                "span": [0.0, 0.5],
                "tables": {"settings": ["analog print shop"]},
            },
            {
                "act": 2,
                "title": "Closing",
                "span": [0.5, 1.0],
                "tables": {"settings": ["digital neon display"]},
            },
        ],
    }
    prepared = pipeline.prepare(store, request)
    assert "plan" in prepared
    plan = prepared["plan"]
    assert len(plan["segments"]) >= 1
    # Check that shots draw from the narrative acts
    for seg in plan["segments"]:
        for shot in seg["shots"]:
            assert shot["vocab"].get("setting") in ("analog print shop", "digital neon display")
