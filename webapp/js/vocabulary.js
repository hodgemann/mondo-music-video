// Visual Vocabulary Customizer — Functional HTML Templates & Delegated UI Controller.

import { $, $$, api, handle, json, notice, option, state } from "./core.js";
import { scheduleSave } from "./project.js";
import {
  cleanDraft,
  cloneDraft,
  getCategoryStats,
  getSummaryStats,
  presetToDraft,
  withCustomLines,
  withoutCategoryItem,
  withToggledBuiltinItem
} from "./vocab-model.js";

let vocabDataCache = null;
let vocabActiveCategory = "settings";
let vocabWorkingDraft = {};

const MAX_SUMMARY_CHIPS = 20;

// --- Pure HTML Template Builders (Option A) ---

const escapeHtml = (s = "") =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const formatCatLabel = (cat = "") => cat.replace(/_/g, " ");

export const VOCAB_CATEGORY_TOOLTIPS = {
  settings:
    "Physical environment and location. In prompt generation, sets the scene space for the shot (shot.vocab.setting); stays continuous across standard passages or rotates per cut in multi-scene montage.",
  lighting:
    "Cinematic light sources, direction, and color temperature. In prompt generation, tells the writer how the scene is illuminated (shot.vocab.lighting), shifting dynamically with musical energy.",
  mechanisms:
    "Dynamic physical actions, object interactions, and mechanical processes. In prompt generation, injects kinetic movement into the shot (shot.vocab.mechanism) and acts as the unifying thematic anchor across cuts.",
  subject_types:
    "Character archetypes and contextual roles. In prompt generation, guides who or what appears on screen (shot.vocab.subject_type) when no specific cast actor is assigned.",
  tonal_registers:
    "Cinematic mood, color grading, and emotional atmosphere. In prompt generation, guides the writer's descriptive tone and aesthetic tension (shot.vocab.tonal_register).",
  costume:
    "Wardrobe styling, fabrics, and silhouettes. In prompt generation, specifies character clothing textures (shot.vocab.costume) unless locked by an actor's OAP rider.",
  practical_effects:
    "In-camera physical stage effects (smoke, haze, rain, sparks, prisms). In prompt generation, sampled once per musical passage (segment.practical_effects) to give the scene tangible atmosphere.",
  footage_anchors:
    "Base film stock, camera format, and optical texture (e.g. 35mm anamorphic, 16mm reversal, VHS). In prompt generation, anchors the physical image medium for the entire segment.",
  camera_by_energy:
    "Camera motion verbs (track, push in, arc, static, whip). In prompt generation, dynamically selected by the song's energy level at the exact downbeat of each cut.",
  shot_scales:
    "Framing distance (extreme wide to macro). In prompt generation, chosen by musical intensity: wide establishing shots during low energy, tightening to intimate close-ups at peak energy.",
  rigging:
    "Facial movement suppression instructions ('lips firmly sealed shut'). In prompt generation, enforces sealed-lip realism when silent mouths is active to eliminate AI babble.",
  themes:
    "Abstract thematic domain or conceptual world. In prompt generation, groups related locations, objects, and actions to preserve thematic continuity across cuts."
};

const tabsHtml = (categories, activeCat, catalog, draft) =>
  categories
    .map((cat) => {
      const { count, isModified } = getCategoryStats(catalog, draft, cat);
      const escCat = escapeHtml(cat);
      const active = cat === activeCat ? " active" : "";
      const weight = isModified ? "700" : "600";
      const tooltip =
        VOCAB_CATEGORY_TOOLTIPS[cat] ||
        `Visual vocabulary pool for ${formatCatLabel(cat)}. Sampled by the montage planner to provide concrete variety for the prompt writer.`;
      const escTip = escapeHtml(tooltip);
      return `<button type="button" class="vocab-tab-btn${active}" data-category="${escCat}" data-tooltip="${escTip}" data-tooltip-position="top" title="${escTip}" style="font-weight:${weight}">${escapeHtml(formatCatLabel(cat))}<span class="vocab-tab-badge">${count}</span></button>`;
    })
    .join("");

const checkboxGridHtml = (baseItems, excludedSet) =>
  baseItems
    .map((item) => {
      const esc = escapeHtml(item);
      const checked = excludedSet.has(item) ? "" : " checked";
      return `<label class="vocab-item-label" title="${esc}"><input type="checkbox" value="${esc}"${checked}>${esc}</label>`;
    })
    .join("");

