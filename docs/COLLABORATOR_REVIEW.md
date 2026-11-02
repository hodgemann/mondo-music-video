# Collaborator review record

## Fork `0d29dcb` integrated (release 1.12.3, 2026-11-02)

Previous reviewed head `7781545`. New commits by [hellonearthis](https://github.com/hellonearthis): `5c5b5b6` (narrative acts), `5cae552` (Dismiss / Purge & Start Fresh), `9853212` (H3 reference and subject tag normalizer), `20e62ee` and `0d29dcb` (studio direction guides). Reviewed in an isolated clone and a read-only Codex pass (`gpt-6.1-sol`, low effort; the model is the CLI request, not a confirmed answer).

- **Narrative acts: adopted.** Opt-in by nature: only presets or requests that carry acts change anything. Fixed: saving a preset from the GUI replaced the whole file and dropped its acts; a save that does not mention acts now keeps them. Remaining caveat: within a passage only setting, costume and subject type are held, so an act can vary mechanism or tonal register between shots where a plain passage shares them. Not verified on a real render.
- **Dismiss / Purge: adopted with a fix.** The fork's endpoint calls `Jobs.reset()`, which exists in the fork's `mmv/jobs.py` but not here, so reset would have raised after the purge had already run. `Jobs.reset()` is added. Purge only checked for `output.json`; it now also keeps any run with an assembly source or renderer work (clips, request receipts).
- **H3 tag normalizer: adapted, off by default.** It rewrites the prompt at render time for every cast video, after the prompt checks, which the owner's defaults do not allow silently. It is now the `h3_tag_normalizer` setting (default off, agent-visible) and the cast is only passed when it is on, so resume fingerprints for submitted Comfy-SDK passages are unchanged by default. Fixed in the function: the colour-word guard never matched (every colour has three or more letters), a shorter actor name could consume part of a longer one ("Ann" / "Ann Marie"), and any `<Picture N>` anywhere counted as a correct binding. The renderer's text still differs from the saved, checked prompt when on; that is why it stays opt-in.
- **Docs and example preset: adopted**, with the normalizer described as optional. `vocab-worlds.js` brace fix: already present here. Fork version labels 1.12.3–1.12.5 map to our single 1.12.3.
- No paid or GPU work, no protected-scheme files touched (`protected_scheme.check()` is clean).

## Fork `7781545` reviewed (documentation integration, 2026-11-01)

The task-start check found exact head `77815455c9bab70f6619fe8d2072cd8661631e20`. Since last reviewed head `aa1e06b`, the new authored commit is `6ee7add8403ba2dfff888cb36cf2fae5b5f5a675` by [hellonearthis](https://github.com/hellonearthis): a production-queue OpenSpec feature, glossary and behavior-report entries, and five executable checks. Merge `7781545` also carries upstream `0a1bdfc` and older fork-side differences; it was reviewed in an isolated clone, not merged into this checkout's history. This is a documentation and test integration, so application version 1.12.2 stays unchanged.

| Contribution | Decision and evidence |
| --- | --- |
| Queue feature, glossary and report | Adopted with corrections against `mmv/production_queue.py` and `webapp/mondo_web.py`. A new ticket stays pending until `/api/queue/start`; a paid request without quote consent cannot be queued; `hold_reason` runs against the current plan at dispatch. `new_ticket` creates a value and `save_ticket` writes it atomically. `resume_ticket` requeues a saved run ID, while `_plan_resume` checks complete prompts and `resume_blocker` checks fingerprint and receipts before reuse. The fork text claimed immediate dispatch, an admission-time held state and unconditional prompt/clip reuse. |
| OpenSpec executable checks | Adopted, with names and comments limited to what they assert. They cover cost holds, paid-stop propagation, movement, interruption/requeue and cancellation; the existing mock queue tests cover API dispatch and consent. The Gherkin scenarios remain specification text, not a step runner. |
| Merge-only differences | Kept current code. `mmv/production_queue.py` matches the fork exactly; `mmv/jobs.py` adds `Jobs.reset` without a caller; the fork's `mmv/takes.py` restores an ambiguous segment-index/seed overload previously rejected in favor of one explicit signature; `mmv/writer_json.py` accepts `divergent`, while the validator's declared answer is `contradicts_style`. The extra `webapp/js/vocab-worlds.js` braces change handler nesting and have no matching new behavior test. These are older fork differences, not part of `6ee7add`; adopting them would change already reviewed behavior without evidence for this task. |

Claude Sonnet 5.5 independently reviewed the exact in-repository files through the guarded read-only launcher (receipt in the ignored collaboration folder). Its first pass could not read the isolated `/tmp` clone; the second identified gaps in cancellation coverage, the difference between Resume and Start, the ticket-creation timestamp used by the paid-stop guard, and a stale `divergent` label in REPORT-38. The documentation and focused tests now reflect those findings. The SHA-256 claim was confirmed in `mmv/pipeline.py`; the existing mock API tests cover queue start, cancellation and saved-run behavior beyond the direct OpenSpec checks.

Verification: `tests/test_openspec_bdd.py` and mock queue tests in `tests/test_public_app.py` passed. No real paid or GPU queue run, browser session, commit, push or publication was part of this review.

## Fork `aa1e06b` reviewed (release 1.12.1, 2026-11-01)

Commit `4d4fb16`; merge `aa1e06b` of our 1.12.0 was not adopted as history. Adopted: rewrite steering, `<think>`/fence extraction, Laya style advice, pre-compiled World matrix, OpenSpec documents and test. Adapted after a read-only Codex review: dropped a `vocab-worlds.js` hunk that failed to parse; `laya_style_feedback` looked for `divergent` while the validator answers `contradicts_style`; extraction now refuses a reply with a further object after the first; steering hidden for idents, where it has no effect (owner decision: an unknown World falls back to default vocabulary without a message); saved Worlds listed in the GUI; `replan_segment_vocabulary` keeps one explicit signature. Omitted: `Jobs.reset`, which nothing called. Open: the BDD test checks document structure and some functions, not the feature steps.

## Fork `ffb3c50` reviewed (release 1.11.6, 2026-10-31)

The task-start check found exact head `ffb3c50c`, one authored commit after last reviewed `7681740` (`ae61fb5`) plus merge `ffb3c50` of our 1.11.4 and 1.11.5. Claude Code (Opus 5.5) coordinated and integrated; Codex reviewed read-only through the plugin (model not reported by the CLI). The owner was told plainly that this changes prompting behaviour and chose it as the only behaviour of Write new prompt, without an extra option.

| Contribution | Decision and evidence |
| --- | --- |
| Rewrite re-rolls passage vocabulary (`replan_segment_vocabulary`) | Adopted as the behaviour of Write new prompt, adapted. The energy, Thematic Worlds and departure passes hash each passage's list position, and the fork passed them a one-item list, so every passage behaved as the first; they now receive the whole list and only the chosen passage is kept. The excluded terms are now the passage's own, not also the terms just drawn. |
| Rigging re-pick | Not adopted. The contribution describes setting and motif; rigging belongs to the sealed-lips scheme and nothing asked for it to change. |
| Saving the changed plan | Adapted. The fork updated `plan` in `prepared.json` but not its `segments`, and saved a plan for idents too, which never replan. All saved copies now change together, for video passages only. A failed rewrite also restores the plan copies and the passage's writer job. |
| Older prompt versions | Added. In the fork, going back to an older prompt kept the newer vocabulary and lost the original pairing and the variation seed. Each version now stores `vocabulary` and `variation_seed`, and `select_prompt_take` restores them. |
| Ident rewrites and "guaranteed" wording | Corrected. The fork's documents said idents re-roll and that a new term is guaranteed; idents have no planned vocabulary, and `VocabSampler.pick` repeats a term when the pool has no other. The GUI text now differs for idents. |
| Optional `seed` (API, CLI, MCP), tooltip and confirmation text, test idea | Adopted. |
| Merge `ffb3c50` | Not adopted, with reasons: two stray braces make `webapp/js/vocab-worlds.js` fail to parse (`node --check`), `docs/RELEASES.md` holds a conflict marker, the older README and package descriptions would replace current ones, and `Jobs.reset` still has no caller. Remaining for the fork: fix that JavaScript. |

Kept from the fork, for the owner to reconsider if wanted: a thematic passage draws its own new anchor, while the planner shares one anchor across a section, so a rewritten passage can differ from its neighbours. Remaining: no real before/after renders; a new scene can sit awkwardly with a passage's storyboard panel or dance/instrument references, and only a render would show it. `writer_jobs/` records the latest writer call and is not switched by selecting an older version. Codex's second pass also found, and we left as is: a retry after a failed rewrite can overwrite that version's archived earlier writer files (`begin_prompt_rewrite`, older than this release), and a request with no `kind` passes `prompt_block` then fails in the worker (the app always saves `kind`).

## Fork `7681740` reviewed (release 1.11.5, 2026-10-28)

The task-start check found head `7681740`, two authored commits after last reviewed `c36c89f` (`60bc3fc`, `7681740`), plus merges of our 1.11.2 and 1.11.3. The patch from our 1.11.3 touched only `webapp/index.html` and four modules in `webapp/js/`, plus the long-standing `Jobs.reset` difference in `mmv/jobs.py`, again not adopted (it has no caller). Claude Code (Opus 5.5) coordinated and integrated; Codex (GPT-6) reviewed read-only.

| Contribution | Decision and evidence |
| --- | --- |
| Functional refactor of `storyboard.js`, `tooltips.js` and the scoring/pool code in `vocab-worlds.js` | Adopted. The tooltip placement and storyboard panel operations were checked branch by branch against the old code and behave the same. Prompt scoring differs only where a prefix-matching keyword precedes an exact match (exact now wins); `toSorted` needs current browsers (Firefox 115+). |
| Panel auto-collapse `userOpened` guard (`panel_progress.js`) | Adopted. Codex confirmed the old focus-out path closed a completed card the user had reopened, and that `auto_collapse_panels` is still respected. |
| Chip states kept in pool data; added terms start pinned | Adopted. Before, chip states lived only in the page and any redraw reset them; an added term was Included, which Guided mode does not send. |
| Pool countdown (`computePoolCounts`, `formatPoolStatusText`) | Adopted with a fix: Codex found that a chip change making a pool short updated its text but not its Borrow button; the pools are now redrawn when the shortage flips. Codex also noted that "in pool" starts from the pool's declared size (e.g. 14 Settings) rather than the four listed terms, so excluding all listed terms still shows terms in the pool; deferred, because counting only listed terms would mark every default pool as low. Remaining: decide whether declared sizes should reflect the catalogue that can actually be applied. |
| "World selection persistence" | Adapted: Codex found the fork did not restore the applied worlds (initialisation still used the defaults, and Apply then overwrote the saved selection). Apply now saves the world list and initialisation restores it, rebuilding older drafts from their saved active names. |
| Term chip tooltip and state title | Restored: the fork removed the chip's "Click to cycle" help and its Included/Pinned/Excluded title. |

A browser test covers chip states, countdown, added-term pinning, Guided compilation and world restoration. Firefox was not tested here.

## Fork `c36c89f` reviewed (release 1.11.1, 2026-10-28)

The task-start check found head `c36c89fc7f2fbfa1f3d4139f5fa7b3ca05225dad`, one authored commit after last reviewed `7367470`, built on the fork's 1.10.31 (not our 1.11.0), so it was ported by hand. Because it touches the protected prompting scheme, the owner was warned first and approved the opt-in approach below. Claude Code (Opus 5.5) coordinated and integrated; Codex (GPT-6) reviewed read-only.

| Contribution | Decision and evidence |
| --- | --- |
| Prompt version history (`prompt_takes.json`, version selector) | Adopted, adapted to 1.11.0's rules: reads are pure (the fork's getter created the file on GET), and a hand edit that did not pass is kept but cannot be selected. |
| Prompt reroll (`reroll_prompt_worker`) | Adopted as behaviour, not as code. The fork copied the worker's prompt stage (system composition, singing/dance/instrument branches, validators, Laya, retry feedback) into `mmv/takes.py`, and added a writer instruction asking for "a fresh, distinct variation". A copy of protected behaviour drifts silently, and the new instruction changes the writer's wording, so both were left out. `mmv/worker.run(rewrite=…)` runs the existing stage for one passage instead, skipping the prompt cache in both directions and stopping before rendering. Temperature 0.7 already yields a new prompt. The fork also used current settings over the production's and ignored `bind_prompts` failures; the worker path uses the prepared settings and reports them. |
| Manual prompt edit | Adapted: the fork saved edited text as the passage prompt with no checks, which could break the sealed-lips scheme. Edits now pass through the same stage with `candidate` (rigging sentence added for sealed passages, `validate_prompt`, quality, lip-sync/dance/instrument checks, Laya) and are used only if they pass. |
| Paid writer | Added: the fork's reroll had no consent for an API writer. Rewrite now needs `accept_writer_cost` when the production's writer is an API service, with a per-passage estimate. |
| Agent client/CLI/MCP | Adopted with the new names `rewrite_prompt` and `edit_prompt` (confirm guards) and `select_prompt_take`. |

Remaining: real same-song, same-seed renders comparing a rewritten or edited prompt with the original have not been made.

## Fork `7367470` reviewed (release 1.11.0, 2026-10-28)

The task-start check found head `7367470`, three authored commits after last reviewed `bdd6973` (`8356eb2`, `355cc26`, `7367470`), plus merge `0a91ce6` of our 1.10.28, whose only differences from our tree are the long-standing `Jobs.reset` and a harvest-card call in `production.js`. Fork content was applied to our `ace7114` from an isolated clone. Claude Code (Opus 5.5) coordinated and integrated; Codex (GPT-6) reviewed the patch and our current source read-only through the Codex plugin.

| Contribution | Decision and evidence |
| --- | --- |
| Prompt character count (`8356eb2`) | Adopted as is. |
| Full-panel Prompts & clips view (`355cc26`) | Adopted. The dialog and its styles are replaced by a sub-view of Finished Videos; videos are unloaded when leaving it. |
| Reroll, takes history, final re-encode (`7367470`) | Adopted with fixes. Codex found the critical one: the reroll endpoint started a render without a quote or consent, and `comfy_sdk_h3` can submit a proxy job (`webapp/mondo_web.py` start/resume require a quote and `consent=true`). Reroll is now limited to `local_h3`, needs `confirm`, and the breakdown reports `reroll_blocked`. Both reviews found: reroll overwrote the run's `render-graph.json`/`local-request.json` (now per take); the worker overlaid current settings on the prepared ones (now prepared settings only, as `mmv/worker.py` does); selecting an older take kept the newer take's seed and receipt fields (each take now stores its render record); GET `/prompts` created `takes.json`/`final_takes.json` (reads are now pure); re-encode silently swallowed subliminal/caption errors and the caption `burn_error`, then kept stale effect records (now reported and recorded); unknown `selected_takes` were ignored (now refused); the take dropdown wrote `renders.json` while its notice called the choice pending (now preview only). We confirmed the re-encode itself follows the single-encode rule: `final_assembly.assemble`, `subliminal.apply_to_run` and `captions.apply_to_run` each build their variant from the saved recipe of original clips. Codex also reported that `-vN.mp4` downloads would fail; that did not reproduce, since the fork's `captions.downloads` lists `final_takes`, and a test now downloads one. Codex's second pass on the integrated tree found that a re-encode saved each take choice before assembling, so a failed encode or a later unavailable take left changed active takes, and that a missing original final would be renumbered as Version 1; choices are now checked together and saved only after the new video is assembled, and a re-encode with neither the finished video nor a saved version list is refused. It confirmed the MCP argument order. Agent docs and the skill were updated. |
| `Jobs.reset`, harvest-card call (merge) | Not adopted, as in 1.10.24–1.10.26: `reset` has no caller, and 1.10.26 already shows the harvest card once per operation, including after a reload. |

Remaining: reroll for Comfy SDK/cloud productions would need a per-passage quote and consent; a rerolled passage does not run the vision quality stage.

## Fork `bdd6973` reviewed (release 1.10.26, 2026-10-27)

The task-start check found exact head `bdd6973221af51932549eb8ee743429e69368e06`, five authored commits after last reviewed `d376164` (`9fb0aac`, `b00add2`, `4560bfc`, `e4f747b`, `bdd6973`). The fork had not merged our 1.10.25, so those commits were cherry-picked onto our `36ef123` in an isolated clone; three conflicts were in lines 1.10.25 had already adapted. Claude Code (Opus 5.5) coordinated and integrated; Codex reviewed the patch and our current source read-only through the Codex plugin.

| Contribution | Decision and evidence |
| --- | --- |
| Vision guide dialog and `GET /api/vision/guide` | Adopted. Codex found the installed-package fallback would 404 (guide not in package data) and the guide called Settings tab 12 (it is 09); both fixed. Codex's second pass found the guide said a quality failure always re-renders; it now says only free local renderers retry once and paid renderers are never resubmitted. Codex also found the clickable service-card `<div>`s were mouse-only; they now have `role="button"`, `tabindex="0"` and Enter/Space. Agents read the guide with `inspect_studio(kind="vision-guide")`. |
| Harvest result card and `GET /api/styles/{id}` | Adopted. Codex confirmed `status.kind` and `status.result.style` are produced for harvests (`mmv/jobs.py`, `mmv/pipeline.py`). Its second pass found the card appeared only on a live state change; it now also appears after a reload, once per operation. |
| Harvest dict/list coercion in `mmv/worker.py` | Adopted as a `harvest_text` helper with a unit test. The pinned `mmv/engine/style.py` parser is unchanged; `protected_scheme.check()` stays `[]`. The fork's extra `from . import runtime` was redundant and dropped. |
| `pattern` escaping (`[a-z0-9_\-]`) | Adopted. Browsers compile `pattern` with the `v` flag, where an unescaped trailing `-` makes the expression invalid and the check is skipped. |
| Right-click reference menu removed | Adopted. This is the collaborator's own 1.10.24 menu; the visible Remove button remains. The leftover context-menu cursor and README/interface-guide mentions were removed. |
| Full-width style cards | Adopted. In 1.10.25 we omitted a first-card-only full-width rule because list order does not single out a style; this version applies one column to every card, which has no such problem. |
| Prompts & clips viewer, `GET /api/outputs/{run}/prompts` and `/clips/{seg}` | Adapted. Codex found: the clip route would serve any `.mp4` path in `renders.json` without a check; `.mov` renderer clips were reported available but refused; and the length shown was the renderer input duration rather than the trimmed passage. The logic moved to `mmv/score_view.py`: one rule decides availability and serving (only the exact video file recorded for that passage, `.mp4`/`.mov`/`.webm`, inside the data folder or the configured `comfy_output` folder, where `local_h3` leaves its clips), and length is `trim_frames / fps`. Codex's second pass found that a recorded path alone did not bound disclosure (now fixed by those roots) and that captioned copies, which keep no prompts, showed an empty viewer; they now follow `source` to the original run. Current final assembly does not create `assembly/work/segNNN.mp4`, so that lookup was dropped. Response keys are the fork's. Agent parity: `read_output_prompts`, `output-prompts`. |
| `mmv/jobs.py` `reset` difference in the fork tree | Still deferred, for the reasons recorded at `d376164`; untouched by these commits. |
| Fork version 1.10.30 | Not adopted; this delivery is 1.10.26 under the one-patch-step release rule. |

No fork history merge, private asset import, protected-prompt edit, paid/GPU work, commit or push was part of the review.

## Fork `d376164` reviewed (release 1.10.25, 2026-10-27)

The task-start check found exact head `d376164fb86d6694b6453689bc330272b5fe498f`. An isolated clone was compared with last reviewed `7047aa3dfb95c16f9cdcfd20cc096a93f37b2763` and our `1e6d93a`. The fork merged our 1.10.24 in `cb34d1f`; its new authored commits are `9ed0aac`, `84763ab`, `fe7bfe3` and `d376164`. Claude Code Sonnet 5.5 reviewed their public diff read-only; Codex reviewed source and integrated the compatible changes.

| Contribution | Decision and evidence |
| --- | --- |
| Reference tooltip footer and thumbnail | Adopted. The removal hint now mentions the visible Remove button as well as right-click, and the existing text-node tooltip renderer preserves the thumbnail without HTML injection. |
| Actor portrait preview and description count | Adopted. The fork's selected filename went into `innerHTML`; it now enters a text node, while the preview image uses a local object URL cleared on reset/change. The count is shown only for editable local descriptions. |
| Actors & OAP accordion cards | Adopted with section headings retained outside the buttons, a repeat-initialization guard and independent fold controls. Folding does not bypass OAP inspection, signer acceptance or role-agreement consent. |
| Style 11-axis card toggle | Adopted with the existing `handle()` action wrapper retained. The fork's `#style-list > article:first-child` full-width rule was omitted because list order does not identify a featured style. The existing export path still contains the card data. |
| `mmv/jobs.py` `reset` difference in the merged fork tree | Deferred again: it is outside these new authored commits, has no new caller, and changes operation-state handling rather than this library UI. A separate workflow review would be needed. |

No fork history merge, private asset import, protected-prompt edit, paid/GPU work, commit or push was part of the review.

## Fork `7047aa3` reviewed (release 1.10.24, 2026-10-27)

Reviewed an isolated clone at exact revision `7047aa3dfb95c16f9cdcfd20cc096a93f37b2763`, compared with last reviewed `1e0978748cbb3f9f23575a1e7c49bba19dd4708b` and this repository's `e074c50`. Merge commit `822dcc8` brought upstream releases through 1.10.23 into the fork. Its two new authored commits are `132074d` and `7047aa3`. Claude Code Sonnet 5.5 reviewed an exported public diff in the ignored collaboration area after its isolated-checkout access was denied; Codex reviewed the patch, current code and tests. The first Claude attempt could not reach its API from the sandbox; the retry could not read `/tmp`. Neither attempt supplied a code finding.

| Contribution | Decision and evidence |
| --- | --- |
| Individual reference-image removal | Adopted. Added a visible Remove button for keyboard and touch use alongside the fork's right-click menu. Removal updates form progress and the saved draft; clearing the final Style Harvest image restores the required-file state. |
| Cast picker spacing | Adopted. The one-pixel item margin keeps adjacent cast choices visually distinct. |
| Dynamic Needs tooltips and required-field color | Adopted. The labels describe only form inputs; preview, quote, and start consent remain authoritative. |
| Dark blue/gold palette and instrument tooltip | Adopted. The instrument copy describes the existing feature and does not start stem separation or model downloads. |
| `mmv/jobs.py` `reset` difference in the merged fork tree | Not part of either new authored commit and not imported. That method has no new caller in this task; adding operation-state behavior needs its own workflow review. |

Claude's successful review identified missing keyboard access to the fork's menu, stale progress after individual/clear removal, weak menu focus, duplicated missing-field conditions, an inaccessible Needs tooltip, awkward hard line breaks in tooltips, and a few old dark-palette colors. The integration fixes those in the current tree. Its warning that two active controls would show white text on gold did not apply: both already had dark-mode overrides; their older green overrides were brought into the new palette. The fork's `user-select:none` was also removed from filenames so they remain copyable. Agent preview requests already accept explicit reference ID lists; omission removes an image before the next quote, while panel progress remains GUI form guidance and is not a second quote validator.

No fork history merge, private asset import, protected-prompt edit, paid/GPU work, commit or push was made during this review.

## Fork `1e097874` reviewed (release 1.10.21, 2026-10-26)

Reviewed an isolated clone of [hellonearthis](https://github.com/hellonearthis)'s fork at exact revision `1e0978748cbb3f9f23575a1e7c49bba19dd4708b`, one commit after last reviewed `db7bec7`. Claude Code Sonnet 5.5 supplied a bounded read-only peer review; Codex checked the patch and integrated it. The commit adds actor inline editing, a wider actor grid, an OPP guide, dark selection contrast and version assertions.

| Contribution | Decision and evidence |
| --- | --- |
| Inline actor description edit | Adopted with agent client, CLI and MCP parity. Restricted to locally created actors: changing the local description of an imported signed OAP actor would disagree with its preserved original export. Empty descriptions are refused. A visible Edit button makes the action keyboard accessible; double-click remains. |
| Wider actor grid | Adopted with a responsive minimum so phone viewports do not overflow. |
| OPP guide and dialog | Adopted. Corrected the guide's archive size wording to match `mmv/props.py`; package data includes the guide for installed apps. Missing guide returns an error instead of a successful empty guide. Agents can inspect it too. |
| Dark text selection contrast | Adopted. |
| Actor form textarea | Fixed malformed `maxlength`/placeholder markup in the fork patch. |

The panel progress design in `.collaboration/PANEL_PROGRESS_DESIGN.md` was implemented in the same release at the owner's request. It is a GUI state view; the server's quote and consent checks remain authoritative. No fork history merge, private asset import, protected-prompt edit, paid/GPU work, commit or push was made during review.

## Fork `56d9f04` reviewed (release 1.10.6, 2026-10-22)

Reviewed from an isolated clone of `hellonearthis/mondo-music-video` at exact head `56d9f04` (one commit after the previously reviewed `c699179`), by [hellonearthis](https://github.com/hellonearthis). The fork labels it 1.10.2, which collides with our 1.10.2, so it ships here as 1.10.6.

| Contribution | Decision and evidence |
| --- | --- |
| Optional style `vocabulary`, validated and stored as data, with a never-automatic "Use this style's vocabulary" offer | Adopted. Agent, CLI, MCP, skill and tests included. Defect fixed: the fork's `index.html` opened `<div class="style-vocab-offer">` and never closed it, which would swallow the rest of the video form. |
| `vocab_selection: contextual` table narrowing (`contextual_vocabulary`) | Adopted, `legacy` stays the default. Dropped the fork's use of `thematic_worlds` (absent here; our Worlds feed `custom_vocabulary`, whose additions are already in the context words). |
| `apply_contextual_shot_vocabulary` per-shot override | Not adopted as written. It rewrites setting, subject, mechanism, lighting, tonal register and costume on every shot, including shots whose values the planner deliberately holds steady across a segment (standard and fragmentation montages) or fixes from an anchor, and it mutates the plan in place although documented as pure. Compatible alternative: re-pick only keys a shot already has, and only for the montage types that rotate per shot, after a real before/after render. |
| `THEMATIC_JUXTAPOSITION_MAP` and tangent departures | Adapted (owner asked for it). The ten fixed archetype clusters are replaced by the owner's own Worlds: a video names mirror / opposite / tangent worlds and a strength; the fork's thresholds (0.65 / 0.85), role odds and `0.5*energy + 0.5*passage energy*strength` score are kept. Differences: pure function returning replacements; only slots a shot already has are swapped (no `juxtaposition_departure` key reaches the writer job); subject and costume slots untouched; held-steady passages depart as a whole; thematic-anchor mechanism kept; contrast pools and ids stripped from shared receipts. Opt-in, protected files untouched. |
| Version 1.10.2 | Not matched (collision); released as 1.10.6. |

## Fork `5e2bba4` integrated (release 1.9.8, 2026-10-20)

Reviewed from an isolated clone of `hellonearthis/mondo-music-video` at `5e2bba4f945d02f7c825e2002d83c2d084819c2e`; the only change beyond the previously reviewed `e6ef03e`.

| Contribution | Decision and evidence |
| --- | --- |
| Component labeling overlay, toggle, shortcuts, CSS, `data-component*` attributes, interface guide | Adopted with adaptation. The `index.html` patch conflicted only at the Actors panel, where our OPP library card was added; it was merged by hand and the OPP card labelled. The badge now uses text nodes rather than `innerHTML` (the labels are static, so this is hardening, not a demonstrated defect). GUI-only by design. |
| Version 1.9.8 | Matches the fork. |

## OPP task-start fork check — `5e2bba4` (2026-10-20)

The fork was checked at exact head `5e2bba4f945d02f7c825e2002d83c2d084819c2e`
and cloned independently into `/tmp/mmv-fork-opp-20261020`. Relative to the
previously reviewed `e6ef03e`, the only new commit adds component-labeling
mode: stable `data-component-*` attributes across the existing GUI, a header
toggle/keyboard shortcut, an overlay in `webapp/js/component_labeling.js`, CSS,
an interface guide, and a version bump to the fork's 1.9.8. This is a useful
pair-programming aid, and its static labels would also help locate the new OPP
card after an adapted integration. It makes no OPP import, actor, model,
payment, renderer or resume changes. The OPP work modifies the same HTML and
app files; copying the fork patch wholesale would omit new OPP elements and
collide with this task's 1.9.7 version. The feature is deferred to its own
interface batch so the labels can cover the final OPP UI and receive focused
keyboard, accessibility and agent-surface review. This is a scope/version
conflict, not a demonstrated defect in the collaborator's contribution. No
fork files, private assets or Git object stores were imported into this tree.

## October 21, 2026 — fork head c699179 (release 1.10.4)

Reviewed isolated clone at exact revision `c699179db724b6b292c63594dc03d48351cfdd5f`.
The fork merged our releases through 1.10.1 in `54f1ba2`; the new contributions
by [hellonearthis](https://github.com/hellonearthis) are `5ca5eb9` and `c699179`.

| Contribution | Decision and evidence |
| --- | --- |
| Mondo favicon (`c699179`) | Adopted unchanged. The `.ico` is a valid four-size icon, the routes serve static files only, and its endpoint test passes here. |
| Thematic Worlds Process button and keyword cluster scoring (`5ca5eb9`) | Deferred. Client-side only and stacked on the deferred `vocab-worlds.js` (see the `79d8515` entry), whose mode/kappa consumer and three defects remain open. No new defect found. Remaining work: land that foundation, then revisit. |

## October 21, 2026 — fork head 79d8515 (release 1.9.10)

Reviewed isolated clone at exact revision `79d8515f76207c21c155981d3255bb60f7165611`
(three commits by [hellonearthis](https://github.com/hellonearthis) after
`5e2bba4`; 31 files, about 3,400 lines). A low-effort read-only Codex pass and a
direct review traced the code; the fork's own new tests were not run (no numpy or
scikit-learn in the review environment). The fork's 1.9.9 label collides with our
shipped 1.9.9, so the adopted subset is 1.9.10.

| Contribution | Decision and evidence |
| --- | --- |
| Markdown renderer and formatted guide dialog | Adapted. 20,000 random inputs found a stack overflow: an indented `>` line was never stripped, so the blockquote recursed on itself. Fixed. Heading ids prefixed `md-`; non-https links no longer open new tabs (in-page anchors did). No XSS bypass found; output is escaped before the HTML sink. |
| Top-placed tooltips, category and button tooltips | Adopted. The `themes` tooltip was removed: `vocab.json` has eleven tables, not twelve. |
| Labels button moved to Settings | Adopted; the narrow-width hide rule was removed with it. |
| Settings tooltip wording | Adapted without `C:\cui` and `C:\llamaCPP` example paths. |
| Thematic Worlds workspace (`vocab-worlds.js`, `thematic_worlds` field) | Deferred. The compiled term pools reach the render through `custom_vocabulary`, but mode, juxtaposition slider and kappa bars are stored and displayed only; nothing under `mmv/` reads them, yet the UI and quote line say they are active. Choosing Off clears the worlds but leaves the compiled vocabulary override in place. Pinned terms are held only in DOM attributes and are lost when a term is added. The request field is an unbounded dict. Remaining work: a real consumer for mode and kappa (this touches the protected planning code and needs the owner's approval), then fix the three defects. |
| `cluster_vocab.py`, `lint_vocab.py`, `mmv/style_embed.py`, embedding docs, `start-embedding.ps1` | Deferred. Depend on scikit-learn, which is not a declared dependency; `choose_k` selects k=1 for a two-term vocabulary and then calls a silhouette score that needs two clusters. Tests not run. |
| `mmv/vision_check.py` `C:/llamaCPP` search, `start.ps1` changes | Deferred. The path search does nothing off Windows; `start.ps1` saves the writer selection before checking whether a different model is already being served. Needs a Windows host to verify. |

## October 20, 2026 — fork head e6ef03e (release 1.9.6)

Reviewed isolated clone `/tmp/mmv-fork-review-20261020-new` at exact revision `e6ef03e28f1cde7018be1710d0b8c89cad1480f4` against our `55671c4` (1.9.5). The fork first merged that upstream release in `26dba46`; new contributions are `5b026e5` and `e6ef03e`, authored by [hellonearthis](https://github.com/hellonearthis). This review compares the two new commits, not the already adopted upstream history. The isolated clone shares no Git object store with this checkout.

| Contribution | Decision and evidence |
| --- | --- |
| Writer working-directory label (`5b026e5`) | Adapted to “Writer working directory (llama.cpp folder)”. The `writer_cwd` setting can also launch other local writer commands, so “LLama Directory” alone would misdescribe it. Existing setting key and agent inspection remain intact. |
| Windows GGUF and projector discovery (`e6ef03e`) | Adopted the single recursive scan and per-directory projector index. The prior loop queried each model directory separately. PowerShell execution is unavailable on this Linux host; no speed claim is made. |
| UTF-8 child environment | Adopted `PYTHONUTF8=1` alongside the existing `PYTHONIOENCODING=utf-8`; mock tests passed. |
| Service probes | Adopted bounded launch-command parsing cache and reused four probe workers. Added a lock around the shared result cache and a monotonic freshness clock so concurrent status requests do not duplicate probes or overwrite one another. External API writer readiness is still only a configuration signal, not verified generation. |
| Unfinished-run traversal and size cache | Adopted `os.scandir` traversal and size counting without following symlinks. Replaced the fork's root-mtime-only invalidation: adding or changing a file in `renders/` does not reliably alter the run root mtime, so its size could remain stale indefinitely. The adapted cache expires after five seconds and is cleared for deleted runs; a temporary-run regression covers nested file growth. Rendered-clip deletion confirmation is preserved. |
| Color wheel image cache | Adopted dimension-keyed `ImageData` reuse. The wheel's hue/saturation mathematics and form values are unchanged. |
| Fork version and performance claims | Adapted to one patch bump, 1.9.6, for this delivery. The fork's 1.9.7 label and unmeasured timing claims were not copied; Windows timing and execution still need operator verification. Existing agent/MCP version assertions and documentation were updated. |

Claude Code Sonnet 5.5 reviewed the fork patch read-only through the guarded launcher after its first attempt could not read the isolated `/tmp` clone; the exact patch was placed under ignored `.collaboration/`. Claude found the root-mtime size cache, `lru_cache` on potentially unhashable launch values, and an unguarded disappearing-directory stat in the fork. The integration addresses all three: a bounded freshness interval, a type guard outside the cached parser, and `OSError` handling before sorting. Claude also flagged symlinked runs as a behavior change; listing now excludes linked run folders and size traversal does not follow links. This keeps the manager within the installation's runs tree. Its concerns about executor lifetime and unfinished futures are unproven and introduce no new paid or GPU action; the shared probe lock prevents concurrent status calls from filling the executor. The normal process exit closes the executor's workers. The additional suggested tests for implementation details were not added; the nested-file growth regression and full mock suite cover the material behavior change. The initial report's missing-review-record observation was based on the tree before this documentation was written.

No protected prompting, model defaults, paid submissions, retries, private assets, commit, push or publication are part of this integration. Verification is recorded in [VERIFICATION.md](VERIFICATION.md).

## October 20, 2026 — Engine lifecycle and GPU memory (1.9.3)

Task-start fork check: exact head `59f820d6306271393aad815fb473104db46a9d17`, already reviewed, no new revisions. Claude Code Sonnet 5.5, medium effort, owned the main implementation and mock tests. Codex reviewed the two handoffs and tightened unknown Apple memory behavior, unverified renderer release, writer startup headroom, CPU/projector estimates, failed vision-stop ownership, and guards against rendering alongside known external GPU services. API, GUI, agent/MCP status and skill coverage were audited. A fresh isolated Claude medium session expanded the factory daylight preset. Codex added the harvest card free axes/motifs, removed copied legacy rigging/audio directives so preset content cannot override mouth/singing behavior, kept shot scale and ensemble framing free, and verified factory-only migration tests. Helper daylight tests were not run in its restricted session; coordinator ran them after integration. No fork merge, protected-source edit, private-asset import, paid/GPU generation, commit or publication.

## October 20, 2026 — Existing ComfyUI handoff and UI labels (1.9.2)

Fork checked at exact head `59f820d6306271393aad815fb473104db46a9d17`, already reviewed; no new changes. The reduced-flashing vocabulary exclusions and writer-tuning behavior contributed by hellonearthis remain intact. At the owner's direction, visible labels use descriptive feature names instead of GitHub handles; the vocabulary profile ID and contribution credit are preserved. The writer control now uses `context_16k`; its command helper still accepts the legacy tuning identifier.

## October 20, 2026 — instrument performance (1.9.0)

Task-start fork check and isolated clone: exact head `59f820d6306271393aad815fb473104db46a9d17`, already reviewed in 1.8.11. No new fork contributions to integrate.

Claude Code Haiku reviewed the opt-in extension (CLI-reported model/receipt recorded locally). Fixed its confirmed Windows filename issue by using instrument staging keys that contain no colon and cannot collide with valid actor IDs. Removed private provenance/license data from writer jobs, stripped paths/provenance from demo instrument receipts, and kept instrument files out of demo exports. Quiet mix/no-sample activity is unknown rather than a forced instrument pause. Added original actor-slot contract checks. Clause attribution, curly quotes, bounded names and mock tests were already being added concurrently; coordinator verified the final paths. Some reported missing assets/tests reflected the earlier tree the helper read. Public authorization comes from the owner's explicit new-instrument request; the four-actor allowlist is unchanged.

A final bounded Haiku review led to explicit saved-mode/assignment/reference-policy checks, pronoun antecedent and ambiguous-pronoun checks, continued-playing wording support and narrower action inflections (a pickup/player noun cannot supply an action). Existing public resume already verifies the original consent fingerprint; the new checks also protect direct preparation/worker use and fail earlier. Original-source hashes were removed from demo receipts; reference-PNG hashes remain for selected-reference identity/cache checks. The helper's claim that original-source hashes entered writer jobs was not supported by the final job structure: only reference-PNG hashes are sent. No API writer or paid-render retries were added.

Guitar and keyboard public sheets supplied by the owner are bundled; drums/bass and real visual validation remain pending. No new fork history merges, private studio assets, protected-pin edits, commit or publication.

## October 20, 2026 — fork integration, head 59f820d (release 1.8.11)

Reviewed an isolated clone at exact revision `59f820d`, following last reviewed head `73cbd4b` (1.8.9). New commits: `5a14e85`, `98a1cc0`, `4c6d79b`, `a7cb9df`, `59f820d`. Codex (low effort, read-only) acted as adversarial reviewer; its findings were checked against source. The owner reports hellonearthis's changes fix a problem that appears on lower-memory machines and was invisible on the owner's larger-memory one.

| Contribution | Decision and evidence |
| --- | --- |
| Clear-log fix (`5a14e85`) | Adopted with fixes. Codex showed the saved offset was dropped once the run finished (cleared output reappeared) and that writer/Comfy service logs and old validation reports were not offset. Offsets now cover all three logs and persist; `tests/test_log_clear.py`. |
| 16k default context, launcher preservation (`98a1cc0`) | Preservation of saved tuning and the duplicate `--image-min-tokens` fix adopted. The 16k default stays opt-in (`hellonearthis` preset): it costs memory on the machines the fix targets. Open (not fixed): the settings lookup hardcodes `%LOCALAPPDATA%` and ignores `MMV_HOME`; and passing only `-ContextSize` skips restoring saved batch settings. Needs a Windows test. |
| Token telemetry (`4c6d79b`) | Adopted as a read-only helper (`mmv/writer_usage.py`, lock-guarded, urlopen always restored). It is needed because `engine/writer.py` is pinned. Context percentage omitted when unknown (the fork assumed 16384). |
| KV-cache flush (`a7cb9df`) | Adapted. `--parallel 1` is now default for every preset (it gives the full context to the active prompt). `--no-cache-prompt`/`-sps 0` are opt-in in the `hellonearthis` preset. The per-request `cache_prompt:false` rewrite was not adopted: it duplicates the server flag and would be sent to paid API writers too (Codex P1; whether a given provider rejects it is unverified). Effect on output quality and speed is unmeasured. |
| Video clips as idents (`59f820d`) | Adopted with a fix: preparation rejected `kind=video` outputs (Codex P1, confirmed at `mmv/pipeline.py`), so the picker option could not work. Accepted now. A real attach-render check is still to do. |

No paid, GPU or Topaz work; no private assets; no commit, push or message to the collaborator.

## October 20, 2026 — fork integration, head 73cbd4b (release 1.8.9)

Reviewed an isolated clone of `hellonearthis/mondo-music-video` at exact revision `73cbd4b`, following last reviewed
head `1704454` (1.8.1). New contribution commits: `63f4826`, `8b70f0a`, `bff3b9e`, `183eeb8`, `312b0c3`, `eeab8c0`, `73cbd4b`.
Their changes were three-way merged (base `1704454`, ours 1.8.5, theirs `73cbd4b`); conflicts were version strings, markup and the vocabulary module.

| Contribution | Decision and evidence |
| --- | --- |
| Style export/import/duplicate (`73cbd4b`) | Adopted. Id pattern, size bounds and overwrite opt-in are enforced by the request models; agent client, CLI, MCP and skill coverage included. The release note's "four-layer validation" is a description of those checks, not a separate validator. |
| Offline-engine guard (`bff3b9e`) | Adopted. It probes at quote and start and blocks only when the service is down and has no launch command. Resumes skip the writer and Laya checks. |
| Unfinished-run manager, output deletion (`63f4826`, `8b70f0a`) | Adopted with a fix: "purge all" could delete interrupted runs that hold already-rendered, possibly paid clips. Those are now kept and need a one-at-a-time confirmation. Regression tests in `tests/test_unfinished_runs.py`. Local productions can now be resumed from the manager. |
| Parallel probes, memoized UI, functional modules (`312b0c3`, `8b70f0a`) | Adopted. The stated "up to 65%" latency figure was not measured here. One of our browser tests assumed eagerly rendered vocabulary cards; it now opens the summary first. |
| Render timeout (`eeab8c0`) | Already fixed independently in 1.8.4. At the owner's decision the unlimited default was replaced by the fork's two-hour default, exposed as the `render_timeout_minutes` setting (0 = unlimited). |
| Home-path redaction in package export | Adopted. The pattern has no word boundary, so it may redact slightly more than a real path; that errs toward privacy. |
| Upstream merge `183eeb8` | Nothing to adopt; it re-applies our 1.8.2. |

No paid, GPU or Topaz work was run; no private assets were imported; no commit, push or message to the collaborator.

## October 19, 2026 — independent dance differentiation (1.8.5)

At the owner's request Claude Code reviewed the repair read-only (CLI-reported
`claude-haiku-5-5`; receipt in the ignored local collaboration report). The first
sandbox attempt failed DNS; the network-enabled attempt completed. No fork work
was included: the owner explicitly directed focus on dancing.

Confirmed from the operator test's saved jobs/prompts: separate stem cues shared
generic move-per-beat hints, a prompt called a dancer the lead, and names instead
of tags bypassed action attribution. Added independent-only movement families
and checks without altering protected originals or group/off rules.

Adopted Claude findings: reject identical mixed-family signatures; resolve
collisions among three choreographed actors even with a larger selected roster;
distinguish copying another dancer from following music or a mirror prop;
handle affirmative nonstop actions and body actions in mouth-policy sentences;
run both dance test classes under direct unittest execution. Added regression
coverage. Name attribution uses saved cast display names; it remains lexical.

Claude questioned approval for the additive independent rule block. Existing
owner approval is recorded in BONK_DESIGN.md and the prior task handoff; this
repair stays within that opt-in mode, leaving protected prompts/pins untouched.
No automatic paid retry was added. Camera repetition is confirmed but recorded
only on the roadmap, per the owner's deferral. Real same-song/seed validation of
the revised choreography remains outstanding.

## October 19, 2026 — live-test timeout repair (1.8.4)

Task-start check found new fork head `eeab8c0b729650d41fa8f2b0093750129c543f9b`.
Fetched into isolated `/tmp/mmv-fork-review-20261019`, without changing the main
checkout or sharing object stores. Focused review of the timeout repair confirms
hellonearthis independently identified the `None`/numeric comparison failure seen
in our real local render test. Adapted at the worker boundary with numeric infinity
so the owner's unlimited-wait default remains; protected engine files stay intact.
The fork's finite 7200-second default is not silently substituted for that default.
The numeric-adapter mock regression simulates history arriving after 9000 seconds.

Other new fork commits (`63f4826`, `8b70f0a`, `bff3b9e`, `183eeb8`, `312b0c3`)
include incomplete-run management/deletion, functional vocabulary/library/output UI,
service-offline handling and concurrent service probes, plus upstream review fixes.
Initial scope inspection confirms substantial unrelated UI/service changes (25 files,
including the timeout commit). Full correctness/privacy/defaults/consent review and
mock integration of those contributions is deferred to a separate integration batch,
rather than expanding this explicitly requested real dance test. They are not rejected
or claimed fully reviewed; latest fully completed broad review remains `1704454`.


## October 19, 2026 — independent dancing (1.8.3)

Task-start fork check: `1704454c4d3f538866b1cb3eed72af5dfb74f0e5`,
unchanged from the completed review below. No new fork contributions to integrate.
Claude Code reviewed current integration read-only through the guarded launcher;
CLI-reported model and receipt are recorded in the ignored local task board.
Antigravity's independent UI/API review has now been received and checked against
the implementation. Its model/effort are self-reported as Gemini 3.8 Flash / High,
not independently verified. The reviewer ran no tests or renders and made no tracked
edits. Both requested reviews are received; visual render validation remains pending.

| Claude finding | Disposition |
| --- | --- |
| Stem cues ignore score edits | Fixed: apply the same edits to copies of stem analysis; regression checks nudge, muted beats and bar phase without modifying caches. |
| Parse failure can retain stale soft-advice draft | Fixed: clear prompt after parsing/assembly failure and require an assembled prompt before retaining a fallback. |
| Empty stem energy mislabeled measured | Fixed: explicit mix fallback for empty-energy parts. |
| Failed cached analysis aborts preview | Fixed: unreadable/failed part analysis falls back independently. |
| Part override names a non-dancer | Intentional API validation, not a defect: reject inconsistent selections rather than silently ignore them. UI currently selects the whole cast. |
| Auto cycle includes explicit overrides | Intentional stable slot assignment: an override must not shift other actors' automatic parts. Documented and tested. |
| Mouth/body sentence can be excluded from lexical dance check | Existing conservative check retained: changing shared mouth-sentence treatment risks group-mode regression. Independent instructions request each visible dancer's body action. A targeted future validator change needs separate fixtures. |
| Soft-advice prompts revalidated on cache reuse | Existing safety behavior retained. Relaxing cache validation needs separate review; no paid submission retries added. |


| Antigravity observation | Verified disposition |
| --- | --- |
| Stable assignments, actor-ID persistence, explicit fallback, semantic controls and unchanged mouth rules | Confirmed against implementation and existing browser/API/worker tests. No blocking defect reported. |
| Optional grid layout for many actors | Deferred cosmetic suggestion; the current native controls remain usable. No measured layout failure was reported, so this review handoff adds no product changes. |
| Deselected actors retain manual overrides | Intentional: reselecting an actor restores their choice, while request serialization filters to currently selected actors. Existing browser test covers binding preservation. |
| Existing stem analysis only | Clarification: existing stem WAVs can also be analyzed on CPU with a worker subprocess. This does not download models, separate audio or submit network/paid work. |

The report's statement that the implementation "strictly satisfies all project
constraints" is a read-only review assessment, not proof of generated video quality
or precise synchronization. The recorded mock-suite results remain the verification
evidence; same-song/same-seed real comparison is still outstanding.


## October 19, 2026 — Antigravity review follow-up (release 1.8.2)

Antigravity delivered its read-only review of fork `1704454`; model/effort were
self-reported as Gemini 3.8 Flash / High, not independently verified. Codex checked
all findings against the integration and original 1.8.0 source.

| Finding | Verified disposition |
| --- | --- |
| Navigation recursion, multi-fold restoration, actor numbering | Already fixed in 1.8.1 with browser coverage. Recursion crosses an `await`; repeated asynchronous reopening is established, while the report's synchronous stack-overflow mechanism is not. |
| Missing vocabulary guide dialog | Confirmed, including in pre-fork 1.8.0. Restored a small dialog displaying the existing guide endpoint and wired its Open Visual vocabulary action to the sidebar workspace. Both guide entry points and the return action are covered in Chromium. |
| Stale guide navigation to removed editor dialog | Confirmed stale code; now targets the workspace. The formerly missing guide meant this handler was unreachable before the repair. |
| Dark hover contrast on the new overflow button | Confirmed pale-on-pale colors. Added a dark background/light foreground hover rule; browser regression computes rendered contrast and requires at least 4.5:1. |
| Overflow action lacks category context | Added a category-specific accessible name, checked in Chromium. |
| Unapplied draft discarded on navigation/reopen | Preserved existing Apply/discard semantics, added visible workspace copy explaining them. A dirty indicator or draft-preservation change remains a separate UX decision; it is not silently enabled. |
| Category tab roles | Pre-existing accessibility gap. Deferred to a complete keyboard/focus/tab-semantics implementation; adding roles alone would leave tab keyboard behavior incomplete. |
| Narrow action bar wrapping | Review concern, not a demonstrated regression; no viewport measurement was supplied. Deferred responsive assessment rather than presenting it as a proven collision. |
| Legacy dialog class names | Harmless CSS compatibility names retained to avoid unnecessary selector churn. |

Antigravity made no tracked edits or test/render calls. Both requested helper reviews
are now received and triaged. Validation is recorded in VERIFICATION.md.

## October 19, 2026 — fork integration, head 1704454 (release 1.8.1)

Reviewed isolated checkout `/tmp/mmv-fork-review-20261019` at exact revision
`1704454c4d3f538866b1cb3eed72af5dfb74f0e5`, following last reviewed fork head
`dc71556b5ef12876042ce0ab13fda5bcc5c9670f`. The intervening history includes our
own releases through `47c745a` (1.8.0), merged by fork commit `889abc7`; the new
contribution commits from hellonearthis are `50e7d59` and `1704454`.
Compared their final tree against our current 1.8.0, rather than reapplying our releases.

| Contribution | Decision and evidence |
| --- | --- |
| Targeted vocabulary summary updates | Adopted: edit only the affected category card; cap summary chips at 20 with a link to the complete category tab. Browser regression checks that unrelated cards keep their DOM identity. |
| Dedicated Visual vocabulary workspace | Adopted with fixes: the fork's `panel("vocab")` called `openVocabularyPanel()`, which unconditionally clicked the same navigation button, causing repeated asynchronous reopening and draft resets. Navigation now occurs only when the workspace is hidden; initialization does not navigate again. Restore the saved vocabulary and profile before opening the workspace. |
| Three advanced production folds | Adopted with independent persistence: the fork saved whether any fold was open but restored only the first. Stable fold IDs and `details_sections` preserve each fold; old `details_open` drafts still restore. Updated moved-control browser selectors and actor navigation numbers. |
| Windows Python UTF-8 mode | Adopted: `start.ps1` adds `-X utf8` to the application launch. No prompt files, scheme pins or protection tests changed. Windows execution remains unverified on this Linux host. |
| Version and assertions | Adopted 1.8.1 once for this delivery; updated additional browser assertions missing from the fork and retained our release history. |

Claude Code independently reviewed the in-repository fork diff and integration (CLI receipt:
`claude-haiku-5-5`, read-only; no tests run by the helper). The coordinator triaged its
additional findings against `47c745a`:

| Additional review point | Disposition |
| --- | --- |
| Navigation silently swallows catalog-loading errors | Fixed: workspace navigation reports failures through the existing notice UI. |
| Hidden quick bar/saved-key row allegedly overridden by flex CSS | Rejected with evidence: `style.css` already has global `[hidden]{display:none!important}`; the helper missed it. |
| Random key retained after manual edits; randomization switches replace to append | Existing behavior in the original `buildPseudoRandomDraft`, category randomization and edit handlers, unchanged by these commits. Deferred to a separate vocabulary behavior change with reproduction tests; clarify whether the key describes the initial draw or the entire edited selection before changing its semantics. |
| Empty category possible through checkboxes/Clear all | Existing UI validation gap; `mmv/pipeline.py:apply_vocabulary_overrides` rejects an empty final pool explicitly. Deferred: add consistent UI validation without changing the planner. |
| Quick Reset clears manual customizations without confirmation | Existing handler and reset behavior, unchanged. Deferred: review wording/confirmation and preservation of manual additions as a separate usability fix. |
| Duplicate counts and preset/custom layering | Existing counting and preset handlers; backend deduplicates final pools. Layering impact remains to be reproduced. Deferred: test effective pools and align displayed counts before changing behavior. |
| Deleted preset selection not immediately saved | Existing delete handler, unchanged. Deferred: reproduce delete/reload and add a persistence regression test. |
| Summary header keyboard access and legacy dialog branches | Existing header and compatibility branches; new overflow control is a native button that opens the complete tab. Deferred header accessibility cleanup; no removal of compatibility code in this integration. |

Antigravity was assigned a separate read-only UI review via the local task board; no
callable terminal connection was available and no report had arrived at validation time.
That review was pending for 1.8.1; the completed follow-up is recorded above.

No new renderer/model defaults, paid submissions, retry paths, OAP behavior or private assets
are introduced by this delta. Agent/MCP operation continues through the existing vocabulary
preset tools and preview fields; no new tool is needed for a web navigation/layout change.
Validation is recorded in the delivery verification notes. No commit, push or publication
is part of this integration.


## October 19, 2026 — contributor credit by history merge (owner-authorized exception)

On the owner's instruction, the fork's 22 commits after the shared base `7f87f91`
(all authored as the collaborator's GitHub account) were recorded in this
repository's history with `git merge -s ours` from `dc71556`, fetched into a
separate ref. The merge changed no files: the integrated code had already been
reviewed and adopted by hand (releases 1.6.4 to 1.6.11). The files touched by
those commits were listed first and contained only source and documentation, no
actors, media, models, keys or data. This is an exception to the rule against
sharing Git object stores with the fork and is not a precedent.

## October 26, 2026 — fork integration, head db7bec7 (release 1.10.20)

Fetched at task start into an isolated checkout; reviewed `26719de..db7bec7` (fork 1.10.15–1.10.20). Codex (medium effort, read-only) and Claude Code reviewed independently.

| Change | Decision | Reason and evidence |
| --- | --- | --- |
| 1.10.15 tooltip and receipt wording | Adopted | Clean apply. |
| 1.10.16 retire pseudo-random vocabulary controls | Adopted | The fork authored the feature we took in 1.6.11 and now retires it. No agent/CLI/MCP path used it; `vocab_random_key` kept for old drafts. Old keys cannot be re-applied from the GUI; a selection already saved still restores. |
| 1.10.17 format fold | Adopted with a fix | Older drafts closed the new fold; restore now leaves unlisted folds at their default. Fold-state test expectations updated. |
| 1.10.18 cast checkboxes | Adopted with a fix | Quick Start and Start fresh did not update the checkboxes; both now call `syncCastPickerUi`. The fork's browser tests drove the now-hidden select; they use `pick_cast`. |
| 1.10.19–1.10.20 reference list, layout | Adopted | Escaping verified; layout CSS merged by hand where the stylesheet tail differed. |
| Version label | Matches the fork (1.10.20) | Our 1.10.12 release notes retained. |

Open: sidebar order places library tabs ahead of Harvest, Vocabulary and Worlds (pre-existing, not from these commits). A browser test with quotes or markup in an actor name or reference filename is not yet added.

## October 19, 2026 — fork integration, head dc71556 (release 1.6.11)

Fetched at the owner's request after head 4e1cbb0. One commit, `dc71556`: pseudo-random
vocabulary generator with reproducible keys, quick editing and preset saving.

| Change | Decision | Reason and evidence |
| --- | --- | --- |
| Pseudo-random vocabulary keys (`vocabulary.js`, `index.html`, `style.css`, `vocab_random_key` in the project state) | Adopted with a fix | Draft-replacing paths now use `showVocabCategory`; the largest category (269) fits the 500-entry exclude cap; project persistence test passes. A key is only reproducible while the built-in lists are unchanged (noted in RELEASES). |
| Version 1.6.11 | Matches the fork | Owner's compact option, labels and silent-mouth decision preserved when merging `index.html`. |

## October 18, 2026 — fork integration, head 4e1cbb0 (release 1.6.10)

Fetched into an isolated checkout at task start. Reviewed `3365943..4e1cbb0`
(10 commits, fork releases 1.6.5 to 1.6.10). Codex ran a read-only adversarial
review of the working tree (it could not reach GitHub from its sandbox).

| Change | Decision | Reason and evidence |
| --- | --- | --- |
| `app.js` split into `webapp/js/*.js` modules | Adopted with fixes | Fork tests read module-private values as globals (`saveProject`, `sseConnected`, `sseSource`) and failed; tests now import the modules via read-only exports. Package data lacked `js/*.js`; added. Local `compact_prompts` and vocabulary-editor fixes re-applied in the modules. |
| Preview/Start busy states, banners | Adopted | Covered by the browser suite. |
| Theme contrast and sticky sidebar | Adopted | CSS only. |
| Vocabulary guide dialog and endpoint | Adopted | Serves `docs/VOCABULARY_GUIDE.md`; reuses the existing file. |
| Local-writer context hint | Adopted | Message text only. |
| Operation-log clearing at start | Adopted | Active run stays visible. Not exercised against a real long run. |
| Configurable encoders (added then reverted) | Nothing to adopt | Net zero in 1.6.10. |
| Facial-movement label "(when lyrics present)" | Kept this repository's label | Depends on the owner's decision on the lyrics-gated silent-mouth rule (see TEAM_STATUS). |
| Vocabulary preset lost on project reopen | Fixed (Codex finding, confirmed in code) | Catalog now loads before project restore; regression test fails on the original order. |

Version: 1.6.10 matches the fork's label so different content does not collide
with the fork's numbering. Writer/ident prompts, `schema.py` and `style.py` are
unchanged by these commits.

## October 18, 2026 — fork integration, head 3365943 (release 1.6.4)

Fetched into an isolated checkout at task start. Reviewed `7f87f91..3365943`
(fork 1.6.2 to 1.6.4, author hellonearthis); it contains the previously deferred
dock and the 14ee458 leftovers. Codex ran a read-only adversarial review of the
applied tree; the coordinator read the dock, pipeline, worker, quality, vision and
web-layer diffs. Full suite 253 passed, 53 subtests, mock services only.

| Change | Decision | Evidence / remaining work |
| --- | --- | --- |
| Vocabulary customizer, presets, API, agent and MCP (30 tools) | Adopted with a fix | Codex found stale editor text overwriting loaded/reset drafts; confirmed in code, fixed, browser regression test added (fails on the original). Skill and agent docs extended. |
| Status dock (`mmv/services.py`) | Adopted with a fix | Cache is keyed by store; only user-configured URLs probed, no credentials returned. Initial SSE probe moved off the event loop. Job-thread callback still probes on a cache miss: not shown to be a problem. |
| Token reductions (compact job JSON, stable system prompt, ident trimming) | Adapted: opt-in `compact_prompts`, default off | The owner's hand-written prompts stay the default. Trimming measured on the real 64 KB ident prompt in every mode. Tests pin the default to the original prompt and message. Effect of compact prompts on output quality is untested. |
| Vision frames at 512 px and `max_tokens` 160 | Adapted: only with `compact_prompts`; full-size frames and no cap by default | Real GPU comparison (see VERIFICATION.md): one borderline frame in 16 judged differently at 512 px; saved about 1.5 s per clip. |
| `--image-min-tokens 1024` in `start.ps1` | Adopted, not yet gated | Windows launcher only; not exercised here. Remaining work: decide whether it belongs behind the compact option. |
| Single-pass ffmpeg frames, streaming hashes, parallel probes | Adopted | Covered by existing tests. |
| Test acceleration and fork test edits | Adopted; one fix | Fork browser test expected an old version string; corrected. |
| Rewritten RELEASES and VERIFICATION history | Omitted | It renamed and replaced this repository's records; a new 1.6.4 entry credits the fork instead. |

Version: 1.6.4 matches the fork's final label, as with 1.3.0, to avoid a number
collision for different content. Codex could not reach GitHub from its sandbox.

## October 18, 2026 — OAP 0.3 integration

Fetched hellonearthis's fork into an isolated temporary checkout at task start.
The new head `78f31ae33f50a9578043d2af33ce05158603ab86` is a merge of this
repository's 1.2.1 (`d6aa193`) into the fork's `764ca66`, labeled fork version
1.2.2. Compared with `d6aa193` it carries the pending hardware status dock
(`180b237`), earlier fork changes from `14ee458` not adopted in 1.1.2 (Laya torch
import placement, validation message wording, `--image-min-tokens 1024` for
vision models in `start.ps1`, vocabulary counts and an engine test), and merge
content of its own: a server-sent `log` event listener in `app.js`, dock refresh
wiring, a longer page title, two test adjustments and version/doc relabeling.
None of it was integrated in this OAP release; it was outside the assigned task
and has not yet had a full review. The dock and these items remain deferred, not
rejected, pending the focused integration pass described below.

This release is numbered 1.3.0 so it does not collide with the fork's 1.2.2
label for a different build.

## October 17, 2026 — starter assets in agent installation

Fetched the isolated collaborator checkout; origin/main is still
`764ca66843843217d51c8708cb1e1fa952d9f364`, with no new commits. This
1.2.1 follow-up integrates public starter imports into both installers and adds
local actor/style deletion controls. No actor asset contents or workflow defaults
change; the separate collaborator hardware dock remains pending its focused review.

## October 17, 2026 — agent installation and provider setup

Fetched the isolated collaborator checkout again: origin/main remains
`764ca66843843217d51c8708cb1e1fa952d9f364`. No new contributions were found.
The hardware/status dock review below remains pending its focused integration;
this setup delivery does not change either collaborator's workflow defaults.

## October 17, 2026 — startup updater development

Checked and downloaded hellonearthis's fork through `764ca66` into an isolated
checkout at task start. The previously integrated substantive review remains
`132c3d3` (released here in 1.1.2).

The new feature commit `180b237` adds a live engine/hardware status dock through
`mmv/services.py`, API status fields, UI components and tests. The merge also
contains this repository's already-published 1.1.0 and public style presets.
Those upstream assets and defaults are already present here.

The dock is useful collaborative work and is deferred, not rejected. It is a
separate UI/monitoring feature from the requested startup updater, and needs a
focused integration pass before claiming equivalent behavior here. Specific
review items from initial code inspection:

- Its probe cache is process-global rather than keyed by store/settings; verify
  invalidation and isolation when configured endpoints change.
- Probe calls perform synchronous network requests from status/event handling;
  measure their effect on event-loop responsiveness and disconnected services.
- Verify status semantics for SDK/proxy rendering and explicit Laya fallback
  selections, keeping the owner's defaults and the collaborator's options.
- Review returned endpoint/error details for credential redaction and check the
  dock at mobile widths and in both themes.

These are review questions from code inspection, not claimed test failures.
Next review should compare `132c3d3..764ca66` against the current main branch,
exercise the new tests with mocks, and integrate the dock with fixes where
needed. Do not silently skip it or re-import already published style assets.
