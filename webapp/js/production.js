import { renderQueue, syncQueueButton } from "./queue.js";
// Production quote/preview, operation controls, live AI service dock, SSE stream, and update status.

import { $, $$, api, copyToClipboard, handle, json, logSession, notice, state, text, updateLogDisplay, upload } from "./core.js";
import { disposeScoreEditor, mountScoreEditor } from "./score_editor.js";
import { loadActors, loadStyles, styleCardDisplay } from "./library.js";
import { loadOutputs, refreshProductionBreakdown } from "./outputs.js";
import { scheduleSave, updateSongPreview } from "./project.js";
import { storyboardFromForm, refreshStoryboards } from "./storyboard.js";
import { loadWorlds } from "./worlds.js";

import { syncInstrumentControls, instrumentsFromForm } from "./instruments.js";

import { syncDanceControls, dancePartsFromForm } from "./dance.js";
import { refreshPanelProgress, showPanelForQuoteError } from "./panel_progress.js";

let sseSource = null;
let sseConnected = false;
export const isSseConnected = () => sseConnected;
export const getSseSource = () => sseSource;
let statusTimer = null;
let lastStreamEvent = 0;

const escapeHtml = (s = "") =>
  String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

export const removeReferenceAtIndex = (references = [], names = [], indexToRemove = -1) => ({
  references: references.filter((_, index) => index !== indexToRemove),
  names: names.filter((_, index) => index !== indexToRemove)
});

function removeReference(form, index) {
  const fState = state.formFiles.get(form);
  if (!fState || index < 0 || index >= fState.references.length) return;
  const updated = removeReferenceAtIndex(fState.references, fState.referenceNames || [], index);
  fState.references = updated.references;
  fState.referenceNames = updated.names;
  form.querySelector(".refs-input").value = "";
  renderReferenceReceipt(form, fState.referenceNames, fState.references);
  const remainingButtons = form.querySelectorAll(".refs-receipt .remove-ref");
  (remainingButtons[Math.min(index, remainingButtons.length - 1)] || form.querySelector(".clear-refs"))?.focus();
  if (form.dataset.kind === "harvest") form.querySelector(".refs-input").required = !fState.references.length;
  refreshPanelProgress();
  scheduleSave();
}

// The form has flat subliminal_* fields; the request carries them as one nested object.

export function renderReferenceReceipt(form, names = [], hashes = []) {
  const receipt = form?.querySelector(".refs-receipt");
  if (!receipt) return;
  if (!names.length) {
    receipt.innerHTML = form.id === "video-form" ? "No additional images" : "No reference images";
    return;
  }
  const items = names.map((name, i) => {
    const hash = hashes[i];
    const titleText = `Reference: ${escapeHtml(name)}`;
    const imgAttr = hash
      ? ` data-tooltip="${titleText}" data-tooltip-image="/api/uploads/reference/${encodeURIComponent(hash)}" data-tooltip-position="top"`
      : ` data-tooltip="${titleText}"`;
    return `<li><code data-ref-index="${i}"${imgAttr}>${escapeHtml(name)}</code><button type="button" class="remove-ref" data-ref-index="${i}" aria-label="Remove reference image ${escapeHtml(name)}">Remove</button></li>`;
  }).join("");
  receipt.innerHTML = `<ul class="file-list">${items}</ul>`;
}

export function subliminalFromForm(request) {
  const mode = request.subliminal_mode || "off";
  const times = String(request.subliminal_times || "").split(/[\s,;]+/).filter(Boolean).map(Number);
  if (times.some(value => !Number.isFinite(value) || value < 0)) throw new Error("Flash times are seconds, like 12.5, 40, 55.2");
  if (mode === "image" && !request.subliminal_image) throw new Error("Choose the picture to flash");
  request.subliminal = {
    mode, image: request.subliminal_image || "", text: request.subliminal_text || "",
    frames: Number(request.subliminal_frames) || 2, placement: request.subliminal_placement || "manual", times,
    count: Number(request.subliminal_count) || 3
  };
  for (const key of Object.keys(request)) if (key.startsWith("subliminal_")) delete request[key];
  return request.subliminal;
}

export function captionsFromForm(request) {
  request.captions = { mode: request.captions_mode || "off", style: request.captions_style || "classic",
    position: request.captions_position || "bottom", size: request.captions_size || "medium",
    color: request.captions_custom ? request.captions_color : "",
    outline_color: request.captions_custom ? request.captions_outline : "", font: request.captions_font || "" };
  for (const key of Object.keys(request)) if (key.startsWith("captions_")) delete request[key];
  return request.captions;
}

// Only the most recently chosen file may set the flash picture: slower, older uploads must never overwrite it.
export function latestSelection() {
  let current = 0;
  return { begin: () => ++current, isCurrent: token => token === current };
}

