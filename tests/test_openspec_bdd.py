"""Executable OpenSpec & Cucumber BDD Specification Test Suite for the Mondo Music Video AI Engine.

Validates:
1. Domain Glossary (`openspec/glossary.yaml`) completeness and source file bindings.
2. All 10 Gherkin `.feature` specifications (`openspec/features/*.feature`) for valid syntax,
   `Feature:`, `Rule:`, `@TAG-NN` Scenario IDs, and `Given` / `When` / `Then` steps.
3. Behavior Report (`openspec/reports/AI_INTERACTIONS_DEEP_DIVE.md`) scenarios (`REPORT-01` .. `REPORT-45`),
   evidence file/line references, Mermaid sequence diagram, Coverage Gaps table, and Unknowns.
4. Direct behavioral execution of the core AI Engine contracts across:
   - Resilient JSON extraction & `<think>` stripping (`mmv/writer_json.py`, `mmv/engine/schema.py`)
   - Pre-compiled Thematic World centroids, P15/P85 calibrated distance matrix & Gaussian dissonance (`mmv/world_vectors.py`, `mmv/vocab_select.py`)
   - Laya `style_adherence` divergence advisory & strict retry feedback (`mmv/writer_json.py`)
   - Passage vocabulary re-sampling & creative world/direction steering (`mmv/takes.py`)
   - Deterministic Mondo motion & framing gates (`mmv/quality.py`)
   - Safe shot interior frame sampling (`mmv/vision_check.py`)
   - Storyboard proportional timeline alignment (`mmv/storyboard.py`)
   - Queue cost holds, crash recovery, ticket movement, resume bookkeeping and cancellation (`mmv/production_queue.py`)
"""
from __future__ import annotations

import json
import re
import tempfile
import types
import unittest
from pathlib import Path

from mmv import production_queue, quality, storyboard, takes, vision_check, vocab_select, world_vectors, writer_json
from mmv.engine.backends import get_backend
from mmv.engine.plan import Shot, Segment, STANDARD, THEMATIC
from mmv.engine.schema import RIGGING_TAIL, ValidationError, WriterResponse, assemble_prompt, validate_prompt
from mmv.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
OPENSPEC_DIR = ROOT / "openspec"
FEATURES_DIR = OPENSPEC_DIR / "features"
GLOSSARY_PATH = OPENSPEC_DIR / "glossary.yaml"
REPORT_PATH = OPENSPEC_DIR / "reports" / "AI_INTERACTIONS_DEEP_DIVE.md"


def parse_gherkin_feature(path: Path) -> dict:
    """Pure parser for Gherkin .feature files returning tags, feature title, rules, and scenarios."""
    lines = path.read_text(encoding="utf-8").splitlines()
    feature_tags: list[str] = []
    feature_title = ""
    rules: list[str] = []
    scenarios: list[dict] = []
    pending_tags: list[str] = []
    current_scenario: dict | None = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("@"):
            tags = [t.strip() for t in stripped.split() if t.startswith("@")]
            if not feature_title:
                feature_tags.extend(tags)
            else:
                pending_tags.extend(tags)
            continue
        if stripped.startswith("Feature:"):
            feature_title = stripped[len("Feature:"):].strip()
            continue
        if stripped.startswith("Rule:"):
            rules.append(stripped[len("Rule:"):].strip())
            continue
        if stripped.startswith(("Scenario:", "Scenario Outline:")):
            kind, title = stripped.split(":", 1)
            current_scenario = {
                "kind": kind.strip(),
                "title": title.strip(),
                "tags": list(pending_tags),
                "steps": [],
            }
            pending_tags = []
            scenarios.append(current_scenario)
            continue
        if stripped.startswith(("Given ", "When ", "Then ", "And ", "But ")):
            keyword, rest = stripped.split(" ", 1)
            if current_scenario is not None:
                current_scenario["steps"].append((keyword, rest.strip()))

    return {
        "file": path.name,
        "feature_tags": feature_tags,
        "feature_title": feature_title,
        "rules": rules,
        "scenarios": scenarios,
    }


