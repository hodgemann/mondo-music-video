// Ordered storyboard drafts live in each form; interpretation uses normal quote/start consent.
import { $$, api, handle, json, notice, option, state, text, upload } from './core.js';
import { scheduleSave } from './project.js';
import { showQuote } from './production.js';

const read = form => JSON.parse(form.elements.storyboard_draft.value || '{"images":[],"panels":[]}');
function save(form, board) {
  form.elements.storyboard_draft.value = JSON.stringify(board);
  scheduleSave();
}
const button = (label, action) => {
  const node = text('button', label, 'quiet');
  node.type = 'button'; node.onclick = handle(action); return node;
};

export function storyboardFromForm(form, request) {
  if (form.dataset.storyboardPending) throw new Error('Wait for storyboard uploads to finish');
  const board = read(form);
  if (form.elements.storyboard_enabled.checked && (!board.panels.length || board.panels.some(p => !p.direction.trim())))
    throw new Error('Interpret the storyboard or write a direction for every panel before using it');
  request.storyboard = form.elements.storyboard_enabled.checked ? {
    ...board,
    enabled: true,
    mode: form.elements.storyboard_mode.value,
    humanize: Boolean(form.elements.storyboard_humanize?.checked)
  } : {};
  for (const key of Object.keys(request)) if (key.startsWith('storyboard_')) delete request[key];
  if (request.kind === 'ident') request.ident_all_references = form.elements.ident_all_references.checked;
}

const updatePanelDirection = (board, index, direction) => ({
  ...board,
  panels: board.panels.map((panel, idx) => (idx === index ? { ...panel, direction } : panel))
});

const swapPanels = (board, indexA, indexB) => ({
  ...board,
  panels: board.panels.map((panel, idx) =>
    idx === indexA ? board.panels[indexB] : idx === indexB ? board.panels[indexA] : panel
  )
});

const removePanelAt = (board, index) => ({
  ...board,
  panels: board.panels.filter((_, idx) => idx !== index)
});

const appendTextPanel = (board) => ({
  ...board,
  panels: [...board.panels, { image: '', direction: '' }]
});

function render(form) {
  const board = read(form), container = form.querySelector('.storyboard-panels');
  form.querySelector('.storyboard-images').textContent = board.images.length + ' storyboard image(s)';
  container.replaceChildren();
  board.panels.forEach((panel, index) => {
    const card = document.createElement('div'); card.className = 'storyboard-panel';
    card.append(text('strong', `Panel ${index + 1}`));
    if (panel.image) {
      const image = document.createElement('img'); image.src = '/api/uploads/reference/' + encodeURIComponent(panel.image);
      image.alt = `Source image for panel ${index + 1}`; image.loading = 'lazy'; card.append(image);
    }
    const area = document.createElement('textarea'); area.rows = 3; area.maxLength = 1200; area.value = panel.direction;
    area.setAttribute('aria-label', `Panel ${index + 1} direction`);
    area.oninput = () => save(form, updatePanelDirection(read(form), index, area.value));
    card.append(area);
    for (const [label, delta] of [['Move up', -1], ['Move down', 1]]) {
      const move = button(label, () => {
        save(form, swapPanels(read(form), index, index + delta));
        render(form);
      });
      move.disabled = index + delta < 0 || index + delta >= board.panels.length; card.append(move);
    }
    card.append(button('Remove panel', () => { save(form, removePanelAt(read(form), index)); render(form); }));
    container.append(card);
  });
}

export function clearStoryboard(form) {
  save(form, {images: [], panels: []});
  form.elements.storyboard_enabled.checked = false;
  render(form);
}

export async function refreshStoryboards() {
  const runs = await (await api('/api/storyboards')).json();
  $$('.storyboard-results').forEach(select => {
    const previous = select.value;
    select.replaceChildren(option('', 'Choose an interpreted storyboard'), ...runs.map(r => option(r.run_id, r.run_id)));
    if (runs.some(r => r.run_id === previous)) select.value = previous;
  });
}

export function restoreStoryboards() {
  $$('#video-form, #ident-form').forEach(render);
}