export function initSubliminalControls() {
  const form = $("#video-form");
  const captionMode = form?.elements.captions_mode;           // the look controls matter only when the words are burned in
  if (captionMode) {
    const syncCaptions = () => { form.querySelector(".captions-fields").hidden = captionMode.value !== "burned"; };
    captionMode.addEventListener("change", syncCaptions);
    syncCaptions();
  }
  const mode = form?.elements.subliminal_mode;
  if (!mode) return;
  const fields = form.querySelector(".subliminal-fields");
  const sync = () => {
    fields.hidden = mode.value === "off";
    form.querySelectorAll('[data-sub="text"]').forEach(node => { node.hidden = mode.value !== "text"; });
    form.querySelectorAll('[data-sub="image"]').forEach(node => { node.hidden = mode.value !== "image"; });
    const downbeats = form.elements.subliminal_placement.value === "downbeats";
    form.querySelectorAll('[data-sub="manual"]').forEach(node => { node.hidden = downbeats; });
    form.querySelectorAll('[data-sub="downbeats"]').forEach(node => { node.hidden = !downbeats; });
  };
  mode.addEventListener("change", sync);
  form.elements.subliminal_placement.addEventListener("change", sync);
  const selection = latestSelection();
  form.elements.subliminal_file.addEventListener("change", handle(async () => {
    const file = form.elements.subliminal_file.files[0];
    const mine = selection.begin();
    form.elements.subliminal_image.value = "";                    // the previous picture is no longer selected
    if (!file) { delete form.dataset.subliminalPending; scheduleSave(); return; }
    form.dataset.subliminalPending = "1";
    try {
      const id = await upload(file, "reference");
      if (selection.isCurrent(mine)) form.elements.subliminal_image.value = id;
    } finally {
      if (selection.isCurrent(mine)) delete form.dataset.subliminalPending;
    }
    scheduleSave();
  }));
  sync();
}

// Gather the contrast_<role> selects into the world_contrast request map and remove the loose fields.
function contrastFromRequest(request) {
  const roles = ["mirror", "opposite", "tangent"];
  const chosen = Object.fromEntries(roles.filter((role) => request["contrast_" + role]).map((role) => [role, request["contrast_" + role]]));
  roles.forEach((role) => delete request["contrast_" + role]);
  return request.world_id ? chosen : {};
}

export async function preview(form) {
  if (form.dataset.subliminalPending) throw new Error("Wait for the flash picture to finish uploading");
  const data = Object.fromEntries(new FormData(form));
  const files = state.formFiles.get(form) || { references: [] };
  if (files.pending) throw new Error("Wait for the selected files to finish uploading");
  const request = { kind: form.dataset.kind, ...data, references: files.references };
  request.compact_prompts = Boolean(form.elements.compact_prompts?.checked);
  request.strict_prompt_checks = Boolean(form.elements.strict_prompt_checks?.checked);
  if (request.kind === "video") {
    if (!files.song) throw new Error("Upload your song first");
    request.song = files.song;
    request.actors = [...form.querySelector(".actor-select").selectedOptions].map(item => item.value);
    for (const name of ["megapixels", "beats_per_bar", "bars_per_phrase", "seed", "on_screen", "render_seed"]) {
      request[name] = Number(request[name]);
    }
    if (String(data.render_seed ?? "").trim() === "") delete request.render_seed;   // empty: the preview picks a random render seed
    dancePartsFromForm(form, request);
    instrumentsFromForm(form, request);
    subliminalFromForm(request);
    captionsFromForm(request);
    request.mouth_mode = request.mouth_mode || "sealed";
    request.silent_mouths = request.mouth_mode !== "natural";   // older agents read this flag
    request.reuse_prompts = form.elements.reuse_prompts ? form.elements.reuse_prompts.checked : true;
    request.vision_quality_check = Boolean(form.elements.vision_quality_check?.checked);
    request.content = {};
    for (const category of Object.keys(state.catalog.ratings)) {
      request.content[category] = request["rating_" + category];
      delete request["rating_" + category];
    }
    if (state.thematicWorlds && state.thematicWorlds.mode && state.thematicWorlds.mode !== "off") {
      request.thematic_worlds = state.thematicWorlds;
    }
    request.world_contrast = contrastFromRequest(request);
    request.world_contrast_strength = Number(request.world_contrast_strength);
    if (state.currentCustomVocab && Object.keys(state.currentCustomVocab).length) {
      request.custom_vocabulary = state.currentCustomVocab;
    }
  }
  if (request.kind === "ident") request.ident_seconds = Number(request.ident_seconds);

  if (["video", "ident"].includes(request.kind)) storyboardFromForm(form, request);

  const submitBtn = form.querySelector('button[type="submit"]') || form.querySelector(".action-bar .primary") || form.querySelector("button.primary");
  const originalHtml = submitBtn ? submitBtn.innerHTML : null;
  const originalCursor = document.body.style.cursor;

  let busyText = "Processing preview…";
  let noticeMsg = "Generating preview quote…";
  if (request.kind === "video") {
    busyText = "Analyzing audio & planning…";
    noticeMsg = "Analyzing audio track and planning production cuts… This may take a few moments.";
  } else if (request.kind === "harvest") {
    busyText = "Analyzing references…";
    noticeMsg = "Analyzing reference images for style harvest…";
  } else if (request.kind === "ident") {
    busyText = "Composing ident plan…";
    noticeMsg = "Composing ident animation plan and preview quote…";
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-busy", "true");
    submitBtn.classList.add("processing");
    submitBtn.innerHTML = `${busyText} <span class="spinner" aria-hidden="true"></span>`;
  }
  document.body.style.cursor = "wait";
  notice(["running", "cancelling"].includes(state.lastState) && (request.analysis_driver || "mix") !== "mix"
    ? "Preparing the preview. If its stems need the GPU, they run as soon as the current production finishes."
    : noticeMsg);

  try {
    logSession(`Preview requested for kind='${request.kind}' backend='${request.backend}'`);
    state.lastRequest = request;
    state.currentQuote = await json("/api/quote", request);
    logSession(`Preview ready: quote_id='${state.currentQuote.id}' estimate=$${Number(state.currentQuote.estimate_usd).toFixed(2)}`);
    if ($("#notice") && $("#notice").textContent === noticeMsg) {
      notice("");
    }
    showQuote(request, state.currentQuote);
  } catch (error) {
    if (request.kind === "video") showPanelForQuoteError(error.message);
    throw error;
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.removeAttribute("aria-busy");
      submitBtn.classList.remove("processing");
      if (originalHtml !== null) submitBtn.innerHTML = originalHtml;
    }
    document.body.style.cursor = originalCursor;
  }
}

