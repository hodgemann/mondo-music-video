// Styles, Cast Actors, OAP package inspection/import, and Role Agreements.

import { $, $$, api, handle, json, notice, option, saveDownload, state, text, upload } from "./core.js";
import { scheduleSave } from "./project.js";
import { updateVocabCustomBadge } from "./vocabulary.js";

// --- Pure Helper & Formatting Functions ---

const escapeHtml = (s = "") =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export function actorOverview(actor) {
  const description = actor.description || "";
  const identity = description.match(
    /(?:^|\n)Identity:\s*([\s\S]*?)(?=\n(?:Hair|Makeup|Wardrobe|Footwear|Accessories|Expression Range|Detail Notes|Canonical Summary|Height):|$)/i
  );
  return identity ? identity[1].trim() : description;
}

export function shortDid(did) {
  return did && did.length > 34 ? did.slice(0, 22) + "…" + did.slice(-8) : did || "none";
}

// --- Pure HTML String Template Generators ---

// The GUI already names the style, so its card's own title line is not shown. The saved card keeps it.
export const styleCardDisplay = card => String(card || "").replace(/^\s*STYLE CARD:[^\n]*\n?/i, "");

const styleCardHtml = (style) => {
  const escId = escapeHtml(style.id);
  const escName = escapeHtml(style.name);
  const shownCard = styleCardDisplay(style.style_card);
  const styleCard = shownCard ? `<pre class="style-card-pre style-card-shown">${escapeHtml(shownCard)}</pre>` : "";
  const fullText = `
    <details class="style-card-fold">
      <summary class="style-card-fold-toggle" data-tooltip="Show or hide the full style text">Full style text</summary>
      <p class="style-full-text">${escapeHtml(style.direction)}</p>
    </details>
  `;
  return `
    <article class="card" data-id="${escId}" data-name="${escName}">
      <h2>${escName}</h2>
      ${styleCard}
      ${fullText}
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
        <button type="button" class="secondary" data-action="export-style" title="Download ${escName} style JSON">Download JSON</button>
        <button type="button" class="secondary" data-action="duplicate-style" title="Duplicate ${escName} style">Duplicate</button>
        <button type="button" class="quiet operation-action" data-action="delete-style" title="Delete ${escName} from this machine">Delete style</button>
      </div>
    </article>
  `;
};

const actorCardHtml = (actor) => {
  const escId = escapeHtml(actor.id);
  const escName = escapeHtml(actor.name);
  const overview = escapeHtml(actorOverview(actor));
  const oapNote = actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export";
  const auditionSection = actor.oap ? "" : `
    <label class="check audition-export" title="Only check this if the reference is a cleaned or watermarked take you are willing to share with casting directors">
      <input type="checkbox" class="audition-cleared-cb"> Reference is cleared for auditions
    </label>
    <button type="button" class="quiet audition-button" data-action="export-audition" title="Export a signed audition package for ${escName}; cast-only assets are left out">Export audition package</button>
  `;
  return `
    <article class="card" data-id="${escId}" data-name="${escName}">
      <img src="/api/actors/${encodeURIComponent(actor.id)}/reference" alt="${escName} reference" loading="lazy">
      <h2>${escName}</h2>
      <p class="actor-desc-text" ${actor.oap ? "" : 'data-tooltip="Double-click to edit visual description" title="Double-click to edit visual description"'}>${overview}</p>
      ${actor.oap ? "" : `<div class="actor-desc-actions"><button type="button" class="quiet actor-edit-btn" data-edit-description>Edit visual description</button><span class="actor-desc-count" data-tooltip="Visual description length">${(actor.description || "").length} chars</span></div>`}
      <p>${oapNote}</p>
      <button type="button" class="secondary" data-action="export-oap" title="Export signed OAP package for ${escName}">Export OAP package</button>
      ${auditionSection}
      <button type="button" class="quiet operation-action" data-action="delete-actor" title="Delete ${escName} from this machine">Delete actor</button>
    </article>
  `;
};

