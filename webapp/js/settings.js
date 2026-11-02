// Studio Settings, API Profiles, Credentials, and Filesystem Browser Picker.

import { $, api, handle, json, keyRow, notice, option, state, text } from "./core.js";
import { refreshServices } from "./production.js";
import { setPanelAutoCollapse } from "./panel_progress.js";

export const settingLabels = {
  writer_api_profile: "Writer API profile",
  vision_api_profile: "Vision API profile",
  video_api_profile: "Video API profile",
  auto_updates: "Automatic updates",
  auto_collapse_panels: "Collapse completed panels automatically",
  h3_tag_normalizer: "Bind H3 pictures and subjects automatically",
  comfy_sdk_url: "Local Comfy API proxy URL",
  backend: "Default renderer",
  comfy_url: "ComfyUI service URL",
  comfy_input: "ComfyUI input folder (shared local path)",
  comfy_output: "ComfyUI output folder (shared local path)",
  writer_launch: "Local writer launch command (JSON arguments)",
  writer_cwd: "Writer working directory (llama.cpp folder)",
  comfy_launch: "ComfyUI launch command (JSON arguments)",
  comfy_cwd: "ComfyUI working folder",
  render_timeout_minutes: "Wait per local clip, minutes (0 = no limit)",
  laya_model_dir: "Laya model folder",
  laya_device: "Laya device (cpu, cuda, mps)",
  writer_url: "Writer service URL (OpenAI-compatible /v1)",
  writer_model: "Music-video writer model",
  writer_mode: "Writer service: local or API",
  writer_call_estimate: "API writer estimate per call, USD",
  workflow_map_path: "Workflow binding map JSON path",
  vision_url: "Vision service URL (OpenAI-compatible /v1)",
  vision_model: "Vision model name",
  vision_launch: "Vision launch command (JSON arguments)",
  vision_key_env: "Vision credential name",
  vision_call_estimate: "Vision estimate per call, USD (0 for local)",
  topaz_backend: "Topaz upscale service: installed program or cloud",
  topaz_executable: "Installed Topaz FFmpeg executable path",
  topaz_models: "Installed Topaz models folder",
  h3_video_vae: "H3 video VAE model",
  h3_audio_vae: "H3 audio VAE model",
  h3_diffusion_model: "H3 reference-to-video diffusion model",
  h3_text_encoder: "H3 text encoder (CLIP) model"
};

export const settingTooltips = {
  auto_updates: "At the next launch, install tracked repository updates automatically. Turn off to check and notify only.",
  h3_tag_normalizer: "Local H3 only, off by default. At render time, tie each cast member's Picture tag to their Subject definition and replace their name in the shot descriptions with the Subject tag. Prompts stay as written and checked.",
  auto_collapse_panels: "Collapse a required panel when its last required field loses focus. Progress colours and labels stay visible when this is off.",
  comfy_sdk_url: "Official Comfy API v2 proxy on this machine, usually http://127.0.0.1:8189",
  backend: "Default video generation engine for music videos and idents",
  comfy_url: "HTTP URL for your running ComfyUI service instance (usually http://127.0.0.1:8188)",
  comfy_input: "Shared local filesystem path to ComfyUI's input directory",
  comfy_output: "Shared local filesystem path to ComfyUI's output directory",
  writer_launch: "Optional JSON argument list to automatically launch a local llama-server writer. Leave blank if running manually",
  writer_cwd: "Working directory for the local writer process",
  comfy_launch: "Optional JSON argument list to automatically launch ComfyUI for local rendering. Leave blank if you run ComfyUI yourself",
  comfy_cwd: "ComfyUI root installation directory containing main.py. Used only when comfy_launch is set",
  render_timeout_minutes: "How long to wait for ComfyUI to finish one clip before the run stops with an error. 0 waits forever, which can hide a hung renderer",
  laya_model_dir: "Path to folder containing Laya model.safetensors and config files",
  laya_device: "Hardware execution device for local Laya prompt review (cuda, cpu, mps)",
  writer_url: "OpenAI-compatible /v1 endpoint URL for the music-video writer LLM",
  writer_model: "Model identifier name served by your writer LLM service",
  writer_mode: "Select 'local' for private local engines or 'api' for cloud providers",
  writer_call_estimate: "Estimated cost in USD per writer generation call",
  workflow_map_path: "Filesystem path to the ComfyUI node injection map JSON",
  vision_url: "OpenAI-compatible /v1 endpoint for multimodal vision style harvesting",
  vision_model: "Model identifier for your vision service",
  vision_launch: "Optional JSON argument list to start your local vision server (llama-server with its --mmproj, --alias equal to the vision model name, and the vision URL port). Leave blank to derive it from the writer launch when a matching mmproj file sits beside the model. Mondo starts it for style harvest, world reading and storyboards when nothing answers, and stops it afterwards",
  vision_key_env: "Environment variable name storing your vision API key",
  vision_call_estimate: "Estimated cost in USD per vision style-harvest call",
  topaz_backend: "Use your installed Topaz Video AI, or the Topaz cloud service (needs a Topaz API key under Provider keys; Topaz charges credits)",
  topaz_executable: "Path to Topaz Video AI ffmpeg.exe binary for upscaling",
  topaz_models: "Folder path containing installed Topaz AI model weight files",
  h3_video_vae: "Video VAE safetensors filename for MiniMax H3 (node 119)",
  h3_audio_vae: "Audio VAE safetensors filename for MiniMax H3 (node 120)",
  h3_diffusion_model: "Reference-to-video UNET diffusion model for MiniMax H3 (node 127)",
  h3_text_encoder: "Text encoder CLIP model for MiniMax H3 (node 128)"
};

