# Mondo Music Video Interface Guide

This document maintains the stable naming, unique identifiers, hierarchy, and design rules for all user interface components in Mondo Music Video.

When discussing, editing, or requesting changes to UI elements, refer to them by their **Component Name** or stable **ID** (e.g. `card-track-direction` or `director-control-room`).

To toggle Component Labeling Mode in the web interface:
- Click the **🏷️ Labels** button in the studio header, or
- Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>L</kbd> (or <kbd>Alt</kbd> + <kbd>L</kbd>). Press <kbd>Esc</kbd> to exit.

---

## 1. Global Shell & Persistent Frame

### Studio Header
- **ID**: `studio-header`
- **Used in**: App layout root (always visible)
- **Code**: `webapp/index.html`, `webapp/style.css`
- **Design rules**: Height 56px, fixed at top, flex layout with brand mark, edition text, and `.header-actions`. Uses `--surface-2` background with bottom border.
- **Notes**: Houses branding, community edition info, `#theme-toggle`, and the OAP and OPP version badges (stacked, OPP under OAP; each opens its guide). The developer component-labeling toggle (`#toggle-component-labels`) lives in Studio Settings (09).

### Navigation Sidebar
- **ID**: `nav-sidebar`
- **Used in**: Main viewport left edge (desktop)
- **Code**: `webapp/index.html`, `webapp/js/core.js`
- **Design rules**: Width ~240px, fixed navigation rail. Contains two sections: `YOUR STUDIO` (active tabs 01–09) and `THE FULL STUDIO` (teaser links).
- **Notes**: Dispatches panel switching via `data-panel` attributes handled by `showPanel()` in `app.js`.

### Operation Control Bar
- **ID**: `operation-bar`
- **Used in**: Top of main workspace `<main>`
- **Code**: `webapp/index.html`, `webapp/js/core.js`
- **Design rules**: Flexbox control strip with `#status-dot`, status title, status message, progress bar, and action buttons (`#show-log`, `#copy-log`, `#clear-log`, `#cancel`, `#resume-production`).
- **Notes**: Reflects live pipeline state: idle, analyzing, writing prompts, reviewing with Laya, rendering video.

### Service Dock
- **ID**: `service-dock`
- **Used in**: Workspace top (below operation bar)
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Grid of hardware and AI engine cards (`#service-card-laya`, `#service-card-writer`, `#service-card-comfy`, `#service-card-vision`, `#service-card-vision_quality`).
- **Notes**: Live health check of local and remote service backends with auto-polling and manual refresh button.

---

## 2. Music Video Production (Panel 01)

### Music Video Panel
- **ID**: `panel-video`
- **Used in**: Primary production workflow (Section 01)
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Main studio panel hosting the multi-step video production form.

### Video Production Form
- **ID**: `video-production-form`
- **Used in**: Inside `panel-video`
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Grid of production configuration cards culminating in the `#start-production` action bar.
- **Progress**: Numbered cards and Director folds expose keyboard-operable headers with Done, Needs N, Optional or Reviewed cues. Header tint reflects inputs only; a production preview and consent are still required. A completed mixed card's **Options available** button opens only optional groups left at their defaults. The adjacent header opens every field. The Settings switch `auto_collapse_panels` stops automatic collapse only. Open, reviewed and partial states are saved in the project draft.

### Track & Direction Card
- **ID**: `card-track-direction`
- **Used in**: Step 1 of `video-production-form`
- **Code**: `webapp/index.html`
- **Design rules**: First card in form grid. Holds audio master upload, title, visual direction prompt, style dropdown, aspect ratio selector, render megapixels, and visual vocabulary controls.

### Cast & Staging Card
- **ID**: `card-cast-staging`
- **Used in**: Step 2 of `video-production-form`
- **Code**: `webapp/index.html`
- **Design rules**: Second card in form grid. Configures renderer backend, render resolution, multi-actor cast selector, supplemental reference images (each with a visible Remove action), facial movement (silent mouths / lip sync), dancing mode, and instrument performance settings. Missing required inputs are highlighted; quote validation still controls readiness.

### Director's Control Room
- **ID**: `director-control-room`
- **Used in**: Step 3 of `video-production-form`
- **Code**: `webapp/index.html`
- **Design rules**: Full-width card with collapsible folds for advanced cinematography and render policies.

#### Musical Rhythm Fold
- **ID**: `director-fold-pacing`
- **Used in**: Inside `director-control-room`
- **Code**: `webapp/index.html`
- **Design rules**: Configures beats per bar, bars per phrase, variation seed (with reroll button; governs narrative blueprints and vocabulary draws while the render seed governs diffusion noise), conceptual theme, and song lyrics / flavor text (which unlock approved singing during performance passages).