export function showQuote(request, quote) {
  state.currentQuote = quote;
  const summary = $("#quote-summary");
  summary.replaceChildren();
  summary.append(
    text("p", request.kind === "storyboard" ? "Interpret storyboard images for review." : request.kind === "harvest" ? "One visual style harvest." : `${quote.clips} clips · ${quote.seconds.toFixed(1)} seconds of ${request.kind === "ident" ? "ident" : "music"}.`),
    text("h2", `Estimated provider cost: $${Number(quote.estimate_usd).toFixed(2)}`),
    ...(quote.render_seed != null && ["video", "ident"].includes(request.kind)
      ? [text("p", `Variation seed ${quote.seed} · render seed ${quote.render_seed}${request.render_seed == null ? " (random; type it into Render seed to repeat this video)" : ""}`, "muted quote-seed")] : []),
    text("p", quote.note, "muted")
  );
  if (quote.storyboard) {
    summary.append(text('h3', 'Storyboard alignment'));
    for (const [passage, panels] of Object.entries(quote.storyboard.passages)) {
      for (const panel of panels) summary.append(text('p', `${panel.start_seconds.toFixed(2)}s · Panel ${panel.panel} · ${panel.direction}`));
    }
  }
  if (quote.dance) {
    const dancing = Object.values(quote.dance.passages).filter(item => item.dancing).length;
    const left = [...new Set(Object.values(quote.dance.passages).flatMap(item => item.not_choreographed || []))];
    if (quote.dance.mode === "independent") {
      for (const [actor, part] of Object.entries(quote.dance.parts || {})) {
        summary.append(text("p", `${quote.dance.actors[actor] || actor}: ${part}`, "muted"));
      }
      const fallbacks = [...new Set(Object.values(quote.dance.passages).flatMap(item => (item.dancers || []).map(d => d.fallback).filter(Boolean)))];
      for (const fallback of fallbacks) summary.append(text("p", fallback, "muted"));
    }
    summary.append(text("p", `Dancing: ${dancing} of ${Object.keys(quote.dance.passages).length} passages, "${quote.dance.direction}".` +
      (left.length ? ` Only the first 3 dancers in a passage are choreographed; not choreographed: ${left.join(", ")}.` : ""), "muted"));
  }
  if (quote.instruments) {
    for (const [actor, instrument] of Object.entries(quote.instruments.assignments)) {
      summary.append(text("p", `${actor}: ${instrument}`, "muted"));
    }
    for (const [kind, asset] of Object.entries(quote.instruments.assets || {})) {
      if (asset.prop_id) summary.append(text("p", `${kind}: OPP prop ${asset.name} (${asset.prop_id}), ${asset.sheet_kind} sheet “${asset.sheet_label}” · ${asset.clearance} clearance`, "muted"));
    }
    const fallbacks = [...new Set(Object.values(quote.instruments.passages).flatMap(p => p.performers.map(player => player.fallback).filter(Boolean)))];
    for (const fallback of fallbacks) summary.append(text("p", fallback, "muted"));
    for (const [id, passage] of Object.entries(quote.instruments.passages)) {
      if (passage.performers.length) summary.append(text("p", `${id}: ${passage.actor_slots} actor references + ${passage.references.length} instrument references; ${passage.performers.map(p => `${p.display_name}: ${p.active ? 'playing' : 'paused'}`).join(', ')}`, "muted"));
    }
  }
  if (quote.subliminal) {
    summary.append(text("p", `Subliminal flashes: ${quote.subliminal.times.length} × ${quote.subliminal.frames} frame(s) at ${quote.subliminal.times.join(", ")} s. ${quote.subliminal.notice}`, "muted"));
  }
  if (quote.captions) {
    if (quote.captions.note) summary.append(text("p", quote.captions.note, "se-warn"));
    else summary.append(text("p", `Lyric captions: ${quote.captions.cues.length} line(s) ${quote.captions.mode === "burned" ? "burned into the video (a copy without captions is kept) and saved" : "saved"} as lyrics.srt.`, "muted"));
  }
  if (request.thematic_worlds && request.thematic_worlds.mode && request.thematic_worlds.mode !== "off") {
    const tw = request.thematic_worlds;
    const activeNames = (tw.activeWorlds && tw.activeWorlds.length) ? tw.activeWorlds.join(", ") : "Selected themes";
    const modeLabel = tw.mode.charAt(0).toUpperCase() + tw.mode.slice(1);
    const mult = (2 * ((tw.slider ?? 50) / 100)).toFixed(1);
    summary.append(text("p", `🧭 Thematic Worlds active: ${modeLabel} mode (juxtaposition ${tw.slider ?? 50}% / x${mult}), anchored by ${activeNames}.`, "muted"));
  }
  if (request.clip_quality && request.clip_quality !== "standard") {
    summary.append(text("p", `Studio-quality raw clips (${request.clip_quality === "prores" ? "ProRes 4444" : "FFV1 lossless"}): each passage clip is saved near-lossless for editing. `
      + "Expect much larger files and a little more time; the final video is still encoded from them.", "muted"));
  }
  if (request.vision_quality_check) {
    summary.append(text("p", "Vision quality check on: after rendering, your local vision model inspects sampled frames. "
      + "This adds model-loading and checking time. ComfyUI can remain open; free local passages may be re-rendered once.", "muted"));
  }
  if (quote.analysis && request.kind === "video") {
    const a = quote.analysis;
    summary.append(text("p", `Detected tempo: ${a.tempo_bpm.toFixed(1)} BPM · ${a.beats} beats · ${a.downbeats} downbeats · ${a.sections} sections · ${a.shots} shots · ${a.width} × ${a.height}`));
    for (const passage of quote.segments) {
      summary.append(text("p", `${(passage.song_start_frame / 24).toFixed(2)}s · ${passage.section_label} · ${passage.montage_type.replaceAll("_", " ")} · ${passage.shots.length} shots`));
    }
  }
  const offlineList = quote.offline_engines || [];
  if (offlineList.length > 0) {
    const banner = document.createElement("div");
    banner.className = "service-alert-banner";
    banner.setAttribute("role", "alert");
    banner.innerHTML = `
      <div class="service-alert-header">
        <span class="service-alert-icon" aria-hidden="true">⚠️</span>
        <strong>Required Engine Offline</strong>
      </div>
      <ul class="service-alert-list">
        ${offlineList.map(err => `<li>${escapeHtml(err)}</li>`).join("")}
      </ul>
      <p class="service-alert-foot">Production cannot start until the problems above are fixed. Engines with a valid launch setting start automatically when needed; correct the setting or free the resource named above, then request a new preview.</p>
    `;
    summary.prepend(banner);

    $("#consent").checked = false;
    $("#consent").disabled = true;
    const startBtn = $("#start-production");
    if (startBtn) {
      startBtn.disabled = true;
      startBtn.title = "A required engine cannot start. Fix the problem named in the preview to proceed.";
    }
  } else {
    $("#consent").disabled = false;
    const startBtn = $("#start-production");
    if (startBtn) {
      startBtn.disabled = false;
      startBtn.title = "";
    }
  }
  $("#consent").checked = false;
  syncQueueButton(request, quote);
  const dialog = $("#preview-dialog");
  if (!dialog.dataset.scoreEditorBound) {
    dialog.dataset.scoreEditorBound = "1";
    dialog.addEventListener("close", disposeScoreEditor);
  }
  dialog.showModal();
  mountScoreEditor($("#score-editor"), request, quote, {
    onReplan: async (edits, driver, quality, lip) => {
      const next = { ...request, score_edits: edits, analysis_driver: driver || "mix", stem_quality: quality || "standard", ...(lip || {}) };
      state.lastRequest = next;
      const replanned = await json("/api/quote", next);
      logSession(`Re-planned with score edits: quote_id='${replanned.id}'`);
      showQuote(next, replanned);
    },
    onDirty: dirty => {
      const start = $("#start-production");
      if (start) {
        start.disabled = dirty;
        start.title = dirty ? "Re-plan first: your score edits are not in the plan yet" : "";
      }
    }
  }).catch(error => notice(error.message));
}