const folderSettings = new Set([
  "comfy_input",
  "comfy_output",
  "writer_cwd",
  "comfy_cwd",
  "laya_model_dir",
  "topaz_models"
]);

const fileSettings = {
  topaz_executable: ".exe",
  workflow_map_path: ".json"
};

let pickerNavigation = 0;
let currentPickerState = {
  mode: "folder",
  ext: "",
  current: "",
  onSelect: null,
  allEntries: []
};

export async function navigatePicker(targetPath) {
  const navigation = ++pickerNavigation;
  $("#picker-confirm").disabled = true;
  const params = new URLSearchParams();
  if (targetPath) params.set("path", targetPath);
  params.set("mode", currentPickerState.mode);
  if (currentPickerState.ext) params.set("ext", currentPickerState.ext);

  const res = await api("/api/fs/browse?" + params.toString());
  if (!res.ok) return;
  const data = await res.json();
  if (navigation !== pickerNavigation || !$("#folder-picker-dialog").open) return;
  currentPickerState.current = data.current;

  $("#picker-selected-path").value = currentPickerState.mode === "folder" ? data.current : "";
  $("#picker-confirm").disabled = currentPickerState.mode === "file";

  const roots = $("#picker-roots");
  roots.replaceChildren();
  if (data.home) {
    const homeBtn = document.createElement("button");
    homeBtn.type = "button";
    homeBtn.className = "picker-root-btn";
    homeBtn.textContent = "🏠 Home";
    homeBtn.onclick = handle(() => navigatePicker(data.home));
    roots.append(homeBtn);
  }
  for (const drive of (data.drives || [])) {
    const driveBtn = document.createElement("button");
    driveBtn.type = "button";
    driveBtn.className = "picker-root-btn";
    driveBtn.textContent = drive;
    driveBtn.onclick = handle(() => navigatePicker(drive));
    roots.append(driveBtn);
  }

  const breadcrumbs = $("#picker-breadcrumbs");
  breadcrumbs.replaceChildren();
  const parts = data.current.split(/[\\/]+/).filter(Boolean);
  const isWin = /^[a-zA-Z]:/.test(data.current);
  let accumulated = "";

  if (data.parent) {
    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "picker-crumb";
    upBtn.textContent = "⬆ Up";
    upBtn.onclick = handle(() => navigatePicker(data.parent));
    breadcrumbs.append(upBtn, document.createTextNode(" · "));
  }

  parts.forEach((part, index) => {
    if (index === 0 && isWin) {
      accumulated = part + "\\";
    } else if (index === 0 && !isWin) {
      accumulated = "/" + part;
    } else {
      accumulated += (accumulated.endsWith("\\") || accumulated.endsWith("/") ? "" : (isWin ? "\\" : "/")) + part;
    }
    const currentPath = accumulated;
    const crumb = document.createElement("button");
    crumb.type = "button";
    crumb.className = "picker-crumb";
    crumb.textContent = part;
    if (index < parts.length - 1) {
      crumb.onclick = handle(() => navigatePicker(currentPath));
      breadcrumbs.append(crumb, document.createTextNode(" > "));
    } else {
      breadcrumbs.append(crumb);
    }
  });

  currentPickerState.allEntries = [
    ...(data.folders || []).map(f => ({ ...f, isDir: true })),
    ...(data.files || []).map(f => ({ ...f, isDir: false }))
  ];
  renderPickerEntries();
}

export const escapeHtml = str =>
  String(str).replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[ch]));