const chipsHtml = (cat, activeItems) => {
  if (!activeItems.length) {
    return `<div class="vocab-summary-chips"><span class="vocab-chip-empty">No active items</span></div>`;
  }
  const escCat = escapeHtml(cat);
  const itemsHtml = activeItems
    .slice(0, MAX_SUMMARY_CHIPS)
    .map((item) => {
      const esc = escapeHtml(item);
      return `<span class="vocab-chip"><span class="vocab-chip-text">${esc}</span><button type="button" class="vocab-chip-remove" data-action="remove-chip" data-category="${escCat}" data-item="${esc}" aria-label="Remove ${esc}">×</button></span>`;
    })
    .join("");
  const moreHtml =
    activeItems.length > MAX_SUMMARY_CHIPS
      ? `<button type="button" class="vocab-chip-more" data-action="select-cat" data-category="${escCat}" aria-label="Show all entries in ${escapeHtml(cat.replace(/_/g, " "))}">+${activeItems.length - MAX_SUMMARY_CHIPS} more (open tab)</button>`
      : "";
  return `<div class="vocab-summary-chips">${itemsHtml}${moreHtml}</div>`;
};

const summaryCardHtml = (cat, activeItems) => {
  const escCat = escapeHtml(cat);
  return `<div class="vocab-summary-cat-card" data-category="${escCat}">
    <div class="vocab-summary-cat-header" data-action="select-cat" data-category="${escCat}">
      <div class="vocab-summary-cat-title-wrap">
        <span class="vocab-summary-cat-name">${escapeHtml(formatCatLabel(cat))}</span>
        <span class="vocab-summary-cat-count">${activeItems.length} active</span>
      </div>
    </div>
    ${chipsHtml(cat, activeItems)}
  </div>`;
};

// --- DOM Sync & Render Functions ---

const copyToClipboard = (text) => {
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).catch(() => {});
};

export function updateVocabCustomBadge() {
  const badge = $("#vocab-custom-badge");
  const customCount = Object.keys(state.currentCustomVocab || {}).length;
  const worlds = state.thematicWorlds;

  if (badge) {
    if (worlds && worlds.mode && worlds.mode !== "off") {
      const modeLabel = worlds.mode.charAt(0).toUpperCase() + worlds.mode.slice(1);
      const mult = (2 * ((worlds.slider ?? 50) / 100)).toFixed(1);
      badge.textContent = `🧭 Worlds: ${modeLabel} (x${mult})`;
      badge.title = `Thematic Worlds active: ${modeLabel} mode, juxtaposition x${mult}`;
      badge.hidden = false;
    } else {
      badge.textContent = `${customCount} customized`;
      badge.title = `${customCount} categories customized`;
      badge.hidden = customCount === 0;
    }
  }
}

export async function loadVocabularyCatalog(force = false) {
  if (!vocabDataCache || force) {
    vocabDataCache = await (await api("/api/vocabulary")).json();
    populateVocabProfileSelects();
  }
  return vocabDataCache;
}

export function populateVocabProfileSelects() {
  if (!vocabDataCache) return;
  const presets = (vocabDataCache.vocabularies || []).map((p) => [
    p.id,
    `${p.name}${p.acts && p.acts.length ? ` [${p.acts.length} Acts]` : ""} (${p.id})`
  ]);
  const entries = [
    ["full", "Full vocabulary (current default)"],
    ["reduced_flashing", "Reduced flash/strobe cues"],
    ...presets
  ];

  ["#vocab-profile-select", "#vocab-dialog-preset-select"].forEach((sel) => {
    const el = $(sel);
    if (!el) return;
    const prev = el.value || "full";
    el.replaceChildren(...entries.map(([val, label]) => option(val, label)));
    if (entries.some(([val]) => val === prev)) el.value = prev;
  });
}

export function updateDeletePresetBtnVisibility() {
  const deleteBtn = $("#vocab-delete-preset-btn");
  const selected = $("#vocab-dialog-preset-select")?.value;
  if (deleteBtn) {
    deleteBtn.style.display =
      selected && selected !== "full" && selected !== "reduced_flashing" ? "inline" : "none";
  }
}

const applySummaryBadgeStyle = (totalActive, customizedCats) => {
  const badge = $("#vocab-random-status-badge");
  if (!badge) return;
  if (customizedCats > 0) {
    badge.textContent = `${customizedCats} categories customized (${totalActive} active)`;
    badge.style.color = "var(--green)";
  } else {
    badge.textContent = `All built-in (${totalActive} active)`;
    badge.style.color = "var(--muted)";
  }
};