export function initStoryboards() {
  $$('#video-form, #ident-form').forEach(form => {
    const section = document.createElement('details'); section.className = 'storyboard-editor';
    section.innerHTML = `<summary>Storyboard</summary>
      <p>Guide the sequence with ordered panels. Narrative follows action and mood; Visual follows composition and framing. Your cast keeps its identity.</p>
      <label class="check"><input type="checkbox" name="storyboard_enabled"> Use this storyboard</label>
      <label>Interpretation<select name="storyboard_mode"><option value="narrative">Narrative</option><option value="visual">Visual direction</option></select></label>
      <label class="check"><input type="checkbox" name="storyboard_humanize"> Humanize directions (strip AI clichés)</label>
      <input type="hidden" name="storyboard_draft" value='{"images":[],"panels":[]}'>
      <label>Add storyboard images (up to 24)<input class="storyboard-files" type="file" accept="image/*" multiple data-max="24"><small class="file-drop-hint">Choose files or drop up to 24 files here</small><small class="file-drop-error" role="alert"></small></label>
      <p class="storyboard-images muted"></p><div class="storyboard-actions"></div>
      <label>Saved interpretations<select class="storyboard-results"></select></label>
      <div class="storyboard-result-actions"></div><div class="storyboard-panels"></div>`;
    (form.querySelector('.action-bar-wrap') || form.querySelector('button.primary')).before(section);
    const actions = section.querySelector('.storyboard-actions');
    const input = section.querySelector('.storyboard-files');
    input.onchange = handle(async () => {
      const files = [...input.files]; if (files.length > 24) throw new Error('Choose at most 24 storyboard images');
      form.dataset.storyboardPending = '1'; input.disabled = true;
      try {
        const images = [];
        for (const file of files) images.push(await upload(file, 'reference'));
        const current = read(form);
        if (current.images.length + images.length > 24 || current.panels.length + images.length > 24)
          throw new Error('Adding these images would exceed 24 images or panels; remove panels or clear the board first');
        save(form, {images: [...current.images, ...images], panels: [...current.panels, ...images.map(image => ({image, direction: ''}))]}); render(form);
      } finally { delete form.dataset.storyboardPending; input.disabled = false; }
    });
    actions.append(button('Add text panel', () => {
      const board = read(form); if (board.panels.length >= 24) throw new Error('Use at most 24 panels');
      save(form, appendTextPanel(board)); render(form);
    }), button('Humanize directions', async () => {
      const current = read(form);
      if (!current.panels.length) throw new Error('No panels to humanize');
      const panels = await json('/api/storyboards/humanize', current.panels);
      save(form, {...current, panels});
      render(form);
      notice('Humanized panel directions: stripped synthetic clichés and throat-clearing.');
    }), button('Preview interpretation', async () => {
      if (form.dataset.storyboardPending) throw new Error('Wait for uploads to finish');
      const board = read(form);
      const request = {kind: 'storyboard', title: form.elements.title.value, direction: form.elements.direction.value,
        storyboard: {mode: form.elements.storyboard_mode.value, humanize: Boolean(form.elements.storyboard_humanize?.checked), images: board.images}};
      showQuote(request, await json('/api/quote', request));
    }), button('Clear storyboard', () => clearStoryboard(form)));
    section.querySelector('.storyboard-result-actions').append(button('Refresh interpretations', refreshStoryboards), button('Load for review', async () => {
      const id = section.querySelector('.storyboard-results').value;
      if (!id) throw new Error('Choose a saved interpretation');
      const board = await (await api('/api/storyboards/' + encodeURIComponent(id))).json();
      save(form, {images: board.images, panels: board.panels}); form.elements.storyboard_mode.value = board.mode;
      form.elements.storyboard_enabled.checked = false; render(form);
      notice('Review the panels, then select Use this storyboard and preview your production.');
    }));
    section.querySelector('.storyboard-result-actions').append(button('Inspect saved response', async () => {
      const id = section.querySelector('.storyboard-results').value || state.currentRun;
      if (!id) throw new Error('Choose an interpretation or run one first');
      const result = await (await api('/api/storyboards/' + encodeURIComponent(id) + '/response')).json();
      let output = section.querySelector('.storyboard-response');
      if (!output) { output = document.createElement('textarea'); output.className = 'storyboard-response'; output.readOnly = true; output.rows = 8; output.setAttribute('aria-label', 'Saved vision response'); section.append(output); }
      output.value = result.response;
    }));
    render(form);
  });
}