const agreementCardHtml = (agreement) => {
  const escId = escapeHtml(agreement.id);
  const escTitle = escapeHtml(agreement.title || agreement.id);
  if (agreement.damaged) {
    return `
      <article class="card" title="Role agreement ${escId}" data-id="${escId}">
        <span class="oap-badge-pill badge-invalid">Damaged record</span>
        <h3>${escId}</h3>
        <p>${escapeHtml(agreement.issues.join("; "))}</p>
      </article>
    `;
  }
  const status = agreement.complete ? ["Signed by both parties", "badge-valid"]
    : agreement.issues.length && agreement.signed.length ? ["Signature problem", "badge-invalid"]
    : agreement.signed.length ? [`Signed by ${agreement.signed.join(" and ")}; awaiting countersignature`, "badge-unsigned"]
    : ["Unsigned draft", "badge-unsigned"];
  const compensation = agreement.compensation || {};
  const issuesHtml = (agreement.issues.length && agreement.signed.length)
    ? `<p>${escapeHtml(agreement.issues.join("; "))}</p>`
    : "";
  const roles = ["director", ...(agreement.local_agent ? ["agent"] : [])].filter(role => !agreement.signed.includes(role));
  const signButtonsHtml = roles.map(role => `
    <button type="button" class="secondary operation-action" data-action="sign-agreement" data-role="${escapeHtml(role)}" data-title="${escTitle}" data-amount="${escapeHtml(String(compensation.amount || ''))}" data-currency="${escapeHtml(String(compensation.currency || ''))}" title="Sign this agreement with this studio's ${role} key">Sign as ${escapeHtml(role)}</button>
  `).join("");
  return `
    <article class="card" title="Role agreement ${escId}" data-id="${escId}">
      <span class="oap-badge-pill ${status[1]}">${escapeHtml(status[0])}</span>
      <h3>${escTitle}</h3>
      <p>${escapeHtml(agreement.character || "Role")} · actor ${escapeHtml(agreement.actor_id || "unknown")} · ${escapeHtml(String(compensation.amount || ""))} ${escapeHtml(String(compensation.currency || ""))}</p>
      <p title="${escapeHtml(agreement.agent_did || '')}">Agent ${escapeHtml(shortDid(agreement.agent_did))}${agreement.local_agent ? " (this studio)" : ""}</p>
      <p title="${escapeHtml(agreement.director_did || '')}">Director ${escapeHtml(shortDid(agreement.director_did))} (this studio)</p>
      ${issuesHtml}
      <div class="agreement-actions">
        ${signButtonsHtml}
        <button type="button" class="secondary" data-action="verify-agreement" title="Check both signatures and the exact manifest and casting call bindings">Verify</button>
        <button type="button" class="secondary" data-action="download-bundle" title="Zip of agreement.json, manifest.json and casting_call.json for the other party">Download bundle</button>
      </div>
    </article>
  `;
};

// --- DOM Population & Renderers ---

export const styleVocabularyOf = (styles, id) => {
  const vocabulary = styles.find((style) => style.id === id)?.vocabulary;
  return vocabulary && Object.keys(vocabulary).length ? vocabulary : null;
};

// Offer (never auto-apply) the selected style's own vocabulary on the video form.
export function refreshStyleVocabularyOffer(select) {
  const offer = select?.closest("form")?.querySelector(".style-vocab-offer");
  if (!offer) return;
  const vocabulary = styleVocabularyOf(state.styles || [], select.value);
  offer.hidden = !vocabulary;
  if (!vocabulary) return;
  const tables = Object.keys(vocabulary).map((key) => key.replaceAll("_", " ")).join(", ");
  const button = Object.assign(document.createElement("button"), {
    type: "button", className: "quiet", textContent: "Use this style's vocabulary",
    title: "Replace this video's custom vocabulary with the one saved in the style",
  });
  button.onclick = () => {
    state.currentCustomVocab = structuredClone(vocabulary);
    state.currentVocabRandomKey = "";
    updateVocabCustomBadge();
    scheduleSave();
    notice(`Applied the style's vocabulary (${tables}) to this video.`);
  };
  offer.replaceChildren(document.createTextNode(`This style carries its own vocabulary (${tables}). `), button);
}

