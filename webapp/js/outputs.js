// Finished Videos, Musical Score Canvas visualization, and Topaz upscale dialog.

import { $, $$, api, copyToClipboard, handle, json, keyRow, notice, option, state, text } from "./core.js";
import { initColourWheels } from "./colorwheel.js";
import { showQuote } from "./production.js";

// One theme observer for all score views; loadOutputs disposes views before replacing cards.
const scoreViews = new Set();
new MutationObserver(() => scoreViews.forEach(view => view.draw())).observe(
  document.documentElement,
  { attributes: true, attributeFilter: ["data-theme"] }
);

const GRAMMAR_CLASSES = {
  "Standard": "standard",
  "Thematic multi-scene": "thematic",
  "Chaotic multi-scene": "chaotic",
  "Single-subject fragmentation": "fragmentation"
};

let pendingExportRun = null;
const MAX_SEED = 2147483647;

// A random seed that no recorded take of the passage has used yet.
export function freshSeed(used = [], random = Math.random) {
  const taken = new Set(used.filter(seed => seed != null).map(Number));
  let seed;
  do { seed = 100000 + Math.floor(random() * (MAX_SEED - 100000)); } while (taken.has(seed));
  return seed;
}
let pendingDeleteRun = null;

export function closeProductionBreakdown() {
  const mainView = $("#outputs-main-view");
  const breakdownView = $("#outputs-breakdown-view");
  openBreakdown = null;
  if (breakdownView) {
    $$("#prompts-view-list video").forEach(v => {
      v.pause();
      v.removeAttribute("src");
      v.load();
    });
    breakdownView.hidden = true;
  }
  if (mainView) {
    mainView.hidden = false;
  }
  restoreGallery();
}

// The hidden gallery's players can keep downloads of large finished videos open, holding the browser's few connections
// to the app; while the Edit view is open they let go, and they come back (a few at a time) on return.
function releaseGallery() {
  $$("#output-list video").forEach(v => {
    if (!v.getAttribute("src")) return;
    v.dataset.releasedSrc = v.getAttribute("src");
    v.pause();
    v.removeAttribute("src");
    v.load();
  });
}

function restoreGallery() {
  const videos = $$("#output-list video").filter(v => v.dataset.releasedSrc);
  videos.forEach(v => {
    v.preload = "none";
    v.src = v.dataset.releasedSrc;
    delete v.dataset.releasedSrc;
  });
  loadThumbnails(videos);
}

async function pollJobCompletion(initialMessage) {
  notice(initialMessage);
  for (let wait = 0; wait < 2400; wait += 1) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    const job = await (await api("/api/status")).json();
    if (job.state === "running" || job.state === "cancelling") continue;
    if (job.state === "failed" || job.state === "cancelled") {
      throw new Error(job.message || "Operation did not complete");
    }
    return job.result || {};
  }
  throw new Error("Operation timed out waiting for completion");
}

function renderFinalTakesBar(sourceRunId, finalTakes = []) {
  const labelEl = $("#prompts-final-takes-label");
  const selectEl = $("#prompts-final-takes-select");
  const downloadBtn = $("#prompts-final-download-btn");
  if (!labelEl || !selectEl || !downloadBtn) return;

  if (!finalTakes.length) {
    labelEl.hidden = true;
    downloadBtn.hidden = true;
    return;
  }

  labelEl.hidden = false;
  downloadBtn.hidden = false;
  selectEl.replaceChildren(
    ...finalTakes.map((ft) => option(ft.file, ft.label || ft.id, `Final video version: ${ft.label || ft.id}`))
  );
  const latest = finalTakes[finalTakes.length - 1];
  if (latest) selectEl.value = latest.file;

  const syncDownloadLink = () => {
    const chosenFile = selectEl.value;
    if (chosenFile) {
      downloadBtn.href = `/api/media/${encodeURIComponent(sourceRunId)}/${encodeURIComponent(chosenFile)}?download=true`;
      downloadBtn.setAttribute("download", chosenFile);
    }
  };
  selectEl.onchange = syncDownloadLink;
  syncDownloadLink();
}

// "4,979 chars", or "4,979 / 10,000 chars" when the production's renderer reports a ceiling.
function charLabel(length, limit) {
  return limit ? `${length.toLocaleString()} / ${Number(limit).toLocaleString()} chars` : `${length.toLocaleString()} chars`;
}