export const pickerEntryHtml = (entry, isSelected = false) => {
  const icon = entry.isDir ? "📁" : "📄";
  const selectedClass = isSelected ? " selected" : "";
  return `<div class="picker-entry${selectedClass}" tabindex="0" role="button" data-path="${escapeHtml(entry.path)}" data-isdir="${entry.isDir ? 'true' : 'false'}"><span class="picker-entry-icon">${icon}</span><span class="picker-entry-name">${escapeHtml(entry.name)}</span></div>`;
};

export function renderPickerEntries() {
  const container = $("#picker-entries");
  if (!container) return;
  const filter = ($("#picker-filter")?.value || "").toLowerCase().trim();
  const selectedPath = $("#picker-selected-path")?.value || "";

  const filtered = currentPickerState.allEntries.filter(entry =>
    !filter || entry.name.toLowerCase().includes(filter)
  );

  if (!filtered.length) {
    container.innerHTML = `<div class="picker-entry" style="color: var(--muted);">(No matching folders or files)</div>`;
    return;
  }

  container.innerHTML = filtered.map(entry => pickerEntryHtml(entry, entry.path === selectedPath)).join("");
}

export function openPicker(options) {
  currentPickerState = {
    mode: options.mode || "folder",
    ext: options.ext || "",
    current: "",
    onSelect: options.onSelect,
    allEntries: []
  };

  $("#picker-title").textContent = options.title || (options.mode === "file" ? "Select file" : "Select folder");
  $("#picker-confirm").textContent = options.mode === "file" ? "Select this file" : "Select this folder";
  $("#picker-filter").value = "";

  const dialog = $("#folder-picker-dialog");
  dialog.showModal();
  navigatePicker(options.initialPath || "").catch(error => notice(error.message));
}

