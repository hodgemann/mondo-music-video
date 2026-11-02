# Mondo Music Video

**Version 1.12.3** · MAXIMUM GOOSE LABORATORY · Apache License 2.0

Turn a song into a music video. Beat-aware shot planning, LLM-written prompts, local or
hosted rendering, actors that dance, lip-sync and play instruments, Worlds, storyboards,
and frame-exact assembly with your original audio. Agent-installable, with MCP tools and
Open Actor/Prop Protocols.

## Easy install — let your AI agent do it

Give a coding agent with terminal access this one instruction:

> Install this: https://github.com/hodgemann/mondo-music-video

Your agent follows the repository's [installation guide](docs/INSTALL_WITH_AGENT.md):
it checks your hardware, recommends suitable models, configures your services,
and starts the app with the **four starter actors and six included styles**.
Existing actors/styles are preserved, and actor imports include OAP signer
review. **It asks before large downloads.** Already have API accounts?
It can configure multiple [API profiles](docs/API_PROVIDER_SETUP.md) and select
writing, vision and video services independently. A new video provider may need
an adapter; the guide explains how an agent can build and verify one.

Installing on a RunPod GPU Pod? The agent also follows the
[RunPod setup guide](docs/RUNPOD.md), covering fresh or existing stacks,
persistent storage, private browser access and first-video verification.