// Prompt versions of one passage: preview any version, make a passed one the prompt, write a new one or check a hand edit.
// Writing and checking go through the same writer, Mondo checks and Laya review as a production; nothing skips them.
function promptVersionControls(seg, data, sourceRunId, showText, reload) {
  const wrap = document.createElement("div");
  wrap.className = "prompt-versions";
  wrap.style.cssText = "display:flex;flex-direction:column;gap:6px;margin-top:8px;";
  const versions = seg.prompt_takes || [];
  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px;";
  const select = document.createElement("select");
  select.className = "prompt-version-select";
  select.style.cssText = "font-size:12px;padding:4px 8px;min-width:170px;";
  select.setAttribute("aria-label", `Prompt versions of ${seg.segment_id}`);
  select.replaceChildren(...versions.map(v => option(v.id, `${v.label}${v.id === seg.active_prompt_take ? " · in use" : ""}`)));
  select.value = seg.active_prompt_take || versions.at(-1)?.id || "";
  select.hidden = versions.length < 2;
  const problems = text("p", "", "muted prompt-version-problems");
  problems.hidden = true;
  const useBtn = text("button", "Use this version", "secondary", "Make this passed version the passage's prompt; reroll the clip to render it");
  useBtn.type = "button";
  const editBtn = text("button", "✏️ Edit prompt", "quiet", "Edit this prompt; it is used only if it passes the Mondo checks and Laya review");
  editBtn.type = "button";
  const writeBtn = text("button", "✍️ Write new prompt", "quiet", data.kind === "ident" ? "Have the writer write a new prompt, checked like every production prompt" : "Roll a fresh setting and motif for this passage and have the writer write a new checked prompt");
  writeBtn.type = "button";
  const steerDetails = document.createElement("details");
  steerDetails.className = "prompt-rewrite-steer";
  steerDetails.style.cssText = "font-size:12px;margin-top:2px;";
  const steerSummary = text("summary", "🧭 Optional rewrite steering (world & note)", "muted");
  steerSummary.style.cursor = "pointer";
  const steerRow = document.createElement("div");
  steerRow.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px;";
  const worldSelect = document.createElement("select");
  worldSelect.className = "prompt-rewrite-world";
  worldSelect.style.cssText = "font-size:12px;padding:4px 8px;min-width:170px;";
  worldSelect.setAttribute("aria-label", `Optional Thematic World for rewriting ${seg.segment_id}`);
  const worldNames = Array.isArray(data.thematic_worlds) ? data.thematic_worlds : [];
  worldSelect.replaceChildren(
    option("", "Production default vocabulary"),
    ...worldNames.map(w => option(w, `World: ${w}`)),
    ...(data.saved_worlds || []).map(w => option(w.id, `Your World: ${w.name}`))
  );
  const steerInput = document.createElement("input");
  steerInput.type = "text";
  steerInput.maxLength = 600;
  steerInput.placeholder = "Optional creative note for this passage…";
  steerInput.className = "prompt-rewrite-direction";
  steerInput.style.cssText = "font-size:12px;padding:4px 8px;flex:1 1 220px;";
  steerInput.setAttribute("aria-label", `Optional creative direction note for rewriting ${seg.segment_id}`);
  steerRow.append(worldSelect, steerInput);
  steerDetails.append(steerSummary, steerRow);
  editBtn.hidden = writeBtn.hidden = steerDetails.hidden = Boolean(data.prompt_blocked);
  steerDetails.hidden = steerDetails.hidden || data.kind === "ident";
  const chosen = () => versions.find(v => v.id === select.value);
  const sync = () => {
    const version = chosen();
    if (version) showText(version.prompt);
    useBtn.hidden = !version || version.id === seg.active_prompt_take || version.validated === false;
    problems.hidden = !(version && version.validated === false);
    problems.textContent = version?.validated === false ? `Did not pass: ${(version.problems || []).join("; ")}` : "";
  };
  select.onchange = sync;
  useBtn.onclick = handle(async () => {
    await json(`/api/outputs/${encodeURIComponent(sourceRunId)}/prompts/${encodeURIComponent(seg.segment_id)}/select`, { prompt_take_id: select.value });
    notice(`${chosen()?.label} is now the prompt for ${seg.segment_id}. Reroll the clip to render it.`);
    await reload();
  });
  const runPrompt = async (action, body, message) => {
    await json(`/api/outputs/${encodeURIComponent(sourceRunId)}/prompts/${encodeURIComponent(seg.segment_id)}/${action}`, body);
    try {
      await pollJobCompletion(message);
      notice(`New prompt for ${seg.segment_id} passed the checks and is in use. Reroll the clip to render it.`);
    } finally {
      await reload();
    }
  };
  writeBtn.onclick = handle(async () => {
    const charge = data.writer_charge || {};
    const cost = charge.api_writer ? ` Your writer is an API service that may charge for this call (estimate about $${Number(charge.estimate_usd || 0).toFixed(2)}).` : "";
    const chosenWorld = worldSelect.value.trim();
    const chosenDirection = steerInput.value.trim();
    const steerNote = chosenWorld || chosenDirection
      ? ` Steering: ${[chosenWorld ? `world "${chosenWorld}"` : "", chosenDirection ? `note "${chosenDirection}"` : ""].filter(Boolean).join(", ")}.`
      : "";
    const intro = data.kind === "ident"
      ? "It goes through the writer, the Mondo checks and Laya."
      : "This rolls a fresh setting and motif from the vocabulary pool, and it goes through the writer, the Mondo checks and Laya.";
    if (!window.confirm(`Write a new prompt for ${seg.segment_id}? ${intro}${steerNote}${cost}`)) return;
    const payload = {
      confirm: true,
      accept_writer_cost: Boolean(charge.api_writer),
      ...(chosenWorld ? { world_id: chosenWorld } : {}),
      ...(chosenDirection ? { direction: chosenDirection } : {}),
    };
    await runPrompt("rewrite", payload, `Writing a new prompt for ${seg.segment_id}…`);
  });
  const editor = document.createElement("div");
  editor.hidden = true;
  editor.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const area = document.createElement("textarea");
  area.rows = 12;
  area.className = "prompt-edit-area";
  area.setAttribute("aria-label", `Edited prompt for ${seg.segment_id}`);
  const editActions = document.createElement("div");
  editActions.style.cssText = "display:flex;gap:6px;";
  const checkBtn = text("button", "Check and use", "primary", "Run the Mondo checks and Laya review; the edit is used only if it passes");
  checkBtn.type = "button";
  const cancelBtn = text("button", "Cancel", "quiet");
  cancelBtn.type = "button";
  editActions.append(checkBtn, cancelBtn);
  const counter = text("p", "", "muted prompt-edit-count");
  area.oninput = () => {
    counter.textContent = charLabel(area.value.length, data.prompt_limit)
      + (data.prompt_limit && area.value.length > data.prompt_limit ? " — too long for this renderer" : "");
  };
  editor.append(area, counter, text("p", "Sealed passages keep their closing sentence; it is added back if removed.", "muted"), editActions);
  editBtn.onclick = () => {
    area.value = chosen()?.prompt || seg.prompt;
    area.oninput();
    editor.hidden = false;
    area.focus();
  };
  cancelBtn.onclick = () => { editor.hidden = true; };
  checkBtn.onclick = handle(async () => {
    if (!area.value.trim()) throw new Error("The prompt is empty.");
    await runPrompt("edit", { prompt: area.value, confirm: true }, `Checking the edited prompt for ${seg.segment_id}…`);
  });
  bar.append(select, useBtn, editBtn, writeBtn);
  wrap.append(bar, steerDetails, problems, editor);
  sync();
  return wrap;
}

let openBreakdown = null;     // the finished video shown in the Edit view, so it can be refreshed

// Re-read the open Edit view (after any operation finishes, or on ↻ Refresh), keeping the reader's place.
export async function refreshProductionBreakdown() {
  if (!openBreakdown || $("#outputs-breakdown-view")?.hidden) return;
  const top = window.scrollY;
  await showProductionBreakdown(openBreakdown, { refresh: true });
  window.scrollTo(0, top);
}