const serviceStateCache = new Map();

export function renderServices(services) {
  if (!services || typeof services !== "object") return;
  const entries = [
    { id: "laya", data: services.laya },
    { id: "writer", data: services.writer },
    { id: "comfy", data: services.comfy },
    { id: "vision", data: services.vision },
    { id: "vision_quality", data: services.vision_quality }
  ];
  for (const { id, data } of entries) {
    if (!data) continue;
    const activity = data.activity || (data.available ? "sleeping" : "offline");
    const onDemand = activity === "offline" && data.has_launch;
    const tone = activity === "configured" || onDemand ? "missing" : activity;
    const detailText = data.detail || (data.available ? "Ready" : "Offline");
    const cacheKey = `${activity}|${detailText}|${Boolean(data.available)}|${Boolean(onDemand)}`;
    if (serviceStateCache.get(id) === cacheKey) continue;
    serviceStateCache.set(id, cacheKey);

    const dot = $(`#service-dot-${id}`);
    const badge = $(`#service-badge-${id}`);
    const detail = $(`#service-detail-${id}`);
    const card = $(`#service-card-${id}`);

    if (dot) {
      dot.className = `service-pulse-dot dot-${tone}`;
    }

    if (badge) {
      badge.className = `service-badge badge-${tone}`;
      if (activity === "processing") {
        badge.textContent = "PROCESSING";
      } else if (activity === "sleeping") {
        badge.textContent = "SLEEPING (READY)";
      } else if (activity === "configured") {
        badge.textContent = "CONFIGURED";
      } else if (onDemand) {
        badge.textContent = "STARTS AUTOMATICALLY";
      } else if (activity === "missing") {
        badge.textContent = "NEEDS SETUP";
      } else {
        badge.textContent = "OFFLINE";
      }
    }

    if (detail) {
      detail.textContent = detailText;
      detail.title = data.detail || "";
    }

    if (card) {
      card.classList.toggle("card-processing", activity === "processing");
      card.classList.toggle("card-missing", activity === "missing");
      const roleEl = card.querySelector(".service-role");
      const roleText = roleEl ? ` (${roleEl.textContent})` : "";
      const summary = `${id}${roleText}: ${badge ? badge.textContent : activity} — ${detailText}`;
      card.dataset.tooltip = summary;
      card.title = summary;
    }
  }
}

