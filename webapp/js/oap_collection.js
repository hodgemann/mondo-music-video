// Public actor collection is checked only when the operator asks. Inspection never imports.
import { $, api, handle, json, notice, state } from "./core.js";
import { renderOapReportCard } from "./library.js";

let collection = null;

const sizeLabel = bytes => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

function renderCollection() {
  const list = $("#oap-collection-list");
  list.replaceChildren();
  if (!collection) return;
  const pending = collection.actors.filter(actor => !actor.installed);
  if (!pending.length) {
    const empty = document.createElement("p");
    empty.textContent = "Every actor in this collection is already in your studio.";
    list.append(empty);
    return;
  }
  for (const actor of pending) {
    const row = document.createElement("div");
    row.className = "oap-collection-row";
    const label = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = actor.name;
    const details = document.createElement("small");
    details.textContent = `${actor.id} · OAP ${actor.oap_version} · ${sizeLabel(actor.bytes)}`;
    label.append(name, details);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "Download & inspect";
    button.dataset.actorId = actor.id;
    row.append(label, button);
    list.append(row);
  }
}

function showStagedPackage(report) {
  state.currentOap = report.filename;
  $("#allow-unsigned").checked = false;
  const importForm = $("#oap-import-form");
  importForm.hidden = true;
  importForm.elements.accept_unknown.checked = false;
  importForm.elements.actor_id.value = "";
  $("#oap-report").textContent = JSON.stringify({ manifest: report.manifest, verification: report.verification }, null, 2);
  $("#oap-report").hidden = true;
  $("#toggle-raw-oap").textContent = "Show raw manifest JSON";
  renderOapReportCard(report, false);
  importForm.hidden = false;
  $("#oap-report-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

export function initOapCollection() {
  const importCard = $("#oap-import-form")?.parentElement;
  if (!importCard) return;
  const fold = document.createElement("details");
  fold.id = "oap-collection-fold";
  fold.className = "oap-collection-fold";
  fold.dataset.component = "Public OAP Actor Collection";
  fold.dataset.componentId = "oap-collection-fold";
  fold.dataset.componentSource = "webapp/js/oap_collection.js";
  fold.innerHTML = `<summary>Check public OAP actors</summary>
    <p>Check the published actor collection when you choose. Its packages are <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a> with attribution to Maximum Goose Laboratory. Each package is downloaded and verified only when you select it. Import still requires your separate signer acceptance. Existing actors are kept.</p>
    <button type="button" id="check-oap-collection" class="secondary">Check for actors</button>
    <p id="oap-collection-status" role="status" class="muted"></p>
    <div id="oap-collection-list"></div>`;
  importCard.append(fold);
  const status = $("#oap-collection-status");
  $("#check-oap-collection").onclick = handle(async () => {
    status.textContent = "Checking the public OAP collection…";
    collection = await (await api("/api/oap-collection")).json();
    renderCollection();
    status.textContent = `${collection.actors.filter(actor => !actor.installed).length} actor packages available · ${collection.license} · ${collection.attribution}. Select one to verify its signature and rider before import.`;
  });
  $("#oap-collection-list").addEventListener("click", handle(async event => {
    const button = event.target.closest("button[data-actor-id]");
    if (!button || !collection) return;
    status.textContent = `Downloading and verifying ${button.dataset.actorId}…`;
    button.disabled = true;
    try {
      const report = await json("/api/oap-collection/stage", {
        actor_id: button.dataset.actorId, index_sha256: collection.index_sha256
      });
      showStagedPackage(report);
      status.textContent = `Verified ${button.dataset.actorId}. Review the signer, rider, visual identity and CC BY 4.0 attribution, then accept the signer to import.`;
    } finally {
      button.disabled = false;
    }
  }));
  document.addEventListener("mmv:actor-imported", event => {
    const actor = collection?.actors.find(item => item.id === event.detail?.id);
    if (actor) { actor.installed = true; renderCollection(); }
  });
}

$("#oap-recipient-key-button")?.addEventListener("click", handle(async () => {
  $("#oap-recipient-key").textContent = (await (await api("/api/oap/recipient-key")).json()).public_key;
}));