export async function loadStyles() {
  const styles = await (await api("/api/styles")).json();
  state.styles = styles;
  $$(".style-select").forEach((select) => {
    const old = select.value;
    select.replaceChildren(...styles.map((style) => option(style.id, style.name, `${style.name} (${style.id})`)));
    if (!styles.length) {
      const empty = option("", "No styles yet — add one in Styles");
      empty.disabled = true;
      select.replaceChildren(empty);
    }
    if (styles.some((x) => x.id === old)) select.value = old;
    if (!select.dataset.vocabOffer) {
      select.dataset.vocabOffer = "1";
      select.addEventListener("change", () => refreshStyleVocabularyOffer(select));
    }
    refreshStyleVocabularyOffer(select);
  });

  const listEl = $("#style-list");
  if (!listEl) return;
  listEl.innerHTML = styles.map(styleCardHtml).join("");
}

export function syncCastPickerUi() {
  const container = $("#cast-checkbox-list");
  const select = document.querySelector(".actor-select");
  if (!container || !select) return;
  const selectedValues = new Set([...select.selectedOptions].map((opt) => opt.value));
  container.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.checked = selectedValues.has(cb.value);
    cb.closest(".cast-checkbox-item")?.classList.toggle("checked", cb.checked);
  });
}

function renderCastCheckboxes(actors, selectedValues = new Set()) {
  const container = $("#cast-checkbox-list");
  if (!container) return;
  if (!actors.length) {
    container.innerHTML = '<div class="cast-empty-note">No cast members yet — add in 03. Actors &amp; Props</div>';
    return;
  }
  container.innerHTML = actors
    .map((actor) => {
      const isChecked = selectedValues.has(actor.id);
      const refUrl = `/api/actors/${encodeURIComponent(actor.id)}/reference`;
      return `<label class="cast-checkbox-item ${isChecked ? "checked" : ""}" data-tooltip="Cast actor: ${escapeHtml(actor.name)} (${escapeHtml(actor.id)})" data-tooltip-image="${refUrl}" data-tooltip-position="right">
        <input type="checkbox" value="${escapeHtml(actor.id)}" ${isChecked ? "checked" : ""}>
        <span>${escapeHtml(actor.name)}</span>
      </label>`;
    })
    .join("");

  if (!container.dataset.bound) {
    container.dataset.bound = "true";
    container.addEventListener("change", (e) => {
      const cb = e.target.closest("input[type=checkbox]");
      if (!cb) return;
      cb.closest(".cast-checkbox-item")?.classList.toggle("checked", cb.checked);
      const select = document.querySelector(".actor-select");
      if (!select) return;
      [...select.options].forEach((opt) => {
        if (opt.value === cb.value) opt.selected = cb.checked;
      });
      select.dispatchEvent(new Event("change", { bubbles: true }));
      scheduleSave();
    });
  }
}

export async function loadActors() {
  const actors = await (await api("/api/actors")).json();
  state.actors = actors;
  $$(".actor-select").forEach((select) => {
    const old = [...select.selectedOptions].map((x) => x.value);
    if (!actors.length) {
      const emptyOpt = option("", "No cast members yet — add in 03. Actors & Props", "No cast members currently in your studio library");
      emptyOpt.disabled = true;
      select.replaceChildren(emptyOpt);
    } else {
      select.replaceChildren(
        ...actors.map((actor) => {
          const node = option(actor.id, actor.name, `Cast actor: ${actor.name} (${actor.id})`);
          node.selected = old.includes(actor.id);
          return node;
        })
      );
    }
    const selectVals = new Set([...select.selectedOptions].map((x) => x.value));
    renderCastCheckboxes(actors, selectVals);
  });

  const listEl = $("#actor-list");
  if (!listEl) return;
  if (!actors.length) {
    listEl.innerHTML = '<div class="empty" title="No actors currently in your studio library">Your cast starts here. Create an actor or import a full OAP package below.</div>';
  } else {
    listEl.innerHTML = actors.map(actorCardHtml).join("");
  }

  const agreementActor = $("#agreement-form")?.elements?.actor_id;
  if (agreementActor) {
    const chosen = agreementActor.value;
    agreementActor.replaceChildren(...actors.map((actor) => option(actor.id, actor.name)));
    if (actors.some((actor) => actor.id === chosen)) agreementActor.value = chosen;
  }
}