export async function refreshServices(force = false) {
  const btn = $("#refresh-services");
  try {
    if (btn) btn.disabled = true;
    const resp = await api(`/api/services/status${force ? "?force=true" : ""}`);
    if (resp.ok) {
      const data = await resp.json();
      renderServices(data);
    }
  } catch (err) {
    console.debug("Failed to fetch service status", err);
  } finally {
    if (btn) btn.disabled = false;
  }
}

export async function applyStatus(status) {
  if (!status || !status.state) return;
  state.currentRun = status.id;
  const busy = ["running", "cancelling"].includes(status.state);
  $("#status-title").textContent = status.state === "idle" ? "READY WHEN YOU ARE" : status.state.toUpperCase();
  $("#status-message").textContent = status.message || "One idea. One production at a time.";
  $("#progress").value = status.progress || 0;
  $("#cancel").hidden = !busy;
  $("#resume-production").hidden = !status.can_resume;
  $("#retry-prompts").hidden = !status.can_retry_prompts;
  const stopped = ["failed", "cancelled", "interrupted"].includes(status.state);
  const resetBtn = $("#reset-operation");
  if (resetBtn) resetBtn.hidden = !stopped;
  const purgeRestartBtn = $("#purge-restart-operation");
  if (purgeRestartBtn) purgeRestartBtn.hidden = !stopped;
  $("#show-log").hidden = false;
  $$(".operation-action").forEach(button => button.disabled = busy);
  if (status.queue) renderQueue(status.queue);
  if (status.services) {
    renderServices(status.services);
  }
  $$(".service-card").forEach(c => c.classList.remove("card-offline-needed"));
  if (status.state === "failed") {
    const msg = (status.message || "").toLowerCase();
    if (msg.includes("offline") || msg.includes("unreachable") || msg.includes("connection refused") || msg.includes("cannot start")) {
      if (msg.includes("writer") || msg.includes("llama")) {
        $("#service-card-writer")?.classList.add("card-offline-needed");
      }
      if (msg.includes("comfy")) {
        $("#service-card-comfy")?.classList.add("card-offline-needed");
      }
      if (msg.includes("vision")) {
        const checker = msg.includes("quality") || msg.includes("vision model") || msg.includes("vision check");
        $(checker ? "#service-card-vision_quality" : "#service-card-vision")?.classList.add("card-offline-needed");
      }
      if (msg.includes("laya")) {
        $("#service-card-laya")?.classList.add("card-offline-needed");
      }
    }
  }
  if (state.lastState && state.lastState !== status.state && !busy) {
    await Promise.all([loadActors(), loadStyles(), loadOutputs(), loadWorlds(), refreshStoryboards()]);
    await refreshProductionBreakdown();   // an open Edit view shows the new take, prompt version or final version
  }
  // Also after a reload: show the latest completed harvest once per operation (Dismiss keeps it hidden).
  if (status.state === "complete" && status.kind === "harvest" && status.result?.style && state.harvestShown !== status.id) {
    state.harvestShown = status.id;
    displayHarvestResult(status.result.style);
  }
  state.lastState = status.state;
}

export function setupEventStream() {
  if (typeof EventSource !== "undefined") {
    try {
      sseSource = new EventSource("/api/events");
      sseSource.addEventListener("status", event => {
        try {
          const status = JSON.parse(event.data);
          lastStreamEvent = Date.now();
          sseConnected = true;
          applyStatus(status).catch(error => notice(error.message));
        } catch {}
      });
      sseSource.addEventListener("log", event => {
        try {
          const data = JSON.parse(event.data);
          if (!$("#operation-log").hidden && data.message) {
            const logElem = $("#operation-log");
            if (logElem && !logElem.textContent.includes(data.message)) {
              logElem.textContent += "\n" + data.message;
            }
          }
        } catch {}
      });
      sseSource.onerror = () => { sseConnected = false; };
    } catch { sseConnected = false; }
  }
  // Keep one watchdog alive even while SSE is healthy, so disconnects and
  // proxies buffering events cannot permanently stop operation updates.
  fallbackPoll();
}

