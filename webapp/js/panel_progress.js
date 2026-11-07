// Form progress is a view of completed inputs. A production quote remains the authority.
import { $, $$, state } from "./core.js";

const CARD_IDS = ["card-track-direction", "card-cast-staging", "director-control-room"];
const FOLD_IDS = ["director-pacing", "director-camera", "director-format", "director-render"];
const FOLD_ID_SET = new Set(FOLD_IDS);
let saved = {};
let units = [];
let autoCollapse = true;
let defaultBackend = "local_h3";
let save = () => {};

export const panelProgress = (required, optional) => ({
  required_total: required.length,
  required_filled: required.filter(Boolean).length,
  optional_total: optional.length,
  optional_changed: optional.filter(Boolean).length
});

export const panelState = (progress, collapsed, reviewed) =>
  progress.required_total === 0 ? (reviewed && collapsed ? "reviewed" : "optional") :
    progress.required_filled === progress.required_total ? "done" :
      collapsed ? "incomplete-collapsed" : "in-progress";

const video = () => $("#video-form");
const field = name => video()?.elements[name];
const songReady = () => Boolean(state.formFiles.get(video())?.song) && !state.formFiles.get(video())?.pending;
const referenceReady = () => Boolean(state.formFiles.get(video())?.references?.length);
const castReady = () => Boolean(field("actors")?.selectedOptions?.length);
const needsReference = () => Number(state.catalog?.backends?.[field("backend")?.value]?.min_reference_images || 0) > 0;
const assignedPlayer = () => {
  if (field("instrument_mode")?.value !== "perform") return true;
  try {
    const assigned = JSON.parse(field("instrument_assignments_json")?.value || "{}");
    return Object.keys(assigned).some(id => [...field("actors").selectedOptions].some(option => option.value === id));
  } catch { return false; }
};

const valueChanged = control => {
  if (control.type === "hidden" || control.type === "button" || control.disabled) return false;
  if (control.type === "file") {
    if (control.classList.contains("refs-input")) return referenceReady();
    return Boolean(control.files?.length);
  }
  if (control.type === "checkbox" || control.type === "radio") return control.checked !== control.defaultChecked;
  if (control.tagName === "SELECT") {
    if (control.name === "backend") return control.value !== defaultBackend;
    if (control.multiple) return [...control.options].some(option => option.selected !== option.defaultSelected);
    return control.value !== ([...control.options].find(option => option.defaultSelected)?.value ?? control.options[0]?.value);
  }
  return control.value !== control.defaultValue;
};

const groupChanged = group => [...group.querySelectorAll("input, select, textarea")].some(valueChanged);
const groups = unit => [...unit.body.children].filter(node => node.querySelector("input, select, textarea"));
const requiredNeeds = id => {
  if (id === "card-track-direction") return [
    { label: "Audio track (upload music)", met: songReady() },
    { label: "Visual direction", met: Boolean(field("direction")?.value.trim()) && field("direction").checkValidity() }
  ];
  if (id === "card-cast-staging") {
    const required = [];
    if (needsReference()) required.push({ label: "Cast actor or reference image", met: castReady() || referenceReady() });
    if (field("instrument_mode")?.value === "perform") required.push({ label: "Assigned instrument player", met: assignedPlayer() });
    return required;
  }
  if (id === "director-camera" && needsReference()) return [
    { label: "Reference policy: Use all references", met: field("ref_policy")?.value === "all" }
  ];
  return [];
};

function progressFor(unit) {
  if (unit.id === "director-control-room") return panelProgress([], []);
  const required = requiredNeeds(unit.id).map(need => need.met);
  const requiredGroups = unit.requiredGroups;
  const optional = groups(unit).filter(group => !requiredGroups.has(group));
  return panelProgress(required, optional.map(groupChanged));
}

function cueFor(unit, progress) {
  if (unit.id === "director-control-room") {
    const folds = units.filter(other => FOLD_ID_SET.has(other.id));
    return `${folds.filter(other => other.reviewed).length} of 4 reviewed`;
  }
  const status = panelState(progress, !unit.open, unit.reviewed);
  if (status === "done") return "✓ Done";
  if (status === "reviewed") return "✓ Reviewed";
  if (!progress.required_total) return "Optional";
  return `Needs ${progress.required_total - progress.required_filled}`;
}