function updateVocabSummaryBadge() {
  if (!vocabDataCache) return;
  const { totalActive, customizedCats } = getSummaryStats(vocabDataCache, vocabWorkingDraft);
  applySummaryBadgeStyle(totalActive, customizedCats);
}

export function renderVocabSelectionSummary(force = false) {
  const grid = $("#vocab-random-summary-grid");
  if (!grid || !vocabDataCache) return;
  const details = $("#vocab-random-summary-details");
  if (!force && details && !details.open) {
    updateVocabSummaryBadge();
    return;
  }
  const { categories, byCategory, totalActive, customizedCats } = getSummaryStats(
    vocabDataCache,
    vocabWorkingDraft
  );
  grid.innerHTML = categories
    .map((cat) => summaryCardHtml(cat, byCategory[cat].activeItems))
    .join("");
  applySummaryBadgeStyle(totalActive, customizedCats);
}

export function updateVocabCategoryCard(cat) {
  const card = $(`#vocab-random-summary-grid .vocab-summary-cat-card[data-category="${cat}"]`);
  if (!card || !vocabDataCache) {
    renderVocabSelectionSummary();
    return;
  }
  const { activeItems, count } = getCategoryStats(vocabDataCache, vocabWorkingDraft, cat);
  const countBadge = card.querySelector(".vocab-summary-cat-count");
  if (countBadge) countBadge.textContent = `${count} active`;
  const oldChips = card.querySelector(".vocab-summary-chips");
  if (oldChips) oldChips.outerHTML = chipsHtml(cat, activeItems);
  updateVocabSummaryBadge();
}

export function renderVocabTabs() {
  const container = $("#vocab-category-tabs");
  if (!container || !vocabDataCache) return;
  const categories = vocabDataCache.categories || [];
  container.innerHTML = tabsHtml(categories, vocabActiveCategory, vocabDataCache, vocabWorkingDraft);
}

export function updateTabBadges() {
  if (!vocabDataCache) return;
  $$(".vocab-tab-btn").forEach((btn) => {
    const { count, isModified } = getCategoryStats(
      vocabDataCache,
      vocabWorkingDraft,
      btn.dataset.category
    );
    const badge = btn.querySelector(".vocab-tab-badge");
    if (badge) badge.textContent = count;
    btn.style.fontWeight = isModified ? "700" : "600";
  });
}

export function updateActiveCategoryCount() {
  if (!vocabDataCache) return;
  const { count } = getCategoryStats(vocabDataCache, vocabWorkingDraft, vocabActiveCategory);
  const badge = $("#vocab-active-count-badge");
  if (badge) {
    badge.textContent = `${count} active`;
    badge.style.color = count === 0 ? "var(--muted)" : "var(--green)";
  }
}

export function renderVocabCategoryContent(cat) {
  if (!vocabDataCache) return;
  const titleEl = $("#vocab-active-category-title");
  if (titleEl) titleEl.textContent = formatCatLabel(cat).toUpperCase();

  const override = vocabWorkingDraft[cat] || { mode: "append", add: [], exclude: [] };
  const modeSelect = $("#vocab-category-mode");
  if (modeSelect) modeSelect.value = override.mode || "append";

  const builtinSection = $("#vocab-builtin-section");
  if (builtinSection) builtinSection.hidden = override.mode === "replace";

  const grid = $("#vocab-checkbox-grid");
  if (grid) {
    const baseItems = vocabDataCache.base?.[cat] || [];
    const excludedSet = new Set(override.exclude || []);
    grid.innerHTML = checkboxGridHtml(baseItems, excludedSet);
  }

  const textarea = $("#vocab-custom-textarea");
  if (textarea) textarea.value = (override.add || []).join("\n");

  const searchInput = $("#vocab-search-input");
  if (searchInput) searchInput.value = "";
  updateActiveCategoryCount();
}

