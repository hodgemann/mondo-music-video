// Pure functional state, PRNG, and draft transformations for Visual Vocabulary.

const SAVED_KEYS_STORAGE_KEY = "mmv_saved_vocab_keys";

export const hashSeed = (str) => {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 0x01000193);
  }
  return h >>> 0;
};

export const mulberry32 = (seed) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export const shuffleIndices = (length, rand = Math.random) => {
  const indices = Array.from({ length }, (_, i) => i);
  for (let i = length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  return indices;
};

export const parseRandomKey = (rawKey, fallbackCount = 5) => {
  const cleaned = (rawKey || "").trim();
  if (!cleaned) return null;
  const [seedPart, countPart] = cleaned.split(":");
  const seedStr = (seedPart || "").trim();
  if (!seedStr) return null;
  const parsedCount = parseInt(countPart, 10);
  const count = !isNaN(parsedCount) && parsedCount >= 1
    ? parsedCount
    : Math.max(1, parseInt(fallbackCount, 10) || 5);
  return { seedStr, count, key: `${seedStr}:${count}` };
};

export const generateRandomKey = (count = 5) => {
  const seed = Math.floor(100000 + Math.random() * 900000);
  const safeCount = Math.max(1, parseInt(count, 10) || 5);
  return `${seed}:${safeCount}`;
};

export const sampleExcluded = (baseItems, count, rand = Math.random) => {
  const sampleSize = Math.min(Math.max(1, count), baseItems.length);
  const chosen = new Set(shuffleIndices(baseItems.length, rand).slice(0, sampleSize));
  return {
    sampleSize,
    excluded: baseItems.filter((_, idx) => !chosen.has(idx))
  };
};

export const cloneDraft = (draft = {}) =>
  Object.fromEntries(
    Object.entries(draft || {}).map(([cat, ov]) => [
      cat,
      {
        mode: ov?.mode || "append",
        add: [...(ov?.add || [])],
        exclude: [...(ov?.exclude || [])]
      }
    ])
  );

export const cleanDraft = (draft = {}) =>
  Object.fromEntries(
    Object.entries(cloneDraft(draft)).filter(
      ([, ov]) => !(ov.mode === "append" && ov.add.length === 0 && ov.exclude.length === 0)
    )
  );

export const computePseudoRandomDraft = (catalog, rawKey, fallbackCount = 5, existingDraft = {}) => {
  const parsed = parseRandomKey(rawKey, fallbackCount);
  if (!parsed || !catalog?.base) return null;
  const { seedStr, count } = parsed;
  const categories = catalog.categories || Object.keys(catalog.base);
  const draft = {};

  categories.forEach((cat) => {
    const baseItems = catalog.base[cat] || [];
    if (!baseItems.length) return;
    const rand = mulberry32(hashSeed(`${seedStr}::${cat}`));
    const { excluded } = sampleExcluded(baseItems, count, rand);
    draft[cat] = {
      mode: "append",
      add: [...(existingDraft[cat]?.add || [])],
      exclude: excluded
    };
  });

  return { draft, key: parsed.key, seed: seedStr, count };
};

export const getCategoryStats = (catalog, draft, cat) => {
  const baseItems = catalog?.base?.[cat] || [];
  const ov = draft?.[cat];
  if (!ov) {
    return { activeItems: baseItems, count: baseItems.length, isModified: false };
  }
  if (ov.mode === "replace") {
    const activeItems = [...(ov.add || [])];
    return { activeItems, count: activeItems.length, isModified: true };
  }
  const exc = new Set(ov.exclude || []);
  const added = ov.add || [];
  const activeItems = exc.size === 0
    ? (added.length ? baseItems.concat(added) : baseItems)
    : baseItems.filter((x) => !exc.has(x)).concat(added);
  return {
    activeItems,
    count: activeItems.length,
    isModified: exc.size > 0 || added.length > 0
  };
};

export const getSummaryStats = (catalog, draft) => {
  const categories = catalog?.categories || Object.keys(catalog?.base || {});
  let totalActive = 0;
  let customizedCats = 0;
  const byCategory = {};

  categories.forEach((cat) => {
    const stats = getCategoryStats(catalog, draft, cat);
    byCategory[cat] = stats;
    totalActive += stats.count;
    if (stats.isModified) customizedCats++;
  });

  return { categories, byCategory, totalActive, customizedCats };
};

export const withRandomizedCategory = (catalog, draft, cat, count = 5) => {
  const baseItems = catalog?.base?.[cat] || [];
  if (!baseItems.length) return null;
  const { sampleSize, excluded } = sampleExcluded(baseItems, count);
  const next = cloneDraft(draft);
  next[cat] = {
    mode: "append",
    add: [...(next[cat]?.add || [])],
    exclude: excluded
  };
  return { draft: next, sampleSize };
};

export const withAddedRandomItem = (catalog, draft, cat) => {
  const baseItems = catalog?.base?.[cat] || [];
  const exc = new Set(draft?.[cat]?.exclude || []);
  const candidates = baseItems.filter((item) => exc.has(item));
  if (!candidates.length) return { draft, picked: null };
  const picked = candidates[Math.floor(Math.random() * candidates.length)];
  exc.delete(picked);
  const next = cloneDraft(draft);
  next[cat] = {
    mode: next[cat]?.mode || "append",
    add: [...(next[cat]?.add || [])],
    exclude: [...exc]
  };
  return { draft: next, picked };
};

export const withoutCategoryItem = (catalog, draft, cat, item) => {
  const { count } = getCategoryStats(catalog, draft, cat);
  if (count <= 1) return { draft, removed: false, minReached: true };
  const next = cloneDraft(draft);
  const cur = next[cat] || { mode: "append", add: [], exclude: [] };
  if (cur.add.includes(item)) {
    cur.add = cur.add.filter((x) => x !== item);
  } else {
    cur.exclude = [...new Set([...cur.exclude, item])];
  }
  next[cat] = cur;
  return { draft: next, removed: true, minReached: false };
};

export const withToggledBuiltinItem = (draft, cat, item, checked, fallbackMode = "append") => {
  const next = cloneDraft(draft);
  const cur = next[cat] || { mode: fallbackMode, add: [], exclude: [] };
  const exc = new Set(cur.exclude);
  if (checked) exc.delete(item);
  else exc.add(item);
  next[cat] = { ...cur, exclude: [...exc] };
  return next;
};

export const withCustomLines = (draft, cat, rawText, fallbackMode = "append") => {
  const lines = (rawText || "").split("\n").map((s) => s.trim()).filter(Boolean);
  const next = cloneDraft(draft);
  const cur = next[cat];
  if (lines.length > 0 || cur?.exclude?.length || cur?.mode === "replace") {
    next[cat] = {
      mode: cur?.mode || fallbackMode,
      add: lines,
      exclude: [...(cur?.exclude || [])]
    };
  } else if (cur) {
    next[cat] = { ...cur, add: [] };
  }
  return next;
};

export const presetToDraft = (catalog, presetId) => {
  if (!catalog || presetId === "full") return {};
  if (presetId === "reduced_flashing") {
    const profile = catalog.profiles?.reduced_flashing?.exclude || {};
    return Object.fromEntries(
      Object.entries(profile).map(([cat, excluded]) => [
        cat,
        { mode: "append", add: [], exclude: [...excluded] }
      ])
    );
  }
  const preset = (catalog.vocabularies || []).find((p) => p.id === presetId);
  return preset ? cloneDraft(preset.tables || {}) : {};
};

export const getSavedVocabKeys = () => {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEYS_STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
};

export const saveVocabKey = (key) => {
  if (!key) return;
  const list = [key, ...getSavedVocabKeys().filter((k) => k !== key)].slice(0, 50);
  try {
    localStorage.setItem(SAVED_KEYS_STORAGE_KEY, JSON.stringify(list));
  } catch {}
};

export const deleteSavedVocabKey = (key) => {
  if (!key) return;
  const list = getSavedVocabKeys().filter((k) => k !== key);
  try {
    localStorage.setItem(SAVED_KEYS_STORAGE_KEY, JSON.stringify(list));
  } catch {}
};