export async function showProductionBreakdown(output, { refresh = false } = {}) {
  const mainView = $("#outputs-main-view");
  const breakdownView = $("#outputs-breakdown-view");
  const listEl = $("#prompts-view-list");
  const titleEl = $("#prompts-view-title");
  const subEl = $("#prompts-view-subtitle");
  const reassembleBtn = $("#prompts-reassemble-btn");

  if (!breakdownView || !listEl) return;

  const runId = output.file.split("/")[0];
  openBreakdown = output;
  if (titleEl) titleEl.textContent = `Edit: ${output.title}`;
  if (!refresh) {             // a refresh keeps the current cards on screen until the new ones are ready
    if (subEl) subEl.textContent = `Fetching passage breakdown for run ${runId}…`;
    listEl.innerHTML = '<div class="prompts-view-loading" style="padding:24px;text-align:center;color:var(--muted);">Loading passage prompts and clips…</div>';
  }

  if (mainView) mainView.hidden = true;
  releaseGallery();
  breakdownView.hidden = false;
  if (!refresh) breakdownView.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const res = await api(`/api/outputs/${encodeURIComponent(runId)}/prompts`);
    if (!res.ok) throw new Error("Could not load prompts for this production");
    const data = await res.json();
    const sourceRunId = data.source_run_id || runId;

    if (subEl) {
      subEl.textContent = `${data.segments.length} passage${data.segments.length === 1 ? "" : "s"} · ${data.kind} production`;
    }
    renderFinalTakesBar(sourceRunId, data.final_takes || []);

    if (reassembleBtn) {
      reassembleBtn.onclick = handle(async () => {
        const selectedTakes = Object.fromEntries(
          $$("#prompts-view-list select.passage-take-select")
            .map(sel => [sel.dataset.segmentId, sel.value])
            .filter(([sid, tid]) => sid && tid)
        );
        const origLabel = reassembleBtn.textContent;
        reassembleBtn.disabled = true;
        reassembleBtn.setAttribute("aria-busy", "true");
        reassembleBtn.textContent = "⏳ Re-encoding Final Video…";
        try {
          await json(`/api/outputs/${encodeURIComponent(sourceRunId)}/reassemble`, { selected_takes: selectedTakes });
          const resData = await pollJobCompletion("Re-encoding final video with selected passage takes…");
          const warned = (resData.warnings || []).join(" ");
          notice(`Final video re-encoded (${resData.final_take?.label || "new version"}). Previous final video versions are preserved.${warned ? " " + warned : ""}`);
          if (resData.final_takes) {
            renderFinalTakesBar(sourceRunId, resData.final_takes);
          }
          await loadOutputs();
        } finally {
          reassembleBtn.disabled = false;
          reassembleBtn.removeAttribute("aria-busy");
          reassembleBtn.textContent = origLabel;
        }
      });
    }

    if (!data.segments.length) {
      listEl.innerHTML = '<div class="empty" style="margin:16px 0;">No individual passage prompts recorded for this production.</div>';
      return;
    }

    listEl.replaceChildren(...data.segments.map((seg) => {
      const card = document.createElement("article");
      card.className = "prompts-passage-card card";
      card.style.margin = "0 0 16px 0";
      card.style.padding = "16px";

      const header = document.createElement("div");
      header.className = "prompts-passage-header";
      header.style.display = "flex";
      header.style.justifyContent = "space-between";
      header.style.alignItems = "center";
      header.style.marginBottom = "10px";
      header.style.flexWrap = "wrap";
      header.style.gap = "8px";

      const title = document.createElement("h3");
      title.style.margin = "0";
      title.style.fontSize = "16px";
      title.textContent = `Passage ${seg.index + 1} (${seg.segment_id})`;

      const badge = document.createElement("span");
      badge.className = "oap-badge-pill";
      badge.style.background = "rgba(255,255,255,0.08)";
      badge.textContent = `${seg.duration ? seg.duration.toFixed(1) + "s" : ""} ${seg.trim_frames ? "· " + seg.trim_frames + " frames" : ""}`.trim();

      header.append(title, badge);
      card.append(header);

      const grid = document.createElement("div");
      grid.className = "prompts-passage-grid";

      // 1. Text prompt on the LEFT
      if (seg.prompt) {
        const preWrap = document.createElement("div");
        preWrap.className = "prompts-passage-text-wrap";

        const metaBar = document.createElement("div");
        metaBar.className = "prompts-passage-meta-bar";
        metaBar.style.display = "flex";
        metaBar.style.justifyContent = "space-between";
        metaBar.style.alignItems = "center";
        metaBar.style.marginBottom = "6px";

        const charCount = document.createElement("span");
        charCount.className = "prompts-passage-char-count";
        charCount.style.fontSize = "12px";
        charCount.style.color = "var(--muted)";
        charCount.style.fontFamily = "monospace";
        charCount.textContent = charLabel(seg.prompt.length, data.prompt_limit);

        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "quiet";
        copyBtn.style.fontSize = "12px";
        copyBtn.style.padding = "2px 8px";
        copyBtn.textContent = "📋 Copy Prompt";
        copyBtn.onclick = handle(async () => {
          if (!await copyToClipboard(pre.textContent)) throw new Error("Could not copy the prompt to the clipboard.");
          notice(`Copied prompt for ${seg.segment_id} to clipboard`);
        });

        metaBar.append(charCount, copyBtn);
        const showText = (prompt) => {
          pre.textContent = prompt;
          charCount.textContent = charLabel(prompt.length, data.prompt_limit);
          charCount.style.color = data.prompt_limit && prompt.length > data.prompt_limit ? "var(--danger, #b91c1c)" : "var(--muted)";
        };

        const pre = document.createElement("pre");
        pre.className = "prompts-passage-pre";
        pre.style.whiteSpace = "pre-wrap";
        pre.style.wordBreak = "break-word";
        pre.style.fontSize = "13px";
        pre.style.lineHeight = "1.6";
        pre.style.background = "var(--input-bg, rgba(0,0,0,0.25))";
        pre.style.border = "1px solid var(--line)";
        pre.style.borderRadius = "4px";
        pre.style.padding = "12px";
        pre.style.margin = "0";
        pre.style.maxHeight = "280px";
        pre.style.overflowY = "auto";
        pre.textContent = seg.prompt;

        preWrap.append(metaBar, pre, promptVersionControls(seg, data, sourceRunId, showText, () => showProductionBreakdown(output)));
        grid.append(preWrap);
      } else {
        const noPrompt = document.createElement("p");
        noPrompt.className = "muted";
        noPrompt.textContent = "No prompt text saved for this passage.";
        grid.append(noPrompt);
      }

      // 2. Video clip and take controls on the RIGHT
      const vidWrap = document.createElement("div");
      vidWrap.className = "prompts-passage-video-wrap";
      vidWrap.style.marginBottom = "0";

      const videoToolbar = document.createElement("div");
      videoToolbar.className = "prompts-passage-video-toolbar";
      videoToolbar.style.display = "flex";
      videoToolbar.style.justifyContent = "space-between";
      videoToolbar.style.alignItems = "center";
      videoToolbar.style.gap = "8px";
      videoToolbar.style.marginBottom = "6px";
      videoToolbar.style.flexWrap = "wrap";

      const takeSelect = document.createElement("select");
      takeSelect.className = "passage-take-select";
      takeSelect.dataset.segmentId = seg.segment_id;
      takeSelect.style.fontSize = "12px";
      takeSelect.style.padding = "4px 8px";
      takeSelect.style.minWidth = "150px";
      takeSelect.dataset.tooltip = `Select a rendered take for ${seg.segment_id}`;

      const v = document.createElement("video");
      v.controls = true;
      v.preload = "none";              // loaded a few at a time below, like the gallery's thumbnails
      v.style.width = "100%";
      v.style.maxHeight = "280px";
      v.style.borderRadius = "4px";
      v.style.background = "#101814";

      // The previewed take's seed, and the seed the next reroll will use (a fresh random one unless the user types another).
      const seedInfo = document.createElement("span");
      seedInfo.className = "passage-take-seed muted";
      seedInfo.style.fontSize = "12px";
      seedInfo.style.fontFamily = "monospace";
      const showSeed = (take) => {
        seedInfo.textContent = take?.seed != null ? `Seed ${take.seed}` : "";
      };

      const populateTakesDropdown = (takesList, activeTakeId) => {
        if (!takesList || !takesList.length) {
          takeSelect.replaceChildren(option("", "No takes recorded"));
          takeSelect.disabled = true;
          return;
        }
        takeSelect.disabled = false;
        takeSelect.replaceChildren(
          ...takesList.map(t => option(t.id, t.label || t.id, `Preview ${t.label || t.id}`))
        );
        const chosenId = activeTakeId || takesList[takesList.length - 1].id;
        takeSelect.value = chosenId;
        const chosenTake = takesList.find(t => t.id === chosenId) || takesList[takesList.length - 1];
        showSeed(chosenTake);
        if (chosenTake && chosenTake.clip_url) {
          v.src = chosenTake.clip_url;
        } else if (seg.clip_url) {
          v.src = seg.clip_url;
        }
      };

      populateTakesDropdown(seg.takes || [], seg.active_take);

      // Choosing a take only previews it here; the re-encode saves every passage's choice.
      takeSelect.onchange = () => {
        const chosen = (seg.takes || []).find(t => t.id === takeSelect.value);
        if (!chosen?.clip_url) return;
        showSeed(chosen);
        v.src = chosen.clip_url;
        v.load();
        notice(`Previewing ${chosen.label || chosen.id} for ${seg.segment_id}. Re-encode the final video to use it.`);
      };

      const rerollBtn = document.createElement("button");
      rerollBtn.type = "button";
      rerollBtn.className = "secondary passage-reroll-btn passage-render-btn";
      rerollBtn.style.fontSize = "12px";
      rerollBtn.style.padding = "4px 10px";
      rerollBtn.textContent = "🎬 Render Clip";
      rerollBtn.dataset.tooltip = `Render a new take of ${seg.segment_id} with the next seed, using its prompt and cast references`;

      const seedLabel = document.createElement("label");
      seedLabel.className = "passage-seed";
      seedLabel.style.cssText = "display:flex;align-items:center;gap:4px;margin:0;font-size:12px;";
      seedLabel.dataset.tooltip = "Seed for the next take. Keep the random one or type your own; the same prompt with a new seed is often all a passage needs.";
      const seedInput = document.createElement("input");
      seedInput.type = "number";
      seedInput.min = "0";
      seedInput.max = String(MAX_SEED);
      seedInput.step = "1";
      seedInput.className = "passage-seed-input";
      seedInput.style.cssText = "width:120px;padding:4px 6px;font-size:12px;";
      seedInput.setAttribute("aria-label", `Seed for the next take of ${seg.segment_id}`);
      const newSeed = () => {
        seedInput.value = String(freshSeed((seg.takes || []).map(t => t.seed)));
      };
      const randomBtn = document.createElement("button");
      randomBtn.type = "button";
      randomBtn.className = "quiet";
      randomBtn.style.cssText = "font-size:12px;padding:2px 6px;";
      randomBtn.textContent = "Random";
      randomBtn.dataset.tooltip = "Pick another random seed";
      randomBtn.onclick = newSeed;
      seedLabel.append("Next seed", seedInput, randomBtn);
      newSeed();

      seedLabel.hidden = rerollBtn.hidden = Boolean(data.reroll_blocked);
      rerollBtn.onclick = handle(async () => {
        const seed = Number(seedInput.value);
        if (seedInput.value.trim() === "" || !Number.isInteger(seed) || seed < 0 || seed > MAX_SEED) {
          throw new Error(`Enter a whole-number seed from 0 to ${MAX_SEED}, or press Random.`);
        }
        if (!window.confirm(`Render a new take of ${seg.segment_id} with seed ${seed} on the local H3 renderer? This uses the GPU for one passage. The finished video changes only when you re-encode it.`)) return;
        const origText = rerollBtn.textContent;
        rerollBtn.disabled = true;
        rerollBtn.setAttribute("aria-busy", "true");
        rerollBtn.textContent = "⏳ Rendering take…";
        try {
          await json(`/api/outputs/${encodeURIComponent(sourceRunId)}/reroll/${encodeURIComponent(seg.segment_id)}`, { confirm: true, seed });
          const updatedBreakdown = await pollJobCompletion(`Re-rendering passage ${seg.index + 1} (${seg.segment_id}) with seed ${seed}…`);
          const updatedSeg = (updatedBreakdown.segments || []).find(s => s.segment_id === seg.segment_id);
          if (updatedSeg) {
            seg.takes = updatedSeg.takes || [];
            populateTakesDropdown(seg.takes, updatedSeg.active_take);
            v.load();
            newSeed();
          }
          notice(`New take rendered for ${seg.segment_id}! Use the dropdown to compare takes or click "Re-encode Final Video" to apply.`);
        } finally {
          rerollBtn.disabled = false;
          rerollBtn.removeAttribute("aria-busy");
          rerollBtn.textContent = origText;
        }
      });

      videoToolbar.append(takeSelect, seedInfo, seedLabel, rerollBtn);
      vidWrap.append(videoToolbar);

      if (seg.has_clip && seg.clip_url) {
        if (!v.src) v.src = seg.clip_url;
        vidWrap.append(v);
      } else {
        v.hidden = true;
        const emptyClip = document.createElement("div");
        emptyClip.className = "empty";
        emptyClip.style.padding = "24px";
        emptyClip.textContent = data.reroll_blocked ? "No clip currently on disk for this passage." : "No clip currently on disk for this passage. Click Render Clip to render one.";
        vidWrap.append(v, emptyClip);
      }

      grid.append(vidWrap);
      card.append(grid);
      return card;
    }));
    loadThumbnails($$("#prompts-view-list video").filter(v => v.getAttribute("src")));
  } catch (err) {
    if (listEl) {
      listEl.innerHTML = `<div class="empty" style="color:var(--danger, #e05252);margin:16px 0;">Failed to load prompts: ${escapeHtml(err.message)}</div>`;
    }
  }
}