class OpenSpecStructureAndGlossaryTests(unittest.TestCase):
    """Verify the OpenSpec glossary, 9 Gherkin feature files, and Behavior Report structure."""

    def test_glossary_terms_and_source_files_exist(self):
        self.assertTrue(GLOSSARY_PATH.is_file(), "openspec/glossary.yaml must exist")
        text = GLOSSARY_PATH.read_text(encoding="utf-8")
        self.assertIn('domain: "Mondo Music Video AI Engine"', text)
        source_lists = re.findall(r"sources:\s*\[(.*?)\]", text)
        self.assertGreaterEqual(len(source_lists), 15)
        for raw_list in source_lists:
            for quoted in re.findall(r'"([^"]+)"', raw_list):
                target = ROOT / quoted
                self.assertTrue(target.is_file(), f"Glossary source file missing: {quoted}")

    def test_all_ten_feature_files_parse_with_rules_tags_and_steps(self):
        feature_files = sorted(FEATURES_DIR.glob("*.feature"))
        self.assertEqual(len(feature_files), 10)
        total_scenarios = 0
        for path in feature_files:
            parsed = parse_gherkin_feature(path)
            self.assertTrue(parsed["feature_title"], f"Missing Feature title in {path.name}")
            self.assertTrue(parsed["feature_tags"], f"Missing Feature tags in {path.name}")
            self.assertGreaterEqual(len(parsed["rules"]), 1, f"Missing Rule blocks in {path.name}")
            self.assertGreaterEqual(len(parsed["scenarios"]), 3, f"Too few scenarios in {path.name}")
            for sc in parsed["scenarios"]:
                total_scenarios += 1
                self.assertTrue(
                    any(re.fullmatch(r"@[A-Z]+-\d{2}", tag) for tag in sc["tags"]),
                    f"Scenario '{sc['title']}' in {path.name} lacks @TAG-NN identifier",
                )
                keywords = [kw for kw, _ in sc["steps"]]
                self.assertIn("Given", keywords, f"Scenario '{sc['title']}' missing Given")
                self.assertIn("When", keywords, f"Scenario '{sc['title']}' missing When")
                self.assertIn("Then", keywords, f"Scenario '{sc['title']}' missing Then")
        self.assertGreaterEqual(total_scenarios, 52)

    def test_behavior_report_contains_all_scenarios_diagram_and_tables(self):
        self.assertTrue(REPORT_PATH.is_file(), "AI_INTERACTIONS_DEEP_DIVE.md must exist")
        content = REPORT_PATH.read_text(encoding="utf-8")
        report_ids = re.findall(r"### (REPORT-\d{2})\b", content)
        self.assertEqual(len(report_ids), 45)
        self.assertEqual(report_ids[0], "REPORT-01")
        self.assertEqual(report_ids[-1], "REPORT-45")
        self.assertIn("```mermaid\nsequenceDiagram", content)
        self.assertIn("## Coverage Gaps", content)
        self.assertIn("## Unknowns", content)