export async function loadSettings() {
  const data = await (await api("/api/settings")).json();
  setPanelAutoCollapse(data.settings.auto_collapse_panels);
  const currentH3 = data.settings.h3_models || {};
  const installedH3 = data.h3_models_installed || {};
  const entries = Object.entries(data.settings).filter(([k]) => k !== "h3_models");

  const fields = entries.map(([name, value]) => {
    const tip = settingTooltips[name] || settingLabels[name] || name;
    const label = text("label", settingLabels[name] || name, "", tip);
    let input;
    if (name.endsWith("_api_profile")) {
      const role = name.replace("_api_profile", "");
      input = document.createElement("select");
      input.append(option("", "Manual configuration", "Use the individual settings below"));
      input.append(...(data.api_profiles || []).filter(p => p.role === role).map(p => option(p.name, p.name)));
    } else if (name === "auto_updates" || name === "auto_collapse_panels" || name === "h3_tag_normalizer") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(value);
    } else if (name === "writer_mode") {
      input = document.createElement("select");
      input.append(option("local", "Local", "Local writer engine"), option("api", "API", "Hosted cloud API provider"));
    } else if (name === "topaz_backend") {
      input = document.createElement("select");
      input.append(option("local", "Installed Topaz", "Run your own Topaz Video AI install"), option("cloud", "Topaz cloud (credits)", "Upscale on Topaz servers using your Topaz API key; charges Topaz credits"));
    } else if (name === "backend") {
      input = document.createElement("select");
      input.append(...Object.entries(state.catalog.backends).map(([key, card]) => option(key, card.name, `${card.name}: ${card.description || key}`)));
    } else if (name === "laya_device") {
      input = document.createElement("select");
      input.append(
        option("cuda_or_cpu", "CUDA with CPU fallback", "Use CUDA when available, otherwise CPU"),
        option("mps_or_cpu", "MPS with CPU fallback", "Use MPS when available, otherwise CPU"),
        option("auto", "Auto (CUDA, MPS, then CPU)", "Choose an available Laya device automatically"),
        option("cpu", "CPU", "Run Laya validator on CPU"),
        option("cuda", "CUDA", "Run Laya validator on NVIDIA GPU (CUDA)"),
        option("mps", "MPS", "Run Laya validator on Apple Silicon (MPS)")
      );
    } else {
      input = document.createElement("input");
      input.type = name.endsWith("call_estimate") || name === "render_timeout_minutes" ? "number" : "text";
      if (name === "render_timeout_minutes") { input.min = "0"; input.max = "1440"; input.step = "1"; }
      else if (input.type === "number") { input.min = "0"; input.max = "100"; input.step = "0.001"; }
    }
    input.name = name;
    input.value = value;
    input.dataset.tooltip = tip;
    input.title = tip;
    if (name === "vision_key_env") input.readOnly = true;

    if (folderSettings.has(name) || name in fileSettings) {
      const group = document.createElement("div");
      group.className = "path-input-group";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "browse-btn";
      btn.textContent = "📁 Browse";
      btn.dataset.tooltip = `Browse filesystem for ${settingLabels[name] || name}`;
      btn.title = btn.dataset.tooltip;
      const isFile = name in fileSettings;
      btn.onclick = (e) => {
        e.preventDefault();
        openPicker({
          title: isFile ? `Select file: ${settingLabels[name] || name}` : `Select folder: ${settingLabels[name] || name}`,
          mode: isFile ? "file" : "folder",
          ext: fileSettings[name] || "",
          initialPath: input.value,
          onSelect: (selectedPath) => {
            input.value = selectedPath;
            input.dispatchEvent(new Event("change", { bubbles: true }));
          }
        });
      };
      group.append(input, btn);
      if (name === "workflow_map_path") {
        const presets = data.workflow_presets || [];
        const picker = document.createElement("select");
        picker.title = picker.dataset.tooltip = "Bundled H3 workflows: standard (20 steps) or FastH3 Omni (8 steps, INT8 or BF16)";
        picker.append(option("", "Custom path", "Use the path typed below"), ...presets.map(p => option(p.path, p.name)));
        picker.value = presets.some(p => p.path === value) ? value : "";
        picker.onchange = () => {
          if (picker.value) { input.value = picker.value; input.dispatchEvent(new Event("change", { bubbles: true })); }
        };
        input.addEventListener("input", () => { picker.value = presets.some(p => p.path === input.value) ? input.value : ""; });
        label.append(picker);
      }
      label.append(group);
      if (name === "workflow_map_path" && data.workflow_steps) {
        label.append(text("small", `The saved workflow renders with ${data.workflow_steps} sampler steps. Choosing a bundled diffusion model switches to that model's own workflow.`, "settings-note"));
      }
    } else {
      label.append(input);
      if (name === "writer_launch") {
        const hint = document.createElement("div");
        hint.style.marginTop = "4px";
        const helpBtn = document.createElement("button");
        helpBtn.type = "button";
        helpBtn.className = "quiet llama-help-btn";
        helpBtn.style.display = "inline";
        helpBtn.style.padding = "0";
        helpBtn.textContent = "ℹ️ Need help with token buffers or launch arguments? Open llama.cpp guide ↗";
        helpBtn.onclick = event => {
          event.preventDefault();
          $("#panel-settings > .panel-header-row .llama-help-btn").click();
        };
        hint.append(helpBtn);
        label.append(hint);
      }
    }
    return label;
  });

  const h3Keys = [
    ["video_vae", "h3_video_vae"],
    ["audio_vae", "h3_audio_vae"],
    ["diffusion_model", "h3_diffusion_model"],
    ["text_encoder", "h3_text_encoder"]
  ];

  for (const [key, fieldName] of h3Keys) {
    const tip = settingTooltips[fieldName];
    const label = text("label", settingLabels[fieldName] || fieldName, "", tip);
    const installed = installedH3[key] || [];
    const currentVal = currentH3[key] || "";
    const select = document.createElement("select");
    select.name = "h3_" + key;
    select.dataset.initialValue = currentVal;
    select.dataset.tooltip = tip;
    select.title = tip;

    const optionsList = Array.from(new Set([currentVal, ...installed].filter(Boolean)));
    if (!currentVal) {
      select.append(option("", "No supported loader in selected workflow"));
      select.disabled = true;
    } else {
      for (const m of optionsList) {
        const optLabel = m === currentVal && !installed.includes(m) ? m + " (current; not detected)" : m;
        select.append(option(m, optLabel, `${settingLabels[fieldName]}: ${m}`));
      }
      select.value = currentVal;
    }
    label.append(select);
    fields.push(label);
  }

  for (const role of ["writer", "vision", "video"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet";
    button.textContent = `Save configured ${role} API as a profile`;
    button.onclick = handle(async () => {
      const name = window.prompt(`Profile ID for the saved ${role} settings (lowercase letters, numbers, underscores or hyphens). Save your settings and key first.`);
      if (!name) return;
      await json("/api/api-profiles", { name, role }, "POST");
      await loadSettings();
      notice("API profile saved privately. Select it to activate it.");
    });
    fields.push(button);
  }
  $("#settings-fields").replaceChildren(...fields);
  $("#key-list").replaceChildren(...Object.entries(data.keys).map(([name, set]) =>
    keyRow(name, set, async () => { await loadSettings(); await refreshServices(true); })));
  return data.settings;
}