export async function fallbackPoll() {
  clearTimeout(statusTimer);
  const busy = ["running", "cancelling"].includes(state.lastState);
  const interval = busy ? 2000 : 10000;
  try {
    if (!sseConnected || Date.now() - lastStreamEvent > 20000) {
      const status = await (await api("/api/status")).json();
      await applyStatus(status);
    }
    if (!$("#operation-log").hidden) await updateLogDisplay();
  } catch {
    $("#status-message").textContent = "Connection unavailable. The server may have stopped.";
  } finally {
    statusTimer = setTimeout(fallbackPoll, interval);
  }
}

window.addEventListener("pagehide", () => {
  if (sseSource) sseSource.close();
  clearTimeout(statusTimer);
});
window.addEventListener("pageshow", event => {
  if (event.persisted) setupEventStream();
});

// A fork that changed the protected prompting scheme sees a persistent warning (see docs/PROMPT_SCHEME_PROTECTION.md).
export async function loadSchemeNotice() {
  try {
    const status = await (await api("/api/integrity")).json();
    const banner = $("#scheme-notice");
    if (banner && status.notice) {
      banner.textContent = status.notice;
      banner.hidden = false;
    }
  } catch { /* The notice must not block the studio UI. */ }
}

export async function loadUpdateStatus() {
  try {
    const status = await (await api("/api/update")).json();
    const banner = $("#update-banner");
    if (!status.available && !["updated", "failed", "unavailable"].includes(status.state)) return;
    $("#update-message").textContent = status.message + (status.available && status.available_version && status.available_version !== "unknown" ? ` Available version: ${status.available_version}.` : "");
    const link = $("#update-repository");
    if (status.repository_url) {
      const url = new URL(status.repository_url);
      if (["https:", "http:"].includes(url.protocol)) {
        link.href = url.href;
        link.hidden = false;
      }
    }
    banner.hidden = false;
  } catch { /* Update availability must not block the studio UI. */ }
}

export function initProductionForms() {
  $$(".production-form").forEach(form => {
    syncDanceControls(form);
    syncInstrumentControls(form);
    form.addEventListener("change", event => {
      syncDanceControls(form, event.target);
      syncInstrumentControls(form, event.target);
    });
    state.formFiles.set(form, { references: [], pending: 0 });
    form.onsubmit = handle(() => preview(form));
    const song = form.querySelector(".song-input");
    if (song) {
      song.onchange = handle(async () => {
        const selected = song.files[0];
        if (!selected) return;
        const fState = state.formFiles.get(form);
        if (fState.songObjectUrl) {
          updateSongPreview(form, "");
          URL.revokeObjectURL(fState.songObjectUrl);
          fState.songObjectUrl = undefined;
        }
        fState.songObjectUrl = URL.createObjectURL(selected);
        updateSongPreview(form, fState.songObjectUrl);
        fState.song = undefined;
        fState.songName = undefined;
        fState.pending++;
        song.disabled = true;
        form.querySelector(".song-receipt").textContent = "Uploading " + selected.name + "…";
        try {
          fState.song = await upload(selected, "song");
          fState.songName = selected.name;
          form.querySelector(".song-receipt").textContent = "Current loaded track (Uploaded: " + selected.name + ")";
          song.required = false;
          scheduleSave();
        } catch (error) {
          if (fState.songObjectUrl) {
            URL.revokeObjectURL(fState.songObjectUrl);
            fState.songObjectUrl = undefined;
          }
          updateSongPreview(form, "");
          form.querySelector(".song-receipt").textContent = "Upload failed; select the song again.";
          throw error;
        } finally {
          fState.pending--;
          song.disabled = false;
        }
      });
    }
    form.querySelector(".refs-input").onchange = handle(async event => {
      const files = [...event.target.files];
      if (files.length > 9) throw new Error("Choose at most nine reference images");
      const fState = state.formFiles.get(form);
      fState.references = [];
      fState.referenceNames = [];
      fState.pending++;
      event.target.disabled = true;
      form.querySelector(".clear-refs").disabled = true;
      form.querySelector(".refs-receipt").textContent = "Uploading reference images…";
      try {
        for (const file of files) {
          fState.references.push(await upload(file, "reference"));
          fState.referenceNames.push(file.name);
        }
        renderReferenceReceipt(form, fState.referenceNames, fState.references);
        if (form.dataset.kind === "harvest") event.target.required = false;
        scheduleSave();
      } catch (error) {
        fState.references = [];
        fState.referenceNames = [];
        form.querySelector(".refs-receipt").textContent = "Upload failed; select references again.";
        throw error;
      } finally {
        fState.pending--;
        event.target.disabled = false;
        form.querySelector(".clear-refs").disabled = false;
      }
    });
    form.querySelector(".clear-refs").onclick = () => {
      const fState = state.formFiles.get(form);
      fState.references = [];
      fState.referenceNames = [];
      form.querySelector(".refs-input").value = "";
      renderReferenceReceipt(form, [], []);
      if (form.dataset.kind === "harvest") form.querySelector(".refs-input").required = true;
      refreshPanelProgress();
      scheduleSave();
    };

    const refsReceipt = form.querySelector(".refs-receipt");
    if (refsReceipt) {
      refsReceipt.addEventListener("click", event => {
        const button = event.target.closest("button.remove-ref");
        if (button) removeReference(form, Number(button.dataset.refIndex));
      });
    }
  });
}