const escapeHtml = (s = "") =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

function showDeleteDialog(output) {
  const dialog = $("#delete-video-dialog");
  if (!dialog) return;
  pendingDeleteRun = output.file.split("/")[0];
  const title = $("#delete-dialog-title");
  if (title) title.textContent = `Delete: ${output.title}`;
  const msg = $("#delete-dialog-msg");
  if (msg) msg.textContent = `Are you sure you want to delete "${output.title}"? This will permanently remove the MP4 and all rendered passage files from this machine.`;

  const cancelBtn = $("#delete-cancel-btn");
  if (cancelBtn) {
    cancelBtn.onclick = () => dialog.close();
  }

  const confirmBtn = $("#delete-confirm-btn");
  if (confirmBtn) {
    confirmBtn.onclick = handle(async () => {
      if (!pendingDeleteRun) return;
      confirmBtn.disabled = true;
      try {
        await api(`/api/outputs/${encodeURIComponent(pendingDeleteRun)}`, { method: "DELETE" });
        dialog.close();
        notice(`Deleted production "${output.title}".`);
        await loadOutputs();
      } catch (err) {
        notice(err.message);
      } finally {
        confirmBtn.disabled = false;
        pendingDeleteRun = null;
      }
    });
  }
  dialog.showModal();
}