export function showVocabCategory(cat) {
  vocabActiveCategory = cat;
  $$(".vocab-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.category === cat));
  renderVocabCategoryContent(cat);
}

export function selectVocabCategory(cat) {
  saveActiveCategoryCustomText();
  showVocabCategory(cat);
}

export function saveActiveCategoryCustomText() {
  const textarea = $("#vocab-custom-textarea");
  if (!textarea || !vocabDataCache) return;
  const mode = $("#vocab-category-mode")?.value || "append";
  vocabWorkingDraft = withCustomLines(vocabWorkingDraft, vocabActiveCategory, textarea.value, mode);
}

export function cleanWorkingDraft() {
  vocabWorkingDraft = cleanDraft(vocabWorkingDraft);
}

export function filterCheckboxGrid(term) {
  const grid = $("#vocab-checkbox-grid");
  if (!grid) return;
  const q = (term || "").toLowerCase().trim();
  grid.querySelectorAll(".vocab-item-label").forEach((label) => {
    label.style.display = !q || label.textContent.toLowerCase().includes(q) ? "flex" : "none";
  });
}

// --- Category Item Mutations ---

const refreshCategoryUI = (cat, fullSummary = false) => {
  if (vocabActiveCategory === cat) renderVocabCategoryContent(cat);
  updateTabBadges();
  if (fullSummary) renderVocabSelectionSummary();
  else updateVocabCategoryCard(cat);
};

export function removeSingleItemFromCategory(cat, item) {
  const { draft, removed, minReached } = withoutCategoryItem(vocabDataCache, vocabWorkingDraft, cat, item);
  if (minReached) {
    notice("Each category must keep at least 1 active entry.");
    return;
  }
  if (removed) {
    vocabWorkingDraft = draft;
    refreshCategoryUI(cat, false);
  }
}

// --- Panel / Dialog Lifecycle ---

const refreshEditorAll = () => {
  renderVocabTabs();
  showVocabCategory(vocabActiveCategory);
  renderVocabSelectionSummary();
};

export async function openVocabularyPanel() {
  await loadVocabularyCatalog();
  vocabWorkingDraft = cloneDraft(state.currentCustomVocab || {});
  const currentProfile = $("#vocab-profile-select")?.value || "full";
  if ($("#vocab-dialog-preset-select")) $("#vocab-dialog-preset-select").value = currentProfile;
  updateDeletePresetBtnVisibility();
  renderVocabTabs();
  showVocabCategory(vocabActiveCategory);

  const summaryDetails = $("#vocab-random-summary-details");
  if (summaryDetails?.open) renderVocabSelectionSummary();
  else updateVocabSummaryBadge();

  const panelVocab = $("#panel-vocab");
  if (panelVocab) {
    if (panelVocab.hidden) {
      $$(".panel").forEach((node) => (node.hidden = node.id !== "panel-vocab"));
      $$(".nav[data-panel]").forEach((node) => {
        const active = node.dataset.panel === "vocab";
        node.classList.toggle("active", active);
        node.setAttribute("aria-current", active ? "page" : "false");
      });
      scheduleSave();
    }
  } else {
    $("#vocabulary-dialog")?.showModal?.();
  }
}

// --- Delegated Listeners & Declarative Action Wiring ---

export function setupVocabularyCustomizer() {
  if (!$("#panel-vocab") && !$("#vocabulary-dialog")) return;
  loadVocabularyCatalog().catch(() => {});

  // 1. Single delegated click handler for Category Tabs
  $("#vocab-category-tabs")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".vocab-tab-btn[data-category]");
    if (btn) selectVocabCategory(btn.dataset.category);
  });

  // 2. Single delegated change handler for Built-in Checkboxes
  $("#vocab-checkbox-grid")?.addEventListener("change", (e) => {
    const cb = e.target;
    if (cb?.type !== "checkbox") return;
    const mode = $("#vocab-category-mode")?.value || "append";
    vocabWorkingDraft = withToggledBuiltinItem(
      vocabWorkingDraft,
      vocabActiveCategory,
      cb.value,
      cb.checked,
      mode
    );
    updateActiveCategoryCount();
    updateTabBadges();
    updateVocabCategoryCard(vocabActiveCategory);
  });

  // 3. Single delegated click handler for Summary Cards & Chips
  $("#vocab-random-summary-grid")?.addEventListener("click", (e) => {
    const actionEl = e.target.closest("[data-action]");
    if (!actionEl) return;
    const { action, category, item } = actionEl.dataset;
    if (action === "remove-chip") removeSingleItemFromCategory(category, item);
    else if (action === "select-cat") selectVocabCategory(category);
  });

  // 4. Summary drawer lazy render on open
  $("#vocab-random-summary-details")?.addEventListener("toggle", (e) => {
    if (e.currentTarget.open) renderVocabSelectionSummary(true);
  });

  // 5. Textarea, Mode & Filter inputs
  const textarea = $("#vocab-custom-textarea");
  if (textarea) {
    textarea.oninput = () => {
      saveActiveCategoryCustomText();
      updateActiveCategoryCount();
      updateTabBadges();
      updateVocabCategoryCard(vocabActiveCategory);
    };
  }

  const modeSelect = $("#vocab-category-mode");
  if (modeSelect) {
    modeSelect.onchange = () => {
      saveActiveCategoryCustomText();
      const cat = vocabActiveCategory;
      vocabWorkingDraft[cat] = {
        ...(vocabWorkingDraft[cat] || { add: [], exclude: [] }),
        mode: modeSelect.value
      };
      refreshCategoryUI(cat, true);
    };
  }

  const searchInput = $("#vocab-search-input");
  if (searchInput) searchInput.oninput = () => filterCheckboxGrid(searchInput.value);

  const dialogSelect = $("#vocab-dialog-preset-select");
  if (dialogSelect) dialogSelect.onchange = updateDeletePresetBtnVisibility;

  // 6. Declarative Button Action Map
  const actions = {
    "#open-vocab-panel-btn, #open-vocab-dialog": handle(() => openVocabularyPanel()),

    "#vocab-load-preset-btn": handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      vocabWorkingDraft = presetToDraft(vocabDataCache, selectedId);
      refreshEditorAll();
      notice(`Loaded preset "${selectedId}" into editor.`);
    }),

    "#vocab-delete-preset-btn": handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      if (!window.confirm(`Delete vocabulary preset "${selectedId}" from this machine?`)) return;
      await api(`/api/vocabularies/${encodeURIComponent(selectedId)}`, { method: "DELETE" });
      await loadVocabularyCatalog(true);
      notice("Vocabulary preset deleted.");
      selectVocabCategory(vocabActiveCategory);
      renderVocabSelectionSummary();
    }),

    "#vocab-select-all-btn": () => {
      const cat = vocabActiveCategory;
      if (vocabWorkingDraft[cat]) vocabWorkingDraft[cat].exclude = [];
      $$("#vocab-checkbox-grid input[type=checkbox]").forEach((cb) => (cb.checked = true));
      updateActiveCategoryCount();
      updateTabBadges();
      renderVocabSelectionSummary();
    },

    "#vocab-clear-all-btn": () => {
      const cat = vocabActiveCategory;
      const baseItems = vocabDataCache?.base?.[cat] || [];
      vocabWorkingDraft[cat] = {
        mode: vocabWorkingDraft[cat]?.mode || "append",
        add: [...(vocabWorkingDraft[cat]?.add || [])],
        exclude: [...baseItems]
      };
      $$("#vocab-checkbox-grid input[type=checkbox]").forEach((cb) => (cb.checked = false));
      updateActiveCategoryCount();
      updateTabBadges();
      renderVocabSelectionSummary();
    },

    "#vocab-reset-cat-btn": () => {
      const cat = vocabActiveCategory;
      delete vocabWorkingDraft[cat];
      refreshCategoryUI(cat, true);
      notice(`Category "${cat}" reset to default.`);
    },

    "#vocab-apply-btn": handle(() => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      state.currentCustomVocab = cloneDraft(vocabWorkingDraft);
      updateVocabCustomBadge();
      scheduleSave();
      const dialog = $("#vocabulary-dialog");
      if (dialog?.open) dialog.close?.();
      const videoNavBtn = $(".nav[data-panel='video']");
      if (videoNavBtn && $("#panel-vocab") && !$("#panel-vocab").hidden) videoNavBtn.click();
      notice("Vocabulary customizations applied to current video.");
    }),

    "#vocab-reset-all-btn": () => {
      if (!window.confirm("Reset all vocabulary customizations back to standard?")) return;
      vocabWorkingDraft = {};
      refreshEditorAll();
      notice("All category customizations cleared.");
    },

    "#vocab-save-preset-btn": handle(async () => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      const presetId = ($("#vocab-preset-id")?.value || "").trim().toLowerCase();
      const presetName = ($("#vocab-preset-name")?.value || "").trim();
      if (!presetId) throw new Error("Enter a preset ID (lowercase letters, numbers, hyphens)");
      if (!presetName) throw new Error("Enter a display name for this preset");
      await json("/api/vocabularies", {
        id: presetId,
        name: presetName,
        base_profile: "full",
        tables: vocabWorkingDraft
      });
      await loadVocabularyCatalog(true);
      if ($("#vocab-profile-select")) $("#vocab-profile-select").value = presetId;
      notice(`Preset "${presetName}" saved!`);
      scheduleSave();
    })
  };

  for (const [selector, fn] of Object.entries(actions)) {
    $$(selector).forEach((el) => (el.onclick = fn));
  }
}