export function initOperationControls() {
  const refreshBtn = $("#refresh-services");
  if (refreshBtn) refreshBtn.onclick = () => refreshServices(true);

  $("#resume-production").onclick = handle(async () => {
    const btn = $("#resume-production");
    const orig = btn ? btn.innerHTML : null;
    try {
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        btn.innerHTML = 'Reviewing resume… <span class="spinner" aria-hidden="true"></span>';
      }
      notice("Loading resume preview…");
      const quote = await json("/api/resume/quote", { run_id: state.currentRun });
      if ($("#notice") && $("#notice").textContent === "Loading resume preview…") notice("");
      showQuote({ kind: quote.kind }, quote);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        if (orig !== null) btn.innerHTML = orig;
      }
    }
  });

  $("#retry-prompts").onclick = handle(async () => {
    const btn = $("#retry-prompts");
    const original = btn.innerHTML;
    try {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      btn.innerHTML = 'Reviewing new preview… <span class="spinner" aria-hidden="true"></span>';
      notice("Loading a new preview from the failed production…");
      const quote = await json("/api/retry-prompts/quote", { run_id: state.currentRun });
      state.lastRequest = quote.request;
      notice("");
      showQuote(quote.request, quote);
    } finally {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.innerHTML = original;
    }
  });

  const resetOpBtn = $("#reset-operation");
  if (resetOpBtn) {
    resetOpBtn.onclick = handle(async () => {
      const updated = await json("/api/operation/reset", { purge_run: false, clear_log: false });
      applyStatus(updated);
      notice("Operation dismissed. Ready when you are.");
    });
  }

  const purgeRestartBtn = $("#purge-restart-operation");
  const purgeRestartDialog = $("#purge-restart-dialog");
  const purgeRestartCancel = $("#purge-restart-cancel");
  const purgeRestartConfirm = $("#purge-restart-confirm");
  const purgeClearLogCheck = $("#purge-clear-log-check");

  if (purgeRestartBtn && purgeRestartDialog) {
    purgeRestartBtn.onclick = () => {
      if (typeof purgeRestartDialog.showModal === "function") {
        purgeRestartDialog.showModal();
      } else {
        purgeRestartDialog.hidden = false;
      }
    };
    if (purgeRestartCancel) {
      purgeRestartCancel.onclick = () => {
        if (typeof purgeRestartDialog.close === "function") {
          purgeRestartDialog.close();
        } else {
          purgeRestartDialog.hidden = true;
        }
      };
    }
    if (purgeRestartConfirm) {
      purgeRestartConfirm.onclick = handle(async () => {
        const clearLog = Boolean(purgeClearLogCheck && purgeClearLogCheck.checked);
        purgeRestartConfirm.disabled = true;
        try {
          const updated = await json("/api/operation/reset", { purge_run: true, clear_log: clearLog });
          if (clearLog) {
            state.sessionLogs.length = 0;
            state.currentRun = null;
            $("#operation-log").textContent = "Log cleared. Waiting for new activity.";
          }
          applyStatus(updated);
          if (typeof purgeRestartDialog.close === "function") {
            purgeRestartDialog.close();
          } else {
            purgeRestartDialog.hidden = true;
          }
          notice(clearLog ? "Draft purged and operation log cleared. Ready when you are." : "Draft purged. Ready when you are.");
        } finally {
          purgeRestartConfirm.disabled = false;
        }
      });
    }
  }

  $("#start-production").onclick = handle(async () => {
    if (state.currentQuote?.offline_engines?.length) {
      throw new Error(`Cannot start production: ${state.currentQuote.offline_engines[0]}`);
    }
    if (!$("#consent").checked) throw new Error("Accept the preview before starting");
    const btn = $("#start-production");
    const orig = btn ? btn.innerHTML : null;
    try {
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        btn.innerHTML = 'Starting production… <span class="spinner" aria-hidden="true"></span>';
      }
      state.sessionLogs.length = 0;
      if ($("#operation-log")) {
        $("#operation-log").textContent = "Starting production…\n";
      }
      logSession(`Starting production for quote '${state.currentQuote.id}'`);
      const started = await json("/api/start", { quote_id: state.currentQuote.id, consent: true });
      if (started && started.id) state.currentRun = started.id;
      $("#preview-dialog").close();
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        if (orig !== null) btn.innerHTML = orig;
      }
    }
  });

  $("#cancel").onclick = handle(() => {
    logSession("Cancellation requested by operator");
    return api("/api/cancel", { method: "POST" });
  });

  $("#show-log").onclick = handle(async () => {
    const logElem = $("#operation-log");
    logElem.hidden = !logElem.hidden;
    $("#show-log").textContent = logElem.hidden ? "View log" : "Hide log";
    scheduleSave();
    if (!logElem.hidden) await updateLogDisplay();
  });

  $("#copy-log").onclick = handle(async () => {
    let content = $("#operation-log").textContent;
    if (!content || $("#operation-log").hidden) {
      await updateLogDisplay();
      content = $("#operation-log").textContent;
    }
    if (!content) content = "No logs recorded yet.";
    const ok = await copyToClipboard(content);
    if (ok) {
      const orig = $("#copy-log").textContent;
      $("#copy-log").textContent = "Copied!";
      setTimeout(() => { $("#copy-log").textContent = orig; }, 2000);
      notice("Operation log copied to clipboard.");
      setTimeout(() => { if ($("#notice").textContent === "Operation log copied to clipboard.") notice(""); }, 3000);
    } else {
      throw new Error("Unable to copy to clipboard. Please copy manually from the log view.");
    }
  });

  $("#clear-log").onclick = handle(async () => {
    state.sessionLogs.length = 0;
    state.currentRun = null;
    await api("/api/log/clear", { method: "POST" });
    applyStatus({ state: "idle", message: "One idea. One production at a time.", progress: 0 });
    $("#operation-log").textContent = "Log cleared. Waiting for new activity.";
    notice("Diagnostic log cleared.", false);
    setTimeout(() => { if ($("#notice").textContent === "Diagnostic log cleared.") notice("", false); }, 2000);
  });

  const rerollSeedBtn = $("#reroll-seed");
  if (rerollSeedBtn) {
    rerollSeedBtn.onclick = handle(() => {
      const input = $('input[name="seed"]');
      if (input) {
        input.value = Math.floor(Math.random() * 2147483647);
        notice(`New variation seed generated: ${input.value}`);
        setTimeout(() => { if ($("#notice").textContent.startsWith("New variation seed")) notice(""); }, 3000);
        scheduleSave();
      }
    });
  }
  const clearSeedBtn = $("#clear-seed");
  if (clearSeedBtn) {
    clearSeedBtn.onclick = () => {
      const input = $('input[name="render_seed"]');
      if (!input) return;
      input.value = "";
      notice("Every video now renders with its own random seed.");
      scheduleSave();
    };
  }

  const clearCacheBtn = $("#clear-cache");
  if (clearCacheBtn) {
    clearCacheBtn.onclick = handle(async () => {
      const res = await (await api("/api/cache/clear", { method: "POST" })).json();
      notice(`Prompt cache cleared (${res.count || 0} files removed).`);
      setTimeout(() => { if ($("#notice").textContent.startsWith("Prompt cache cleared")) notice(""); }, 3000);
    });
  }
}