export async function loadAgreements() {
  const agreements = await (await api("/api/agreements")).json();
  const listEl = $("#agreement-list");
  if (!listEl) return;
  if (!agreements.length) {
    listEl.innerHTML = '<div class="empty">No role agreements yet. Draft one below.</div>';
  } else {
    listEl.innerHTML = agreements.map(agreementCardHtml).join("");
  }
}

export function renderOapReportCard(report, allowUnsigned) {
  const card = $("#oap-report-card");
  if (!card) return;
  const manifest = report.manifest || {};
  const verification = report.verification || {};
  const identity = manifest.identity || {};
  const rider = manifest.rider || {};
  const signed = Boolean(verification.signature_valid);
  const valid = Boolean(verification.ok);

  const displayName = identity.display_name || identity.actor_id || "Actor";
  const badgeText = signed && valid
    ? (verification.agent_known ? "Signature valid · known signer" : "Signature valid · signer not locally trusted")
    : (valid && allowUnsigned ? "Unsigned package · explicitly allowed" : "Verification warning");
  const badgeClass = signed && valid ? "badge-valid" : "badge-unsigned";

  const ratings = rider.content && typeof rider.content === "object"
    ? Object.entries(rider.content).map(([k, v]) => `${k}: ${v}`).join(", ")
    : "Not specified in package";

  const rows = [
    ["Actor ID", identity.actor_id || "Not specified"],
    ["Display name", identity.display_name || "Not specified"],
    ["Signing public key", signed ? (manifest.agent?.public_key || "Not supplied") : "Unsigned"],
    ["Visual identity", manifest.visual?.core_identity || "Not specified"],
    ["Ratings ceiling", ratings],
    ["Commercial rider", rider.commercial ? JSON.stringify(rider.commercial, null, 2) : "Not specified in package"],
    ["OAP version", manifest.oap_version || "Not specified"],
    ...(verification.warnings?.length ? [["Warnings", verification.warnings.join("; ")]] : [])
  ];

  const gridHtml = rows
    .map(([lbl, val]) => `<div class="oap-report-label">${escapeHtml(lbl)}:</div><div class="oap-report-value">${escapeHtml(String(val))}</div>`)
    .join("");

  card.innerHTML = `
    <div class="oap-report-header">
      <div class="oap-report-title">Package: ${escapeHtml(displayName)}</div>
      <span class="oap-badge-pill ${badgeClass}">${escapeHtml(badgeText)}</span>
    </div>
    <div class="oap-report-grid">${gridHtml}</div>
  `;
  card.hidden = false;
  if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = false;
}

// --- Delegated Action Listeners & Form Submissions ---

function makeCollapsibleCard(card, id) {
  if (!card) return;
  const title = card.querySelector(":scope > .card-title");
  const heading = title?.querySelector(":scope > h2");
  if (!heading || heading.querySelector(".progress-toggle")) return;
  const body = document.createElement("div");
  body.className = "progress-body";
  for (const child of [...card.children].filter(c => c !== title)) {
    body.append(child);
  }
  card.append(body);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "progress-toggle";
  toggle.setAttribute("aria-controls", id + "-body");
  toggle.setAttribute("aria-expanded", "true");

  while (heading.firstChild) toggle.append(heading.firstChild);
  heading.append(toggle);
  body.id = id + "-body";

  toggle.addEventListener("click", () => {
    const isExpanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!isExpanded));
    body.hidden = isExpanded;
  });
}