function showExportDialog(output, errorMsg = "") {
  const dialog = $("#export-dialog");
  if (!dialog) return;
  pendingExportRun = output.file.split("/")[0];
  const title = $("#export-dialog-title");
  if (title) title.textContent = `Export: ${output.title}`;

  const warningBox = $("#export-actors-warning");
  const msgElem = $("#export-actors-msg");
  const confirmCb = $("#export-owner-confirm");
  const manageLink = $("#export-manage-actors-link");

  if (errorMsg) {
    if (warningBox) warningBox.hidden = false;
    if (msgElem) msgElem.textContent = errorMsg.replace("PRIVATE_ACTORS: ", "");
    if (confirmCb) confirmCb.checked = false;
  } else {
    if (warningBox) warningBox.hidden = true;
    if (confirmCb) confirmCb.checked = true;
  }

  if (manageLink) {
    manageLink.onclick = (e) => {
      e.preventDefault();
      dialog.close();
      const navActors = $(".nav[data-panel='actors']");
      if (navActors) navActors.click();
    };
  }

  const cancelBtn = $("#export-cancel-btn");
  if (cancelBtn) {
    cancelBtn.onclick = () => dialog.close();
  }

  const confirmBtn = $("#export-confirm-btn");
  if (confirmBtn) {
    confirmBtn.onclick = handle(async () => {
      const allow = !warningBox || warningBox.hidden || (confirmCb && confirmCb.checked);
      if (warningBox && !warningBox.hidden && (!confirmCb || !confirmCb.checked)) {
        throw new Error("Please check the box confirming actor ownership/authorization to export.");
      }
      dialog.close();
      await executeExportPackage(pendingExportRun, allow);
    });
  }

  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  }
}

async function executeExportPackage(runId, allow) {
  notice("Preparing editing package…");
  try {
    await json(`/api/outputs/${encodeURIComponent(runId)}/package`, { zip: true, allow_private_actors: allow });
    for (let wait = 0; wait < 900; wait += 1) {
      await new Promise(resolve => setTimeout(resolve, 1500));
      const job = await (await api("/api/status")).json();
      if (job.state === "running") continue;
      if (job.state === "failed") throw new Error(job.message);
      const result = job.result || {};
      notice(`Package written: ${result.path} (${result.files} files)${result.zip ? " and " + result.zip : ""}`);
      return;
    }
  } catch (error) {
    if (String(error.message).startsWith("PRIVATE_ACTORS")) {
      showExportDialog({ file: `${runId}/video.mp4`, title: "Production" }, error.message);
      return;
    }
    throw error;
  }
}

// Prominent dedicated export button for finished productions
function exportButton(output) {
  const button = text("button", "Export package", "secondary",
    `Export ${output.title} with raw clips, song stem, prompts, CMX 3600 timeline EDL and receipts`);

  button.onclick = handle(async () => {
    const runId = output.file.split("/")[0];
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      try {
        await executeExportPackage(runId, false);
      } catch (error) {
        if (String(error.message).startsWith("PRIVATE_ACTORS")) {
          showExportDialog(output, error.message);
        } else {
          throw error;
        }
      }
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  });
  return button;
}

const field = (label, control, tip) => {
  const node = document.createElement("label");
  node.dataset.tooltip = node.title = tip;
  node.append(label, control);
  return node;
};

const numberInput = (min, max, step, placeholder = "") => {
  const input = document.createElement("input");
  Object.assign(input, { type: "number", min, max, step, placeholder });
  return input;
};

// Builds the Topaz cloud model, frame rate and tuning controls from the catalog; returns a reader for their values.
function buildCloudOptions(catalog) {
  const model = document.createElement("select");
  model.append(option("none", "No upscale or enhance (frame rate only)", "Only change the frame rate"));
  for (const group of catalog.upscale) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group.group;
    optgroup.append(...group.models.map(m => option(m.id, `${m.name} (${m.id})`, m.note)));
    model.append(optgroup);
  }
  model.value = catalog.upscale.some(g => g.models.some(m => m.id === "prob-4")) ? "prob-4" : model.options[1]?.value;
  const note = text("p", "", "muted");
  const describe = () => { note.textContent = catalog.upscale.flatMap(g => g.models).find(m => m.id === model.value)?.note || ""; };
  model.addEventListener("change", describe);
  describe();

  const motion = document.createElement("select");
  motion.append(option("", "Keep the original frame rate", "No frame interpolation"),
    ...catalog.interpolation.map(m => option(m.id, `${m.name} (${m.id})`, m.note)));
  const fps = numberInput(15, 240, 1, "e.g. 60");
  const slowmo = numberInput(1, 16, 1, "1 = normal speed");
  const duplicate = document.createElement("input");
  duplicate.type = "checkbox";
  const mode = document.createElement("select");
  mode.append(...catalog.modes.map(m => option(m, m === "Auto" ? "Auto (Topaz chooses)" : m, `${m} parameter mode`)));
  const tuning = catalog.tuning.map(t => [t, numberInput(t.min, t.max, 0.05, `${t.min} to ${t.max}`)]);

  const frames = document.createElement("fieldset");
  frames.append(text("legend", "Frame rate"),
    field("Interpolation model ", motion, "Create in-between frames for a higher frame rate or slow motion"),
    field("Target frames per second ", fps, "Output frame rate, 15 to 240; leave blank to keep the original"),
    field("Slow motion factor ", slowmo, "Stretch time: 2 plays at half speed; 1 or blank keeps normal speed"),
    field("Remove duplicate frames ", duplicate, "Detect repeated frames in the source and remove them before interpolating"));
  const advanced = document.createElement("details");
  advanced.append(text("summary", "Tuning (Precision models)", "", "Fine-tune Proteus, Artemis, Gaia, Iris and Theia models"),
    field("Parameter mode ", mode, "Auto ignores the values below; Relative nudges Topaz's automatic values; Manual uses only your values"),
    ...tuning.map(([t, input]) => field(`${t.label} `, input, `${t.label}: ${t.min} to ${t.max}; blank leaves Topaz's value`)));
  $("#upscale-options").replaceChildren(
    field("Model ", model, "Topaz cloud model; the note below describes the selected one"), note, frames, advanced);

  return () => {
    const options = {};
    if (motion.value) {
      options.interpolation = { model: motion.value, duplicate: duplicate.checked };
      if (fps.value) options.interpolation.fps = Number(fps.value);
      if (slowmo.value) options.interpolation.slowmo = Number(slowmo.value);
    }
    const values = Object.fromEntries(tuning.filter(([, input]) => input.value !== "").map(([t, input]) => [t.key, Number(input.value)]));
    if (mode.value !== "Auto" && Object.keys(values).length) Object.assign(options, { mode: mode.value, tuning: values });
    return { model: model.value, options };
  };
}

function showUpscaleKey(saved) {
  $("#upscale-key-row").replaceChildren(...(saved ? [] : [keyRow("MMV_TOPAZ_API_KEY", false, showUpscaleKey)]));
  $("#upscale-key-row").hidden = saved;
  $("#upscale-estimate").disabled = !saved;
}

async function openUpscaleDialog() {
  await refreshUpscaleDialog();
  $("#upscale-dialog").showModal();
}