#### Camera Policies Fold
- **ID**: `director-fold-camera`
- **Used in**: Inside `director-control-room`
- **Code**: `webapp/index.html`
- **Design rules**: Configures reference policy (`all` to eliminate random strangers across all montage types, `single_subject`, or `fragmentation`), casting policy (`section` to hold character focus through a musical section, `rotate`, or `random`), ensemble mode (`off`, `mixed`, `always`), and maximum simultaneous actors on screen.

#### Video Format & Render Engine Fold
- **ID**: `director-fold-format`
- **Used in**: Inside `director-control-room`
- **Code**: `webapp/index.html`
- **Design rules**: Configures framing aspect ratio (e.g. 16:9, 9:16 vertical for reels/shorts, 21:9 anamorphic cinemascope), local render megapixels (0.9–1.0 MP for fast previews up to 1080p master density), video generation backend (Renderer), and render resolution.

#### Render Engine & Post-Processing Fold
- **ID**: `director-fold-render`
- **Used in**: Inside `director-control-room`
- **Code**: `webapp/index.html`
- **Design rules**: Configures raw clip quality (Standard, ProRes 4444, FFV1), lyric captions burn-in/sidecar, subliminal flashes, vision quality frame checking, compact prompts, opening/closing idents, and prompt cache reuse (`reuse_prompts` to skip the writer LLM when testing render seeds or styles).

---

## 3. Visual Vocabulary Engine (Panel 06)

### Visual Vocabulary Workspace
- **ID**: `panel-vocab`
- **Used in**: Section 06 navigation
- **Code**: `webapp/index.html`, `webapp/js/vocab.js`
- **Design rules**: Interactive vocabulary customization suite for camera, lighting, settings, and prop rotation pools.

### Visual Vocabulary Editor Card
- **ID**: `card-vocab-editor`
- **Used in**: Inside `panel-vocab`
- **Code**: `webapp/index.html`, `webapp/js/vocab.js`
- **Design rules**: Contains preset loader, active selection chip summary, category tabs, checkbox grid, custom keyword textarea, and save/apply actions.

---

## 4. Actors & Open Actor Protocol (Panel 03)

### Actors & Props Panel
- **ID**: `panel-actors`
- **Used in**: Section 03 navigation
- **Code**: `webapp/index.html`, `webapp/js/library.js`, `webapp/js/guides.js`
- **Design rules**: Cast management, reference portrait binding, and Open Actor Protocol packaging.
- **Actor editing**: Locally created actor cards expose an Edit visual description button, current description length and double-click inline editor. Imported signed OAP actors remain read-only, since export preserves their original package. The OPP help button opens the local guide; inspection and explicit signer acceptance remain separate from import.

### Open Prop Protocol Library
- **ID**: `opp-library-fold`
- **Used in**: `panel-actors`
- **Code**: `webapp/index.html`, `webapp/js/instruments.js`
- **Design rules**: Collapsible card listing all props, including the bundled guitar and keyboards that serve as instrument references, with OPP inspect/import. There is no separate instrument library.

### Actor Creation Form
- **ID**: `actor-create-form`
- **Used in**: Inside `panel-actors`
- **Code**: `webapp/index.html`, `webapp/js/library.js`
- **Design rules**: Collapsible card with actor ID, display name, visual description, and a local portrait preview before saving. OAP import and role-agreement cards have the same independent fold controls; folding never accepts a signer or agreement.

### OAP Import Card
- **ID**: `oap-import-card`
- **Used in**: Inside `panel-actors`
- **Code**: `webapp/index.html`, `webapp/js/library.js`, `webapp/js/oap_collection.js`
- **Design rules**: `.oap` bundle upload, unsigned package override, signature verification inspector, and trust confirmation checkbox. The public collection fold checks the published index only on button press, lists missing packages with OAP versions, and stages one selected package for signature and rider review. Import remains a separate explicit signer-acceptance action; installed IDs are preserved.

### Role Agreements Manager
- **ID**: `role-agreements-card`
- **Used in**: Bottom of `panel-actors`
- **Code**: `webapp/index.html`, `webapp/js/agreements.js`
- **Design rules**: OAP 0.5 contract drafting form (offer, currency, character, role description, ratings check) and countersigned agreement importer.

---

## 5. Visual Styles & Harvesting (Panels 04 & 05)

### Styles Library Panel
- **ID**: `panel-styles`
- **Used in**: Section 04 navigation
- **Code**: `webapp/index.html`, `webapp/js/styles.js`
- **Design rules**: Grid of visual style direction cards with preview chips and creation/import cards.