Prefer to install it yourself? Jump to [manual installation](#install).

The platform installers include starter assets too. Remove unwanted items with
**Delete actor** or **Delete style** on their library cards. Deletions are
confirmed and remembered across restarts and setup reruns; existing videos and
exports are kept.

The studio defaults to dark mode. Use the header theme toggle for light mode; your
browser remembers your choice.

File controls accept a click or a drop on their labeled area. Dropping reference
images replaces that control's selection (up to nine images); dropping a package
only selects it, so inspect and import remain separate actions.
Each attached reference image has a Remove button.

In Music Video, card and Director fold headers show input progress. **Done** means the required fields are filled; you still review the preview and approve any paid start. Complete required cards collapse after you leave the last required field, and you can turn that behavior off in Settings. Open a header to see every field, or use **Options available** to review optional fields left at their defaults. Actor cards let you edit local visual descriptions; imported signed OAP actors need an updated package from their signer. The OPP library includes an in-app guide. Actors & Props can check the public actor collection on demand and offer missing packages for verified, signer-approved import. The public collection is OAP v0.5; the four bundled starter packages stay OAP v0.2.
The Actors & Props creation, OAP import and role-agreement cards can be folded open
or closed. Creating an actor shows the selected portrait before you save it, and
local actor cards show the current visual-description length. Style cards with
an 11-axis breakdown have an expandable view.

Turn your song into a complete music video. Mondo listens to the track, detects
beats and downbeats, measures energy, and identifies musical sections. Its
seeded planner turns that musical structure into montage passages and timed
shots. An LLM writer develops the visuals from your direction, style and cast;
Laya reviews the prompts before the video renderer runs. Mondo then trims every
passage to its planned frames, joins the picture, and restores your original song.

## What you can make

- Music videos with beat-driven cuts and energy-aware montage grammar.
- Optional group dancing or independent dancing with per-actor beat/drums/bass/vocals assignments.
- Opt-in [instrument-playing actors](docs/INSTRUMENTS.md) with drums/bass/guitar/keyboards assignments and per-passage references; guitar/keyboard sheets included, drums/bass sheets pending.
- Output folders named for the uploaded song plus date and time; existing runs retain their IDs.
- Consistent reference-image actors and props with Open Actor Protocol and Open Prop Protocol built in.
- Your own visual styles, including styles harvested from reference images, plus
  six optional [style presets](examples/style-presets/README.md).
- Animated production idents and opening or closing credits.
- A big red **Just do the thing!** button: pick a song and it chooses the rest (random starter cast, optional dancing) and opens the preview for your approval. A quiet **Start fresh** link clears the panel.
- Optional [storyboards](docs/STORYBOARDS.md) for music videos and idents: interpret images, edit ordered panels, and preview their timing.
- Lyric captions: a `lyrics.srt` file, or the words burned into the video, from your timed lyric lines; later caption copies are rebuilt from the saved original clips.
- Every clean, subliminal and captioned version uses one final FFmpeg encode directly from original clips at the same CRF-6 quality. Topaz upscaling is the explicit exception.
- Finished videos to play, download, or upscale with your installed Topaz tools or the Topaz cloud service (your own Topaz API key; Topaz charges credits).

Use local models or supported API providers. One production runs at a time,
with progress, logs and cancellation. You provide your media, models and API
keys. Four optional [starter actors](examples/starter-cast/README.md) are included
as importable OAP packages. Model weights and third-party commercial software
are not bundled.

If prompt review exhausts its attempts before rendering, **Try again** loads a
new preview from that failed run in the GUI. Review it and approve the new start;
the failed run and its diagnostics remain available.
In instrument mode, Mondo can correct an unambiguous vague guitar action to
explicit string and fret contact, then run the full prompt checks as usual.

## Updates

The launcher checks its tracked Git repository at startup. **Automatic
installation is off by default**: an available update shows a notice and a link
to that repository. Enable **Automatic updates** in Settings to install on the
next launch, before production starts. Local changes and diverged branches are
preserved, and user data stays private. See [update behavior and recovery](docs/UPDATES.md).

## Official Comfy SDK rendering

Install `python -m pip install '.[comfy]'`, start the official local API proxy,
and choose **H3 / Comfy SDK (local proxy)**. This path runs the existing H3 graph
through the official Python SDK, uploads references/audio, downloads results and
supports receipt-based recovery after interrupted renders or failed downloads.
Your direct local workflow stays the default. See [setup and recovery](docs/COMFY_SDK.md)
for pinned dependencies and operator verification.

## Model selection and setup helpers

Settings lists the models reported by your ComfyUI installation, alongside the
models already selected in your active workflow. Changing a model creates a
private workflow copy; your original graph, bindings and precision settings are
preserved. Nothing is downloaded or selected automatically. File/folder Browse
buttons help configure local paths, and the OAP guide explains actors, reference
images, signatures and content riders. See [model settings](docs/MODEL_SETTINGS.md).

## Song preview, live status and setup tuning

Listen to and scrub your uploaded song directly in the production form, including
after reloading a saved project. Live operation updates fall back to polling if
the stream disconnects. Service failures identify the failing component and
include relevant writer/ComfyUI logs.

The local writer guide offers optional 16k-context tuning while preserving
your selected model paths. Laya device and fallback modes are explicit choices;
your existing CUDA and workflow defaults remain intact. An optional reduced
flash/strobe vocabulary keeps the full expanded pool as the default. See
[local writer tuning](docs/LOCAL_WRITER_TUNING.md) and
[visual direction](docs/STUDIO_DIRECTION_PROMPTING.md).

## Four montage grammars, driven by your music

Mondo uses four distinct visual grammars. The analyzer detects the track's
beats, downbeats, energy and musical sections; the planner uses that structure
to select a grammar and place the shots and cuts.

| Musical section energy | Montage grammar | Visual structure |
| --- | --- | --- |
| Low | **Standard** | One subject, sustained observation, fewer and longer shots. |
| Mid | **Thematic multi-scene** | New subjects and settings connected by one thematic anchor. |
| High | **Chaotic multi-scene** | New subjects, settings and actions in discontinuous collisions. |
| Peak | **Single-subject fragmentation** | A recurring subject seen through many angles and shot scales. |

Every passage also passes motion and framing checks. Before rendering, prompts
that would produce a still image or a bordered picture are sent back to the
writer. After rendering, each passage is measured for frozen shots and uniform
borders; on free local renderers a failing passage is re-rendered once with a
new seed, and anything still wrong appears as a warning on the finished video.
Paid renderers are never resubmitted automatically.

Checks now run as a batch after all passages render, with one shared retry
budget per passage. Optionally enable **Vision quality check (slower)** (off by
default) to inspect sampled single frames with your local vision-capable writer
model and its mmproj. This adds model loading and judging time. Mondo stops and
restarts only ComfyUI it launched, including on the SDK path; close ComfyUI
before starting and configure its launch command. Vision checks mostly add
warnings; repeated unrequested framing devices may use the same free local
retry budget. Pixel checks remain authoritative for motion. If the vision model
cannot start, production continues with pixel checks and a visible warning.

Open **Watch the song conduct** under any finished music video to see this
happen. A synchronized score shows the energy curve, beats and downbeats, each
passage's grammar and the planned cuts, with a playhead that follows playback.
Click it to seek; a caption explains the current musical decision, such as a
peak passage switching to single-subject fragmentation with a cut on a downbeat.

These are the default energy-to-grammar assignments. The song's detected
sections determine which grammars a production uses. Shot density, camera motion
and shot scale respond to the musical energy; passage boundaries follow detected
downbeats. Timing is detected from the uploaded audio automatically.

The LLM writer receives the selected grammar, planned shots, camera instructions,
visual vocabulary and reference bindings. It writes the visual content while
the planner owns timing. GPU Laya reviews the prompts before rendering, and
Mondo assembles the rendered passages against the original song.

## Expanded visual vocabulary

The planner now draws from 269 settings, 233 subject types, 256 mechanisms,
227 lighting choices, 185 tonal registers, 111 practical effects, 70 footage
anchors and 31 costume choices. These are the SFW selections from the owner's
full vocabulary, with the existing camera bands, shot scales and mouth-rigging
contract retained.

The original seeded sampler still rotates each vocabulary table without
repeating a draw until its pool is exhausted. Shared section/segment choices
can intentionally recur across shots. A larger pool changes the visual choices
for existing seeds; musical timing and actor assignments stay unchanged.
See [vocabulary details](docs/VOCABULARY.md).

## Worlds

A world is the canon your videos share: its places, rituals, people, objects and
rules. Build one in **Worlds** from pictures, video clips, lore or backstory text
and videos you have already made; your configured vision model reads them and
proposes a world. Nothing is saved until you review the changes and accept, every
accepted change is a new version you can restore, and a world can keep growing as
you add more material. Choose a world on the video form to draw that video's
settings, lighting, mechanisms, wardrobe, effects, subjects and tone from it.
Worlds are private, stay in your data directory and are never packaged or
published. See [Worlds](docs/WORLDS.md).

## Install

Manual installation:

Install **Python 3.11+**, **Git**, and **FFmpeg/ffprobe**, then:

```sh
git clone https://github.com/hodgemann/mondo-music-video.git
cd mondo-music-video
```

Linux, macOS, or Windows through WSL:

```sh
bash install.sh
bash start.sh                 # runs in this terminal; Ctrl+C stops it
bash start.sh --background    # runs in the background; stop it with: bash stop.sh
```

`start.sh` always runs this checkout's code (the `.venv` can hold an older installed copy), uses `$MMV_HOME` or this
checkout's `data/` folder when it has one, refuses to start a second copy, and in the background writes `server.pid`, `server.log`
and `server-url.txt` into the data folder. `stop.sh` waits for the app to exit and refuses while a production is running unless
you pass `--force`. The plain command `.venv/bin/mondo-music-video serve` still works.

**macOS** uses the same `start.sh` and `stop.sh` (they run on the bash 3.2 that macOS ships, and use the Mac's own data folder). In Finder you
can also double-click **`start.command`** (opens a Terminal window; closing it or pressing Ctrl+C stops the app) and **`stop.command`**
(for a copy started with `--background`). These Mac paths were written to be portable but have only been run on Linux so far.

Windows PowerShell:

```powershell
.\install.ps1
.\start.ps1            # Starts Mondo and connects to local llama-server
.\start.ps1 -SelectModel # Select or switch your llama.cpp GGUF model interactively
```

Open **http://127.0.0.1:8091**. Setup saves paths and model/service choices for
your machine. The app runs on localhost and uses a single worker.

## Configure your models

The music-video writer accepts an OpenAI-compatible chat service, either local
or API-based. Local H3 uses ComfyUI and the included standard H3 workflow and
injection map. Setup can configure launch commands so the local writer stops
before the renderer starts, freeing GPU memory. Existing externally managed
services stay under your control.

Laya reviews music-video prompts locally and uses CUDA by default. Select your
Laya model folder in Settings, or download the pinned model files yourself with:

```sh
.venv/bin/mondo-music-video download-laya
```

The helper displays the source, terms and destination and verifies checksums.
You can also select existing model files. See [model setup](docs/LOCAL_MODELS.md)
for the required files, renderer setup, and download manifests.

Hosted rendering supports WaveSpeed H3, Seedance 2.0 and Seedance 2.5. Supply your
own provider key. Charges are shown before you accept a production. An API
writer has a separately configured estimate; paid submissions are not retried
automatically. Uploaded references and song passages go to your chosen provider.

## Make a video

1. Upload your song and choose a style and visual direction.
2. Optionally choose actors or reference images, a conceptual theme, or lyrics
   to inform the visuals. Musical timing comes from the track analysis.
3. Review the detected musical structure, planned shots and estimated charges.
4. Start production. Mondo writes and reviews the prompts, renders the passages,
   and assembles the finished music video automatically.
5. Play or download your video. Create an ident in Credits & Idents to attach
   to another production, or use the optional Topaz export on a finished video.

Two seeds shape a video. The **variation seed** (0 unless you change it) picks
the shot plan, vocabulary and casting, so the same song and variation seed plan
the same passages and reuse their checked prompts. The **render seed** is new and
random for every video unless you type one; the preview shows it, so you can
enter both to repeat a video exactly.

**Edit** on a finished video opens it passage by passage. For a local H3
production you can render a new take of one passage (the same prompt with a new
seed is often all it needs; the seed is shown and can be typed), compare takes,
write a new prompt or check your own edit of it (both pass the same Mondo checks
and Laya review as any production prompt; an API writer asks before it charges),
and re-encode the final video from the chosen takes. Earlier final versions are
kept and downloadable. Rerolls and prompt rewrites never run without your
confirmation and are never retried automatically.

The Actors tab imports and exports OAP packages, verifies their signatures and
checks actor riders. No account, reporting or public actor sharing is required.
MMV reads Open Actor Protocol 0.2 to 0.5 packages, including packages sealed to
this studio's recipient key. Imported manifests are schema-validated offline, local actors can be exported as audition packages that leave out
cast-only assets, and role agreements record a casting between this studio
(Director) and an actor's Agent, each signing with their own key.

### Character consistency and eliminating random subjects

When casting characters from your character sheets or reference images, you can eliminate random uncast strangers and control how your characters appear throughout the video inside the **Camera & Montage Policies** fold on the Music Video panel:

- **Reference policy:** Set to **All montage types** (`all`) to eliminate random strangers completely. The default (`fragmentation`) only binds reference sheets to peak-energy passages, causing intro, verse, or multi-scene passages to invent anonymous, one-off figures. Setting this to **All montage types** forces every single passage across the entire song to use your cast members and reference images.
- **Cast assignment:** Choose **Hold through musical section** (`section`) to keep character continuity through an entire verse or chorus before switching to the next actor. Use **Rotate** (`rotate`) for strict round-robin alternation, or **Seeded random** (`random`) for variety.
- **Ensemble mode & Actors on screen:** By default (`One actor at a time`), passages feature solo characters. To have your characters appear together in the same frames, set **Ensemble** to **Always** (or **Mixed** during energetic passages) and increase **Actors on screen** to 2 or more.

### Studio direction & power-user tips

For fine-grained creative control over video generation and post-production, see [Studio Direction & Prompting](docs/STUDIO_DIRECTION_PROMPTING.md#6-power-user-production-tips--studio-best-practices):
- **Passage takes & single-clip rerolls:** Reroll, rewrite, or hand-edit single passage clips on finished local productions and re-encode the final video losslessly from chosen takes without re-rendering the whole song.
- **The Two Seeds:** Master the difference between the **Variation Seed** (narrative blueprint, scene cuts, and vocabulary draws) and the **Render Seed** (diffusion noise, facial micro-expressions, and lighting physics).
- **Lip-sync & approved singing:** How lyrics and singer assignments lift the default sealed-lips constraint during performance passages while preventing mouth spasms in instrumentals.
- **Reference image composition:** Best practices for neutral backgrounds, clean three-quarter framing, and the optional `h3_tag_normalizer` setting (off by default) that ties each `<Picture N>` to its `<Subject N>` for local MiniMax H3.
- **Aspect ratios & resolution scaling:** Configure 9:16 vertical video for mobile social reels or 2.39:1 anamorphic cinemascope for cinema releases.

## Queue several productions

Preview a music video or ident and choose **Add to queue** instead of starting it, even while something is
rendering, then press **Start queue** on the Queue tab. Productions run one at a time. Free local work needs no
acceptance. A priced production runs only on the plan and price you approved, and is otherwise held without spending
anything. After a crash or restart the queue waits for you; **Start queue** then continues interrupted local tickets
from their saved prompts and clips.

## Agent operation

The v1.12.3 MCP server has 76 tools, including operation recovery and reset (`reset_operation`), a production queue (`queue_production`, `start_queue`, `read_queue`), OPP package inspection/import/sheet selection, prompt-retry previews, API profile add/select/remove,
model/service preferences, starter installation, confirmed actor/style
deletion, audition exports, OAP role agreements, musical score reading, lyric captioning of finished videos, visual vocabulary presets,
world editing, passage prompts and versions (`rewrite_prompt`, `edit_prompt`, `select_prompt_take`), clip takes with seeds
(`reroll_segment`, `select_segment_take`) and re-encoding the final video (`reassemble_output`). Reconnect the MCP client after upgrading to refresh its tool list.

**Open Prop Protocol:** Import verified `.opp` packages into a private, general
prop library (OPP v0.1 and v0.2; v0.2 generic assets such as stems are recorded but not rendered). For now, a selected OPP base or interaction sheet can serve as an
instrument reference in an opt-in music video. The prop format and library are
not limited to the four current musical roles; see [instrument and OPP use](docs/INSTRUMENTS.md).

The included skill and optional MCP server let an agent operate the same app,
including its OAP, review and production workflow:

```sh
.venv/bin/python -m pip install '.[mcp]'
.venv/bin/mondo-music-video-mcp
```

Run the app separately. See [agent setup](docs/AGENT_SETUP.md) and the bundled
[skill](skills/mondo-music-video/SKILL.md). A CLI client is also included:
`mondo-music-video-agent --help`.

## Your data

Data lives in your user data directory: XDG data on Linux, Application Support
on macOS, or LocalAppData on Windows. `MMV_HOME` or `--data-dir` selects another
location. Back it up to preserve actors, styles, signing identity and productions.
Keys stay in a local secrets file; environment variables `WAVESPEED_API_KEY`,
`MMV_WRITER_API_KEY`, and `MMV_VISION_API_KEY` override saved values. Keep that
directory private.

See [platform support](docs/PLATFORMS.md), [verification](docs/VERIFICATION.md),
[scope](docs/SCOPE.md), and [third-party notices](docs/THIRD_PARTY.md).

## Credits and thanks

Special thanks to [hellonearthis](https://github.com/hellonearthis) for his
contributions to Windows support, model selection, setup and OAP guidance,
and faster parallel testing—and for helping make Mondo Music Video better.

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for the full list of contributors.

## License

Mondo Music Video is licensed under [Apache License 2.0](LICENSE). Third-party
components retain their own licenses. [Open Actor Protocol](https://github.com/hodgemann/oap)
is MIT-licensed. Laya inference code is attributed in [its vendor notice](mmv/engine/validators/laya/VENDOR.md).

Copyright 2026 MAXIMUM GOOSE LABORATORY.