class OpenSpecExecutableBehaviorTests(unittest.TestCase):
    """Execute the behavioral scenarios specified in openspec/features/ against the real modules."""

    def test_validate_09_think_block_and_fences_stripped_before_json_parse(self):
        """@VALIDATE-09 & REPORT-36: <think> blocks, markdown fences, and control chars inside strings are repaired."""
        raw_reply = (
            "<think>\nLet me plan a high-density 2-shot sequence with sodium vapor light.\n"
            "Checking constraints: sealed mouths.\n</think>\n"
            "Here is your JSON payload:\n"
            "```json\n"
            "{\n"
            '  "segment_id": "seg000",\n'
            '  "style_opening": "Gritty 16mm halation with heavy grain.",\n'
            '  "style_retention": ["keep sodium glow", "keep harsh shadow"],\n'
            '  "summary": "A lone courier crosses a flooded basement\nand inspects a pneumatic dispatch tube.",\n'
            '  "shot_bodies": [\n'
            '    "In @Picture1, the courier steps through ankle-deep water\tunder flickering fluorescent tubes.",\n'
            '    "Close on gloved hands pulling a brass canister from the pneumatic valve as steam vents."\n'
            "  ],\n"
            '  "overall_soundscape": "low transformer hum and dripping water",\n'
            '  "music_tag": "@Music1"\n'
            "}\n"
            "```\n"
            "Hope this helps!"
        )
        cleaned = writer_json.escape_control_characters(raw_reply)
        parsed = WriterResponse.parse(cleaned, "seg000")
        self.assertEqual(parsed.segment_id, "seg000")
        self.assertEqual(len(parsed.shot_bodies), 2)
        self.assertIn("ankle-deep water", parsed.shot_bodies[0])

    def test_validate_08_truly_broken_non_json_still_triggers_free_retry_detection(self):
        """@VALIDATE-08 & REPORT-26: Unclosed/truncated non-JSON still raises ValidationError with BROKEN_JSON."""
        truncated = "<think>thinking...</think>\nI cannot fulfill this request without more details"
        cleaned = writer_json.escape_control_characters(truncated)
        with self.assertRaises(ValidationError) as ctx:
            WriterResponse.parse(cleaned, "seg000")
        self.assertTrue(writer_json.is_broken_json([str(ctx.exception)]))

    def test_validate_10_laya_style_adherence_feedback_advisory_and_strict_mode(self):
        """@VALIDATE-10 & REPORT-38: Laya style_adherence divergence yields advisory note by default and retry problem when strict."""
        divergent_response = {
            "answers": {
                "visual_density": {"expected": 4.2, "confidence": 0.85},
                "style_adherence": {"selected": "contradicts_style", "confidence": 0.80},
            }
        }
        advice_default, problems_default = writer_json.laya_style_feedback(divergent_response, strict=False)
        self.assertEqual(len(advice_default), 1)
        self.assertIn("contradict the style card (confidence 0.80)", advice_default[0])
        self.assertEqual(problems_default, [])

        advice_strict, problems_strict = writer_json.laya_style_feedback(divergent_response, strict=True)
        self.assertEqual(len(advice_strict), 1)
        self.assertEqual(len(problems_strict), 1)
        self.assertIn("judged to contradict the style card", problems_strict[0])

        aligned_response = {
            "answers": {
                "style_adherence": {"selected": "adherent", "confidence": 0.92},
            }
        }
        self.assertEqual(writer_json.laya_style_feedback(aligned_response, strict=True), ([], []))

    def test_world_02_03_precompiled_thematic_world_matrix_and_gaussian_dissonance(self):
        """@WORLD-02, @WORLD-03, @WORLD-04 & REPORT-37: Pre-compiled centroids & P15/P85 matrix drive Gaussian dissonance."""
        self.assertEqual(len(world_vectors.BUILTIN_WORLD_CENTROIDS), len(world_vectors.BUILTIN_THEMATIC_WORLDS))
        cal = world_vectors.BUILTIN_CALIBRATED_MATRIX
        self.assertGreater(cal["p85"], cal["p15"])
        self.assertEqual(cal["calibrated"]["Nocturnal Noir"]["Nocturnal Noir"], 0.0)

        # Low energy -> harmonic band (all base)
        low_seg = types.SimpleNamespace(
            energy=0.15,
            thematic_anchor=None,
            shots=[
                types.SimpleNamespace(
                    energy=0.15,
                    vocab={"setting": "alley", "lighting": "neon", "mechanism": "fan", "costume": "coat"},
                )
            ],
        )
        self.assertEqual(
            vocab_select.plan_gaussian_world_dissonance([low_seg], "Nocturnal Noir", seed=42, slider_percent=30.0),
            {},
        )

        # High energy -> surreal_clash / hot_bars departures while preserving thematic_anchor when present
        peak_seg = types.SimpleNamespace(
            energy=0.92,
            thematic_anchor="locked_mechanism_anchor",
            shots=[
                types.SimpleNamespace(
                    energy=0.95,
                    vocab={"setting": "alley", "lighting": "neon", "mechanism": "locked_mechanism_anchor", "costume": "coat"},
                )
            ],
        )
        departed = vocab_select.plan_gaussian_world_dissonance([peak_seg], "Nocturnal Noir", seed=42, slider_percent=85.0)
        self.assertIn((0, 0), departed)
        target_world, new_vocab = departed[(0, 0)]
        self.assertNotEqual(target_world, "Nocturnal Noir")
        self.assertEqual(new_vocab["mechanism"], "locked_mechanism_anchor")
        self.assertNotEqual(new_vocab["setting"], "alley")

    def test_takes_01_and_06_replan_segment_vocabulary_and_creative_world_steering(self):
        """@TAKES-01, @TAKES-06 & REPORT-39: Passage rewrite rolls fresh vocabulary and supports world_id + direction steering."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp))
            seg = Segment(
                index=0,
                song_start_frame=0,
                musical_frames=96,
                gen_frames=107,
                trim_frames=96,
                duration_input=4.0,
                montage_type=THEMATIC,
                section_index=0,
                section_label="verse",
                energy=0.65,
                thematic_anchor="initial_mechanism",
                ref_image_slots=1,
                footage_anchor="16mm",
                practical_effects="dust",
                rigging="rig",
                audio_slice_start_s=0.0,
                audio_slice_end_s=4.0,
                shots=[
                    Shot(
                        n=1,
                        start_frame=0,
                        frames=48,
                        cut_time=None,
                        camera="The camera pushes in slowly",
                        shot_scale="medium shot",
                        energy=0.6,
                        vocab={
                            "setting": "initial_setting",
                            "subject_type": "initial_subject",
                            "mechanism": "initial_mechanism",
                            "lighting": "initial_lighting",
                            "tonal_register": "initial_tone",
                            "costume": "initial_costume",
                        },
                    ),
                    Shot(
                        n=2,
                        start_frame=48,
                        frames=48,
                        cut_time="00:02.000",
                        camera="The camera holds a static shot",
                        shot_scale="close-up",
                        energy=0.7,
                        vocab={
                            "setting": "initial_setting_2",
                            "subject_type": "initial_subject",
                            "mechanism": "initial_mechanism",
                            "lighting": "initial_lighting",
                            "tonal_register": "initial_tone",
                            "costume": "initial_costume",
                        },
                    ),
                ],
            )
            request = {"seed": 100, "vocabulary_profile": "full", "vocab_selection": "contextual"}
            steered_seed = takes.replan_segment_vocabulary(
                store,
                request,
                [seg],
                0,
                seed=777,
                world_id="Cyberpunk / High-Tech",
                direction_note="saturated neon rain and optic cabling",
            )
            self.assertEqual(steered_seed, 777)
            cyber_pools = world_vectors.BUILTIN_THEMATIC_WORLDS["Cyberpunk / High-Tech"]
            for sh in seg.shots:
                self.assertIn(sh.vocab["setting"], cyber_pools["settings"])
                self.assertIn(sh.vocab["lighting"], cyber_pools["lighting"])
                self.assertIn(sh.vocab["costume"], cyber_pools["costume"])

    def test_a_valid_example_before_the_answer_is_not_taken_as_the_answer(self):
        example_then_truncated = 'For example {"shots": []} and my answer: {"shots": ["unfinished'
        self.assertEqual(writer_json.extract_json_object(example_then_truncated), example_then_truncated)
        self.assertEqual(writer_json.extract_json_object('<think>{x}</think> Here: {"a": 1} done.'), '{"a": 1}')

    def test_laya_never_answers_the_old_divergent_label(self):
        from mmv.engine.validators import laya_semantic
        source = Path(laya_semantic.__file__).read_text(encoding="utf-8")
        self.assertIn('"contradicts_style"', source)

    def test_unknown_steering_world_falls_back_to_default_vocabulary(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(takes.world_custom_vocabulary(Storage(temp), "no_such_world"), {})

    def test_validate_02_03_mondo_quality_and_sealed_lips_validation(self):
        """@VALIDATE-02, @VALIDATE-03 & REPORT-19..21: Sealed-lips rigging validation and Mondo motion/framing regex gates."""
        seg = Segment(
            index=0,
            song_start_frame=0,
            musical_frames=96,
            gen_frames=107,
            trim_frames=96,
            duration_input=4.0,
            montage_type=STANDARD,
            section_index=0,
            section_label="verse",
            energy=0.5,
            thematic_anchor=None,
            ref_image_slots=1,
            footage_anchor="16mm",
            practical_effects="dust",
            rigging="rig",
            audio_slice_start_s=0.0,
            audio_slice_end_s=4.0,
            shots=[
                Shot(
                    n=1,
                    start_frame=0,
                    frames=96,
                    cut_time=None,
                    camera="The camera holds a static shot",
                    shot_scale="wide shot",
                    energy=0.5,
                    vocab={},
                )
            ],
        )
        tags = get_backend("local_h3").ref_tags(1, 0, 1)
        resp = WriterResponse(
            segment_id="seg000",
            style_opening="High-contrast monochrome grain.",
            subject_definitions=["<Picture 1> is the lone courier."],
            summary="A figure stands in a concrete plaza as wind whips gravel across the floor.",
            retention_analysis=["<Picture 1>: identity and coat retained."],
            shot_bodies=[f"In <Picture 1>, the courier walks steadily across the plaza while wind whips fine gravel. {RIGGING_TAIL}"],
            overall_soundscape="wind and low rumble",
            non_diegetic_music="N/A",
        )
        assembled = assemble_prompt(seg, resp, tags)
        self.assertEqual(validate_prompt(assembled, seg, tags, strict_words=False, silent_mouths=True), [])
        self.assertEqual(quality.prompt_problems(assembled, seg, direction=""), [])

        # Static camera + motionless subject triggers Mondo motion gate
        static_bad = assembled.replace(
            "walks steadily across the plaza while wind whips fine gravel",
            "stands completely motionless in the room",
        )
        problems = quality.prompt_problems(static_bad, seg, direction="")
        self.assertTrue(any("holds a static camera" in p for p in problems))

    def test_render_04_vision_check_safe_shot_interior_sampling(self):
        """@GATE-04 & REPORT-29: sample_frames avoids cut boundaries (CUT_GUARD = 2) and samples shot interiors."""
        samples = vision_check.sample_frames(96, 96, [0, 48], budget=4)
        self.assertEqual(len(samples), 4)
        for frame_idx in samples:
            self.assertNotIn(frame_idx, (46, 47, 48, 49), f"Sampled frame {frame_idx} violated CUT_GUARD around cut 48")

    def test_story_03_storyboard_proportional_alignment_preserves_cuts(self):
        """@STORY-03 & REPORT-35: Storyboard panel alignment maps panels across shots without altering planned cut frames."""
        seg = Segment(
            index=0,
            song_start_frame=0,
            musical_frames=96,
            gen_frames=107,
            trim_frames=96,
            duration_input=4.0,
            montage_type=STANDARD,
            section_index=0,
            section_label="verse",
            energy=0.5,
            thematic_anchor=None,
            ref_image_slots=1,
            footage_anchor="16mm",
            practical_effects="dust",
            rigging="rig",
            audio_slice_start_s=0.0,
            audio_slice_end_s=4.0,
            shots=[
                Shot(n=1, start_frame=0, frames=48, cut_time=None, camera="static", shot_scale="wide", energy=0.5),
                Shot(n=2, start_frame=48, frames=48, cut_time="00:02.000", camera="push", shot_scale="close", energy=0.6),
            ],
        )
        board = {
            "enabled": True,
            "mode": "narrative",
            "panels": [
                {"image": "", "direction": "Wide establishing view of the salt pier in fog."},
                {"image": "", "direction": "Close-up on the rusted capstan winch turning."},
            ],
        }
        aligned = storyboard.align(board, [seg], fps=24, kind="video")
        ctx = storyboard.writer_context(aligned, "seg000")
        self.assertEqual(len(ctx["shots"]), 2)
        self.assertIn("salt pier", ctx["shots"][0]["direction"])
        self.assertIn("rusted capstan", ctx["shots"][1]["direction"])
        self.assertEqual([s.start_frame for s in seg.shots], [0, 48])

    def test_queue_01_and_02_free_vs_paid_fingerprint_hold_invariants(self):
        """@QUEUE-01, @QUEUE-02 & REPORT-40: A free plan needs no approval; a newly paid plan is held."""
        free = production_queue.new_ticket({"kind": "video", "backend": "local_h3"}, "Free Ticket", 1, estimate=0)
        self.assertIsNone(production_queue.hold_reason(free, [free], 0, "any-hash"))
        self.assertIn("never approved", production_queue.hold_reason(free, [free], 4.50, "new-plan"))

        paid = production_queue.new_ticket({"kind": "video", "backend": "wavespeed"}, "Paid Ticket", 2, estimate=4.50, fingerprint="sha-abc")
        self.assertEqual(paid["approved_fingerprint"], "sha-abc")
        # Same fingerprint -> runnable
        self.assertIsNone(production_queue.hold_reason(paid, [paid], 4.50, "sha-abc"))
        # Changed fingerprint -> held
        self.assertIn("inputs, settings or price changed", production_queue.hold_reason(paid, [paid], 4.50, "sha-diff"))
        # Unapproved paid ticket -> held
        unapproved = {**paid, "approved_fingerprint": None}
        self.assertIn("never approved", production_queue.hold_reason(unapproved, [unapproved], 4.50, "sha-abc"))

    def test_queue_03_prior_paid_failure_cascades_hold_onto_subsequent_tickets(self):
        """@QUEUE-03 & REPORT-42: A paid failure or interruption holds tickets created before the stop."""
        now = 1000.0
        approved = production_queue.new_ticket({"kind": "video"}, "Next Paid", 2, estimate=5.0, fingerprint="fp", now=now)
        prior_failed = production_queue.new_ticket({"kind": "video"}, "Old Paid", 1, estimate=5.0, fingerprint="fp", now=now - 50)
        for state in ("failed", "interrupted"):
            stopped = {**prior_failed, "state": state, "finished": now + 10.0}
            reason = production_queue.hold_reason(approved, [stopped, approved], 5.0, "fp")
            self.assertIn("earlier paid ticket did not finish", reason)

    def test_queue_04_waiting_ticket_swapping_and_running_protection(self):
        """@QUEUE-04 & REPORT-43: Waiting tickets swap; a running ticket cannot move or be removed."""
        t1 = production_queue.new_ticket({"kind": "video"}, "Ticket 1", 1)
        t2 = production_queue.new_ticket({"kind": "video"}, "Ticket 2", 2)
        swapped = production_queue.moved([t1, t2], t1["id"], 1)
        self.assertEqual({t["id"]: t["position"] for t in swapped}, {t1["id"]: 2, t2["id"]: 1})

        running = {**t1, "state": "running"}
        with self.assertRaises(ValueError):
            production_queue.moved([running, t2], running["id"], 1)
        with tempfile.TemporaryDirectory() as td:
            store = Storage(Path(td))
            production_queue.save_ticket(store, running)
            with self.assertRaises(ValueError):
                production_queue.remove_ticket(store, running["id"])

    def test_queue_05_and_06_crash_recovery_and_resumable_contract(self):
        """@QUEUE-05, @QUEUE-06 & REPORT-44, REPORT-45: Startup interrupts running tickets; a saved run ID can be requeued."""
        ticket = {**production_queue.new_ticket({"kind": "video", "backend": "local_h3"}, "Crash Test", 1), "state": "running", "run_id": "run-xyz"}
        with tempfile.TemporaryDirectory() as td:
            store = Storage(Path(td))
            production_queue.save_ticket(store, ticket)
            production_queue.recover_tickets(store, lambda kind: "Died with server crash")
            recovered = production_queue.get_ticket(store, ticket["id"])
            self.assertEqual(recovered["state"], "interrupted")
            self.assertTrue(production_queue.resumable(recovered))
            resumed = production_queue.resume_ticket(store, recovered)
            self.assertEqual(resumed["state"], "pending")
            self.assertEqual(resumed["resume_run"], "run-xyz")
            production_queue.save_ticket(store, {**recovered, "state": "interrupted"})
            production_queue.resume_interrupted(store)
            self.assertEqual(production_queue.get_ticket(store, ticket["id"])["resume_run"], "run-xyz")

    def test_queue_07_cancellation_pauses_queue_execution(self):
        """@QUEUE-07: Settling a cancelled operation pauses dispatch and leaves waiting tickets alone."""
        with tempfile.TemporaryDirectory() as td:
            store = Storage(Path(td))
            t = {**production_queue.new_ticket({"kind": "video"}, "Cancel Test", 1), "state": "running", "run_id": "run-abc"}
            waiting = production_queue.new_ticket({"kind": "video"}, "Next Test", 2)
            production_queue.save_ticket(store, t)
            production_queue.save_ticket(store, waiting)
            control = {"running": True, "dispatching": False, "prepare_lock": None}
            from mmv.jobs import Jobs
            jobs = Jobs(store)
            production_queue.settle_operation(store, jobs, control, {"id": "run-abc", "state": "cancelled", "message": "Cancelled by operator"})
            updated = production_queue.get_ticket(store, t["id"])
            self.assertEqual(updated["state"], "cancelled")
            self.assertFalse(control["running"], "Queue must pause upon operation cancellation")
            self.assertEqual(production_queue.get_ticket(store, waiting["id"]), waiting)


if __name__ == "__main__":
    unittest.main()