### Style Creation Form
- **ID**: `style-create-form`
- **Used in**: Inside `panel-styles`
- **Code**: `webapp/index.html`, `webapp/js/styles.js`
- **Design rules**: Custom style ID, name, and visual language prompt directives.

### Style Import Card
- **ID**: `style-import-card`
- **Used in**: Inside `panel-styles`
- **Code**: `webapp/index.html`, `webapp/js/styles.js`
- **Design rules**: JSON style card importer with 4-layer validation and overwrite option.

### Style Harvest Panel
- **ID**: `panel-harvest`
- **Used in**: Section 05 navigation
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Multimodal vision analysis interface to reverse-engineer aesthetic prompt vocabularies from reference pictures.

### Harvest Production Form
- **ID**: `harvest-production-form`
- **Used in**: Inside `panel-harvest`
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Narrow card with new style ID, style name, 1–9 reference images, and preview harvest button.

### Harvest Result Feedback
- **ID**: `harvest-result-card`
- **Used in**: Inside `panel-harvest`, shown after a harvest completes
- **Code**: `webapp/index.html`, `webapp/js/production.js`
- **Design rules**: Shows the harvested style's name, visual language and 11-axis card, with View in Styles Library, Copy Style JSON and Dismiss.

---

## 6. Credits, Idents & Finished Productions (Panels 02 & 08)

### Credits & Idents Panel
- **ID**: `panel-idents`
- **Used in**: Section 02 navigation
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Production ident and title card animator.

### Ident Production Form
- **ID**: `ident-production-form`
- **Used in**: Inside `panel-idents`
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Design rules**: Title text, motion direction, style select, backend renderer, duration (4–12s), shape, and reference image inputs.

### Finished Videos Panel
- **ID**: `panel-outputs`
- **Used in**: Section 08 navigation
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Design rules**: Gallery grid of rendered music videos and idents with inline playback, download, Topaz upscale, Edit, and export triggers.

### Edit View (passages)
- **ID**: `outputs-breakdown-view`
- **Used in**: Replaces the gallery inside `panel-outputs` when **Edit** is pressed on a finished output card; **Back to Finished Videos** returns and **↻ Refresh** re-reads the video (it also refreshes itself whenever an operation finishes)
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Design rules**: One card per passage: the written prompt (character count, copyable) on the left, the clip on the right with a take menu that previews recorded takes and, for local H3 productions, **🎬 Render Clip** (the app's teal action colour, one step lighter) after a confirmation. The header offers **Re-encode Final Video with Selected Takes** and a Final Video Version menu that downloads preserved versions. Each prompt's length is shown against the renderer's own ceiling when it has one (from its rate card). Under each prompt, a version menu previews prompt versions; **Use this version** (passed versions only), **✏️ Edit prompt** with **Check and use**, and **✍️ Write new prompt** (confirmation, with the writer's estimate for an API writer) go through the production's own checks and Laya. The clip side shows the previewed take's seed and a **Next seed** field with **Random**. Opening the view changes nothing.

### Unfinished Runs Manager
- **ID**: `unfinished-runs-manager`
- **Used in**: Bottom of `panel-outputs`
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Design rules**: Collapsible table displaying interrupted or incomplete production runs with Resume, View, and Purge actions.

---

## 7. Worlds (Panel 07)

### Worlds Panel
- **ID**: `panel-worlds`
- **Used in**: Section 07 navigation
- **Code**: `webapp/index.html`, `webapp/js/worlds.js`
- **Design rules**: Persistent, versioned canon shared across videos. Contains the worlds list, the proposal review card and the build/grow form. Nothing is saved to a world until a proposal is accepted. See `docs/WORLDS.md`.

### Worlds List and Detail
- **IDs**: `worlds-list-card`, `worlds-list`, `world-detail`
- **Used in**: Top of `panel-worlds`
- **Code**: `webapp/index.html`, `webapp/js/worlds.js`
- **Design rules**: Lists saved worlds; the detail view shows the ledger, version history, rollback, export and delete (delete needs explicit confirmation).

### World Proposals
- **IDs**: `world-proposals-card`, `world-proposals`
- **Used in**: Inside `panel-worlds`, hidden until a proposal is pending
- **Code**: `webapp/index.html`, `webapp/js/worlds.js`
- **Design rules**: Field-level changes from a world harvest, with Accept and Reject. A proposal made against an older version must be harvested again.