function tintFor(unit, progress) {
  if (unit.id === "director-control-room") {
    const folds = units.filter(other => FOLD_ID_SET.has(other.id));
    return folds.length ? folds.reduce((sum, other) => sum + tintFor(other, progressFor(other)), 0) / folds.length : 0;
  }
  return progress.required_total ? progress.required_filled / progress.required_total :
    progress.optional_total ? progress.optional_changed / progress.optional_total : 0;
}

function paint(unit) {
  const progress = progressFor(unit);
  const status = panelState(progress, !unit.open, unit.reviewed);
  const cue = cueFor(unit, progress);
  unit.element.dataset.progressState = status;
  const fraction = tintFor(unit, progress);
  const required = progress.required_total > 0;
  unit.element.style.setProperty("--progress-mix", `${Math.round(fraction * (required ? 100 : 25))}%`);
  unit.element.style.setProperty("--progress-mix-dark", `${Math.round(fraction * (required ? 30 : 8))}%`);
  if (unit.cue.textContent !== cue) unit.cue.textContent = cue;
  const missing = requiredNeeds(unit.id).filter(need => !need.met).map(need => need.label);
  const missingSet = new Set(missing);
  if (missing.length) {
    const detail = `Needs:\n• ${missing.join("\n• ")}`;
    if (unit.cue.dataset.tooltip !== detail) unit.cue.dataset.tooltip = detail;
    unit.cue.tabIndex = 0;
    unit.cue.setAttribute("aria-label", `Needs: ${missing.join("; ")}`);
  } else {
    unit.cue.removeAttribute("data-tooltip");
    unit.cue.removeAttribute("tabindex");
    unit.cue.removeAttribute("aria-label");
  }

  // Highlight individual needed labels
  if (unit.id === "card-track-direction") {
    const songGroup = unit.body.querySelector(".song-input")?.closest("label");
    const dirGroup = unit.body.querySelector('[name="direction"]')?.closest("label");
    if (songGroup) songGroup.classList.toggle("field-needed", missingSet.has("Audio track (upload music)"));
    if (dirGroup) dirGroup.classList.toggle("field-needed", missingSet.has("Visual direction"));
  } else if (unit.id === "card-cast-staging") {
    const castGroup = unit.body.querySelector(".cast-picker")?.closest("label") || unit.body.querySelector(".cast-picker");
    const refGroup = unit.body.querySelector(".refs-input")?.closest("label");
    const needsRef = missingSet.has("Cast actor or reference image");
    if (castGroup) castGroup.classList.toggle("field-needed", needsRef);
    if (refGroup) refGroup.classList.toggle("field-needed", needsRef);
    const players = unit.body.querySelector(".instrument-assignments");
    if (players) players.classList.toggle("field-needed", missingSet.has("Assigned instrument player"));
  } else if (unit.id === "director-camera") {
    const refPolicyGroup = unit.body.querySelector('[name="ref_policy"]')?.closest("label");
    if (refPolicyGroup) refPolicyGroup.classList.toggle("field-needed", missingSet.has("Reference policy: Use all references"));
  }

  unit.toggle?.setAttribute("aria-expanded", String(unit.open));
  if (unit.body && !unit.details) unit.body.hidden = !unit.open;
  if (unit.options) unit.options.hidden = status !== "done" || unit.open;
  if (unit.partial) {
    for (const group of groups(unit)) {
      if (!Object.hasOwn(group.dataset, "progressWasHidden")) {
        group.dataset.progressWasHidden = group.hidden ? "1" : "0";
        group.dataset.progressReveal = !unit.requiredGroups.has(group) && !groupChanged(group) && !group.hidden ? "1" : "0";
      }
      group.hidden = group.dataset.progressReveal !== "1";
    }
  } else {
    for (const group of groups(unit)) {
      if (Object.hasOwn(group.dataset, "progressWasHidden")) {
        group.hidden = group.dataset.progressWasHidden === "1";
        group.removeAttribute("data-progress-was-hidden");
        group.removeAttribute("data-progress-reveal");
      }
    }
  }
  return progress;
}

