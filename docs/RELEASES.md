# Releases

## 1.12.4 — Storyboard cleanup, more thematic Worlds, and measured code paths

Credit: [hellonearthis](https://github.com/hellonearthis) for fork revisions `f814ecf` and `2389f58`, reviewed at exact head `2389f58` with a bounded Claude Haiku 5.5 review.

- **Optional storyboard prose cleanup.** A checkbox cleans new vision interpretations, and **Humanize directions** cleans panels already in the editor. Both are off until chosen. The cleanup is local and free; interpretation still uses its existing quote and explicit start consent. GUI, `AgentClient`, CLI `humanize-storyboard`, MCP `humanize_storyboard`, and `POST /api/storyboards/humanize` use the same Python rules. Review the text before applying it to a production.
- **Eight additional thematic World cards** are available in the browser library. Agents can inspect their terms through `inspect_studio(kind="thematic-worlds")` or CLI `thematic-worlds`, then preview chosen `custom_vocabulary` overrides. No World is applied automatically.
- **Performance pass.** Reused regular expressions, reduced repeated JS array copies, cached static World scoring data, and vectorized World centroid and distance calculations. The measured results and test scope are in [verification](https://github.com/hodgemann/mondo-music-video/blob/main/docs/VERIFICATION.md).
- **Lipsync helper optimization.** The fork's precompiled word and clause patterns and `str.translate` punctuation masking are included. The owner clarified that these later helper mechanics are outside the original protected core. The singing wording, sealed-lips rules and protection pins are unchanged; differential checks matched the prior helper outputs. The measured speed difference on a small synthetic corpus was modest and is recorded in [verification](https://github.com/hodgemann/mondo-music-video/blob/main/docs/VERIFICATION.md).
- **Direction guide.** Added a concise cognitive pacing and physical-action section adapted from the fork's longer guide.

Integration fixes: the fork's prose rule could delete a following sealed-lips instruction and produced broken grammar for some phrases; the local action now keeps a following clause and conjugates its replacements. The new browser action uses the same API as agents. The fork's ambiguous `replan_segment_vocabulary` overload remains omitted because it can select a passage by seed, and its `divergent` Laya label remains omitted because the declared validator answer is `contradicts_style`. The fork's expanded storyboard architecture document was adapted instead of copied because it contains machine-specific links and claims beyond the verified workflow. No paid or GPU call was made for this integration.

## 1.12.3 — Narrative acts, recovery buttons, optional H3 tag binding

Integrates hellonearthis's fork revisions `5c5b5b6`, `5cae552`, `9853212` (fork versions 1.12.3–1.12.5) and the documentation commits `20e62ee`, `0d29dcb`. Credit: hellonearthis.

- **Narrative acts.** A visual vocabulary preset can carry acts (for example Act I, II, III) with their own settings, lighting, mechanisms, costumes, tonal registers and subject types. Each passage draws from the act its midpoint falls in, with optional custom spans or equal parts. Held setting, costume and subject type stay held within a passage; a thematic anchor stays. Presets without acts behave exactly as before. The selector badges presets with their act count, and `examples/vocabulary-presets/the_great_escape.json` is a three-act example. Saving a preset from the GUI no longer drops its acts.
- **Dismiss and Purge & Start Fresh.** A failed, cancelled or interrupted operation can be dismissed back to ready, or purged with an optional log clear. Purging removes only a draft run with no finished output, assembly source or renderer work; anything else is kept and the banner still resets. An active operation is never reset. Agents: `reset_operation` (MCP), `reset-operation [--purge-run] [--clear-log]` (CLI), `AgentClient.reset_operation`; the MCP server now has 76 tools.
- **Optional H3 tag binding (adapted).** The fork's normalizer is a Settings switch, `h3_tag_normalizer`, **off by default**. When on, local H3 and Comfy-SDK H3 renders tie each cast member's `<Picture N>` to their `<Subject N>` and replace the member's name in shot descriptions with the Subject tag. Plain colour words are never treated as names, longer names win across actors, and a definition that already names a picture is left alone. Off, the job and its Comfy fingerprint are unchanged, so earlier submitted passages still resume. The prompt as written and checked is still what is saved.
- **Studio direction guide.** Character consistency, reference policy, the two seeds and other production tips from the fork (`docs/STUDIO_DIRECTION_PROMPTING.md`).
- The fork's `vocab-worlds.js` brace fix was already present here. The protected prompting scheme is untouched.

## 1.12.2 — OAP 0.5 actors

- **The public actor collection works again.** Actors & Props now reads the OAP 0.5 packages in the public collection. A future protocol version in the index no longer stops the list loading; each package is checked when you select it.
- **Older actors keep working.** The four bundled starters and actors you already imported stay as they are, and OAP 0.2 and 0.3 packages still import. Existing role agreements keep their original signatures.
- **Sealed packages.** An actor sealed to this studio now imports. **Show this studio's recipient key** gives you the public key to send the Agent (CLI `oap-recipient-key`, MCP `oap_recipient_key`). The decrypted reference is stored in the actor's folder like any other, because renderers need it.
- **Exports use OAP 0.5.** A full export still carries a plain reference readable by whoever receives the file, and is now an OAP 0.5 portfolio package. Audition packages no longer list a hash for a left-out cast-only reference. Exporting a sealed package is not offered yet.
- **Revocation and attestations.** Revocation lists inside a package are checked, and a revoked signer is refused. MMV does not use attestations yet, so it does not check them and they do not block an actor.
- **Guide updated.** The OAP guide now explains sealed packages and revocation, and that a full export's reference is not encrypted.
- Now built on OAP 0.5.0, which adds PyNaCl as a dependency.

## 1.12.1 — Steer a new prompt; clearer Styles; stems wait for the GPU

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commit `4d4fb16`, reviewed at exact head `aa1e06b`.

- **Steer Write new prompt.** A music video passage's **Write new prompt** can now take a Thematic World or your own saved World, and a creative note for that passage (GUI, CLI `--world` and `--direction`, MCP `rewrite_prompt`). Leaving them empty changes nothing. An unknown World simply uses the default vocabulary.
- **Reasoning models parse better.** Writer replies wrapped in `<think>` blocks, code fences or commentary now yield their JSON. A reply with more than one object still counts as broken, so an example can never pass as the answer.
- **Laya's style verdict is visible.** A high-confidence "contradicts style" answer is recorded as advice on the passage. With `strict_prompt_checks` on, it sends the prompt back for a rewrite. The default run still accepts the prompt.
- **Faster World contrast.** Built-in Thematic World distances are worked out once at startup.
- **OpenSpec documentation.** `openspec/` adds a glossary, nine Gherkin feature specifications and a behaviour report. `tests/test_openspec_bdd.py` checks their structure and a few real functions; it does not execute the feature steps or the GUI workflows.
- **Stem work waits its turn.** A preview needing new stem separation during a render now waits for the free GPU, then runs ahead of the next queued ticket. An unknown steering World uses the default vocabulary.
- **Styles are easy to scroll.** Each Styles card now shows its style card without its redundant title line, with the full style text behind a **Full style text** fold that opens and closes. The harvest result panel matches. The fold did nothing when clicked before; that is fixed.
- **Fuller preset cards.** The six public presets now have complete eleven-axis style cards, like Daylight Cinema. Laya and the ident writer read these cards, so results with these presets may differ. An existing installation keeps its current copies. An interrupted production using one of these presets resumes only with its original card in place.

Integration fixes: a syntax error in `vocab-worlds.js` that stopped the page loading was dropped; the style check looked for an answer Laya never gives; a first balanced object could replace a truncated real answer; steering appeared on idents, which cannot use it; the GUI listed only built-in Worlds; unused `Jobs.reset` was omitted. Tested on mock services only, with no real before/after renders. No pinned prompt or validator file changed; the steered note and the strict-mode style retry do change writer input or prompt acceptance when used.

## 1.12.0 — The production queue

- **New Queue tab (08).** Preview a music video or ident, choose **Add to queue**, and line up as many as you like, even while something is rendering. **Start queue** runs them one at a time, as whole productions. Reorder, remove, pause after the current one, or clear finished. Finished Videos is now tab 09 and Settings tab 10.
- **Local work just runs.** A free ticket needs no acceptance tick and uses your settings of the moment.
- **Paid work keeps its safeguards.** A priced ticket needs acceptance of its estimate and runs only on that exact plan. If the plan changes, a free ticket becomes priced, or an earlier paid ticket stops after this one was approved, it is held and spends nothing. Paid work never retries itself; **Queue again** shows the full plan for a fresh decision.
- **Stopped work resumes.** After a crash or restart the queue waits to be started, then **Start queue** continues interrupted local tickets in their own production folders, keeping their prompts and finished clips. Failed, cancelled or held local tickets have a **Resume** button. A ticket that stopped before its prompts were finished starts over with written prompts from cache, and is held instead if that could charge a paid writer again. Changed inputs or settings hold a resume until they are restored.
- **Failures and Cancel.** A failed ticket is reported and the queue moves on. Cancel stops the current ticket and pauses the queue.
- Previews and song/reference uploads now work during an operation. If a preview needs new stem separation, that work waits until the GPU is free, then runs ahead of the next queued ticket.
- Agent parity: 9 new MCP tools (`read_queue`, `queue_production`, `start_queue`, `pause_queue`, `move_queue_ticket`, `preview_queue_ticket`, `resume_queue_ticket`, `remove_queue_ticket`, `clear_finished_queue_tickets`) and matching CLI commands.

Tested on mock services and in Chromium only: no real GPU or paid queue run yet, and Firefox has not been checked. On `local_h3`, a resume can re-render a clip whose automatic quality retry had already finished; the same applies to the existing Resume. No protected prompts or private assets changed.

## 1.11.7 — OpenSpec BDD suite, `<think>`-resilient writer parsing, Laya style adherence feedback, pre-compiled World matrices, and creative rewrite steering

- **Resilient JSON extraction and `<think>` stripping.** `escape_control_characters` (`mmv/writer_json.py`) now strips `<think>...</think>` reasoning blocks, markdown code fences, and conversational wrappers to isolate the outermost balanced `{...}` JSON payload before `WriterResponse.parse`, preventing reasoning-enabled models from wasting retry budgets while keeping `is_broken_json` free-retry detection intact for genuinely truncated replies.
- **Pre-compiled Thematic World centroids and distance matrix.** `mmv/world_vectors.py` now pre-computes `BUILTIN_WORLD_CENTROIDS` and `BUILTIN_CALIBRATED_MATRIX` once at import, avoiding repeated lexical embedding and P15/P85 percentile calibration inside `plan_gaussian_world_dissonance` (`mmv/vocab_select.py`).
- **Laya `style_adherence` feedback.** Without modifying the protected Laya validator, `mmv/worker.py` now inspects `style_adherence` via `laya_style_feedback`: high-confidence style divergence (`selected == "divergent"`, `confidence >= 0.65`) is recorded as an advisory note in `segNNN.advice.json` by default, and escalated to a corrective writer retry problem when `strict_prompt_checks` is enabled.
- **Creative steering on passage prompt rewrite.** Passage prompt rewrites (`POST /api/outputs/{run_id}/prompts/{segment_id}/rewrite`, CLI `rewrite-prompt --world --direction`, MCP `rewrite_prompt`, and the Edit view's **🧭 Optional rewrite steering** controls) now accept optional `world_id` and `direction` steering to override that passage's vocabulary pools with a chosen Thematic World or studio World and inject a passage-specific creative note.
- **OpenSpec & Cucumber BDD specification and test suite.** Added `openspec/glossary.yaml`, 9 Gherkin `.feature` specifications under `openspec/features/`, the `openspec/reports/AI_INTERACTIONS_DEEP_DIVE.md` behavioral report, and executable verification in `tests/test_openspec_bdd.py`.

No protected prompts, private assets, paid operations or automatic retries changed.

## 1.11.6 — Write new prompt rolls a fresh setting and motif

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commit `ae61fb5`, reviewed at exact head `ffb3c50`.

- **A new prompt can now be a new scene.** In a finished video's Edit view, **Write new prompt** draws a fresh setting and motif for that passage from the production's vocabulary pool, then runs the writer, Mondo checks and Laya as before. Musical timing, cuts, cast and rigging stay. A very small pool or a world's own terms can repeat a term.
- **Prompt versions keep their vocabulary.** Each version stores the vocabulary it was written from, and a written one its variation seed; choosing an older version brings its vocabulary back with it.
- Optional `seed` on the rewrite API, CLI (`--seed`) and MCP `rewrite_prompt`. Idents have no planned vocabulary, so their rewrite still changes only the text.

The owner chose this as the behaviour of Write new prompt after the prompting-scheme warning. No pinned prompt or planning file changed. It has been tested on mock services only: no real before/after renders were compared. No private assets, paid operations or automatic retries changed.

## 1.11.5 — Thematic Worlds keeps your choices; panels stay open when you open them

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commits `60bc3fc` and `7681740`, reviewed at exact head `7681740`.

- **Pool countdown.** Each Thematic Worlds pool now counts down what it still needs as terms are pinned (*14 in pool, 7 needed (2/9 selected)*), and excluded terms leave the pool count.
- **Term choices are kept.** Pinned, included and excluded states were only on the page: adding a term, switching a world or any redraw reset every chip. They are now part of the pools, saved with Apply and restored with the draft.
- **Added terms count.** A term added by hand or from the catalogue starts Pinned. Before, it was only Included, which Guided mode does not send, so it had no effect.
- **The worlds you applied come back.** Apply saved the active worlds, but reopening the workspace showed the default selection, and applying again replaced yours. The applied world list is now restored (older drafts rebuild it from their saved active names).
- **A panel you reopen stays open.** With auto-collapse on, a completed Music Video card that you opened again closed itself as soon as focus left it; it now stays open until you close it.
- Storyboard, tooltip and scoring code was rewritten as small pure functions with the same behaviour.
- In the Edit view, **🎲 Reroll Clip** is now **🎬 Render Clip** (the slate matches Re-encode Final Video), in a lighter shade of the app's teal action colour (both themes, with hover and keyboard-focus states) so the step that renders a new take stands out; its place is unchanged. The agent action keeps its name, `reroll_segment`.
- Sidebar tab 03 is now **Actors & Props** (was Actors & OAP): it holds both the actor cast and the Open Prop Protocol prop library. Agent actions are unchanged.
- The header badge now reads just **OAP** and the supported version (was OAP BUILT IN), and an **OPP** badge with the supported Open Prop Protocol version sits under it, opening the OPP guide. Stacked, they keep the header as narrow as before on phones.

Integration fixes (Claude Code and Codex review): the term chips' hover help and state labels, dropped in the fork, are restored; the world selection was still not restored after the fork (fixed as above); a pool that becomes short when terms are excluded now gets its **Borrow from nearest world** button at once. Agents are unaffected: Thematic Worlds is a browser draft, and agents send `custom_vocabulary` with a preview as before. See [collaborator review](COLLABORATOR_REVIEW.md).

No protected prompts, private assets, paid operations or automatic retries changed.

## 1.11.4 — Cancellable re-encodes and tidy recovery after a crash

- **Cancel stops a re-encode.** Re-encoding a final video from chosen takes ran FFmpeg directly, so Cancel only raised a flag and the encode ran to the end. Each encode (clean, flashed, captioned) now runs through the operation like a production's own commands, and Cancel stops it. The finished video is replaced only by a complete, frame-checked encode, so a cancelled re-encode leaves it as it was; if Cancel lands after the new clean version was built, that version is recorded as clean (no flashes or captions claimed) with a note.
- **Leftover encode folders are removed.** If the app or computer stops mid-encode, the half-written work folder (`assembly-…`, `subliminal-…`, `captions-…`) stayed in the production folder. The app now removes such folders when it starts, before any operation can run, and notes each in the studio log.
- **A fitting message after an interruption.** An operation that only works on this computer (re-encode, captions, export, prompt check, stem model) now says that nothing finished was replaced and it can be started again, instead of asking to check remote request IDs, which remains for renders and other remote work.

Investigated, owner's report: a Windows crash (bugcheck 0x154, `UNEXPECTED_STORE_EXCEPTION`, in Windows' memory store) about a minute into a re-encode. The encode was the same FFmpeg graph that built earlier versions that day, with no frame-buffering filter; no application defect explaining a host crash was found (Codex reviewed read-only). Encoder threads stay uncapped by the owner's choice, so many-core CPUs keep their speed.

No protected prompts, private assets, paid operations or automatic retries changed.

## 1.11.3 — The Edit view keeps itself up to date

- Fixed: a take rendered (or a prompt written) while you had left and reopened the Edit view did not appear until a hard browser refresh. The reopened view had read the passages before the operation finished, and only the view that started it was updated. Now, whenever an operation finishes, an open Edit view reads its video's passages, takes, prompt versions and final versions again, keeping your place on the page.
- **↻ Refresh** beside Back re-reads the open video at any time.

Agents are unaffected: `read_output_prompts` always reads the current state. No protected prompts, private assets, paid operations or automatic retries changed.

## 1.11.2 — Edit view clips play in Firefox

- Fixed: in Firefox, the Edit view's passage clips showed no picture and spun forever when played (Chromium browsers played them). The clip route sent them as a download (`Content-Disposition: attachment`), which Firefox will not play in a video player; they are now sent `inline`, keeping the file name for saving. This affected the passage clips since 1.10.26.
- Opening Edit now lets the hidden gallery's players release their downloads of finished videos, and passage clips load two at a time, as the gallery's thumbnails do since 1.10.12, so a long-open tab does not run out of connections to the app. Back restores the gallery.
- Agents: the GUI must work in Firefox as well as Chromium browsers (AGENTS.md).

No protected prompts, private assets, paid operations or automatic retries changed.

## 1.11.1 — Your own seeds, and passage prompt versions

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commit `c36c89f` (prompt editing, prompt reroll and version history), reviewed at exact head `c36c89f`.

- **A random render seed for every video.** One seed used to do two jobs: the Variation seed (0 by default) chose the shot plan, vocabulary and casting, and every video also rendered its passages with that seed + passage number, so every video rendered with seeds 0, 1, 2… The renderer now has its own **render seed**: empty by default, a fresh random one is picked at preview, shown, and kept by the production for start, resume and export (type one, or press **Random** to empty the field). The Variation seed is unchanged, so the same song and variation seed still plan the same passages and reuse their checked prompts. Agents that omit `render_seed` get the same behaviour; the quote returns `seed` and `render_seed`. Productions made earlier keep rendering (and resuming) with their variation seed.
- **Prompts & clips is now Edit.** The finished-video button that opens the passage view is called **Edit**, since the view now edits prompts, clip takes, seeds and the final video.
- **Seeds for clip rerolls.** The Edit view shows the seed of the take you are previewing, and **Next seed** holds the seed for the next take: a fresh random one, or one you type. The same prompt with a new seed is often all a passage needs. Take 1 now reports the seed that actually rendered it (1.11.0 showed 42 + passage number for productions with seed 0, and missed seeds from a kept quality retry).
- **Prompt versions.** Each passage's prompt has versions. **✍️ Write new prompt** has the writer write a new one; **✏️ Edit prompt** lets you change the text and **Check and use** it. Both go through the same writer, Mondo checks and Laya review as a production, so a hand edit can never skip the sealed-lips or quality checks: an edit that does not pass is kept, marked, for another try, but is never used. **Use this version** returns to any passed version, including the original. Reroll the clip to render the prompt in use.

- **Prompt length follows the chosen model.** The Seedance rate card now records each model's real prompt ceiling (Seedance 2: 10,000 characters; Seedance 2.5: 30,000; owner-supplied). The prompt checks ask the production's renderer for its `max_prompt_chars` and send an over-long prompt back to the writer (or refuse an over-long hand edit) before anything is submitted, so nothing is charged. No number is written into the checks: a renderer that reports no ceiling, such as H3, has none, and a changed limit is a rate-card edit. The Edit view shows each prompt's length against its renderer's ceiling. Earlier, nothing checked this: 5 of 159 prompts in the owner's productions exceed 10,000 characters and would have been refused by Seedance 2 after submission. The rate card is part of the protected scheme; this change was approved by its owner.
- **View log during a reroll or prompt rewrite** now shows ComfyUI's and the writer's output as it happens; their logs are written to that operation's folder instead of the original production's.

Agent parity: `rewrite_prompt` (`confirm`, `accept_writer_cost` for an API writer), `edit_prompt` (`confirm`), `select_prompt_take` (MCP, 65 tools), matching `AgentClient` methods and CLI `rewrite-prompt`, `edit-prompt`, `select-prompt-take`; `read_output_prompts` adds `prompt_takes`, `active_prompt_take`, `prompt_blocked` and `writer_charge`; `reroll_segment` documents its optional `seed`; `preview_production` documents the random default seed.

Integration decisions (protected prompting scheme, owner-approved opt-in approach): the fork's prompt reroll was a ~300-line copy of the worker's writer loop and added a new writer instruction ("Write a fresh, distinct variation…"); both were left out. Instead `mmv/worker.run` gained a `rewrite` option that runs its own prompt stage for one passage and stops before rendering, so rewritten and checked prompts can never drift from production prompts. The fork's manual edit saved text with no checks; edits are now checked by the same stage, with Laya. An API writer now needs explicit acceptance of its per-passage estimate. Reading prompts writes nothing; the passage's earlier writer/review files are moved aside instead of being overwritten; the prompt cache is neither read nor overwritten by a rewrite; a prompt-plan binding failure is reported instead of ignored. `protected_scheme.check()` stays `[]`: no pinned file, rule text or composed system prompt changed. See [collaborator review](COLLABORATOR_REVIEW.md).

Not yet verified on real renders: a rewritten or edited prompt rendered with the same song and seed against the original, as the protection guide requires before calling prompt work done. No paid operations or automatic retries were added.

## 1.11.0 — Passage takes: reroll one clip, choose, re-encode

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commits `8356eb2`, `355cc26` and `7367470`, reviewed at exact head `7367470`.

- **Prompts & clips is a full view** inside Finished Videos (Back returns to the gallery), with the prompt on the left, the clip on the right and each prompt's character count above it.
- **Passage takes.** A finished local H3 production can render a new take of one passage (🎲 Reroll Clip, after a confirmation, local GPU only) using that passage's saved validated prompt, cast and instrument references and the production's own saved settings. The original clip is Take 1. Each passage's dropdown previews its takes.
- **Re-encode the final video** with the chosen take for each passage. It is assembled once from the original renderer clips, with subliminal flashes and burned captions reapplied inside that encode as in the first production. The first re-encode keeps the original as `music-video-v1.mp4`, each version is saved as `-vN.mp4`, and the Final Video Version menu downloads any of them.

Agent parity: `reroll_segment` (needs `confirm=true`), `select_segment_take` and `reassemble_output` (MCP, 62 tools), the matching `AgentClient` methods and CLI `reroll-segment … --confirm`, `select-segment-take`, `reassemble-output`; `read_output_prompts` adds `takes`, `active_take`, `final_takes` and `reroll_blocked`.

Integration fixes (Claude Code and Codex review): reroll is refused for every renderer except `local_h3`, because the Comfy SDK and cloud renderers can submit paid jobs and reroll has no preview or consent step; reroll needs explicit confirmation in the GUI and `confirm=true` through the API; it replays the production's saved settings instead of today's; each take keeps its own render graph and request receipt, so the original run's `render-graph.json` and `local-request.json` stay as recovery records; choosing a take restores that take's whole render record; opening Prompts & clips no longer writes `takes.json` or `final_takes.json`; the take dropdown only previews, and the choices are saved by the re-encode; take choices in a re-encode are checked together and saved only after the new video is assembled, so a refused or failed re-encode changes nothing, and a re-encode is refused when the original finished video is missing (so Version 1 is always the original); a subliminal or caption failure during a re-encode is reported in the notice and on the output (`reassembly_warnings`) instead of being hidden. The older `Jobs.reset` and duplicate harvest-card call carried by the fork's merge remain out of scope (unused / already covered after reload). See [collaborator review](COLLABORATOR_REVIEW.md).

Limitations: a reroll skips the vision quality check and its automatic retry; productions on renderers other than `local_h3` cannot reroll yet. No protected prompts, private assets, paid operations or automatic retries changed.

## 1.10.28 — Nothing else in memory while ComfyUI renders; resume keeps finished passages

- Fixed: a resumed local production rendered every passage again, discarding finished clips (they were moved aside, not deleted). Resume now keeps each passage whose original clip is still on disk with at least its planned frames, logs "already rendered; keeping it", and renders only the rest. Missing or short clips are rendered again.
- Fixed: after prompt review, Laya's freed CPU memory stayed reserved by the Mondo worker for the whole render. The worker now hands it back to the system before ComfyUI starts, and the operation log records "Mondo worker memory before rendering". A 0.9 MP, 20-step H3 run with the bf16 model and text encoder needs almost all of a 98 GB machine's RAM in ComfyUI (93.4 GB at the end of a 345-frame passage), so even a few hundred megabytes held elsewhere can get ComfyUI killed.

No protected prompts, private assets, paid operations or automatic retries changed.

## 1.10.27 — The H3 model picker brings the model's own workflow

Fixed: choosing the 20-step H3 model (`minimax_h3_ref2va_pruned_bf16`) in Settings while a FastH3 workflow was selected swapped only the filename into FastH3's graph, so the full model rendered with FastH3's 8 sampler steps. A bundled diffusion model now brings its own bundled workflow and step count whenever they differ from the saved workflow (in both directions), keeping the other chosen models such as the text encoder. A custom workflow whose step count already matches is unchanged. Settings shows the saved workflow's sampler steps, and `inspect_studio("settings")` reports them as `workflow_steps`; agents' `update_studio_settings` with `h3_models` follows the same rule.

No protected prompts, private assets, paid operations or automatic retries changed.

## 1.10.26 — Vision guide, harvest result and passage prompts

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commits `9fb0aac`, `b00add2`, `4560bfc`, `e4f747b` and `bdd6973`, reviewed at exact head `bdd6973221af51932549eb8ee743429e69368e06`.

- **Vision guide.** Style Harvest has a guide button, and the Vision and Quality Vision service cards open it too (click, Enter or Space). It explains that Style Harvest uses the Vision endpoint in Settings, while the Quality Vision frame checker is started from the writer launch with a sibling mmproj. Served by `GET /api/vision/guide` and installed with the package.
- **Harvest result.** When a style harvest finishes (and again after a page reload, until dismissed), Style Harvest shows the new style's name, visual language and 11-axis card, with View in Styles Library, Copy Style JSON and Dismiss (`GET /api/styles/{id}`). Vision models that return the card or directives as JSON objects or lists are stored as text instead of failing.
- **Prompts & clips.** Each finished output card has a **Prompts & clips** button listing every passage's written prompt (copyable), its length after trimming and, while it is still on disk, the renderer's original clip. A captioned copy shows the passages of the video it was made from.
- **Reference images** are removed with their visible Remove button; the right-click menu is gone.
- **Style cards** use the full width of the Styles list.
- ID fields (actor, style, harvest, agreement, world, vocabulary preset) accept their documented letters, digits, `_` and `-` again in current browsers, which had rejected the old `pattern` as invalid.

Agent parity: `inspect_studio(kind="vision-guide")` / CLI `vision-guide`; `read_output_prompts` (MCP, 59 tools), `AgentClient.output_prompts` and CLI `output-prompts OUTPUT_FILE`, with absolute clip URLs. The harvest result is already available through `inspect_studio(kind="styles")`.

Integration fixes: the clip route serves only the video file recorded for that passage in the run's own `renders.json` (`.mp4`, `.mov`, `.webm`) and only from the data folder or the configured ComfyUI output folder, and the clip-available flag uses the same rule; captioned copies follow their `source` to the original run; the guide no longer implies paid renderers are retried automatically; the passage length is trimmed frames ÷ fps, not the renderer's input duration; the guide names Settings as tab 09; the guide is added to installed package data; the Copy Prompt button uses the shared clipboard helper; the duplicate harvest coercion became one `harvest_text` helper. See [collaborator review](COLLABORATOR_REVIEW.md).

No protected prompts (`parse_harvest_response` is unchanged), private assets, paid operations, automatic retries or GPU work changed.

## 1.10.25 — Actor and style library presentation

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commits `9ed0aac`, `84763ab`, `fe7bfe3` and `d376164`, reviewed at exact head `d376164fb86d6694b6453689bc330272b5fe498f`. Reference-image tooltips now separate the name, thumbnail and removal hint. The Actors & OAP creation, package-import and role-agreement cards have independent fold controls. A newly selected actor portrait appears before creation, local actor cards show the visual-description length, and styles with an 11-axis card have a clearer expandable view.

Integration fixes: the selected filename is inserted as text instead of HTML; section headings remain headings with their toggle buttons inside; the fold initialization is safe to repeat; the existing style-action handler is reused; the first style is not arbitrarily stretched across the grid; and tooltip guidance includes the visible Remove action. The new fold state and portrait preview are browser presentation only. Agent actor/OAP/agreement operations and style inspection/export already expose the underlying actions and results; no new agent action or paid consent path is introduced. Existing model, renderer, OAP trust and production defaults are unchanged. See [collaborator review](COLLABORATOR_REVIEW.md).

No private assets, protected prompts, automatic paid retries or GPU work changed.

## 1.10.24 — Reference controls and visual cues

Credit: [hellonearthis](https://github.com/hellonearthis) for fork commits `132074d` and `7047aa3`, reviewed at exact head `7047aa3dfb95c16f9cdcfd20cc096a93f37b2763`. Individual uploaded reference images can be removed with a right-click menu or a visible Remove button. The Music Video form highlights missing required fields and explains each Needs cue. The dark theme uses the fork's blue and gold palette; instrument performance has a clearer tooltip. The reference removal also refreshes form progress immediately, and keyboard/touch access uses the visible button. Agent preview requests already accept an explicit reference list, so agents can make the same selection before requesting a quote; confirmation and paid-start rules are unchanged.

No protected prompting, renderer, default model, automatic retry, private asset, or paid-consent behavior changed. See [collaborator review](COLLABORATOR_REVIEW.md) for the integration decisions.

## 1.10.23 — World editor

- New: **Edit** next to Open on each world's row, and at the top and bottom of an opened world. Names, rules, lists, subjects and vocabulary pools can be changed or removed in place. The pools reuse the Visual Vocabulary editor's tabs, standard-term checkboxes and `vocab-model.js` draft logic (a world's pools are a custom vocabulary: its own terms plus kept-out terms). Changes are previewed field by field before **Save as new version** is enabled, and any further edit requires a new preview. Saving writes the next version, keeps the world's sources and earlier versions, and is refused when the world changed after the editor was opened or nothing changed.
- Agent parity: `PUT /api/worlds/{id}` and `POST /api/worlds/{id}/edit-preview`, `AgentClient.preview_world_edit` / `edit_world`, CLI `world-edit-preview` / `edit-world`, MCP `preview_world_edit` / `edit_world` (58 tools), the project skill reference and agent setup guide. Saving through the agent requires `confirm` after the user has reviewed the previewed changes, like accepting a proposal; `rollback_world` is the recovery path.
- Changed text: the Visual Vocabulary "Add custom entries" suggestion no longer includes "neon" ("abandoned bowling alley").
- No protected prompts, private assets, paid operations or automatic retries changed.

## 1.10.22 — Growing a world adds what the new material says

Fixed: growing a world could report "No changes to the world" although new lore was supplied. The grow prompt asked the vision model to return the complete updated ledger, and a local model simply copied the ledger back (2,499 output tokens, every entry word for word, in a real run with five new backstories and a finished video). Growth now asks only for additions and merges them in code (`worlds.grow`): new entries are appended without case-sensitive duplicates, an existing subject's non-empty canon line replaces its old one, pools are unioned, and the world's name and seed sentence are kept unless the reply gives a new seed sentence. An echoed or empty reply still adds nothing, but the proposal now says why and offers Dismiss instead of Accept. Growth no longer removes entries; there is no in-place world editor, so dropping one means saving a hand-edited copy as a new world (a limitation, recorded here). The REST, client, CLI and MCP proposal results are unchanged (`changes` is simply empty when nothing is new). This touches only the Worlds module's own prompt, not the protected writer, ident or sealed-lips scheme.

Validation: full temporary-data/mock-service suite, 772 passed + 141 subtests; the owner then grew their Fehenviz world from five new backstories and a finished video and confirmed that it added entries. No protected prompts, private assets, paid operations or automatic retries changed.

## 1.10.21 — hellonearthis's actor and prop UI, with music-video panel progress

Credit: [hellonearthis](https://github.com/hellonearthis) for fork revision `1e0978748cbb3f9f23575a1e7c49bba19dd4708b` (one commit after reviewed `db7bec7`). The actor cards have a wider responsive grid and an inline description editor for locally created actors; the OPP library has a readable in-app guide, and dark-theme text selection has better contrast. The fork's malformed actor textarea was repaired. Imported signed OAP actors are deliberately read-only in this editor, because their original package is preserved on export. Agents can edit local descriptions through API, CLI and MCP; OPP guide text is available by inspection.

Music Video cards and Director folds now show input progress in their headers. Required inputs shade toward the existing GO! green; completion is labelled **Done** and collapses after the last required field loses focus. The Settings switch, on by default, can stop auto-collapse. Optional panels tint faintly as choices change and show **Reviewed** after a manual close. A collapsed complete card offers **Options available** to show unchanged optional groups; its header opens the whole card. Drafts save open, reviewed and partial states. A completed-input cue never replaces the preview quote, renderer checks or explicit paid consent. No protected prompts, private assets, paid operations or automatic retries changed.

Actors & OAP now has an on-demand public collection check. It lists missing actors, stages one selected package with index checksum, package hash and OAP signature verification, then presents the existing manifest/rider and explicit signer-acceptance import. Installed actors are preserved. REST, client, CLI and MCP expose the same check, stage, inspect and import sequence (56 MCP tools). The original four starter packages remain OAP v0.2; the five newer public collection packages are OAP v0.3 and are not automatically installed by this button.

Also fixed in this release: the Outputs list showed blank players until you pressed play. Release 1.10.12 stopped videos preloading to keep the browser's connections free for uploads and autosave, which also removed the first-frame thumbnail. Thumbnails now load two at a time: each video asks for its first frame, and the next starts once the browser stops fetching (or after 5 seconds), so the connection pile-up behind the Firefox upload stall cannot return. GUI only; no agent-interface change.

The header tagline now reads "FILMED IN MACHINE COLOUR" (it was "A LITTLE STUDIO. A BIG PICTURE.").

See [collaborator review](COLLABORATOR_REVIEW.md) for the exact fork assessment and adaptations.

## 1.10.20 — Fork UI polish (hellonearthis 1.10.15–1.10.20)

Credit: hellonearthis. Reviewed fork head `db7bec7` (six commits after `26719de`); UI and documentation only, no backend or protected-scheme change.

- Visual direction tooltip, track-receipt markers and Start fresh tooltip wording (1.10.15).
- Visual Vocabulary: the pseudo-random seed toolbars, saved-key actions and per-category re-roll are retired; summary cards keep chip removal and counts (1.10.16). Saved selections still restore, and `vocab_random_key` stays in the project API for old drafts, but keys can no longer be re-applied from the GUI.
- Dedicated **Video format & output** fold (aspect, megapixels, renderer, resolution), open by default (1.10.17).
- Cast is a checkbox list with portrait hover previews and a one-line guidance strip (1.10.18); reference images are a file list with thumbnail tooltips (1.10.19); vocabulary button layout and chip tooltip fixes (1.10.20).
- Our fixes while integrating: Quick Start and Start fresh now sync the cast checkboxes with the hidden actor select (previously the page could show a cast different from the one previewed); drafts saved before the format fold existed keep it at its default (open) instead of closing it; browser tests pick the cast through the checkboxes (`pick_cast`), with regression assertions for both fixes; stale interface-guide text removed.
- Reviewed by Codex (medium reasoning effort, read-only), whose findings produced the three fixes above. Escaping of filenames and actor names in the new tooltips was checked and found sound.
- Version label follows the fork (1.10.20); our 1.10.12 changes are retained. Full suite 761 passed + 141 subtests.

## 1.10.12 — Vision server starts when needed

- Style Harvest, world reading (Worlds) and storyboard interpretation now start the local vision server when nothing is answering at the Vision service URL, and stop it afterwards. A server that was already running is used as is and never stopped. The preview no longer refuses just because the server is offline; it refuses only when Mondo cannot start it, and says why.
- Launch command: the new optional **Vision launch command** setting (`vision_launch`, JSON argument list), else derived from the writer launch plus the matching `mmproj*.gguf` beside the model, with `--alias` set to the Vision model name, the port from the Vision URL, and a 32768 context. Remote URLs and download options are never launched; only loopback addresses are.
- Safeguards: free GPU memory is checked before starting; the program must exist; any server already answering at the Vision URL is used as before (Mondo does not try to tell it from the writer; with both on port 8080, run them on different ports). No automatic retries.
- Agent interface: launch commands stay GUI-only for agents, as for `writer_launch` and `comfy_launch`; agents get the same behavior through `preview_production` and `start_production` for the `harvest`, `world_harvest` and `storyboard` kinds, and the error text names the cause.
- Reviewed with a low-effort read-only Codex pass. The quality-check vision stage (port 8083) is unchanged.
- Fixed: the saved project rejected the `worlds` panel (HTTP 422, silently ignored by the page), so nothing on the Worlds panel was autosaved and a reload blanked it. Text fields now persist. Chosen image, video and lore files cannot be restored by the browser after a reload and are still re-selected; they are uploaded only when you press Preview.
- Fixed: file uploads could hang on "Uploading…" in Firefox. The Outputs list asked every rendered video for its metadata, which kept most of the browser's six connections to the app busy streaming videos, so the upload request waited behind them. Videos now load only when played.

### Integration review of fork 26719de

Reviewed by Claude Code with a low-effort read-only Codex pass; credit for the changes: hellonearthis.
- Adopted: all UI work, contextual vocabulary scaling, world vectors, lint and cluster tools, embedding launch script. No protected-scheme file is touched.
- Fixed: `POST /api/log/clear` no longer resets a failed operation on the server; Thematic Worlds slider is read from the `slider` key the UI sends (was `juxtapositionSlider`, so ignored); malformed `thematic_worlds` now degrades safely; style sidecar names cannot leave the styles folder; narrow-screen header overflow; vocabulary guide test selector.
- Agent-interface limitation (intentional for now): `thematic_worlds` is set from the GUI and saved project state only; the agent client, MCP tools and skill do not yet expose it. The earlier deferral in `docs/COLLABORATOR_REVIEW.md` (no consumer) is superseded: `mmv/pipeline.py` now consumes it, only under `vocab_selection: contextual`.
- Accepted as authored: pseudo-random vocabulary key default raised 5 to 10. Changed: the Gaussian world pick now samples every candidate world by its weight (it only chose between the top two). Left as authored: `C:/llamaCPP` lookup fallback in `mmv/vision_check.py` (only if a relative model path is missing); `start-embedding.ps1` is Windows PowerShell, now hardened (see below).
- `start-embedding.ps1`: reads the llama-server location from the app settings.json (writer launch) when the default folder is absent; new `-ModelPath`, `MMV_EMBEDDING_MODEL`, `-ServerExe`, PATH lookup for llama-server, a one-level (non-recursive) model lookup, and a clear message when the port answers.

## 1.10.11 — Fork integration (hellonearthis)

All fork releases 1.10.11–1.10.14 ship together as this one version.

### Fork 1.10.14 - Static File Drop Targets & Staging Guidance Polish

- **Static Drop Zone Markup**: Embedded drop zone hints (`Choose a file or drop it here`, `Choose files or drop up to N images here`) and error containers directly into the HTML body across all 16 file upload targets, eliminating post-load text insertion and visual shift.
- **Idempotent File Drop Initialization**: Updated `initFileDropTargets` in `webapp/js/file_drop.js` to preserve existing static hint and error elements in the markup instead of appending duplicates dynamically.
- **Cast & Staging Box Architecture**: Preserved clean `.oap-hint-box` layout and header badge semantics distinguishing character identities from scene reference images.

### Fork 1.10.13 - Tooltip Theming & Operation Bar Polish

- **Polished Tooltip Theming**: Upgraded studio tooltips with an emerald forest dark mode (`#0e201b` background, `#224b3d` border, `#e8f4ec` text) and a clean soft-blue light mode (`#f0f5fc` background, `#0d233a` text, `#b8d1ea` border).
- **Consolidated Operation Bar Tooltip**: Merged redundant individual status tooltips into a unified tooltip on the studio status container (`Current status and real-time execution report of the studio engine.`).
- **Sidebar & Tooltip Refinements**: Retained right-side offset positioning for sidebar items and cleaned duplicate attributes across the application header.

### Fork 1.10.12 - GUI Decluttering, Accessible Tooltips & Studio Polish

- **Streamlined Service Dock & Form Cards**: Slimmed the service dock into a compact single-line horizontal status strip with informative tooltips; organized Card 1 & Card 2 secondary parameters into collapsible `.sub-fold` accordions while keeping all form input names, IDs, and tests 100% intact.
- **Accessible & Tautology-Free Tooltip System**: Stripped over 200 redundant `title` attributes that caused double-tooltip flickers, consolidated nested label-input tooltips into single comprehensive triggers, added right-side placement for sidebar elements, enabled `white-space: pre-line` for line breaks (`&#10;`, `\n`), and expanded tooltip `max-width` to 480px.
- **Button Styling Polish (`button.quiet`)**: Upgraded quiet actions from plain underlined text to modern tactile pill buttons with borders, hover transitions, and dark-mode styling.
- **Interactive Full Studio Toggle**: Transformed "The Full Studio" preview section into a collapsible dropdown with animated directional indicators (`▶` to `▼`) and informative edition notes.
- **Immediate Drag-and-Drop Area**: Styled the audio drop zone statically in CSS so it renders instantly on page load without layout shift; updated loaded track receipt display and balanced vertical spacing.
- **Clear Log (adapted on integration)**: the studio's status bar returns to idle in the browser after Clear Log; the server-side `FAILED` state is kept so recovery information is not lost.

### Fork 1.10.11 - Semantic World Vector Clustering & Gaussian Dissonance

- **Dynamic audio-scaled vocabulary windowing**: `select_term_for_energy` scales accessible table depth directly with `ScoreMap` energy ($0.20 \to 1.0$), keeping calm sections focused on the top canonical terms while opening full depth during peak sections.
- **Multi-tag attribute stacking**: At energy $\ge 0.80$, stackable attributes (`mechanism`, `lighting`) deterministically draw a secondary complementary cue to increase prompt density during climaxes.
- **Semantic world vector clustering (`mmv/world_vectors.py`)**: Canonical domain prefixing (`setting: ...`, `mechanism: ...`), normalized cluster centroids $c_k = \frac{1}{N}\sum \frac{E(t)}{\|E(t)\|}$, and percentile-calibrated distance matrices ($P_{15} \leftrightarrow P_{85}$) to resolve tight cosine clustering.
- **Gaussian dissonance selection & five-band dimensional binding**: Continuous Gaussian dissonance sampling governed by $\kappa_{\text{eff}} \in [0.0, 1.0]$ with Montage Grammar preservation (Harmonic, Soft Accent, Motivated Tension, Surreal Juxtaposition, and Hot Bars maximal collision).
- **Protected scheme preserved**: `mmv/engine/plan.py` remains untouched; all original engine golden plan fixtures and protected scheme checks pass cleanly.

## 1.10.10 — Open Prop Protocol v0.2

- The pinned OPP dependency moves from v0.1.0 (`1e1bc6c`) to v0.2.0 (`ec097e1`).
  v0.2 packages import and verify; v0.1 packages still do. Unknown minor versions
  are rejected by the protocol verifier. `/api/catalog` reports `opp_version`
  `0.2.0` and `opp_accepts` `0.1.x`, `0.2.x`.
- v0.2 generic assets (audio stems, 3D files, LoRAs and similar) are listed in the
  imported prop record (`assets`: file, role, clearance, hash, whether included)
  and remain in the preserved `original.opp`. MMV does not render or extract them.
- MMV already rewrites image sheets through its own cleaner on import, so OPP's new
  author-side `clean_asset` helper is not needed by the importer. No GUI, CLI or MCP
  change: the existing inspect/import/select tools carry the new field.
- `GET /api/opp/inspect` (and the CLI/MCP `inspect_opp`) now also returns `tier`
  (`full` or `preview`), `included` and `omitted` files, so a reviewer sees which
  listed master sheets and assets a preview-tier bundle does not carry. The GUI
  review panel shows tier, omitted files and generic assets; library cards count assets.
  (From the Codex read-only review.)
- **Instruments are now OPP props; the separate instrument reference library is gone.**
  The bundled guitar and keyboards ship as OPP v0.2 source trees
  (`mmv/assets/props/mmv-guitar`, `mmv-keyboards`), are packed unsigned and imported
  into the props library at startup (never overwriting), and are those roles'
  defaults. The GUI's Instrument reference library and import form are removed; the
  Open Prop Protocol library lists everything. Sheets saved by earlier releases in
  `data/instruments/` become `mmv-local-<role>` props (files kept) and are that role's
  default. Removed: `POST /api/instruments/{id}`, `GET /api/instruments/{id}/reference`,
  the agent `import_instrument` / MCP tool (import with the OPP tools). `GET /api/instruments`
  and `inspect_studio(kind="instruments")` remain as a read-only role/default-prop view.
  Drums and bass need an imported prop. Runs saved before this release that pointed at
  the old bundled sheet files will ask for a fresh preview.
- Agent surface audit: `inspect_opp`, `import_opp`, `select_opp_sheet`, the catalog
  and project skill need no new tool; docs now say v0.1 and v0.2.

## 1.10.9 — One final encode from original clips

- Subliminal flashes and burned captions now run inside final assembly, at the same
  H.264 CRF-6 / slow quality as the clean version. Each variant reads original clips;
  neither a clean export nor a flashed export becomes another render's video input.
- Final assembly trims and joins the original clips, adds effects and encodes in one
  FFmpeg invocation per variant. Attached idents/videos resolve their original
  clips too, including their saved effects. The optional PCM editing stem is retained.
- Adding captions later rebuilds from saved source provenance, retaining flashes and
  replacing captions. Old runs can reconstruct from plan/render/request/prepared
  records. Missing originals fail clearly; restoring sources is required, never
  a fallback to recompressing the final. Existing final files are not modified by
  this upgrade. Sidecars still require no video encode.
- Topaz remains the owner-approved exception, operating on the selected finished
  video. No paid/GPU work, provider retry or prompt changes are part of this fix.
- GUI, existing caption API/client/MCP and production preview/start/resume retain
  their interfaces and consent guards. Source provenance stays local; no new tool
  is required. Legacy per-clip video assembly intermediates are no longer generated.
- Validation: 713 full-suite tests + 141 subtests, then two added timing/source
  regression tests passed using synthetic media and mock services. Live 1.10.9
  and the served UI verified; no real production render performed.
- Fork task-start HEAD: `56d9f04027dab5e2cc9c9e2860a614e1190d75fd`,
  unchanged since the completed collaborator review.

## 1.10.8 — One-click "Just do the thing!"

- A big red button at the top of 01 Music Video. With a song already chosen it fills
  the blanks and opens the usual preview; without one it opens a "Select a song to
  begin" dialog with browse and drag-and-drop. The preview's consent step is unchanged:
  nothing is rendered or charged until the person accepts it.
- The random plan (`GET /api/quick-start`, `mmv/quick_start.py`) prefers the bundled
  starter cast, sometimes chooses no cast at all, and when it casts, sometimes adds
  group dancing. Instruments, subliminal flashes and captions are never chosen.
  Anything the person already filled in (direction, style, cast) is kept.
- A quiet **Start fresh** link beside it clears the panel (song, references, storyboard,
  vocabulary choices and all fields) after a confirmation; renderer and resolution are kept.
  GUI-only by design: agents build each request from scratch, so there is nothing to clear.
- Settings (09) now save automatically a moment after each change (or on Enter); the
  Save settings button is gone. Choosing an API profile or workflow redraws the form so
  the fields it fills in are shown. A failed save (for example while a production is
  running) says so beside the form. Agents already persist settings with PATCH, so no
  agent change was needed.
- Agents: `inspect_studio` kind `quick-start`, CLI `quick-start`; merge the plan into a
  `preview_production` request. No consent guard changed.

## 1.10.7 — Optional storyboards for music videos and idents

- Ordered storyboard images, narrative/visual interpretation, editable panels,
  reordering, source thumbnails, separate saved video/ident drafts and timing preview.
- Interpretation uses one configured vision call behind the existing quote/consent
  flow; results persist for review and recovery. No automatic retry or new services.
- Reviewed storyboard direction is optional writer job data / ident user notes.
  Protected system prompts, planner files and pins remain unchanged.
- Ident can explicitly use all attached references through existing ensemble
  controls; single-reference behavior remains the default.
- REST, client, CLI and MCP coverage (54 tools), documentation and mock checks.
  Actual visual adherence has not been verified with real renders. Visual mode
  describes composition; it does not promise pixel replication or inject board images
  into actor slots. Music timing remains authoritative.
- Claude Code reviewed the design; implementation adapts the user's proposal to
  existing MMV services. No Redis/vector database/Remotion additions.
- Collaborator task-start head: `56d9f04027dab5e2cc9c9e2860a614e1190d75fd`,
  unchanged since the substantive review recorded for 1.10.6.

See [Storyboards](STORYBOARDS.md).


## 1.10.6 — Style vocabulary and contextual selection (fork contribution)

- Adapted from hellonearthis's fork commit `56d9f04`. Styles may carry an optional
  `vocabulary` (`custom_vocabulary` format). Import, create, CLI `import-style`,
  the MCP style tools and the Style JSON import accept it; it is validated with
  the real vocabulary rules and stored as data. It is never applied automatically:
  picking the style on the music-video form shows a **Use this style's vocabulary**
  button, and nothing changes until it is pressed.
- New request setting `vocab_selection` (`legacy` default, `contextual`).
  `contextual` narrows the rotation tables (settings, lighting, mechanisms,
  costume, practical effects) to the terms that best match the direction,
  title and custom additions, with seeded hash tie-breaks, before planning. The
  planner, prompts and pins are untouched and `legacy` requests are identical to
  before. No GUI control yet (API, CLI and MCP request objects only); no real
  before/after render has been compared.
- **Contrast worlds (opt-in).** Adapting the fork's mirror / opposite / tangent
  juxtaposition to our Worlds: a video may name contrast worlds and a departure
  strength; intense, high-energy shots borrow settings, lighting, mechanisms and tonal
  registers from them (request fields `world_contrast`, `world_contrast_strength`;
  video-form "Contrast worlds" section; agent, CLI and MCP request objects; see
  `docs/WORLDS.md`). Off by default and off-identical. Planner, prompts and pins are
  untouched. Not yet compared on real renders.
- Fixed in the port: the fork's unclosed `<div>` in the video form.
- Not adopted: the fork's blanket per-shot term override (see
  `docs/COLLABORATOR_REVIEW.md`).

## 1.10.5 — FastH3 Omni workflows

- Two new bundled workflows for the FastVideo FastH3 Omni 8-step model
  (`FastVideo/FastH3-Omni-Comfy`), selectable from a **Bundled H3 workflow**
  picker above the workflow path in Settings or by the agent setting
  `workflow_preset` (`standard`, `fasth3_int8`, `fasth3_bf16`):
  - **FastH3 Omni INT8**: `fasth3_omniref_8step_pruned_int8_convrot` with the
    `qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot` text encoder.
  - **FastH3 Omni BF16**: `fasth3_omniref_8step_pruned_bf16` with the
    `qwen3vl_32b_h3_ultra_uncensored_heretic_bf16` text encoder.
  Neither has a LoRA option. The standard 20-step workflow and map are untouched
  and remain the default.
- A map may now set `default_steps`; the new maps use 8 (the model card's step
  count). Local and SDK renders read it, otherwise stay at 20. Guidance 1.0 is
  what the graph's BasicGuider already applies; the card's video/audio shift
  values (12.0 / 3.0) are not set by the graph and rely on ComfyUI's native
  MiniMax-H3 handling. Sampler/scheduler are unchanged (`res_multistep`/`simple`),
  as the card does not specify them. Real inference is not verified here.
- Instrument performance no longer requires a named player to be playing in every
  shot they appear in. The check (`mmv/instruments.py`) now rejects a shot only for
  a vague attempt to play ("strikes the guitar"), another instrument's gesture, or
  playing during a paused shot; the instrument reference must be cited at the first
  shot where the player plays. The matching sentence in the instrument writer rules
  (appended only when instruments are on) says players may also stand, move or react.
  Cause: with dancing on, four runs failed because every shot naming the keyboard
  player demanded keys and a picture-tag link. Known gap: a player's instrument being
  played by a different named actor in a shot where the owner does not play is no
  longer caught by that shot's check.
- Local-writer retries for dancing and instrument passages are sturdier
  (`mmv/worker.py`, `mmv/writer_json.py`; the pinned `writer.py`/`schema.py` are
  untouched): raw newlines/tabs inside a JSON string are escaped before parsing;
  a reply that is not valid JSON is asked again with the same feedback and does not
  use up one of the four attempts (at most two such free retries per passage); and a
  retry now includes the previous draft's shots so the writer revises instead of
  rewriting every shot. Passages without dancing or instruments are unchanged.
- Dance check (`mmv/dance.py`): "lunge" and "footwork" count as moves, a few more
  downbeat accent words are accepted, and in group mode a move in the same sentence
  as a mouth clause now counts (the mouth clause is dropped, face-only sentences are
  still ignored). Evidence: Codex read-only review of runs 160410-172316.
  Independent mode's assigned-movement-family check also accepts natural wording
  (vertical: "vertical sway", "flexes and extends", "rising and falling"; lateral:
  "weight shifted", "slides"; rotation: "spins", "twirls", "torso"). Run 180005 failed
  all four attempts on shots that already showed the assigned vertical movement.
  The "prompt validation failed" message no longer blames Laya alone.
- **Dance and instrument wording checks are advice, not rewrites.** Before, any
  word-list finding (a dancer "not described moving", a movement family, a downbeat
  accent, "must visibly play", a pronoun) sent the passage back to the local writer,
  up to four times, before Laya ever saw it. Runs 163328-181732 used 9-12 writer
  calls for 3-5 passages and several died on these checks. Now only integrity
  problems force a rewrite: a wrong shot count, a missing instrument player, and an
  uncited instrument reference (`dance.is_blocking`, `instruments.is_blocking`),
  plus the existing schema, quality and lip-sync checks. All other findings are
  written to `segNNN.advice.json` (with the prompt's SHA-256) and the draft goes
  straight to Laya. Cached prompts are no longer refused for advice-level findings.
  A new video option, **Strict dance & instrument checks** (`strict_prompt_checks`,
  off by default, in the form under Dancing and in the preview request), restores the
  earlier send-back-to-the-writer behaviour for every finding; cached prompts made
  under it are kept separate. Compare the two on the same song and seed by eye.
  The advice receipt is in the run folder and in production packages; the Agent
  API/CLI/MCP are otherwise unchanged. Known limit: Laya's questions do not yet
  include the dance or instrument job, so it cannot judge whether each dancer
  follows their assigned cues or each player plays the right instrument. Teaching
  Laya that means editing the protected `validators/` folder and needs the owner's
  explicit approval and a before/after render comparison; it was not done here.
- No protected prompts, pins or banner changed.

## 1.10.4 — Mondo favicon

- The app now has a browser-tab icon: `/favicon.svg` (green badge with an italic
  "M") and a multi-size `/favicon.ico`, linked from the page head and included
  in the package data. Adopted unchanged from hellonearthis's fork revision
  `c699179` with its endpoint test. Credit: hellonearthis.
- Reviewed fork head `c699179`. Not adopted: `5ca5eb9` (Thematic Worlds "Process"
  button and keyword cluster matching). It builds on the deferred
  `vocab-worlds.js` work from `79d8515`, so it waits on that foundation; no new
  defect was found in the diff. See `docs/COLLABORATOR_REVIEW.md`.
- No protected prompts, pins or banner changed. The icon is a static asset;
  Agent API, CLI and MCP are unchanged.

## 1.10.3 — Topaz cloud upscale

- Provider keys in Settings are now one paste-and-save row per key (WaveSpeed,
  writer, vision, ComfyUI proxy, Topaz) with saved / not set status, and the
  upscale dialog offers the same row in place when the Topaz key is missing.
- New Settings choice **Topaz upscale service**: installed program (default,
  unchanged) or **Topaz cloud** (`api.topazlabs.com`), so upscaling works without
  a local Topaz install. Save the Topaz API key as `MMV_TOPAZ_API_KEY` in
  Provider keys (private, redacted from logs like the other keys).
- The upscale dialog has an **Upscale service** dropdown (installed or cloud) that
  saves on selection, and the running status shows Topaz's own wording (for example
  "Queued - waiting for resources (0%, about 21 min once running)") instead of
  its raw state names; unchanged statuses are no longer logged every 5 seconds.
  A first real cloud export (2×, with audio) was verified by the operator.
- Paid-consent flow: the dialog first asks Topaz for a free estimate (credits,
  time, output size), then requires a credit-approval tick. The job re-prices and
  stops before reserving anything if the price rose above the approved figure.
  Reserving credits is never retried; a failure or cancel before the result is
  ready asks Topaz to cancel and refund unused credits, and the request id is
  logged. The finished video downloads to a new `upscale` output; the source is
  untouched. Output is H.264 (H.265 above 4096 px) with audio copied.
- Cloud model and frame-rate choices: the dialog has a grouped model picker
  (Proteus/Artemis/Gaia/Iris/Theia/Dione, Starlight, Astra 2, Nyx denoise, Themis,
  stabilization, Hyperion) from `mmv/topaz_models.py`, narrowed to what Topaz's
  public `/video/status` list accepts now (new Topaz models appear as "Other").
  Frame rate section: interpolation model (Apollo, Chronos, Aion), target fps
  15–240, slow-motion factor, duplicate-frame removal; "no upscale" gives
  frame-rate-only jobs and 1× enhances without enlarging. A Tuning section
  (parameter mode Auto/Relative/Manual plus compression, detail, noise, halo,
  anti-aliasing, sharpness, original-detail, grain) applies to Precision models.
  The credit approval is bound to the exact model, scale and options estimated.
- Agents: MCP `list_topaz_models`, `estimate_upscale` and `upscale_video` take
  `options` (53 tools), CLI `upscale-models` and `--options JSON`;
  earlier: MCP `estimate_upscale` (53 tools), `upscale_video(max_credits=…)`,
  `AgentClient.upscale_estimate`, CLI `upscale-estimate` and `upscale --max-credits`, REST `POST /api/upscale/estimate` and
  `max_credits` on `/api/upscale`; skill, AGENT_SETUP, interface guide, platform
  and scope documents updated.
- Limitations: cloud models are chosen by Topaz model ID (for example `prob-4`,
  `ahq-12`); model tuning parameters, frame interpolation and Topaz's
  external-storage and webhook options are not exposed. The cloud key is not part
  of the writer/vision/video API profiles. Uploads read the file into memory in
  segments of up to 500 MB. Automated tests use a mock service; a real cloud export
  spends credits and needs the operator's deliberate go-ahead.

## 1.10.2 — Panel heading numbers

- Panel headings (the small "07 / WORLDS" line) now match the sidebar numbers
  introduced in 1.10.1; a test checks them. `docs/interface-guide.md` gains a
  Worlds section and the new panel numbers. No new agent tool was needed: the
  Worlds MCP tools, CLI commands and skill text already shipped in 1.10.0, and
  agents address panels by tool, not by sidebar number.

## 1.10.1 — Sidebar tab order

- Sidebar order is now Music video, Credits & idents, Actors & OAP, Styles,
  Style harvest, Visual vocabulary, Worlds, Finished videos, Settings, with
  numbers 01–09 and in-app cross-references updated.
- New standing rules (AGENTS.md): generative tabs stay on top, Settings is
  always last.

## 1.10.0 — Worlds

A world is persistent, in-universe canon that videos share, built and grown from
references.

- **Worlds panel and store.** Private versioned ledgers under `worlds/`
  (core laws, subjects, locations, practices, objects, factions, ecological
  rules, moral ambiguities, open threads, never-contradict list, and include /
  exclude pools for seven vocabulary tables). Every accepted change is a new
  version; any version can be restored.
- **World harvest.** A new operation reads pictures, video keyframes (ffmpeg),
  lore text and finished runs through the configured vision model and writes a
  proposal with a field-level diff. Nothing changes a world until accepted;
  a proposal made against an older version is refused. It has its own prompt and
  parser in `mmv/worlds.py`; the style harvest prompt and every protected file
  are unchanged. Limits: 24 images (8 per video, 4 per run), 3 videos, 5 lore
  files of 60 KB.
- **Using a world.** Choosing a world on the video form fills the existing
  custom vocabulary from its pools, either confined to the world's terms or added
  to the standard pools. Planner and writer behaviour are unchanged.
- **Privacy.** `worlds/` and `world-proposals/` are ignored and pruned from
  sdists; shared production receipts leave out the world's identity and derived
  pools.
- **Agents.** Nine MCP tools (51 in all), matching CLI commands and agent client
  methods, `video` and `lore` upload kinds, and skill/reference updates. Accepting
  a proposal and deleting a world require explicit confirmation.
- Deliberately not included: pinned terms (the existing vocabulary path cannot
  guarantee a term appears), planner weighting and section-aware behaviour, and
  injecting world canon into the writer's context. Each would touch the protected
  prompting scheme and needs the owner's approval first.
- Stale instruction fix carried with this release: the file-drop count test now
  expects the three new Worlds inputs (14).

## 1.9.10 — Formatted vocabulary guide, tooltips and Labels relocation

Selective integration of hellonearthis's fork revision `79d8515`, reviewed
adversarially in an isolated checkout.

- The vocabulary guide dialog renders `docs/VOCABULARY_GUIDE.md` with a new
  dependency-free Markdown renderer (`webapp/js/markdown.js`), with a raw-text
  toggle and copy buttons for the document and for code blocks. Adapted from the
  fork: a blockquote line with leading spaces recursed without end and overflowed
  the stack (found by fuzzing, fixed); heading ids are prefixed `md-` so they
  cannot collide with page ids such as `version`; only `https` links open in a
  new tab, `#` anchors stay in the page and relative links render as plain text.
- Tooltips prefer to open above the target and flip when they would clip. The
  vocabulary category tabs and Select/Clear/Reset buttons explain what each
  table does. The fork's tooltip for a twelfth `themes` table was dropped: the
  catalog has eleven tables.
- The component-labeling button moves from the header to Studio Settings (08)
  and is no longer hidden at narrow widths; settings tooltips gain clearer
  launch guidance without Windows-only example paths.
- Deferred: Thematic Worlds, its Strict/Guided mode, juxtaposition and kappa
  controls, the `thematic_worlds` request field, clustering and lint tools,
  embedding setup and the Windows launch changes. See
  `docs/COLLABORATOR_REVIEW.md`.
- No protected prompts, pins or banner changed. Agent API, CLI and MCP are
  unchanged: the guide is already served at `/api/vocabulary/guide`.

## 1.9.9 — File drop on browser inputs

All 11 browser file controls accept drops on their labeled areas. Dropped files
enter the existing change handlers for song and reference uploads, actor and
instrument images, and package/JSON selection. Multi-image drops replace the
current selection. Unsupported types and too many images show an inline error
without changing the selection. OAP and OPP inspection must be repeated after
a new package selection; signer acceptance and import remain explicit. Settings
Browse selects server paths and is unchanged. Agent API, CLI, MCP and the
included skill keep their existing upload and import paths; the drag gesture is
browser-only. No production, prompt, consent or automatic retry behavior changed.

## 1.9.8 — Component labeling mode

Integrates [hellonearthis](https://github.com/hellonearthis)'s fork commit `5e2bba4`: a **Labels** header button (Ctrl+Shift+L, Alt+L, Esc to exit) outlines the hovered interface component and shows its stable name and ID; clicking the badge copies them. Components carry `data-component*` attributes, and `docs/interface-guide.md` records the naming. Adapted for this tree: the Open Prop Protocol library card is labelled, and the badge is built with text nodes instead of `innerHTML`. The overlay is a developer and pair-programming aid with no workflow, so it is intentionally GUI-only; agents use the existing API, CLI and MCP surfaces. No protected prompting, paid-consent or retry behavior changed. See [collaborator review](COLLABORATOR_REVIEW.md).

## 1.9.7 — Open Prop Protocol instrument references

Added a private, general Open Prop Protocol v0.1 library. Users can upload,
inspect and import signed `.opp` packages after explicitly accepting the
inspected signer key, or separately allow an unsigned local draft. The app
checks archive bounds, paths, hashes and signatures, preserves the original
bundle, and creates clean image references. Its first production adapter lets
an assigned musical role use a selected OPP base or interaction sheet; free-form
use text picks an interaction match with a base fallback. The quote shows the
selected sheet and reference-slot cost, and saved plans/fingerprints bind the
chosen sheet and package bytes. Existing instrument sheets remain available,
and the original prompt scheme stays unchanged. GUI, API, CLI, MCP and the
included operation skill cover import, selection and preview. General prop use
outside musical instruments is a later host workflow; OPP itself keeps arbitrary
prop IDs and tags. No private props are included in source or release packages.
Package-authored prompt modifiers and descriptions are kept as data and do not
enter the writer prompt.

Claude Code Sonnet 5.5 reviewed the MMV adapter read-only. Its sandbox could
not read the sibling OPP checkout, so Codex compared the pinned protocol source
and tests directly. The review prompted exact-key signer acceptance, package
text isolation from writer prompts, and stronger import/replay checks. The
collaborator fork's new component-labeling feature at `5e2bba4` was reviewed
for compatibility and deferred to a separate interface task; see
[collaborator review](COLLABORATOR_REVIEW.md).

## 1.9.6 — Collaborator performance improvements

Integrated compatible work from [hellonearthis](https://github.com/hellonearthis)'s fork commits `5b026e5` and `e6ef03e`: Windows model/projector discovery now scans GGUF files once, production child processes started by `JobContext` use UTF-8 mode, service probes reuse workers and validated launch commands, the color wheel reuses its rendered image, and unfinished-run listing uses directory entries for faster traversal. The run-size cache expires after five seconds because writes in nested folders do not update the run folder's mtime. The writer working-directory label now mentions llama.cpp while retaining its generic meaning for other local writers. Existing preview, start, paid consent, deletion confirmation and agent actions are unchanged.

No performance timings or Windows execution are claimed from this Linux review. See [collaborator review](COLLABORATOR_REVIEW.md) for integration decisions.

## 1.9.5 — Bounded instrument action repair

For opted-in instrument performances, a clearly attributed but vague guitar action such as “strikes the guitar” can be corrected to explicit string and fret contact before the normal prompt, motion and Laya checks. The original writer response remains in the run record, and a small repair receipt lists the edited shots. Wrong-instrument gestures, lyrics and ambiguous attribution stay with the writer for correction. Retry feedback names the failing actor and shot, gives a physically specific example, and asks the writer to preserve the other shots. Passage lengths, protected core prompting and paid retry limits remain unchanged.

Claude Code Sonnet 5.5 at medium effort improved the opt-in feedback; Codex added the bounded correction and verified it against the saved failed draft without running a model.

## 1.9.4 — Instrument prompt retry

Natural hand actions such as striking guitar strings now pass the opt-in instrument guard. One clear reference binding can carry through later shots that continue to name the assigned instrument. A failed, unrendered prompt run offers **Try again** in the GUI: it creates a fresh preview from the saved request and still requires the operator to review and approve a new start. The agent client, CLI and MCP expose the same retry-preview path. The misleading context-size hint is no longer appended to unrelated validation failures. The protected core prompting scheme is unchanged.

Claude Code Sonnet 5.5 at medium effort implemented the instrument guard change; Codex reviewed it against saved writer drafts, added GUI/agent retry and verified the release with mock services. No production was automatically retried.

## 1.9.3 — Automatic model startup and GPU handoffs

Quality vision now checks its own service on port 8083, independently of style harvesting on vision_url. Previews and starts accept a configured model that Mondo can launch when its stage needs it. Separate quality-vision status and automatic-start badges distinguish launch capability from a running model. Invalid launch settings name the configuration problem.

Mondo releases idle ComfyUI caches before local prompt preparation, confirms its writer has stopped before rendering, and swaps renderer/vision models between stages. Laya uses the GPU only when measured headroom covers its staged weights plus a reserve; otherwise that production uses CPU without rewriting Settings. Unknown memory does not authorize Laya overlap. Known insufficient writer/vision headroom, busy queues, unverified external renderer release and failed process exits prevent competing loads. Known external GPU writer/vision services are preserved and block local renderer startup; external vision also prevents automatic re-render overlap. Existing paid-consent and retry limits remain unchanged.

The lower-left sidebar tagline now reads “You can do anything”.

Daylight Cinema now includes a complete 11-axis harvest-style card, free axes, borrowable motifs and detailed aesthetic direction. Untouched factory daylight files upgrade automatically; customized or deliberately removed defaults are preserved.

Claude Code Sonnet 5.5 at medium effort implemented the main lifecycle, memory policy, interface and regression tests, and a fresh session expanded daylight; Codex reviewed and tightened conservative cases and integrated the release. No protected prompting sources changed.

## 1.9.2 — Vision checks with ComfyUI already running

Vision-enabled previews now accept an existing ComfyUI. After rendering, Mondo requests cache/model release while its queue is idle and waits for memory release before loading vision; it leaves external ComfyUI alive and preserves other queued/running work. Mondo-owned processes keep their existing stop/restart path. No automatic paid retry changes.

Removed contributor handles from the displayed visual-vocabulary and writer-tuning labels; the vocabulary profile ID, legacy tuning compatibility and contribution credit remain. OPP is acknowledged as the forthcoming prop import/use protocol; no speculative schema was added.

## 1.9.1 — Instrument controls without internal validation warnings

Removed the instrument caution banner and its preview/export text. Instrument selection stays optional, with normal activity/reference information. Agent instructions no longer ask agents to repeat that caution. Validation tracking stays in developer documentation; the original protected-scheme integrity safeguards are unchanged.

## 1.9.0 — Opt-in instrument-playing actors (operator validation pending)

- Per-actor drums, bass, guitar and keyboard assignments; existing-stem energy/pauses with explicit unknown/mix fallback. No implicit separation or downloads.
- Instrument references are wired per passage after actor references, only for cast players with playing/unknown activity, with shared-design deduplication, renderer budget/cost checks and backend labels. Saved plans, cache validators and consent fingerprints include instrument decisions and sheet identity.
- BONK-style extension outside protected originals, off by default; form/preview/export warning. Players are excluded from dance choreography; approved singing and mouth rules are preserved.
- Instrument library/import API, agent method, CLI discovery and MCP import tool (38 total), private-provenance export redaction. Props remain separate from OAP actors; OAP verification and consent guards are unchanged.
- Owner-supplied guitar and keyboard sheets bundled at their created resolutions under Apache-2.0; drums/bass sheets pending.
- Claude Code Haiku reviewed the architecture/implementation; staging, privacy and unknown-activity findings were addressed. See [instrument documentation](INSTRUMENTS.md) for asset limits and pending same-song/seed real-render validation.

## 1.8.14 — Custom caption colours and fonts

Joint Claude Code and Codex work: the backend was written and tested by Claude Code, the browser controls by Codex in an isolated worktree, and the diff was reviewed and integrated by Claude Code.

- Burned captions can use your own **text colour** and **outline / glow colour** (`#rrggbb`) and any **installed font**. Blank keeps the chosen style's own colours and the default font, so nothing changes unless you ask. A box style keeps its see-through panel when you recolour it, and neon's glow follows the outline colour.
- Fonts must really be installed where the app runs (`fc-list`): a missing font is refused with a clear message, because FFmpeg would otherwise silently draw another one. Font names and colours are validated strictly, so nothing from them can reach the subtitle script as a command.
- Colours are chosen on inline **colour wheels** (hue around the circle, saturation toward the centre, a brightness slider, a swatch and an editable hex box; `webapp/js/colorwheel.js`, no library) instead of the browser's own colour picker. Mouse, touch and pen work, one pointer at a time; the keyboard moves hue and saturation with the arrow keys; screen readers get the hue, saturation and hex colour read out. Typing `abc` becomes `#aabbcc` and junk reverts to the last good colour. Codex reviewed the wheel (read-only) and its accessibility findings were fixed.
- Surfaces: the production form and the "Add lyric captions" dialog (a Custom colours checkbox with two colour wheels, and a font box with an installed-fonts list that fills from `GET /api/captions/fonts`), the agent client (`caption_video` options and `caption_fonts`), the MCP server (`caption_video` options and the new read-only `list_caption_fonts`, 37 tools) and the skill. Saved projects remember the choices.
- `start.sh` / `stop.sh` made portable for macOS (bash 3.2 empty-array handling, `ps` instead of `/proc`, the Mac data folder) with double-click `start.command` / `stop.command` wrappers. Verified on Linux only; not yet run on a Mac.
- Not done: word-by-word highlighting (only line timing is stored), and a live preview of the look before rendering.

## 1.8.13 — Readable folder names for every job, and start.sh / stop.sh

- Every new job folder now has a human-readable name like productions already did (`<what>_<what for>_<date>_<time>`): Topaz upscale outputs, lyrics detection and model setup, stem-model setup and package-export jobs no longer get random strings (`mmv/jobs.py`: `job_run_id`). Existing folders are not renamed, so saved references and resumes keep working. The package folders themselves were already readable.
- `start.sh` and `stop.sh` for Linux, macOS and WSL (Windows keeps `start.ps1`): start in the foreground or with `--background`, always run this checkout's code, refuse a second copy, keep an accurate `server.pid`, and stop waits for a clean exit and protects a running production.
- Not changed: protected prompts and scheme, the app's own session lock, and the Windows launcher.

## 1.8.12 — Lyric captions

New, free and post-assembly (a joint Claude Code and Codex free-time project; Codex reviewed the design before the code was written).

- Setting **Lyric captions** (off by default): the timed lyric lines already used for lip sync become `lyrics.srt` (subtitle file only) or are also burned into the video with FFmpeg's libass (`mmv/captions.py`). Burning keeps the exact frame count and audio, verifies the result before replacing the video, and keeps the video without captions as `music-video-uncaptioned.mp4`. If burning fails the video is untouched, `lyrics.srt` stays, and a warning is shown.
- Captions use the lines on their own: they do not turn on lip sync, the captions feature adds no path to the writer or any prompt (the existing lyrics and lip-sync inputs behave as before), and no protected file changed. Lines whose timing was only guessed are skipped; captions are shifted past an opening ident and stop where the assembled song ends (the joined passage lengths), so they should not run over a closing ident; this is checked in tests with synthetic videos, not yet on a real render with idents.
- With captions on but no timed lines yet, the preview says so and the video is made without captions; the score editor's lyric box (detect, paste, edit) now also opens for captions, not just lip sync. Old saved runs keep their consent fingerprints because the captions field is absent when off. The media route now serves `lyrics.srt` and the backup videos recorded in `output.json` (previously only the main video), so the agent client's `download` can fetch them; project exports include `lyrics.srt` and the uncaptioned copy.
- **Looks**: burned captions have four styles (classic white with outline, bold yellow capitals, neon glow, box on a dark panel), three positions (bottom, middle, top) and three sizes, with a short fade in and out; sizes scale with the video height. The selectors appear in the form when burning is chosen, and the same options exist for the agent client and MCP. Not done: custom colours or fonts, and word-by-word highlighting (only line timing is stored).
- **Caption a finished video**: `POST /api/captions`, the agent client's `caption_video`, the MCP tool `caption_video` (36 tools) and an "Add lyric captions" button on finished videos (it opens a small dialog: where, bottom by default or middle or top, look and size) burn the saved lyric lines (or lines you pass) into a NEW output, `captioned.mp4` with `lyrics.srt`; the original is never changed. It runs under the single-operation guard, starts from the uncaptioned copy when the video was captioned when made, and is free.
- Surfaces: Render Engine settings, preview summary, MCP tool text, skill, README. Not done: custom colours or fonts, a font check for non-Latin lyrics, and a preview of the caption look before rendering.

## 1.8.11 — Fork integration: token telemetry, single-slot writer, log clearing, video clips as idents

Integrates hellonearthis' fork revisions `5a14e85`, `98a1cc0`, `4c6d79b`, `a7cb9df`, `59f820d` (fork versions 1.8.9–1.8.13). Credit: hellonearthis.

- Writer token telemetry: each writer call prints `[tokens] <passage>: prompt + generated = total — N% context used, t/s` to the operation log. It only observes the response (`mmv/writer_usage.py`); no request or response is changed. The context percentage appears only when the llama-server context size is known from the launch arguments.
- Launcher: every preset now runs llama-server with `--parallel 1`. By default llama-server splits `-c` across four slots, so an 8192 context left each prompt about 2048 tokens — a truncation problem on lower-memory machines that larger-memory machines never see. The 16k-context, `--no-cache-prompt` and `-sps 0` settings remain opt-in with `-TuningPreset hellonearthis`. The launcher also keeps existing context/batch/image-token tuning from `settings.json` instead of resetting it, and no longer passes `--image-min-tokens` twice.
- Clear log: clearing now actually clears. During a run the current size of the operation, writer-service and Comfy-service logs is recorded and only newer output is shown, also after the run finishes; older validation reports stay hidden.
- Completed video clips can be attached as opening or closing cards (fork `59f820d`), grouped apart from idents in the picker. Preparation now accepts a completed video clip as well as an ident; the fork's picker alone would have been rejected with "Choose a completed ident".
- Not changed: the protected prompt scheme and pins. Not adopted: the fork's per-request `cache_prompt:false` rewrite (see COLLABORATOR_REVIEW.md).

## 1.8.10 — Voice/gender check for lip sync

- New advisory check in the lip-sync preview: when the vocals stem sounds clearly male (median sung pitch under 165 Hz) or female (over 250 Hz) and the main singer reads as the other gender, the editor shows a note under "Main singer" with a one-click button for the best-matching actor. It never blocks a deliberate choice, and it stays silent when the voice or the singer is unclear.
- Voice comes from the median pitch of the loud, voiced frames of an already cached vocals stem (it never starts a separation); at least 3 seconds of voiced audio are required. Quiet frames are ignored because stem bleed otherwise drags the median around. Actor gender is read from the actor's own description (pronouns and nouns must clearly favor one side).
- The preview carries it as a separate `voice` key (also in the agent client, MCP preview and skill docs). It is excluded from fingerprints and saved passage plans, so existing runs and resumes are unaffected.
- Real-song checks (htdemucs, CPU, mock-free): "In Heaven There Is No Beer (Hell) ++++" reads male at 126 Hz. "Let's Go Chill With Hodge(2)" has only about 3 seconds of female vocal; it yields too little clear voiced audio and is correctly left unsure (the ungated stem would have read male from bass bleed). A short female-only clip is therefore not yet verified positive; a longer female vocal is still to be tested.
- Not changed: the protected prompt scheme, pins and sealed-lips wording.

## 1.8.9 — Fork integration: style portability, offline-engine guard, run manager

- Version 1.8.9 deliberately skips past the fork's own 1.8.6–1.8.8 tags so the same number never names different code.
- Integrates hellonearthis's fork contributions `63f4826` through `73cbd4b` (reviewed in the [review record](COLLABORATOR_REVIEW.md)).
- **Styles:** export a style as JSON, import one (overwrite only when explicitly requested), duplicate a style, and preview the 11-axis style card. New `export_style` and `import_style` agent client methods, CLI commands and MCP tools (35 tools).
- **Offline-engine guard:** quoting and starting a production report a missing prompt writer, renderer, Laya reviewer or vision service in plain words before any work starts; the web app disables Start while one is offline. A configured launch command still counts as startable.
- **Run manager:** unfinished drafts and interrupted runs can be listed, resumed (local or Comfy SDK productions) or purged; finished videos can be deleted after a confirmation dialog. Added by us: runs that hold rendered clips are never removed by "purge all", and a single purge of such a run needs explicit confirmation, because those clips may already be paid for.
- **Faster, simpler UI:** service probes run in parallel; the vocabulary, library, outputs and settings modules use pure template functions; the vocabulary summary cards render when the summary is opened.
- Package export also redacts Windows-style home paths.
- **Local render wait:** a hung ComfyUI no longer freezes a run silently. The wait per local clip is now a setting (`render_timeout_minutes`, default 120, shown in Settings); 0 keeps the old unlimited wait for testing. This replaces the unlimited default from 1.8.4 and adopts the fork's two-hour default from `eeab8c0`.
- Protected prompts and pins are unchanged.

## 1.8.5 — Distinct independent dance movements

- Independent mode assigns contrasting bounce, lateral-step and torso-rotation
  movements, including distinct pause poses, rather than relying on instrument
  names and generic beat hints alone. New plans use choreography version 3.
- Prompt checks recognize actor names, reject copied movement-family signatures
  and dance leadership, and preserve references to a shared musical rhythm.
  Claude Code reviewed the repair; mock checks do not prove rendered distinctness.
- Existing group/off modes, protected prompts and pins remain unchanged. Start a
  new preview to use the repair; existing productions resume their saved plan.
- Repeated camera moves are recorded for a future planner fix at the owner's
  request; no camera behavior changed in this release.

## 1.8.4 — Local render timeout and agent song names

- Fixes a live-test failure: the original local H3 polling adapter requires a numeric timeout. The worker now passes infinity for unlimited local waits, without changing protected engine code. hellonearthis independently identified the same defect in fork revision `eeab8c0`; our adaptation preserves the owner’s unlimited-wait default.
- Agent song uploads preserve a safe basename, so song-name/date-time run folders work from agents as well as the browser. Other upload kinds retain generic filenames.
- Mock polling regression covers delayed history results after more than two hours; agent transport checks the retained song basename.

## 1.8.3 — Independent dancing

- Optional independent mode assigns each actor overall beat, drums, bass or vocals, automatically or by override. Each dances individually; group mode and defaults remain unchanged.
- Existing stem audio/analysis guides per-shot accents, pauses and intensity. Missing parts explicitly fall back to the overall beat; no separation or model download starts automatically.
- New production folders use the uploaded song name plus local date/time (with collision suffixes); old folders and resumed run IDs remain intact. Existing export-package naming was already present.
- Preview, API, MCP and agent skill expose assignments and fallback sources. Saved choreography remains bound to prompts on resume. New instructions are additive; protected originals and pins remain unchanged.
- Claude Code and Antigravity reviews are received and triaged in the [review record](COLLABORATOR_REVIEW.md); no blocking findings remain from either review.
- Owner approved the optional instructions. Mock verification is recorded separately; real same-song/same-seed render comparison remains pending.

## 1.8.2 — Vocabulary guide and accessibility review fixes

- Addresses Antigravity’s UI review: restores the missing vocabulary guide dialog and connects its navigation to the workspace.
- Gives overflow buttons readable dark-mode hover colors and category-specific accessible names; explains when unapplied workspace edits are discarded.
- Protected prompts and generation defaults are unchanged. Both Claude Code and Antigravity reviews are received and triaged in the [review record](COLLABORATOR_REVIEW.md).

## 1.8.1 — Vocabulary workspace and faster editing

- Integrates hellonearthis’s fork contributions through `1704454`: a dedicated Visual vocabulary workspace, updates limited to the edited summary card, and bounded summary chips with access to the full category.
- Groups advanced production controls into pacing, camera and render folds, each remembering its open state. Existing generation defaults are preserved.
- Fixes workspace navigation recursion and restores saved vocabulary before opening the workspace. Updates browser regression coverage and navigation labels.
- Windows launcher uses Python UTF-8 mode; protected prompts and fingerprints are unchanged. See [integration review](COLLABORATOR_REVIEW.md).

## 1.8.0 — BONK: dancing actors

- **Dance mode** (opt-in `dance_mode: group`, off by default; music videos): the cast dances in time with the song. The app reads the song's
  tempo and beats and tells the writer, per shot, how many beats it holds and where the downbeat falls; intensity comes from the song's
  energy (calm, medium, high). Up to three dancers per passage, chosen from whoever is cast there; an optional lead is followed by the
  others and is ignored in shots where the lead is off screen. Deliberate stillness, held poses and slowed movement are welcome
  choreography. The direction field (`dance_direction`) chooses the style of movement only.
- **Singing and dancing together**: a singer can also dance. Everyone who is not singing stays sealed while dancing; dancing never
  changes a mouth rule. Verified on real renders (a singing henchman with a dancing robot and pig, sealed).
- Dance planning is made once at preview and replayed on resume (a versioned, digest-bound plan, with the prompts bound to it), so a
  resumed production keeps the same choreography. A bounded wording check rejects prompts that leave a visible dancer without a body
  action or describe one as merely standing; style advice (follow the lead, downbeat accent, calm wording) is kept on the last try and
  recorded in `dance-advice-kept.json` instead of failing the run. The sealed-lips sentences are never treated as dancing.
- **Local renders are no longer limited by a one-hour wait**, and one status check that times out while a render is still running no
  longer ends the production (the render was already submitted; a hung proxy is retried, never resubmitted).
- Preview, API, agent client, MCP tools, skill and export package (`passage-plan-prompts.json` receipt, dance line in the README) cover it.
- Work shared with Codex, which built the passage-plan binding and resume prerequisites and adversarially reviewed the design and
  integration. Requests that do not use dancing produce byte-identical prompts, job files and fingerprints to 1.7.2 (golden fixtures).
- **Exceptions to the protected prompting scheme:** the writer, ident and sealed-lips text, the singing wording and the quality rules
  are unchanged. The owner-approved dance rules are an extra block appended outside the original engine, as the singing rules are.

## 1.7.2 — Subliminal message mode and sturdier Suno lyric parsing

- **Subliminal message mode** (opt-in, off by default; music videos): flash a chosen picture, or a few words rendered full-frame, for 1 to 12
  frames at times you give or spread over the song's downbeats. Applied after assembly with FFmpeg, outside the engine: frame count,
  duration and audio (copied, never re-encoded) are unchanged, and the untouched video is kept as `music-video-clean.mp4`. Photosensitivity
  guards: flashes are at least a second apart and stay clear of the first and last second. The quote shows the planned times; a failed flash
  leaves the finished video exactly as it was and records a warning. The export package notes it. Available in the app, API, agent client and
  MCP tools.
- **Suno lyric parsing and timing hardened** after an adversarial review: stray words heard far away no longer stretch a line across the song,
  lines never heard are placed in the gap beside the singing instead of at zero, curly apostrophes, accents and other scripts match, stage
  directions such as `[laughs]` are ignored, several markers on one line combine, `(x2)` and `(Chorus)` are ignored, real short shouts are
  kept while recognizer blips are dropped, and input sizes are capped. Regression tests cover each case.
- The prompting scheme, writer, ident and singing wording are unchanged.

## 1.7.1 — Studio-quality clips, prompting-scheme protection, rented-GPU guide

- **Studio-quality raw clips** (opt-in `clip_quality`: `standard` default, `prores`, `lossless`; Comfy SDK renderer, music videos only). The
  SDK path used to keep ComfyUI's built-in SaveVideo output (ordinary H.264, about 1.4 Mbps for a 736x416 clip) and the final video was
  rebuilt from it. Studio mode switches the workflow's VideoHelperSuite save node to ProRes 4444 (near-lossless, editor-friendly) or FFV1
  (mathematically lossless) with the audio inside, and takes that file as the passage clip; the final video is still encoded from it by
  ffmpeg at assembly. Files are much larger, so it is off by default. Clips are now named by what they really are (`video.mov`,
  `video.mkv`, `audio.flac`): the renderer's audio used to be FLAC data under a `.wav` name that many editors cannot open. If the job does
  not return the studio file, the standard clip is used and the run records a note. The shipped workflow and engine are unchanged.
- **Export package for editors**: raw clips keep their real extension; ProRes and FFV1 clips also get exact-length `_studio_trimmed` copies
  cut without re-encoding, and the timeline (`.edl`) points at them; audio files are true PCM WAV; the README has a media-format guide and
  says whether the prompting scheme is unmodified. Folders are named by title and date-time.
- **Prompting-scheme protection** (`docs/PROMPT_SCHEME_PROTECTION.md`): the writer and ident prompts, the sealed-lips scheme, the schema,
  validators, plan code, the singing wording and the quality rules are pinned in `mmv/protected_scheme.py` (line endings ignored). A fork
  that changes them sees an orange banner in the app (`GET /api/integrity`), exports say so, tests fail with a message that tells an agent
  to warn the person in plain words, offer an opt-in alternative and never edit the pins; `AGENTS.md`, `mmv/engine/PROTECTED.md`, the
  skill and `.github/CODEOWNERS` carry the same rule. `tools/update_protected_pins.py` refuses to run without an explicit owner flag.
- **Install guides**: `docs/GPU_CLOUD.md` for other rented GPU hosts (Vast.ai, Lambda, TensorDock, Paperspace, the big clouds), derived from
  the RunPod guide and reviewed by Codex; **not tested on any of them**. `PLATFORMS.md` refreshed. A rule that internal lab names are
  never published.

## 1.7.0 — Lip-sync mode and optional lyrics detection

Designed with Codex (read-only design review, `docs/LIPSYNC_DESIGN.md`). The owner approved the direction.

- **Third Facial movement mode, "Lip sync to vocals"** (`mouth_mode`: `sealed` default, `natural`,
  `lip_sync`; the old `silent_mouths` flag still works). Every passage stays sealed (rule, rigging tail
  and validators unchanged) except those whose audible slice carries about 0.75 s or more of sung lyric
  lines. Singing passages use a second prompt set: the natural-mouths system text, a new `SINGING_RULES`
  block, a cast block without sealed-lips rules, the singer's `lines` in the job, no rigging tail, the
  singer's picture tag and quoted words required in the shots that overlap singing (a deterministic
  shot-level check, since Laya has no singing question), and the audio sentence replaced outside the
  engine. Everything is outside `mmv/engine/`. The singing wording was approved by the owner.
- **Lyrics and singing in the score editor**: editable lyric lines with times, a main-singer choice (or a
  seeded pick; only the main singer sings: a passage where they are not on screen, or with no cast,
  stays sealed), and a per-passage summary of who sings. Plans resolve at preview and are stored in
  `prepared.json`, so resume replays them. Cached prompts are not reused for singing passages.
- **Optional lyrics detection** (Whisper, MIT, an optional add-on): detect timed lines from the vocals
  stem (when the stems add-on is ready; on the full mix otherwise), or paste lyrics and have them timed
  against what was heard (matching with uncertainty flags; unmatched lines get guessed times and are
  marked). Reuses an existing Whisper environment (`MMV_LYRICS_PYTHON`) and model files
  (`MMV_WHISPER_DIR`, default `~/.cache/whisper`); nothing installs or downloads without approval. Measured
  with large-v3: about 10.2 GB of VRAM and 46 s on a GPU or 164 s on a CPU for a 60 s clip, so the GPU is
  used only when the model fits in free memory. Smaller models are untested on singing.
- **Suno lyric format**: pasted lyrics may use section markers (`[Verse 1]`, `[Chorus]`, inline `[Chorus] la la`)
  and `(backing vocals)`. Markers never become lines or lower the match; each sung line keeps its section label (shown
  in the editor and passed to the writer), blocks marked instrumental, solo, interlude, break, drop or beat are not
  timed (a voice word such as "Vocal Solo" keeps a block sung), and repeated choruses stay in order. Detection also
  drops hallucinated blips under 0.25 s (Whisper invented "We'll be right back." at the end of a real clip). Tested on
  the owner's 57 s song "halp fren": 12 of 13 lines heard almost word for word, all 13 pasted lines timed.
  Parser written by Codex in a separate worktree and reviewed and merged by Claude Code.
- **Export production package** (owner request for the demo video, owner's friend edits it): an "Export package" button
  on each finished video, `POST /api/outputs/{run}/package` and the `export_production_package` tool copy the production
  into `MMV_HOME/exports/<title>_<date>_<time>/` (plus a zip; for example `halp_fren_lip_sync_test_2026-10-19_0409`): the finished video, every raw per-passage clip, the song, one prompt file
  per passage, the receipts (request, consent, render request IDs, quality and vision checks, plan, score, casting, logs),
  one still per passage, a README with a per-passage table (who sings, lyric lines used) and a checksum manifest. Keys and
  secrets are never copied (the stored keys are also redacted by value), home paths are shortened, only the four public
  starter actors' reference pictures are included, and a run with other actors needs an explicit confirmation and carries a
  warning not to publish it. Pure file copying; a first version written by a Claude helper and adapted by Claude Code.
- **Agents**: `detect_lyrics` and `align_lyrics` tools (32 tools; 33 with the package export below), `inspect_studio` kind `lyrics` (status,
  hardware, recommendation), and `mouth_mode`, `lyric_lines` and `singers` on `preview_production`.
- **Verified once on real H3 output** (operator GPU run, 2026-10-19): the owner's 57 s song "halp fren" at 0.3 MP with three public
  starter actors, Henchman #1 as singer and 13 lyric lines in Suno format. All six passages validated, rendered and passed the
  automatic motion/framing checks on the first render with no warnings (34 min including writing prompts); frames show the singer
  with his mouth open in the sung close-ups. Whether the lip movement matches the words is the owner's judgement from watching the
  video; stills cannot show it. It took four prompt-writer attempts per passage under the singing check. Backup singers are pinned on the roadmap.

## 1.6.14 — Stem quality option and hardware-aware agent guidance

- **Stem quality** (`stem_quality`: `standard` default, or `high`): high uses the fine-tuned
  Demucs model (`htdemucs_ft`, about 324 MB, 2 to 3 times slower). On the owner's songs it left far
  less stray sound in the vocals stem on one song (2% vs 23% of frames with quiet bleed),
  made no difference on two, and was slightly worse on one, so it is opt-in. The editor offers it
  with its own one-time download approval; guitar and piano always use the 6-stem model, which was
  noisier on vocals and is never used for them. Plans from the two settings were nearly identical
  on the tested song (19 shots each).
- **Hardware-aware recommendation**: `GET /api/stems` (and `inspect_studio` kind `stems`) now
  reports the GPU, free VRAM and RAM, per-model download sizes and a plain-language
  recommendation from measured figures; the editor shows the first line.
- **Agent installation**: the install guide, AGENTS.md, the skill and `AGENT_SETUP.md` now tell
  agents to mention instrument analysis, ask whether the user wants it, recommend a model quality
  for the detected hardware, include the add-on and model sizes in the single download proposal,
  and never install or download without approval.

## 1.6.13 — Stem separation on smaller GPUs

Measured with the real models on a 4-minute track: 4-stem, fine-tuned and 6-stem Demucs models
each need about 1.2 GB of VRAM (they work in chunks) and take 8 to 17 s on a GPU or about 71 s on
CPU (4-stem). Stem separation now uses the GPU when about 3 GB is free (Demucs documents 3 GB as
its minimum; it was 6 GB) and otherwise falls back to CPU. The editor's download approval states
the measured sizes (about 81 MB for the 4-stem model, about 53 MB for the 6-stem model). On real
songs the models agree on drums and bass but differ on vocals, so the default 4-stem model is kept
and the fine-tuned one is not added until listening shows a benefit. The editor test no longer
depends on whether Demucs is installed.

## 1.6.12 — Edit the score before generating, and follow an instrument

"Watch the song conduct" now happens before generation. Idea from a musician friend
of the owner; designed with Codex (read-only design review, `docs/SCORE_EDITOR_DESIGN.md`).

- **Score editor in Preview production**: a waveform (wavesurfer.js 7.10.1, vendored,
  BSD-3-Clause), the detected beat grid, energy curve and planned cuts, playback, and
  edits that cost nothing: shift the grid, choose which beat starts a bar, mute beats
  as cut candidates, and drag, split, merge and relabel sections. Press Re-plan to
  rebuild the cuts and cost; Start production stays disabled while edits are unplanned.
- **`score_edits` request field** (also for agents): applied to a copy of the cached
  analysis between analysis and planning, validated and quantized to frames. The
  original engine sources and the analysis cache are unchanged; edits enter the quote
  fingerprint, `request.json` and the approved `prepared.json` that resume replays.
  Previews now return `score` and `detected` (the unedited analysis), and
  `GET /api/waveform` returns bounded peaks computed with ffmpeg.
- **Instrument driver (optional add-on)**: `analysis_driver` (mix, drums, bass, vocals,
  other, guitar, piano) takes per-beat energy and section ranking from one stem while
  the beat grid stays from the whole mix. It needs the optional Demucs add-on (MIT,
  `pip install demucs`) and a one-time model download that is never automatic: it is
  approved with a checkbox in the editor (`POST /api/stems/prepare`). Separation runs in
  a subprocess, is cached per song and model, uses the GPU only if about 6 GB is free,
  and the stems are analysis input only; the video keeps the original audio.
  `inspect_studio` kind `stems` reports availability.
- **Limits**: the driver changes energy (cut density, camera, scale, montage style), not
  where cuts land; following an off-beat attack would need engine changes. Muted beats
  are not cut candidates but still count in bar counting. Hearing a single stem in the
  editor and a stem waveform are not built yet.
- Defaults unchanged: no edits and driver `mix` plan exactly as before.
- **Review fixes (Codex, read-only)**: edited section boundaries just after a downbeat could
  make the planner silently drop a sliver of the song (shifting picture against music), so
  edited plans must now cover the song contiguously or the preview is rejected with a plain
  message, and the editor snaps section edges to downbeats; beat 0 is now a valid bar-one
  choice; bar phase follows each beat's original index when a nudge drops edge beats. The
  editor also shows the first section at 0 s like the planner. Each has a regression test.

## 1.6.11 — Pseudo-random vocabulary keys

Integrates hellonearthis's fork commit `dc71556` (fork 1.6.11). Credit: hellonearthis.

- **Pseudo-random vocabulary generator**: a `seed:count` key deterministically
  keeps `count` entries per category and excludes the rest; quick bar (roll,
  apply, reroll, save, edit, clear) in the main panel, matching tools in the
  vocabulary dialog, saved keys kept in the browser, and the key stored with the
  project (`vocab_random_key`). Typed custom entries are preserved when a key is
  applied.
- Integration: draft-replacing paths use `showVocabCategory` (the earlier
  stale-text fix) so a replaced draft cannot be overwritten by editor text. The
  largest vocabulary category (269 entries) fits the 500-entry exclude limit. A key
  reproduces the same selection only while the built-in vocabulary lists are
  unchanged.

## 1.6.10 — Collaborator integration, part 2: module split, guide dialog, preview feedback

Integrates hellonearthis's fork changes after `3365943` up to reviewed head
`4e1cbb0` (fork releases 1.6.5 to 1.6.10). This delivery is the single version
bump covering both integration passes (the 1.6.4 notes below are part of it).
Credit: hellonearthis authored the changes below; the integration review fixed
the defects listed.

- **`app.js` split into ES modules** under `webapp/js/` (core, guides, library,
  outputs, production, project, settings, tooltips, vocabulary); the page loads
  `app.js` as a module and the server serves `/js/<module>`. Package data now
  includes `js/*.js`. This repository's two front-end changes (the
  `compact_prompts` request flag and the vocabulary-editor stale-text fix) were
  carried into the modules.
- **Preview/Start feedback**: spinners, busy state and status banners while the
  audio is analysed and the plan is built.
- **Accessibility**: light and dark theme contrast adjustments; sticky sidebar.
- **Vocabulary guide dialog** and `/api/vocabulary/guide`.
- **Local writer hint** when prompt validation fails with a local writer (context
  size `-c` or token limit may be too small).
- **Operation log** is cleared when a production starts; the log view keeps the
  active run.
- Configurable video encoders were added and reverted by the fork; nothing to adopt.
- **Silent mouths (owner decision):** the sealed-lips rule no longer depends on
  lyrics text being empty; it applies to every production unless Natural
  expressions is selected. The planned lyrics and lip-sync mode must switch it off
  itself. The rule text, rigging tail and validators are unchanged.

Integration fixes: the fork's module split broke its own browser tests (they read
module-private state as page globals), so tests now import the modules
(`isSseConnected` and `getSseSource` are exported read-only accessors). Codex found
that reopening a project dropped a saved custom vocabulary preset (the project was
restored before the preset list loaded); the catalog now loads first, with a browser
regression test that fails on the original order.

## 1.6.4 — Collaborator integration: vocabulary presets, service dock, token savings

Integrates hellonearthis's fork (reviewed head `3365943`, fork releases 1.6.2 to
1.6.4, including the previously deferred hardware dock `180b237`). Credit:
hellonearthis authored all of the changes below; the integration review fixed two
defects and adjusted one behaviour.

- **Visual vocabulary customizer**: `custom_vocabulary` per-video overrides,
  reusable presets in `MMV_HOME/vocabularies` (`/api/vocabularies`), a
  Customize vocabulary dialog, `docs/VOCABULARY_GUIDE.md`, agent client and two new
  MCP tools (30 total).
- **Live engine status dock**: `mmv/services.py`, `/api/services/status`, and
  `/api/events?once=true`. Probes only URLs from the user's own settings, with no
  proxy and short timeouts; results are cached per store.
- **Compact prompts (opt-in, off by default)**: a "Compact prompts (low VRAM/RAM)"
  checkbox and `compact_prompts` request field. Off, the writer and ident prompts and
  job messages are exactly the original full ones. On, it uses compact job JSON, keeps
  the system prompt stable across retries (feedback goes in the user message), and
  leaves out ident sections that do not apply to the chosen mode (about 62% of the
  ident prompt in standard mode, 44% in harvest, 8% in scenographic), and the vision
  check sees frames scaled to 512 px wide with replies capped at 160 tokens. Prompt
  files on disk are never modified.
- **Runtime savings (always on)**: single-pass multi-frame
  ffmpeg extraction, streaming hashes, parallel `/object_info` probes, and
  `--image-min-tokens 1024` in the Windows launcher `start.ps1` (not yet gated; it
  forces at least 1024 tokens per image for vision models).
- **Silent mouths no longer depends on lyrics (behaviour change)**: before, a request
  without lyrics text silently turned the sealed-lips protection off and the writer was
  told to describe lip and tongue articulation; found when a no-lyrics test run produced
  talking mouths. Silent mouths now follows the setting (default on) for every
  production; "Natural expressions" stays the explicit opt-out, for the planned lyrics
  and lip-sync mode to use.
- **Fixes made during integration**: stale text in the vocabulary editor could
  overwrite a loaded or reset preset (found by Codex review; browser regression test
  added); the initial SSE status probe ran on the event loop and now runs in a thread.
  The fork's own browser test expected a stale version string.
- The fork's rewritten release and verification history was not taken; this
  repository's records are kept. A real GPU comparison of full and compact settings
  is recorded in `docs/VERIFICATION.md`.

## 1.6.1 — Agent installation on RunPod and selected H3 workflows

Agent installation now includes a RunPod handoff for fresh, partial and existing
setups: discover/reuse components, persist private data and models, configure
SSH browser access, record restart steps and explain cloud rental charges.

For local H3, the installing agent must adapt and activate a private graph/map
for the selected model stack, checking loaders, precision, nodes, reference/audio
connections and runtime overrides. Filename-only model changes are not treated
as compatibility verification. These are agent procedures using existing workflow
support, not automatic conversion of arbitrary H3 variants by the shell installer.

RunPod and variant-specific end-to-end verification remain pending; installation
readiness must reflect the actual operator-approved test result. No Pod was
rented and no GPU generation was run for this release. The included skill,
installation entry points and platform notes link the procedures.

Codex prepared the guidance and release. The collaborator fork check found HEAD
unchanged at `78f31ae33f50a9578043d2af33ce05158603ab86`; existing substantive
review findings remain in [COLLABORATOR_REVIEW](COLLABORATOR_REVIEW.md).

## 1.6.0 — Batched pixel and optional vision quality checks

All passages render before pixel checks and one batch of free local retries.
The optional **Vision quality check (slower)** is off by default and judges
sampled single frames with a local vision-capable writer model and mmproj.
Pixel measurements remain authoritative for motion. Vision mostly warns;
unrequested framing devices in at least two sampled frames may use the same
single retry budget. Paid renderers are never automatically resubmitted.

Mondo swaps only services it owns: on direct H3 and SDK H3, close ComfyUI before
preview and configure its launch command. The SDK proxy stays operator-managed.
External ComfyUI is never stopped. Vision startup failure continues on pixel
checks with a visible warning. Per-attempt judgments and hashes in `quality.json`
support checkpoint reuse; `vision.json` records service notes.

SDK recovery now validates a saved local completion before querying the proxy,
so valid local media can survive proxy expiry without another submission.
Fingerprints, receipt bindings, path confinement, hashes, decoding and frame
counts guard that fast path; ambiguous submissions still require reconciliation.

Codex implemented phase 1 SDK local-completion recovery and the phase 3 vision
module with their tests, and completed orchestration tests, fixes and agent/docs
coverage. Claude Code implemented batched quality orchestration, service swaps,
preview diagnostics and UI wiring. The final fork check found HEAD unchanged at
`78f31ae33f50a9578043d2af33ce05158603ab86`; previously recorded review findings
remain unchanged. Final validation: 240 tests and 53 subtests passed, plus a $0
RTX 4090 production with both passages passing pixel and vision checks, no
retries or warnings, and a verified 11.5-second output. Hardware retry-path and
platform limits are recorded in [VERIFICATION](VERIFICATION.md).


## 1.5.0 — Motion and framing quality gates

A real Comfy SDK render produced a passage that was effectively a still image
inside a white pillarbox frame. The plan asked for a static camera, the writer
then described a motionless subject and static composition, and nothing checked
the rendered clip beyond its frame count. Production now guards both ends.

Before rendering, the music-video writer receives motion and framing rules, and
a deterministic check returns prompts that declare a still image, describe a
motionless subject under a static camera with nothing else moving, or use a
framing device such as a projected film or letterbox. Negations ("no motion
blur", "without black bars") are ignored, and framing devices the director asks
for are allowed. Cached prompts that fail the check are not reused. Laya is
unchanged: tested on the failing prompt, it could not judge motion confidently.

After each passage renders, Mondo measures frame-to-frame motion within each
planned shot, skipping cuts, and looks for uniform borders with a detailed
interior. Flat black edges are reported as inconclusive rather than failed. On
the free local renderers (`local_h3`, `comfy_sdk_h3`), a failing passage is
re-rendered once with a fixed new seed under its own segment ID, so SDK
receipts and resume stay exact; the better attempt is kept and the original
wins ties. Paid renderers are never resubmitted. Remaining problems are
assembled with a warning on the output card, in `/api/outputs` and for agents;
`quality.json` in the run records every measurement. Idents are not gated.
Original engine sources remain byte-identical.

Codex reviewed the design before integration; its findings on resume safety,
renderer allowlisting, per-shot measurement, dark-scene false positives,
negated phrases, creative intent and inspection errors were adopted. A
vision-model check with Qwen 3.8 27B judged single frames correctly in testing
but needs VRAM orchestration with ComfyUI, so it is not yet in production.

## 1.4.0 — Watch the song conduct

Every finished music video now has a synchronized musical score under its
player. It draws the per-beat energy curve, beat and downbeat ticks, each
passage colored by montage grammar, and the planner's cuts, with a playhead that
follows playback and click-or-drag seeking. A caption names the current
decision: section energy, grammar, shot scale, and whether the cut lands on a
downbeat, a beat, or splits a long hold. Opening idents shift the score onto
the video's clock. The view reads only saved run artifacts; it starts no
generation and costs nothing.

`/api/outputs/{run}/score`, the agent client and a new read-only MCP tool,
`read_music_score` (28 tools), expose the same data without local paths,
prompts or provider details. Cuts inside a passage are labelled as planned:
assembly guarantees passage boundaries, but a generated clip may not follow
every internal cut.

The idea came from collaborative ideation between Claude Code and Codex: Codex
independently ranked it first of three proposals for making the beat-driven
montage visible in a short demo.

## 1.3.0 — Open Actor Protocol 0.3

MMV now pins Open Actor Protocol 0.3.0 (`35902b1`), which adds the `jsonschema`
runtime dependency. Imported manifests are validated against OAP's bundled
offline schemas before signature checks; errors name the JSON path. The four
0.2 starter packages still validate, verify and import unchanged. New exports
declare OAP 0.3.0; older OAP readers may reject them.

Local actors can be exported as audition packages. Cast-only assets are listed
by hash but left out; a reference can be marked audition-cleared when it is a
prepared take. Imported actors still export only their preserved original.
Importing a portfolio or audition package now reports a clear "no reference
sheet" error instead of an internal failure when listed sheets are absent.

Role agreements cast an actor with this studio as Director. A draft binds the
actor's exact signed manifest and a generated casting call, and refuses rider
conflicts. The Director key is stored separately from the export signing key.
The studio can also sign as Agent for actors it exported. For outside actors, a
bundle goes to the Agent and their returned `agreement.json` is imported; only
valid signatures on unchanged terms are merged. The Actors tab, agent client,
five new MCP tools (27 in total) and the skill cover the workflow. Agent and MCP
signing requires explicit `confirm=true`. Agreements do not move money,
approve rider exceptions or establish signer trust.

The collaborator fork was checked at task start: its new revision `78f31ae`
merges this repository's 1.2.1 into the fork's pending hardware dock and labels
the result 1.2.2. Its dock and related changes were not part of this release and
remain pending a focused review (see COLLABORATOR_REVIEW.md).

## 1.2.1 — Starter installation and local library deletion

The Linux/WSL/macOS and PowerShell installers install the six public styles and
include a verified, signer-approved import of the four public starter actors.
The same step is available as `install-starter-assets`, including from wheels.
Noninteractive actor import requires explicit starter-signer acceptance; pending
actors are reported. Existing assets are preserved and the complete bundle is
checked before import. Only the authorized public assets are packaged.

Actor and style cards now offer confirmed local deletion. Active production
blocks deletion and stale previews are invalidated. Completed videos and exports
remain. Deletions survive restarts and setup reruns, including Daylight; starter
restoration is an explicit `--restore` action. Agent setup and public asset guides
now describe the integrated installation and library controls.

MCP now exposes 22 tools, including actor/style deletion, API profile creation,
selection/removal, bounded settings updates, public starter installation and
read-only API model discovery. Explicit confirmations protect destructive tools;
credentials can be imported from a designated process environment variable and
never appear in results. Active-profile removal restores manual configuration.
Existing stdio clients need reconnecting to load the new tool list.

## 1.2.0 — Agent installation and multiple API profiles

A repository installation handoff guides agents through hardware inspection,
model choices, explicit large-download approval, configuration and readiness.
Setup asks about existing API providers and documents how to configure compatible
writer/vision APIs or implement a reviewed video adapter. The new `inspect-api`
command performs a bounded, read-only model listing without generating, changing
settings, or following redirects. It does not establish inference compatibility.
Named private API profiles retain multiple accounts/models, with independent
writer, vision and supported hosted-video selectors in Settings and agent CLI
commands. Each selection uses its own credential; returning to manual settings
restores the previous configuration. No account/provider is used as an automatic
paid fallback. Keys from inactive profiles are also redacted from operation logs.
Existing providers, model/workflow defaults and paid-consent rules are preserved.
The collaborator fork remains at reviewed revision `764ca66`.

Thanks to Abandoned Muse for her inspiration and patience.

## 1.1.3 — Optional startup updates

Launch-time checks follow the installation's own tracked remote and branch.
Automatic installation is **off by default**; the UI reports available versions
with a repository link. A saved Settings switch enables installation at the next
launch, with clean fast-forward checks, staged wheel builds, preservation of
installed Comfy/MCP extras, ignored-file collision protection and re-exec into
the new code. Failures during installation attempt application-package recovery
and stop startup for environment repair. Active/interrupted work and local
changes prevent automatic replacement.

A checkout-wide runtime lease prevents another launcher updating a live app.
Source-only/wheel-only and native-platform limits are documented in `UPDATES.md`.
The collaborator fork was checked through `764ca66`; its separate hardware dock
is recorded for focused follow-up in `COLLABORATOR_REVIEW.md`.

## 1.1.2 — Additional aspect ratios

Music-video and ident shape selectors add 5:4, 4:5, 2:1, 1:2, 9:21, 3:1 and
1:3. The 9:21 option sits immediately after 21:9. Local H3 and its SDK path
use the selected shape with the existing model-grid dimension snapping.
This publication also includes the reviewed fork improvements listed below.
The launcher bounds shutdown time while live browser event streams are open.

## 1.1.1 — Reviewed fork usability and diagnostics

Reviewed hellonearthis's updates through `132c3d3` and integrated inline song
playback (including saved-project reload), bounded live operation events with
polling recovery, component-aware startup/worker errors and ComfyUI service logs.
Logs redact configured API keys. Single-operation enforcement, paid consent,
SDK receipt recovery and upstream OAP checks remain intact.

Settings adds a Laya device selector and a writer setup/tuning guide. Existing
model/workflow defaults remain in place. Optional hellonearthis presets preserve
16k context/batch/image-token tuning and CUDA/MPS CPU fallback, and the optional
reduced-flashing vocabulary retains the fork's smaller lighting/effects pools
without changing the default vocabulary or its golden fixture. The Windows
launcher exposes the alternate tuning and passes settings as UTF-8 JSON.

The fork's prompting guide is adapted to this public engine's actual controls.
Native Windows, real device fallback and GPU/paid generation require separate
operator verification. See `LOCAL_WRITER_TUNING.md` for preset behavior.

## 1.1.0 — Studio usability release

The browser tab now starts with the goose emoji: **🪿 Mondo Music Video**.
This minor release follows the SDK rendering integration, expanded vocabulary,
model controls, dark mode and resizable casting improvements delivered across
1.0.x. Six owner-reviewed styles are now available as optional presets in
`examples/style-presets`, with installation instructions and integrity hashes.
This asset-only addition leaves the application at 1.1.0.

## 1.0.16 — Resizable cast list

The music-video cast list can be resized vertically using its lower-right
handle, making larger rosters easier to browse. Its width follows the form,
and existing selections and multiple-selection controls remain intact.

## Optional starter cast — asset addition

Four owner-authorized actors are available in `examples/starter-cast` as signed
OAP packages: `animal_pig`, `robobabe1`, `henchman_1` and
`human_female_casual_01`. Import instructions and SHA-256 hashes accompany them.
All other roster actors remain private and ignored. Application behavior and
version remain 1.0.15; this adds optional assets and documentation only.

## 1.0.15 — Dark mode by default

The studio opens in dark mode, including forms, dialogs, file browsing and OAP
reports. A header toggle switches to light mode; the browser remembers the choice
and applies it before the page paints. Theme switching works even when browser
storage is unavailable.

## 1.0.14 — Actor card overviews

Actor cards show only the Identity section when a description includes structured
visual details. Full actor descriptions remain available for generation and OAP
export. Plain descriptions continue to display normally.

## 1.0.13 — Expanded SFW vocabulary and contributor thanks

Imports the owner-authorized vocabulary data into the public music-video pool,
with suggestive entries and incompatible mouth actions removed. Includes 269
settings, 233 subjects, 256 mechanisms, 227 lighting choices, 185 tones, 111
practical effects, 70 footage anchors and 31 costumes. Deduplicates tonal entries
and retains the existing camera bands, shot scales and mouth-rigging contract.
No private studio code, models, actors or runtime imports are added. The source
extraction manifest records authorization, source/published hashes and counts.

The original sampler, planner and casting code remain unchanged. The historical
golden plan is preserved with a frozen legacy vocabulary fixture, alongside a
new expanded-vocabulary golden plan. Cross-backend/seed checks verify unchanged
timing and actor assignments. Adds a README thank-you to hellonearthis.

## 1.0.12 — Reviewed model controls and setup guidance

Integrates selected improvements from hellonearthis through `c1db1c6`: installed
H3 model dropdowns, local path browsing, OAP help/inspection cards, Windows JSON
read lock retries, and four-worker testing with pytest-xdist.

Model changes now derive private copies of the active workflow and injection map,
preserving custom nodes, loader IDs and precision settings. Unchanged selections
do not override a newly chosen workflow. Ambiguous loaders and unavailable models
are rejected. OAP summaries use the upstream display name, signing public key,
content ratings and actual commercial rider without inferring permission.

The original model defaults, workflow, vocabulary and golden plan remain intact.
The expanded vocabulary and its direction guide are excluded from this delivery.

## 1.0.11 — Official Comfy SDK H3 rendering

Adds an opt-in `comfy_sdk_h3` renderer using the official Python SDK and a
loopback Comfy API v2 proxy. Reuses the original H3 workflow, planning lattice,
reference ordering, Laya review and frame-exact assembly. Assets transfer through
the SDK; no shared input/output folders are needed. Submissions are sent once,
with receipts persisted before dispatch. Known jobs and failed downloads can
resume through a new preview and consent step without rerunning the writer or
resubmitting existing generations. Unknown outcomes and failed/canceled/expired
jobs require operator reconciliation. Adds setup, UI, CLI and MCP integration
and a reproducible operator procedure in [COMFY_SDK.md](COMFY_SDK.md).

The direct local renderer remains the default. Real GPU verification through
the proxy remains outstanding.

## 1.0.10 — Reviewed integration

Integrates the fork’s draft persistence, diagnostics, Windows launcher, prompt
reuse, cache clearing and seed controls while retaining the original H3 workflow.
Restores the public actor metadata adapter. Passage reuse now requires matching
system instructions and job data; only saved validated prompts are recovered.
A new cache namespace avoids reusing entries created by the earlier fallback.

## 1.0.9 — Prompt cache clearing & variation seed reroll

- **Clear prompt cache**: Added `POST /api/cache/clear` endpoint and a `#clear-cache` button in the UI under *Timing, credits & content*, allowing instant deletion of cached passage and ident prompts and recording `cache_cleared.json` so previous runs are not picked up on subsequent generations.
- **Reroll variation seed**: Added a `🎲 Reroll seed` button (`#reroll-seed`) next to the variation seed input to quickly generate a new random seed, rerolling shot cut points, grammars, and camera movement.
- **Cache invalidation integration**: `find_cached_passage_prompt` now respects `cache_cleared.json` timestamps, ensuring runs after a cache clear always regenerate cleanly with new settings.

## 1.0.8 — Instrumental track lip-sync suppression & rigging auto-injection

- **Instrumental tracks / no lyrics**: When no lyrics are provided in the production request, lip-sync suppression is automatically disabled so prompt validation does not fail with "Subject Rigging block is missing (lip-sync suppression)".
- **Rigging tail auto-injection**: When lyrics are present and silent mouths is enabled, any missing boilerplate rigging tail is automatically injected into the detailed description before validation, preventing writer omissions from failing the run.
- **UI clarifications**: Updated the facial movement settings description to make clear that lip-sync suppression is applied when lyrics are present and skipped on instrumental tracks.

## 1.0.7 — Passage prompt caching, progressive saving & production resumption

Introduces progressive prompt disk persistence and persistent hash-keyed passage caching
in `store.home / 'cache' / 'prompts'`. When a production is restarted or resumed, completed
and Laya-validated passage prompts are retrieved instantly without re-invoking the writer
LLM or prompt reviewer. Recovers completed segments across prior interrupted runs and adds a
"Reuse validated passage prompts" UI toggle to force full regeneration when desired.

## 1.0.6 — User-friendly upload validation & contextual studio error logs

Enhances input validation in `mmv/pipeline.py` to check for missing audio files, invalid
reference image paths, harvest references, and ident paths prior to directory traversal,
replacing cryptic sandbox errors ("Path is outside its data directory") with clear,
actionable messages ("Upload a song first"). Enriches studio event logs with production
kind context (`Preview failed (video)`, `Start preparation failed (video)`).

## 1.0.5 — One-click operation log clearing & suppression

Adds a dedicated "Clear log" button (`#clear-log`) to the studio header alongside
"View log" and "Copy log", resetting the live diagnostic log display, clearing client
session records, wiping `studio.log`, and suppressing historical runs prior to the clear
timestamp (`POST /api/log/clear`).

## 1.0.4 — Windows start script with llama.cpp model selector

Introduces `start.ps1`, an all-in-one PowerShell starter for Windows that automatically
discovers local GGUF models in `C:\llamaCPP\models`, pairs multimodal vision projectors (`mmproj`),
configures the local writer service in Mondo's settings, manages or verifies `llama-server.exe`,
and launches the studio server with automatic browser navigation.

## 1.0.3 — One-click operation log clipboard export

Adds a dedicated "Copy log" button (`#copy-log`) to the studio header next to the log viewer,
allowing operators to copy the full combined diagnostic output (client session notices,
background worker tracebacks, Laya validation reports, writer service output, and server
event logs) to their system clipboard with one click.

## 1.0.2 — Diagnostic operational logs & CSP inline script compatibility

Resolves browser extension inline script blocks by relaxing Content-Security-Policy
script/style directives, expands the `#show-log` diagnostic viewer with unified client session
activity and server event logging (`studio.log`), surfaces validation and writer errors
directly in the UI log pane, and keeps the log toggle accessible at all times.

## 1.0.1 — Project reload persistence, comprehensive UI tooltips & Windows UTF-8 fix

Adds automatic current project draft persistence across page reloads (persisting active
panel, form fields, details expansion, log visibility, and uploaded song/references via
`/api/project` and `localStorage`), accessible WCAG 1.4.13-compliant studio tooltips for
all interface controls, and UTF-8 process encoding for Windows background jobs.

## 1.0.0 — Mondo Music Video

Complete song-to-video workflow with automatic beat/downbeat, energy and section
analysis, seeded musical montage planning, the Mondo LLM writer, GPU Laya prompt
review, standard local H3 and hosted renderer adapters, frame-exact assembly,
OAP actors, styles/harvest, credits/idents and optional Topaz export. Includes
portable setup, verified opt-in Laya downloads, agent CLI, MCP server and skill.


## 0.1.1 — agent operation and first public GitHub release

Optional local stdio MCP server, a bundled Mondo Music Video agent skill, and a
JSON CLI helper. Agent calls use the same preview/consent, single-operation and
OAP paths as the browser. Local-only endpoints, no submission retries, and no
credential-writing or arbitrary shell tools in the MCP server.

The application remains a development preview with the external verification
limits recorded below. Public source includes no models, actors, credentials or
private studio history.

## 0.1.0 — initial development preview

Independent public application with music-video production, automatic final
assembly, reference-image actors and built-in OAP, styles/style harvesting,
credits/idents, output playback/download and optional direct Topaz export.

One active operation, explicit previews/consent, local/API renderer adapters,
platform setup launchers, system doctor and opt-in verified model-download helper.
No private studio implementation, models, actors or production data are bundled.

This is a development preview. See VERIFICATION.md and PLATFORMS.md for the
automated checks and external/platform checks still outstanding.