### World Builder Form
- **IDs**: `world-form`, `world-builder-form`, `world-images`, `world-videos`, `world-lore`, `world-runs`, `world-preview`, `world-clear`, `world-quote`, `world-consent`, `world-start`
- **Used in**: Inside `panel-worlds`
- **Code**: `webapp/index.html`, `webapp/js/worlds.js`
- **Design rules**: Start a new world or grow an existing one from pictures (up to 24), video clips (up to 3), lore text (up to 5 files) and finished runs. Preview first; starting follows the usual quote and paid-consent flow when an API vision profile is used. Each world row has **Open** (read-only view with Restore buttons) and **Edit** buttons, and the opened view has Edit at its top and bottom: names, rules, subjects and the vocabulary pools (the Visual Vocabulary editor's tabs and checkboxes) are edited in place, **Preview changes** shows exactly what would change, and only then can **Save as new version** be pressed. Earlier versions can be restored.

### World Selector
- **ID**: `world-select`
- **Used in**: Music Video form (`panel-video`)
- **Code**: `webapp/index.html`, `webapp/js/worlds.js`
- **Design rules**: Chooses the world a video draws on; the pool mode decides whether the world's terms replace or add to the standard vocabulary pools.

---

## 8. Studio Settings (Panel 09)

### Studio Settings Panel
- **ID**: `panel-settings`
- **Used in**: Section 09 navigation
- **Code**: `webapp/index.html`, `webapp/js/settings.js`
- **Design rules**: Local hardware, model parameters, API profiles, and credential configuration.

### Studio Settings Form
- **ID**: `settings-form`
- **Used in**: Inside `panel-settings`
- **Code**: `webapp/index.html`, `webapp/js/settings.js`
- **Design rules**: Dynamic grid of input fields populated from server configuration schema.

### Provider Keys Form
- **ID**: `key-form`
- **Used in**: Inside `panel-settings`
- **Design rules**: One paste-and-save row per provider key (WaveSpeed, ComfyUI, Vision, Writer, Topaz cloud) with saved / not set status; the row component (`keyRow` in `webapp/js/core.js`) is reused in the Topaz upscale dialog. Keys are never shown again.
- **Design rules**: Secret credential storage for Wavespeed, ComfyUI, Vision, and Writer API keys.

---

## 9. Modals & Dialogs

### Pre-Production Review Dialog
- **ID**: `preview-dialog`
- **Code**: `webapp/index.html`, `webapp/js/app.js`
- **Purpose**: Displays musical beat analysis, montage passage breakdown, score editor, and cost estimates. Requires explicit user consent before generation starts.

### Lyric Captions Dialog
- **ID**: `caption-dialog`
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Purpose**: Re-encodes finished video with burned-in lyric subtitle lines in selected style, position, and colors.

### Topaz Upscale Dialog
- **ID**: `upscale-dialog`
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Purpose**: Launches a Topaz enhancement job (2x or 4x) on finished renders, using the installed Topaz Video AI or, when Settings chooses Topaz cloud, the Topaz cloud service. The cloud mode shows a model picker, Frame rate controls (interpolation model, fps, slow motion, duplicate removal), a Tuning section and a free **Get free estimate** step (credits, time, output size) and a credit-approval checkbox; Start stays disabled until it is ticked.

### Folder Picker Dialog
- **ID**: `folder-picker-dialog`
- **Code**: `webapp/index.html`, `webapp/js/settings.js`
- **Purpose**: Native-like filesystem browser for selecting local paths in settings without manual typing.

### OAP Helper Dialog
- **ID**: `oap-helper-dialog`
- **Code**: `webapp/index.html`, `webapp/js/oap.js`
- **Purpose**: Multi-tab guide explaining characters vs references, OAP specification, Ed25519 signatures, safety riders, and pipeline isolation.

### Local Writer Helper Dialog
- **ID**: `llama-helper-dialog`
- **Code**: `webapp/index.html`, `webapp/js/settings.js`
- **Purpose**: Guide and JSON tuner for local `llama.cpp` server flags, context sizes, and vision projectors.

### Production Package Export Dialog
- **ID**: `export-dialog`
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Purpose**: Packages raw passage clips, stems, EDL timeline, and prompts into an NLE editing bundle.

### Delete Video Dialog
- **ID**: `delete-video-dialog`
- **Code**: `webapp/index.html`, `webapp/js/outputs.js`
- **Purpose**: Confirmation modal before deleting finished video files and passages from disk.

### Visual Vocabulary Guide Dialog
- **ID**: `vocab-helper-dialog`
- **Code**: `webapp/index.html`, `webapp/js/vocab.js`
- **Purpose**: Reference guide documenting rotation pools, categories, and keyword syntax.

### Vision Guide Dialog
- **ID**: `vision-helper-dialog`
- **Code**: `webapp/index.html`, `webapp/js/guides.js`
- **Purpose**: Shows `docs/QUALITY_VISION_SETUP.md`, explaining Style Harvest vision versus the Quality Vision frame checker. Opened from the Style Harvest header button or by clicking (or pressing Enter on) the Vision and Quality Vision service cards.