export function refreshPanelProgress() { units.forEach(paint); }
export function setPanelAutoCollapse(value) { autoCollapse = Boolean(value); }

export function panelProgressSnapshot() {
  return {
    details_sections: Object.fromEntries(units.filter(unit => !unit.details).map(unit => [unit.id, unit.open])),
    details_reviewed: Object.fromEntries(units.filter(unit => unit.reviewed).map(unit => [unit.id, true])),
    details_partial: Object.fromEntries(units.filter(unit => unit.partial).map(unit => [unit.id, true]))
  };
}

export function restorePanelProgress(project) {
  saved = {
    sections: project?.details_sections || {},
    reviewed: project?.details_reviewed || {},
    partial: project?.details_partial || {}
  };
  if (!units.length) return;
  for (const unit of units) {
    if (!unit.details && unit.id in saved.sections) unit.open = Boolean(saved.sections[unit.id]);
    unit.reviewed = Boolean(saved.reviewed[unit.id]);
    unit.partial = Boolean(saved.partial[unit.id]);
    unit.blurred = false;
    const progress = progressFor(unit);
    unit.userOpened = Boolean(unit.open && progress.required_total && progress.required_filled === progress.required_total);
  }
  refreshPanelProgress();
}

export function resetPanelProgress() {
  for (const unit of units) {
    unit.reviewed = false;
    unit.partial = false;
    unit.open = true;
    unit.userOpened = false;
    unit.blurred = false;
    if (unit.details) {
      const target = unit.id === "director-format";
      unit.ignoreNextToggle = unit.element.open !== target;
      unit.visited = false;
      unit.element.open = target;
    }
  }
  saved = {};
  refreshPanelProgress();
  save();
}

export function showPanelForQuoteError(message) {
  const error = String(message || "").toLowerCase();
  const id = /reference policy|reference in every passage/.test(error) ? "director-camera" :
    /reference|actor|cast|instrument/.test(error) ? "card-cast-staging" :
      /song|audio|direction/.test(error) ? "card-track-direction" : null;
  const unit = units.find(item => item.id === id);
  if (!unit) return;
  if (unit.details) {
    const parent = units.find(item => item.id === "director-control-room");
    parent.open = true;
    parent.partial = false;
  }
  unit.open = true;
  unit.userOpened = true;
  unit.partial = false;
  refreshPanelProgress();
  save();
  unit.element.scrollIntoView({ behavior: "smooth", block: "start" });
}

function makeCard(element, id) {
  const title = element.querySelector(":scope > .card-title");
  const body = document.createElement("div");
  body.className = "progress-body";
  for (const child of [...element.children].filter(child => child !== title)) body.append(child);
  element.append(body);
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "progress-toggle";
  toggle.setAttribute("aria-controls", id + "-body");
  while (title.firstChild) toggle.append(title.firstChild);
  const cue = document.createElement("span");
  cue.className = "progress-cue";
  toggle.append(cue);
  cue.setAttribute("aria-live", "polite");
  title.append(toggle);
  body.id = id + "-body";
  const options = document.createElement("button");
  options.type = "button";
  options.className = "progress-options";
  options.textContent = "Options available";
  options.hidden = true;
  title.append(options);
  return { element, id, body, toggle, cue, options, details: false, open: true, reviewed: false, partial: false, requiredGroups: new Set() };
}

function makeFold(element) {
  const summary = element.querySelector(":scope > summary");
  const wrapper = document.createElement("div");
  wrapper.className = "progress-fold-wrap";
  element.before(wrapper);
  wrapper.append(element);
  const cue = document.createElement("span");
  cue.className = "progress-cue";
  cue.setAttribute("aria-live", "polite");
  summary.append(cue);
  const options = document.createElement("button");
  options.type = "button";
  options.className = "progress-options";
  options.textContent = "Options available";
  options.hidden = true;
  wrapper.append(options);
  return { element, id: element.id, body: element.querySelector(":scope > .fold-content"), cue, options,
    details: true, get open() { return element.open; }, set open(value) { element.open = value; },
    reviewed: false, partial: false, requiredGroups: new Set() };
}