async function chooseUpscaleService(backend) {
  const { settings } = await (await api("/api/settings")).json();
  delete settings.h3_models;
  await json("/api/settings", { ...settings, topaz_backend: backend }, "PUT");
  await refreshUpscaleDialog();
}

async function refreshUpscaleDialog() {
  const data = await (await api("/api/settings")).json();
  $("#upscale-service").value = data.settings.topaz_backend;
  const settings = data.settings;
  state.upscaleCloud = settings.topaz_backend === "cloud";
  showUpscaleKey(data.keys.MMV_TOPAZ_API_KEY);
  $("#upscale-cloud").hidden = !state.upscaleCloud;
  $("#upscale-model-local").hidden = state.upscaleCloud;
  $("#upscale-options").hidden = !state.upscaleCloud;
  $("#upscale-form").elements.scale.querySelector('option[value="1"]').hidden = !state.upscaleCloud;
  if (state.upscaleCloud) {
    try {
      state.readUpscaleOptions = buildCloudOptions(await (await api("/api/upscale/models")).json());
    } catch (error) {
      state.readUpscaleOptions = null;
      notice(error.message);
    }
  }
  $("#upscale-local-note").hidden = state.upscaleCloud;
  state.upscaleCredits = null;
  $("#upscale-quote").textContent = "";
  $("#upscale-consent").checked = false;
  $("#upscale-consent-row").hidden = true;
  $("#upscale-start").disabled = state.upscaleCloud;
}