function initActorPanelCards() {
  const panel = $("#panel-actors");
  if (!panel) return;
  makeCollapsibleCard($("#actor-form"), "actor-create-card");
  makeCollapsibleCard(panel.querySelector('[data-component-id="oap-import-card"]'), "oap-import-card");
  makeCollapsibleCard($("#agreements-card"), "agreements-card");
}

export function initLibraryForms() {
  initActorPanelCards();
  // Delegated handler for Style cards
  $("#style-list")?.addEventListener("click", handle(async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("article[data-id]");
    const { id, name } = card.dataset;
    const action = btn.dataset.action;

    if (action === "delete-style") {
      if (!window.confirm(`Delete style “${name}” from this machine? Completed videos are kept.`)) return;
      await api(`/api/styles/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadStyles();
      scheduleSave();
      notice("Style deleted from your local collection.");
    } else if (action === "export-style") {
      await saveDownload(await api(`/api/styles/${encodeURIComponent(id)}/export`), `${id}.json`);
      notice(`Exported style “${name}” as ${id}.json`);
    } else if (action === "duplicate-style") {
      const existing = (state.styles || []).find((s) => s.id === id);
      const form = $("#style-form");
      if (form && existing) {
        form.elements.id.value = `${existing.id}_copy`.slice(0, 64);
        form.elements.name.value = `${existing.name} (Copy)`.slice(0, 160);
        form.elements.direction.value = existing.direction || "";
        form.scrollIntoView({ behavior: "smooth" });
        form.elements.name.focus();
        notice(`Duplicating “${name}”. Edit fields and save.`);
      }
    }
  }));


  // Double-click inline editor for Actor description
  const editDescription = (e) => {
    const card = e.target.closest("article[data-id]");
    if (!card || (e.type === "dblclick" && !e.target.closest(".actor-desc-text")) ||
        (e.type === "click" && !e.target.closest("[data-edit-description]"))) return;
    const descP = card.querySelector(".actor-desc-text");
    if (!descP || descP.querySelector("textarea")) return;
    const { id, name } = card.dataset;
    const existing = (state.actors || []).find((a) => a.id === id);
    if (!existing || existing.oap) return;
    const originalText = existing?.description || descP.textContent || "";

    const textarea = document.createElement("textarea");
    textarea.className = "actor-inline-editor";
    textarea.rows = 4;
    textarea.maxLength = 6000;
    textarea.value = originalText;
    textarea.setAttribute("aria-label", `Edit visual description for ${name}`);

    let saved = false;
    const saveAndClose = async () => {
      if (saved) return;
      saved = true;
      const newText = textarea.value.trim();
      if (newText === originalText.trim()) {
        descP.textContent = actorOverview({ description: originalText });
        return;
      }
      try {
        descP.textContent = "Saving description…";
        const updated = await json(`/api/actors/${encodeURIComponent(id)}`, { description: newText }, "PATCH");
        if (existing) existing.description = updated.description;
        await loadActors();
        notice(`Updated visual description for “${name}”.`);
        scheduleSave();
      } catch (err) {
        descP.textContent = actorOverview({ description: originalText });
        notice(`Failed to save description: ${err.message}`);
      }
    };

    textarea.addEventListener("blur", saveAndClose);
    textarea.addEventListener("keydown", (evt) => {
      if (evt.key === "Escape") {
        saved = true;
        descP.textContent = actorOverview({ description: originalText });
      }
    });

    descP.replaceChildren(textarea);
    textarea.focus();
    textarea.select();
  };
  $("#actor-list")?.addEventListener("dblclick", editDescription);
  $("#actor-list")?.addEventListener("click", editDescription);

  // Delegated handler for Actor cards
  $("#actor-list")?.addEventListener("click", handle(async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("article[data-id]");
    const { id, name } = card.dataset;
    const action = btn.dataset.action;

    if (action === "export-oap") {
      await saveDownload(await api(`/api/actors/${encodeURIComponent(id)}/export`, { method: "POST" }), id + ".oap");
    } else if (action === "export-audition") {
      const clearedCb = card.querySelector(".audition-cleared-cb");
      const isCleared = Boolean(clearedCb?.checked);
      const query = new URLSearchParams({ tier: "audition", reference_clearance: isCleared ? "audition" : "cast" });
      await saveDownload(await api(`/api/actors/${encodeURIComponent(id)}/export?${query}`, { method: "POST" }), id + "-audition.oap");
      notice(isCleared ? "Audition package exported with the audition-cleared reference." : "Audition package exported. The cast-only reference is not included.");
    } else if (action === "delete-actor") {
      if (!window.confirm(`Delete actor “${name}”, their reference image and imported package from this machine? Export first if you want a backup. Completed videos and earlier exports are kept.`)) return;
      await api(`/api/actors/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadActors();
      scheduleSave();
      notice("Actor deleted from your local cast.");
    }
  }));

  // Delegated handler for Agreement cards
  $("#agreement-list")?.addEventListener("click", handle(async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("article[data-id]");
    const { id } = card.dataset;
    const action = btn.dataset.action;
    const path = `/api/agreements/${encodeURIComponent(id)}`;

    if (action === "sign-agreement") {
      const { role, title, amount, currency } = btn.dataset;
      if (!window.confirm(`Sign “${title}” as ${role}? This commits the ${role} to ${amount} ${currency} and the casting call terms. Signatures cannot be withdrawn from copies already shared.`)) return;
      await json(`${path}/sign`, { role });
      await loadAgreements();
      notice(`Signed as ${role}.`);
    } else if (action === "verify-agreement") {
      const result = await (await api(`${path}/verify`)).json();
      notice(result.ok ? `Verified: both signatures are valid. ${result.note}` : `Not complete: ${result.issues.join("; ")}`);
    } else if (action === "download-bundle") {
      await saveDownload(await api(`${path}/bundle`, { method: "POST" }), id + "-agreement.zip");
    }
  }));

  const actorForm = $("#actor-form");
  const actorRefInput = actorForm?.querySelector("input[name=reference]");
  const actorRefPreview = $("#actor-ref-preview");
  let actorRefObjectUrl = null;

  function updateActorRefPreview(file) {
    if (!actorRefPreview) return;
    if (actorRefObjectUrl) {
      URL.revokeObjectURL(actorRefObjectUrl);
      actorRefObjectUrl = null;
    }
    if (!file) {
      actorRefPreview.hidden = true;
      actorRefPreview.replaceChildren();
      return;
    }
    actorRefObjectUrl = URL.createObjectURL(file);
    const image = document.createElement("img");
    image.className = "actor-ref-thumb";
    image.src = actorRefObjectUrl;
    image.alt = "";
    const name = document.createElement("span");
    name.className = "actor-ref-name";
    name.textContent = file.name;
    actorRefPreview.replaceChildren(image, name);
    actorRefPreview.hidden = false;
  }

  actorRefInput?.addEventListener("change", () => {
    const file = actorRefInput.files?.[0];
    updateActorRefPreview(file);
  });

  actorForm?.addEventListener("reset", () => {
    updateActorRefPreview(null);
  });

  actorForm.onsubmit = handle(async (event) => {
    await api("/api/actors", { method: "POST", body: new FormData(event.target) });
    event.target.reset();
    updateActorRefPreview(null);
    await loadActors();
    scheduleSave();
  });

  $("#style-form").onsubmit = handle(async (event) => {
    await json("/api/styles", Object.fromEntries(new FormData(event.target)));
    event.target.reset();
    await loadStyles();
    scheduleSave();
  });

  $("#import-style-btn")?.addEventListener("click", handle(async () => {
    const file = $("#style-import-file")?.files?.[0];
    if (!file) throw new Error("Choose a style .json file first");
    const overwrite = Boolean($("#style-import-overwrite")?.checked);

    let parsed;
    try {
      const textContent = await file.text();
      parsed = JSON.parse(textContent);
    } catch (err) {
      throw new Error(`Invalid JSON file: ${err.message}`);
    }

    if (!parsed || typeof parsed !== "object") {
      throw new Error("Invalid style format: Root must be a JSON object");
    }

    const payload = {
      id: String(parsed.id || "").trim(),
      name: String(parsed.name || "").trim(),
      direction: String(parsed.direction || "").trim(),
      overwrite,
    };
    if (parsed.style_card) {
      payload.style_card = String(parsed.style_card);
    }
    if (parsed.vocabulary && typeof parsed.vocabulary === "object") {
      payload.vocabulary = parsed.vocabulary;
    }

    if (!payload.id) throw new Error("Style JSON must include an 'id'");
    if (!payload.name) throw new Error("Style JSON must include a 'name'");
    if (!payload.direction) throw new Error("Style JSON must include 'direction'");

    const result = await json("/api/styles/import", payload);
    $("#style-import-file").value = "";
    $("#style-import-overwrite").checked = false;
    await loadStyles();
    scheduleSave();
    notice(`Style “${result.name}” (${result.id}) successfully imported.`);
  }));

  $("#oap-file").addEventListener("change", () => {
    state.currentOap = undefined;
    $("#oap-import-form").hidden = true;
    $("#oap-report-card").hidden = true;
    $("#oap-raw-toggle-wrap").hidden = true;
    $("#oap-report").hidden = true;
  });

  $("#inspect-oap").onclick = handle(async () => {
    const file = $("#oap-file").files[0];
    if (!file) throw new Error("Choose an OAP package first");
    $("#oap-import-form").hidden = true;
    $("#oap-import-form").elements.accept_unknown.checked = false;
    $("#oap-report-card").hidden = true;
    $("#oap-raw-toggle-wrap").hidden = true;
    $("#oap-report").hidden = true;
    $("#toggle-raw-oap").textContent = "Show raw manifest JSON";
    state.currentOap = await upload(file, "oap");
    const allowUnsigned = $("#allow-unsigned").checked;
    const report = await (await api(`/api/oap/inspect/${state.currentOap}?allow_unsigned=${allowUnsigned}`)).json();
    $("#oap-report").textContent = JSON.stringify(report, null, 2);
    renderOapReportCard(report, allowUnsigned);
    $("#oap-import-form").hidden = false;
  });

  $("#oap-import-form").onsubmit = handle(async (event) => {
    const body = new FormData(event.target);
    body.set("filename", state.currentOap);
    body.set("allow_unsigned", String($("#allow-unsigned").checked));
    body.set("accept_unknown", String(event.target.elements.accept_unknown.checked));
    const imported = await (await api("/api/oap/import", { method: "POST", body })).json();
    event.target.hidden = true;
    $("#oap-report").hidden = true;
    if ($("#oap-report-card")) $("#oap-report-card").hidden = true;
    if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = true;
    notice("Actor successfully imported into your studio cast library.");
    await loadActors();
    document.dispatchEvent(new CustomEvent("mmv:actor-imported", { detail: { id: imported.id } }));
  });

  $("#agreement-form").onsubmit = handle(async (event) => {
    const values = Object.fromEntries(new FormData(event.target));
    const body = { content: {} };
    for (const [key, value] of Object.entries(values)) {
      if (key.startsWith("content_")) body.content[key.slice(8)] = value;
      else body[key] = value;
    }
    await json("/api/agreements", body);
    event.target.elements.agreement_id.value = "";
    await loadAgreements();
    notice("Agreement drafted. Sign as Director, then send the bundle to the Agent to countersign.");
  });

  $("#import-agreement").onclick = handle(async () => {
    const file = $("#agreement-file").files[0];
    if (!file) throw new Error("Choose a signed agreement.json first");
    const body = new FormData();
    body.set("filename", await upload(file, "agreement"));
    const result = await (await api("/api/agreements/import", { method: "POST", body })).json();
    $("#agreement-file").value = "";
    await loadAgreements();
    notice(result.complete
      ? "Countersigned agreement imported; both signatures verify."
      : "Signatures imported; the agreement is not yet signed by both parties.");
  });
}