export function initPanelProgress(settings, scheduleSave) {
  const form = video();
  if (!form) return;
  save = scheduleSave;
  setPanelAutoCollapse(settings.auto_collapse_panels !== false);
  defaultBackend = settings.backend || "local_h3";
  units = CARD_IDS.map(id => makeCard(form.querySelector(`[data-component-id="${id}"]`), id))
    .concat(FOLD_IDS.map(id => makeFold($("#" + id))));
  const requiredGroup = (id, selector) => {
    const unit = units.find(item => item.id === id);
    const control = unit.body.querySelector(selector);
    const group = [...unit.body.children].find(child => child.contains(control));
    if (group) unit.requiredGroups.add(group);
  };
  requiredGroup("card-track-direction", ".song-input");
  requiredGroup("card-track-direction", '[name="direction"]');
  requiredGroup("card-cast-staging", ".actor-select");
  requiredGroup("card-cast-staging", ".refs-input");
  requiredGroup("card-cast-staging", '[name="instrument_mode"]');
  requiredGroup("director-camera", '[name="ref_policy"]');

  for (const unit of units) {
    if (unit.id in saved.sections && !unit.details) unit.open = Boolean(saved.sections[unit.id]);
    unit.reviewed = Boolean(saved.reviewed?.[unit.id]);
    unit.partial = Boolean(saved.partial?.[unit.id]);
    const initialProgress = progressFor(unit);
    unit.userOpened = Boolean(unit.open && initialProgress.required_total && initialProgress.required_filled === initialProgress.required_total);
    if (unit.details) {
      unit.element.querySelector(":scope > summary").addEventListener("click", () => { unit.visited = true; });
      unit.element.addEventListener("toggle", () => {
        if (unit.ignoreNextToggle) { unit.ignoreNextToggle = false; return; }
        if (!unit.open && unit.visited) unit.reviewed = true;
        if (unit.visited) unit.userOpened = unit.open;
        unit.partial = false;
        refreshPanelProgress();
        save();
      });
    } else {
      unit.toggle.addEventListener("click", () => {
        unit.open = !unit.open;
        unit.userOpened = unit.open;
        unit.partial = false;
        unit.blurred = false;
        if (!unit.open && !requiredNeeds(unit.id).length) unit.reviewed = true;
        refreshPanelProgress();
        save();
      });
    }
    unit.options.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      unit.open = true;
      unit.userOpened = true;
      unit.partial = true;
      refreshPanelProgress();
      save();
    });
  }
  form.addEventListener("input", refreshPanelProgress);
  form.addEventListener("change", refreshPanelProgress);
  form.addEventListener("focusin", event => {
    for (const unit of units) if (unit.element.contains(event.target)) unit.blurred = false;
  });
  form.addEventListener("focusout", event => {
    const unit = units.find(item => item.details && item.element.contains(event.target)) ||
      units.find(item => item.element.contains(event.target) && item.id !== "director-control-room");
    if (!unit) return;
    const requiredControl = unit.id === "card-track-direction" ?
      event.target.matches('.song-input, [name="direction"]') :
      unit.id === "card-cast-staging" ?
        Boolean(event.target.closest('.cast-checkbox-list, .instrument-assignments')) ||
          event.target.matches('.refs-input, [name="instrument_mode"]') :
        unit.id === "director-camera" && event.target.matches('[name="ref_policy"]');
    if (!requiredControl) return;
    setTimeout(() => {
      if (unit.element.contains(document.activeElement)) return;
      unit.blurred = true;
      if (!autoCollapse || unit.userOpened) return;
      const progress = progressFor(unit);
      if (progress.required_total && progress.required_filled === progress.required_total && unit.open) {
        unit.open = false;
        refreshPanelProgress();
        save();
      }
    }, 0);
  });
  new MutationObserver(() => {
    refreshPanelProgress();
    const first = units[0];
    const progress = progressFor(first);
    if (autoCollapse && !first.userOpened && first.blurred && first.open && songReady() &&
        progress.required_filled === progress.required_total) {
      first.open = false;
      refreshPanelProgress();
      save();
    }
  }).observe(form.querySelector(".song-receipt"), { childList: true, subtree: true });
  refreshPanelProgress();
}