// The PUT body for the whole settings form; h3 loaders are sent only when they differ from what is installed now.
function settingsPayload(form) {
  const raw = Object.fromEntries(new FormData(form));
  const h3_models = {};
  for (const key of ["video_vae", "audio_vae", "diffusion_model", "text_encoder"]) {
    const field = form.elements["h3_" + key];
    const value = raw["h3_" + key];
    if (value && value !== field?.dataset.initialValue) h3_models[key] = value;
    delete raw["h3_" + key];
  }
  raw.auto_updates = form.elements.auto_updates.checked;
  raw.auto_collapse_panels = form.elements.auto_collapse_panels.checked;
  raw.h3_tag_normalizer = form.elements.h3_tag_normalizer.checked;
  raw.vision_call_estimate = Number(raw.vision_call_estimate);
  raw.writer_call_estimate = Number(raw.writer_call_estimate);
  raw.render_timeout_minutes = Math.max(0, Math.round(Number(raw.render_timeout_minutes) || 0));
  if (Object.keys(h3_models).length) raw.h3_models = h3_models;
  return raw;
}

// Choosing a profile, a workflow or an H3 model changes other fields on the server, so only those redraw the form.
const redrawsForm = name => name.endsWith("_api_profile") || name === "workflow_map_path" || name.startsWith("h3_");
function initSettingsAutosave(form) {
  const status = form.querySelector("#settings-autosave-status");
  let timer = null, saving = false, queued = false, redraw = false;
  const show = message => { status.textContent = message; };
  const flush = async () => {
    if (saving) { queued = true; return; }
    saving = true;
    const refresh = redraw;
    redraw = false;
    try {
      await json("/api/settings", settingsPayload(form), "PUT");
      setPanelAutoCollapse(form.elements.auto_collapse_panels.checked);
      if (refresh) await loadSettings();
      refreshServices(true);   // a probe can be slow; never hold up the next save
      show("Saved automatically at " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    } catch (error) {
      show("Not saved: " + error.message + " Change the setting again to retry.");
    } finally {
      saving = false;
      if (queued) { queued = false; timer = setTimeout(flush, 0); }
    }
  };
  const schedule = delay => { clearTimeout(timer); show("Saving…"); timer = setTimeout(flush, delay); };
  form.addEventListener("change", event => {
    if (!event.target.name) return;
    redraw ||= redrawsForm(event.target.name);
    schedule(600);
  });
  form.onsubmit = event => { event.preventDefault(); schedule(0); };   // Enter in a field saves right away
}

export function initSettingsAndPicker() {
  initSettingsAutosave($("#settings-form"));

  $("#key-form").onsubmit = event => event.preventDefault();

  const pickerFilter = $("#picker-filter");
  if (pickerFilter) pickerFilter.oninput = () => renderPickerEntries();
  const pickerCancel = $("#picker-cancel");
  if (pickerCancel) pickerCancel.onclick = () => $("#folder-picker-dialog").close();
  const pickerConfirm = $("#picker-confirm");
  if (pickerConfirm) {
    pickerConfirm.onclick = () => {
      const selected = $("#picker-selected-path").value;
      if (selected && currentPickerState.onSelect) {
        currentPickerState.onSelect(selected);
      }
      $("#folder-picker-dialog").close();
    };
  }

  const pickerEntries = $("#picker-entries");
  if (pickerEntries) {
    pickerEntries.onclick = (event) => {
      const row = event.target.closest(".picker-entry[data-path]");
      if (!row) return;
      const path = row.dataset.path;
      const isDir = row.dataset.isdir === "true";
      $("#picker-selected-path").value = path;
      if (pickerConfirm) {
        pickerConfirm.disabled = currentPickerState.mode === "file" && isDir;
      }
      pickerEntries.querySelectorAll(".picker-entry").forEach(el => el.classList.remove("selected"));
      row.classList.add("selected");
    };

    pickerEntries.ondblclick = (event) => {
      const row = event.target.closest(".picker-entry[data-path]");
      if (!row) return;
      const path = row.dataset.path;
      const isDir = row.dataset.isdir === "true";
      if (isDir) {
        navigatePicker(path).catch(error => notice(error.message));
      } else {
        if (currentPickerState.onSelect) {
          currentPickerState.onSelect(path);
        }
        $("#folder-picker-dialog").close();
      }
    };

    pickerEntries.onkeydown = (event) => {
      const row = event.target.closest(".picker-entry[data-path]");
      if (!row) return;
      if (event.key === "Enter") {
        event.preventDefault();
        row.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
      } else if (event.key === " ") {
        event.preventDefault();
        row.click();
      }
    };
  }
}