export async function displayHarvestResult(styleId) {
  if (!styleId) return;
  try {
    const style = await (await api(`/api/styles/${encodeURIComponent(styleId)}`)).json();
    if (!style) return;
    const card = $("#harvest-result-card");
    if (!card) return;
    const title = $("#harvest-result-title");
    const dir = $("#harvest-result-direction");
    const fold = $("#harvest-result-fold");
    const pre = $("#harvest-result-card-pre");
    if (title) title.textContent = `${style.name || style.id} (${style.id})`;
    if (dir) dir.textContent = style.direction || "";
    if (pre) pre.textContent = styleCardDisplay(style.style_card) || "No style card recorded.";
    if (fold) fold.open = false;
    card.hidden = false;
    card.scrollIntoView({ behavior: "smooth" });

    const viewBtn = $("#harvest-view-style-btn");
    if (viewBtn) {
      viewBtn.onclick = () => {
        const nav = document.querySelector('.nav[data-panel="styles"]');
        if (nav) nav.click();
        setTimeout(() => {
          const styleEl = document.querySelector(`#style-list [data-id="${CSS.escape(style.id)}"]`);
          if (styleEl) {
            styleEl.scrollIntoView({ behavior: "smooth" });
            styleEl.style.outline = "2px solid var(--green)";
            setTimeout(() => { styleEl.style.outline = ""; }, 3000);
          }
        }, 150);
      };
    }

    const copyBtn = $("#harvest-copy-json-btn");
    if (copyBtn) {
      copyBtn.onclick = handle(async () => {
        const payload = JSON.stringify(style, null, 2);
        if (!await copyToClipboard(payload)) throw new Error("Could not copy style JSON to clipboard.");
        notice(`Style JSON for '${style.name}' copied to clipboard.`);
        const orig = copyBtn.textContent;
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => { copyBtn.textContent = orig; }, 2500);
      });
    }

    const dismissBtn = $("#harvest-dismiss-result-btn");
    if (dismissBtn) {
      dismissBtn.onclick = () => {
        card.hidden = true;
      };
    }
  } catch (err) {
    console.debug("Failed to fetch harvest result", err);
  }
}