export function scoreView(output, video) {
  const box = text("details", "", "score-view");
  box.append(text("summary", "Watch the song conduct", "", "Show the beats, energy and planned cuts behind this video"));
  const canvas = document.createElement("canvas");
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "slider");
  canvas.setAttribute("aria-label", "Musical score position. Arrow keys jump between planned cuts; Home and End go to the start and end.");
  canvas.setAttribute("aria-valuemin", "0");
  const caption = text("p", "", "score-caption");
  caption.setAttribute("aria-live", "polite");
  const legend = text("div", "", "score-legend");
  box.append(canvas, caption, legend);
  let score = null, frame = 0, lastCaption = "";
  const x = time => time / Math.max(score.duration || score.song_end, 0.001) * canvas.clientWidth;

  function colors() {
    const style = getComputedStyle(box);
    const value = name => style.getPropertyValue(name).trim();
    return {
      ink: value("--ink"),
      muted: value("--muted"),
      line: value("--line"),
      accent: value("--score-accent"),
      grammar: Object.fromEntries(Object.values(GRAMMAR_CLASSES).map(key => [key, value("--score-" + key)]))
    };
  }

  function describe(time) {
    if (time < score.offset) return "Opening ident · the song starts at " + score.offset.toFixed(1) + " s";
    if (time >= score.song_end) return "Closing ident";
    const passage = score.passages.find(item => time >= item.start && time < item.end) || score.passages.at(-1);
    const index = passage.shots.findIndex((shot, i) => time >= shot.start && (time < shot.end || i === passage.shots.length - 1));
    const shot = passage.shots[Math.max(index, 0)];
    const cut = {
      passage: passage.on_downbeat ? "passage starts on a downbeat" : "passage start",
      downbeat: "cut on a downbeat",
      beat: "cut on a beat",
      split: "long hold split"
    }[shot.cut];
    return `${passage.section} energy (${Number(passage.energy).toFixed(2)}) → ${passage.grammar}: ${passage.grammar_description} ` +
      `Shot ${Math.max(index, 0) + 1} of ${passage.shots.length}, ${shot.shot_scale}, ${cut}. ` +
      `${passage.shots.length} ${passage.shots.length === 1 ? "shot" : "shots"} across ${passage.beats} beats at ${Math.round(score.tempo_bpm)} BPM.`;
  }

  function draw() {
    if (!score) return;
    const ratio = window.devicePixelRatio || 1, width = canvas.clientWidth, height = canvas.clientHeight;
    if (canvas.width !== Math.round(width * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const ctx = canvas.getContext("2d"), c = colors();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const band = 22, curveTop = band + 8, curveBottom = height - 20;
    for (const passage of score.passages) {
      ctx.fillStyle = c.grammar[GRAMMAR_CLASSES[passage.grammar]] || c.line;
      ctx.fillRect(x(passage.start), 0, Math.max(1, x(passage.end) - x(passage.start) - 1), band);
      ctx.strokeStyle = c.ink;
      ctx.globalAlpha = 0.55;
      for (const shot of passage.shots.slice(1)) {
        ctx.beginPath();
        ctx.moveTo(x(shot.start), 0);
        ctx.lineTo(x(shot.start), curveBottom);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
    ctx.beginPath();
    ctx.moveTo(x(score.offset), curveBottom);
    for (const beat of score.beats) ctx.lineTo(x(beat.time), curveBottom - beat.energy * (curveBottom - curveTop));
    ctx.lineTo(x(score.song_end), curveBottom);
    ctx.closePath();
    ctx.fillStyle = c.accent;
    ctx.globalAlpha = 0.28;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = c.accent;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.lineWidth = 1;
    for (const beat of score.beats) {
      ctx.fillStyle = beat.downbeat ? c.ink : c.muted;
      ctx.fillRect(x(beat.time) - (beat.downbeat ? 1 : 0.5), height - (beat.downbeat ? 16 : 9), beat.downbeat ? 2 : 1, beat.downbeat ? 16 : 9);
    }
    const now = video.currentTime || 0;
    ctx.fillStyle = c.ink;
    ctx.fillRect(x(now) - 1, 0, 2, height);
    const line = describe(now);
    if (line !== lastCaption) {
      caption.textContent = line;
      lastCaption = line;
    }
    canvas.setAttribute("aria-valuemax", String(end()));
    canvas.setAttribute("aria-valuenow", now.toFixed(1));
    canvas.setAttribute("aria-valuetext", `${now.toFixed(1)} seconds. ${line}`);
  }

  const end = () => score.duration || score.song_end;
  function jump(time) {
    video.currentTime = Math.min(Math.max(0, time), end());
    draw();
  }
  function loop() {
    draw();
    if (!video.paused && !video.ended) frame = requestAnimationFrame(loop);
  }
  function seek(event) {
    if (!score) return;
    const rect = canvas.getBoundingClientRect();
    jump((event.clientX - rect.left) / rect.width * end());
  }

  canvas.addEventListener("keydown", event => {
    if (!score) return;
    const cuts = [0, ...score.passages.flatMap(passage => passage.shots.map(shot => shot.start)), end()];
    const now = video.currentTime || 0;
    const target = {
      ArrowRight: cuts.find(t => t > now + 0.05),
      ArrowUp: cuts.find(t => t > now + 0.05),
      ArrowLeft: cuts.filter(t => t < now - 0.05).at(-1),
      ArrowDown: cuts.filter(t => t < now - 0.05).at(-1),
      Home: 0,
      End: end()
    }[event.key];
    if (target === undefined && !(event.key in { Home: 1, End: 1 })) return;
    event.preventDefault();
    jump(target ?? now);
  });

  canvas.addEventListener("pointerdown", event => { canvas.setPointerCapture(event.pointerId); seek(event); });
  canvas.addEventListener("pointermove", event => { if (canvas.hasPointerCapture(event.pointerId)) seek(event); });
  video.addEventListener("play", () => { cancelAnimationFrame(frame); loop(); });
  ["seeked", "pause", "timeupdate", "loadedmetadata"].forEach(name => video.addEventListener(name, draw));

  const resize = new ResizeObserver(draw);
  resize.observe(canvas);
  const view = { draw, dispose: () => { resize.disconnect(); cancelAnimationFrame(frame); } };
  scoreViews.add(view);

  box.addEventListener("toggle", async () => {
    if (!box.open || score) return draw();
    try {
      score = await (await api(`/api/outputs/${encodeURIComponent(output.file.split("/")[0])}/score`)).json();
      legend.replaceChildren(
        ...[...new Set(score.passages.map(passage => passage.grammar))].map(name =>
          text("span", name, "score-key score-" + (GRAMMAR_CLASSES[name] || "other"))
        ),
        text("span", "energy", "score-key score-energy"),
        text("span", "beats · downbeats (tall)", "score-key score-beats"),
        text("span", "planned cuts", "score-key score-cuts")
      );
      draw();
    } catch (error) {
      box.replaceChildren(text("summary", "Watch the song conduct"), text("p", error.message, "muted"));
    }
  });
  return box;
}

const THUMBNAIL_SLOTS = 2;
const THUMBNAIL_TIMEOUT_MS = 5000;

// Ask for the first frame; resolves once the browser stops fetching (or gives up).
const loadThumbnail = video => new Promise(resolve => {
  if (!video.isConnected) return resolve();
  const timer = setTimeout(resolve, THUMBNAIL_TIMEOUT_MS);
  ["suspend", "error"].forEach(name => video.addEventListener(name, () => { clearTimeout(timer); resolve(); }, { once: true }));
  video.preload = "metadata";
  video.load();
});

// A few at a time, so the list never holds most of the browser's connections (see 1.10.12).
const loadThumbnails = videos => {
  let nextIndex = 0;
  return Promise.all(Array.from({ length: THUMBNAIL_SLOTS }, async () => {
    while (nextIndex < videos.length) {
      const video = videos[nextIndex++];
      if (video) await loadThumbnail(video);
    }
  }));
};

export async function loadOutputs() {
  const outputs = await (await api("/api/outputs")).json();
  scoreViews.forEach(view => view.dispose());
  scoreViews.clear();
  $("#output-list").replaceChildren(...outputs.map(output => {
    const card = text("article", "", "card", `Rendered output: ${output.title}`);
    const video = document.createElement("video");
    video.src = "/api/media/" + output.file;
    video.controls = true;
    video.preload = "none";
    video.dataset.tooltip = `Video player for ${output.title}`;
    video.title = video.dataset.tooltip;

    const download = text("a", "Download MP4", "secondary", `Download ${output.title} as MP4`);
    download.href = "/api/media/" + output.file + "?download=true";
    download.setAttribute("download", output.file.split("/").pop() || "video.mp4");

    const upscale = text("button", "Topaz upscale", "secondary", `Upscale ${output.title} using Topaz Video AI`);
    upscale.onclick = () => {
      state.upscaleSource = output.file;
      openUpscaleDialog();
    };

    const caption = text("button", "Add lyric captions", "secondary", `Rebuild ${output.title} with lyrics from its original clips; the original output is kept`);
    caption.onclick = () => {
      state.captionSource = output.file;
      $("#caption-dialog").showModal();
    };

    const deleteBtn = text("button", "Delete", "delete-btn", `Delete ${output.title} from studio`);
    deleteBtn.onclick = () => showDeleteDialog(output);

    card.append(video);
    if (output.kind === "video") card.append(scoreView(output, video));
    card.append(text("h2", output.title), text("p", `${output.kind} · ${Number(output.duration).toFixed(1)} seconds`));
    if (output.quality_warnings?.length) {
      const warning = text("div", "", "quality-warning", "Automatic motion and framing check results");
      warning.setAttribute("role", "note");
      warning.append(text("strong", "Quality check: "), output.quality_warnings.join(" · "));
      card.append(warning);
    }

    const actions = document.createElement("div");
    actions.className = "output-actions";
    actions.append(download, upscale);
    const viewPromptsBtn = text("button", "Edit", "secondary", `Edit ${output.title} passage by passage: prompts, clip takes, seeds and the final video`);
    viewPromptsBtn.onclick = () => showProductionBreakdown(output);
    actions.append(viewPromptsBtn);
    if (output.kind === "video") actions.append(caption);
    if (output.kind === "video") actions.append(exportButton(output));
    actions.append(deleteBtn);
    card.append(actions);
    return card;
  }));
  loadThumbnails($$("#output-list video"));

  if (!outputs.length) {
    $("#output-list").append(text("div", "Your finished videos and idents will appear here.", "empty", "No completed productions yet"));
  }
  $$(".ident-select").forEach(select => {
    const old = select.value;
    const identOutputs = outputs.filter(output => output.kind === "ident");
    const videoOutputs = outputs.filter(output => output.kind === "video");

    const children = [
      option("", identOutputs.length ? "None" : "None (render one in 02. Credits & Idents)", "No ident clip attached")
    ];

    if (identOutputs.length) {
      const group = document.createElement("optgroup");
      group.label = "Idents & Title Cards";
      identOutputs.forEach(o => group.appendChild(option(o.file, o.title, `Ident clip: ${o.title}`)));
      children.push(group);
    }

    if (videoOutputs.length) {
      const group = document.createElement("optgroup");
      group.label = "Completed Video Clips";
      videoOutputs.forEach(o => group.appendChild(option(o.file, `${o.title || "Untitled"} (${o.file.split("/")[0].slice(0, 8)})`, `Attach video: ${o.title}`)));
      children.push(group);
    }

    select.replaceChildren(...children);
    if ([...select.options].some(item => item.value === old)) select.value = old;
  });

  await loadUnfinishedRuns();
}

// --- Pure Template Generator for Unfinished Runs ---

const unfinishedRunRowHtml = (run) => {
  const escId = escapeHtml(run.id);
  const escTitle = escapeHtml(run.title);
  const passages = run.segments ? `${run.validated_prompts}/${run.segments}` : "—";
  const statusHtml = run.can_finish
    ? '<span style="color:#16a34a;font-weight:600;">Ready to finish</span>'
    : '<span class="muted">Draft / Partial</span>';
  const finishBtn = run.can_finish
    ? `<button type="button" class="secondary" data-action="finish-run" style="padding:4px 8px;font-size:13px;margin-right:8px;" title="Resume generation for ${escTitle}">Finish / Resume</button>`
    : "";

  return `
    <tr data-id="${escId}" data-title="${escTitle}" data-size="${run.size_mb}" data-clips="${run.rendered_clips || 0}" style="border-bottom:1px solid var(--line);">
      <td style="padding:8px;font-weight:600;">${escTitle}</td>
      <td style="padding:8px;" class="muted">${escapeHtml(run.created_str)}</td>
      <td style="padding:8px;">${passages}</td>
      <td style="padding:8px;">${statusHtml}</td>
      <td style="padding:8px;" class="muted">${run.size_mb} MB</td>
      <td style="padding:8px;text-align:right;">
        ${finishBtn}
        <button type="button" class="delete-btn" data-action="purge-run" style="padding:4px 8px;font-size:13px;" title="Delete draft ${escTitle}">Purge</button>
      </td>
    </tr>
  `;
};

export async function loadUnfinishedRuns() {
  const tbody = $("#unfinished-runs-list");
  const countBadge = $("#unfinished-count");
  if (!tbody) return;
  try {
    const list = await (await api("/api/runs/unfinished")).json();
    if (countBadge) countBadge.textContent = String(list.length);

    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted" style="padding:16px 8px;text-align:center;">No unfinished drafts or interrupted renders found.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map(unfinishedRunRowHtml).join("");
  } catch (err) {
    console.error("Failed to load unfinished runs:", err);
  }
}

// Single delegated click listeners initialized once
function setupOutputsDelegatedHandlers() {
  const tbody = $("#unfinished-runs-list");
  if (tbody && !tbody._hasDelegatedActions) {
    tbody._hasDelegatedActions = true;
    tbody.addEventListener("click", handle(async (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const row = btn.closest("tr[data-id]");
      if (!row) return;
      const { id, title, size, clips } = row.dataset;
      const action = btn.dataset.action;

      if (action === "finish-run") {
        notice("Loading resume preview...");
        const quote = await json("/api/resume/quote", { run_id: id });
        notice("");
        showQuote({ kind: quote.kind }, quote);
      } else if (action === "purge-run") {
        const rendered = Number(clips) > 0;
        if (!window.confirm(`Purge draft "${title}" (${size} MB)? This cannot be undone.` + (rendered ? ` It holds ${clips} rendered clip(s) that may already be paid for.` : ""))) return;
        btn.disabled = true;
        try {
          await api(`/api/runs/unfinished/${encodeURIComponent(id)}?confirm_rendered=true`, { method: "DELETE" });
          notice(`Purged draft "${title}".`);
          await loadUnfinishedRuns();
        } finally {
          btn.disabled = false;
        }
      }
    }));
  }

  const purgeAllBtn = $("#purge-all-unfinished-btn");
  if (purgeAllBtn && !purgeAllBtn._hasClickAction) {
    purgeAllBtn._hasClickAction = true;
    purgeAllBtn.onclick = handle(async (e) => {
      e.stopPropagation();
      if (!window.confirm("Purge unfinished drafts? Completed videos and interrupted runs that hold rendered clips will NOT be touched.")) return;
      purgeAllBtn.disabled = true;
      try {
        const res = await (await api("/api/runs/unfinished/purge", { method: "POST" })).json();
        notice(`Purged ${res.purged_count} unfinished draft folders.` + (res.kept_with_clips ? ` Kept ${res.kept_with_clips} with rendered clips; purge those one at a time.` : ""));
        await loadUnfinishedRuns();
      } finally {
        purgeAllBtn.disabled = false;
      }
    });
  }
}

export async function initCaptionControls() {
  initColourWheels();                       // inline colour wheels replace the browser's own colour pickers
  $$('[data-caption-custom]').forEach(checkbox => {
    const form = checkbox.closest("form");
    const sync = () => { form.querySelector('[data-caption-colours]').hidden = !checkbox.checked; };
    checkbox.addEventListener("change", sync);
    sync();
  });
  const form = $("#video-form");
  form.querySelector(".captions-fields").hidden = form.elements.captions_mode.value !== "burned";
  try {
    const response = await fetch("/api/captions/fonts");
    const { fonts } = response.ok ? await response.json() : { fonts: [] };
    $("#caption-fonts").replaceChildren(...fonts.map(font => option(font, font)));
  } catch { /* Installed font suggestions are optional. */ }
}

export function initUpscaleForm() {
  setupOutputsDelegatedHandlers();
  $("#caption-form").onsubmit = handle(async event => {
    const form = event.target;
    await json("/api/captions", { position: form.elements.position.value, style: form.elements.style.value,
      size: form.elements.size.value, color: form.elements.custom.checked ? form.elements.color.value : "",
      outline_color: form.elements.custom.checked ? form.elements.outline.value : "",
      font: form.elements.font.value, source: state.captionSource });
    $("#caption-dialog").close();
  });
  const upscaleBody = () => {
    const form = $("#upscale-form").elements;
    const cloud = state.upscaleCloud && state.readUpscaleOptions ? state.readUpscaleOptions() : null;
    return { model: cloud ? cloud.model : form.model.value, scale: Number(form.scale.value), source: state.upscaleSource,
      ...(cloud && Object.keys(cloud.options).length ? { options: cloud.options } : {}) };
  };
  let quoteSerial = 0;
  const resetQuote = () => {
    quoteSerial += 1;
    state.upscaleCredits = null;
    $("#upscale-quote").textContent = "";
    $("#upscale-consent").checked = false;
    $("#upscale-consent-row").hidden = true;
    $("#upscale-start").disabled = state.upscaleCloud;
  };
  $("#upscale-form").elements.model.oninput = $("#upscale-form").elements.scale.onchange = resetQuote;
  $("#upscale-service").onchange = handle(async event => { await chooseUpscaleService(event.target.value); });
  $("#upscale-options").addEventListener("input", resetQuote);
  $("#upscale-options").addEventListener("change", resetQuote);
  $("#upscale-consent").onchange = event => { $("#upscale-start").disabled = !event.target.checked; };
  $("#upscale-estimate").onclick = handle(async () => {
    resetQuote();
    $("#upscale-quote").textContent = "Asking Topaz for a price…";
    const serial = quoteSerial;
    const quote = await json("/api/upscale/estimate", upscaleBody());
    if (serial !== quoteSerial) return;
    const [low, high] = quote.credits;
    state.upscaleCredits = high;
    $("#upscale-quote").textContent = `Estimate: ${low}–${high} Topaz credits, about ${quote.seconds[0]}–${quote.seconds[1]} seconds, output ${quote.output.width}×${quote.output.height} at ${Math.round(quote.frame_rate * 100) / 100} fps.`;
    $("#upscale-consent-text").textContent = `I approve spending up to ${high} Topaz credits.`;
    $("#upscale-consent-row").hidden = false;
  });
  $("#upscale-form").onsubmit = handle(async event => {
    await json("/api/upscale", { ...upscaleBody(), ...(state.upscaleCloud ? { max_credits: state.upscaleCredits } : {}) });
    $("#upscale-dialog").close();
  });
  $("#prompts-view-back-btn")?.addEventListener("click", closeProductionBreakdown);
  $("#prompts-view-refresh-btn")?.addEventListener("click", handle(refreshProductionBreakdown));
}
