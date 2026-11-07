// Thematic Worlds, Classification Mode & Juxtaposition Arc Workspace.
// Pure functional architecture: deterministic calculations, explicit inputs/outputs, side-effect isolation.

import { $, $$, copyToClipboard, notice, state as appState } from "./core.js";
import { scheduleSave } from "./project.js";
import { loadVocabularyCatalog, updateVocabCustomBadge } from "./vocabulary.js";
import { EXTENDED_THEMATIC_WORLDS } from "./thematic-worlds-extended.js";

// WHAT: Default baseline thematic worlds loaded when no custom project state exists.
// WHY: Ensures the UI has a balanced initial set of active (bureaucratic, brutalist) and inactive
// anchor worlds with realistic similarity scores before the user runs prompt classification.
export const DEFAULT_WORLDS = [
  { name: "Bureaucratic / Carceral", score: 0.81, active: true, locked: false },
  { name: "Brutalist Concrete", score: 0.70, active: true, locked: false },
  { name: "Industrial Decay", score: 0.62, active: false, locked: false },
  { name: "Maritime / Salt", score: 0.31, active: false, locked: false }
];

// WHAT: Core built-in aesthetic worlds library defining keywords and signature vocabulary pools across 5 dimensions.
// WHY: Provides the foundational domain knowledge base that ships directly with the application.
export const BUILTIN_THEMATIC_WORLDS_LIBRARY = [
  {
    name: "Bureaucratic / Carceral",
    keywords: [
      "clerk", "archive", "office", "government", "paperwork", "dossier", "cubicle", "desk",
      "stamp", "lanyard", "prison", "carceral", "cell", "fluorescent", "warden",
      "institutional", "records", "annex", "ledger", "typewriter", "linoleum", "official",
      "tribunal", "audit", "shift", "night-shift", "document", "filing", "cabinet", "pen", "stairwell"
    ],
    pools: {
      Settings: ["evidence locker", "sodium-lit stairwell", "records annex", "flooded basement", "linoleum corridor", "interrogation room", "card-catalogue annex"],
      Lighting: ["flickering fluorescent tube", "single desk lamp", "amber exit signs", "cold green cathode hum", "overhead strip glare"],
      Mechanisms: ["pneumatic tube dispatch", "card-catalogue drawers sliding", "stamp descending", "manual typewriter carriage", "rotary dial spin"],
      Costume: ["grey wool cardigan", "laminated lanyard", "rumpled polyester tie", "oversized metal badge", "stiff cotton clerk coat"],
      "Practical Effects": ["drifting paper dust", "steam from a vent", "yellowing water stain", "buzzing ballast flicker", "coffee ring on parchment"]
    }
  },
  {
    name: "Brutalist Concrete",
    keywords: [
      "brutalist", "concrete", "monolith", "bunker", "aggregate", "gray", "grey", "shear wall",
      "geometric", "slab", "underpass", "pillar", "cold", "overpass", "fortress", "foundation",
      "viaduct", "gravel", "cement", "raw", "monolithic", "architecture", "monumental"
    ],
    pools: {
      Settings: ["monolithic atrium", "shear concrete underpass", "subterranean bunker", "recessed pedestrian tunnel", "brutalist civic plaza"],
      Lighting: ["stark raking sidelight", "deep geometric shadow", "cold halogen wash", "single slit aperture sunbeam"],
      Mechanisms: ["hydraulic blast door", "counterweight pulley", "heavy steel turnstile", "concrete core drill", "cable-stayed winch"],
      Costume: ["heavy charcoal trench", "rough wool greatcoat", "steel-toe boots", "utilitarian boiler suit", "dark canvas parka"],
      "Practical Effects": ["chalky concrete dust", "dripping condensation", "cold breath mist", "wind whipping fine gravel"]
    }
  },
  {
    name: "Industrial Decay",
    keywords: [
      "industrial", "decay", "factory", "rust", "abandoned", "iron", "boiler", "furnace",
      "scrap", "grease", "foundry", "smokestack", "pipe", "turbine", "corrugated", "toxic",
      "derelict", "mill", "smelting", "assembly", "soot", "machinery", "metal", "welding"
    ],
    pools: {
      Settings: ["abandoned assembly floor", "rusted catwalk", "inactive blast furnace", "scrap yard crane bay", "dripping steam conduit"],
      Lighting: ["flickering sodium vapor", "welding flash reflection", "amber hazard strobe", "dull rusted twilight"],
      Mechanisms: ["cracked flywheel spinning", "pneumatic piston hiss", "rusty chain hoist", "loose drive belt flapping"],
      Costume: ["grease-stained canvas overalls", "battered leather apron", "pitted welding goggles", "frayed cloth gloves"],
      "Practical Effects": ["curling iron filings", "oily puddle rainbow", "soot fallout", "high-pressure steam leak"]
    }
  },
  {
    name: "Maritime / Salt",
    keywords: [
      "maritime", "salt", "ocean", "sea", "wharf", "harbor", "brine", "trawler", "dock",
      "pier", "foghorn", "slicker", "fish", "tide", "boat", "ship", "wave", "coast",
      "coastal", "buoy", "barnacle", "hull", "seaweed", "gulls", "lighthouse", "water", "anchor"
    ],
    pools: {
      Settings: ["fog-choked timber pier", "rusted trawler deck", "fish cannery slipway", "salt-crusted watchtower", "low-tide mudflat"],
      Lighting: ["revolving lighthouse beam", "grey overcast sea mist", "lantern reflecting in wet planks", "sickly yellow deck floodlight"],
      Mechanisms: ["winch drum groaning", "rusty capstan turning", "foghorn bellows breathing", "bilge pump chugging"],
      Costume: ["yellow rubber slicker", "salt-stiffened denim", "heavy knit fisherman sweater", "sou'wester oilskin hat"],
      "Practical Effects": ["cold sea spray", "thick sea fog rolling", "dripping brine", "scattered wet fish scales"]
    }
  },
  {
    name: "Cyberpunk / High-Tech",
    keywords: [
      "cyberpunk", "cyber", "tech", "high-tech", "neon", "fiber", "optic", "server", "terminal",
      "circuit", "hacker", "glitch", "holographic", "data", "synthetic", "diode", "wire",
      "screen", "motherboard", "digital", "network", "drone", "interface", "virtual", "matrix", "code"
    ],
    pools: {
      Settings: ["crowded server bank", "neon-lit rainy alleyway", "subterranean cyber clinic", "cramped terminal booth", "optic cabling conduit"],
      Lighting: ["saturated magenta neon", "pulsing cyan diode glow", "scanning laser grid", "stuttering CRT monitor flicker"],
      Mechanisms: ["robotic actuator arm", "cooling fan spin-up", "optic cable rack patching", "motorized iris camera lens"],
      Costume: ["transparent vinyl coat", "modular techwear harness", "reflective visor", "fingerless grounding gloves"],
      "Practical Effects": ["circuit board smoke", "holographic glitch artifact", "fiber optic sparks", "pooling oily neon reflection"]
    }
  },
  {
    name: "Nocturnal Noir",
    keywords: [
      "noir", "detective", "night", "nocturnal", "rain", "wet", "asphalt", "trenchcoat",
      "alley", "venetian", "blinds", "shadow", "cigarette", "smoke", "jazz", "crime",
      "mystery", "streetlamp", "diner", "femme", "fatale", "fedora", "midnight", "whiskey"
    ],
    pools: {
      Settings: ["rain-slicked back alley", "venetian-blinded private office", "empty 2am diner", "fire escape landing", "telephone booth under streetlight"],
      Lighting: ["slanted venetian blind shadow", "single sodium streetlight", "glowing cigarette tip", "wet pavement neon bounce"],
      Mechanisms: ["rotary phone cradle click", "revolver cylinder spin", "ceiling fan turning slowly", "coin clinking in jukebox"],
      Costume: ["damp gabardine trenchcoat", "tilted felt fedora", "loosened silk tie", "leather shoulder holster"],
      "Practical Effects": ["curling cigarette smoke", "rain pouring off metal awning", "wet tire hiss", "windshield wiper drag"]
    }
  },
  {
    name: "Pastoral Nature",
    keywords: [
      "nature", "pastoral", "overgrowth", "forest", "woods", "moss", "meadow", "trees",
      "leaves", "pollen", "roots", "soil", "canopy", "flora", "garden", "organic",
      "wild", "fungal", "mushrooms", "thicket", "lichen", "grove", "sunbeam", "creek", "river", "botanical"
    ],
    pools: {
      Settings: ["moss-carpeted forest clearing", "ruined stone chapel overgrown with ivy", "sun-dappled creek bed", "ancient hollow oak grove"],
      Lighting: ["dappled canopy sunlight", "amber golden-hour slant", "glowing bioluminescent moss", "soft morning mist"],
      Mechanisms: ["creaking tree bough", "timber water wheel turning", "seed pod bursting", "deep root cracking stone"],
      Costume: ["hand-spun linen tunic", "dirt-stained hem", "woven willow crown", "unbleached cotton smock"],
      "Practical Effects": ["floating airborne pollen", "falling dried leaves", "rising soil dew", "spore cloud drifting"]
    }
  },
  {
    name: "Baroque / Theatrical",
    keywords: [
      "baroque", "theatrical", "theater", "theatre", "velvet", "curtain", "gold", "gilded",
      "masquerade", "chandelier", "opera", "stage", "footlights", "proscenium", "drama",
      "costume", "regal", "palace", "candle", "candelabra", "brocade", "orchestra", "mask"
    ],
    pools: {
      Settings: ["decaying opera house balcony", "gilded mirror gallery", "empty orchestra pit", "dusty backstage dressing room"],
      Lighting: ["gas footlights flickering", "multi-tiered crystal chandelier", "single amber spotlight cone", "flickering beeswax candles"],
      Mechanisms: ["counterweighted stage rope", "velvet grand drape rising", "trapdoor latch releasing", "mechanical music box cylinder"],
      Costume: ["heavy crimson velvet cape", "tarnished filigree mask", "gold brocade waistcoat", "ruffled lace collar"],
      "Practical Effects": ["billowing stage rosin dust", "drifting red rose petals", "melting wax drip", "floating theatrical haze"]
    }
  },
  {
    name: "Clinical / Medical",
    keywords: [
      "medical", "clinical", "hospital", "sterile", "surgical", "tile", "doctor", "nurse",
      "clinic", "syringe", "stainless", "examination", "patient", "antiseptic",
      "laboratory", "pharma", "specimen", "diagnosis", "white", "gloves", "quarantine", "scalpel"
    ],
    pools: {
      Settings: ["glazed white tile operating theater", "silent quarantine corridor", "specimen preservation vault", "sterile recovery ward"],
      Lighting: ["harsh shadowless surgical ring light", "pale blue inspection beam", "cold white fluorescent glare"],
      Mechanisms: ["centrifuge spinning", "pneumatic syringe valve", "stainless gurney caster rolling", "ECG tape feeding"],
      Costume: ["pale mint surgical scrubs", "translucent examination gloves", "starch-white lab coat", "disposable paper mask"],
      "Practical Effects": ["condensation inside oxygen tent", "dripping saline chamber", "antiseptic mist spray", "frost on cryogenic vial"]
    }
  },
  {
    name: "Cosmic / Void",
    keywords: [
      "cosmic", "void", "space", "star", "stars", "starfield", "obsidian", "gravity",
      "zero-g", "vacuum", "celestial", "nebula", "observatory", "radio", "dish", "meteor",
      "dust", "satellite", "astronaut", "orbit", "planetary", "black hole", "galaxy", "deep space"
    ],
    pools: {
      Settings: ["deep space observation cupola", "radio telescope dish rim", "obsidian asteroid crater", "pressurized airlock chamber"],
      Lighting: ["distant blue starlight pinpricks", "earth-rise specular rim light", "cold solar flare glare", "monochrome instrument backlight"],
      Mechanisms: ["airlock decompression cycle", "reaction control thruster puff", "gyroscope spinning in gimbal", "solar array unrolling"],
      Costume: ["multilayer EVA spacesuit", "gold-tinted reflective helmet visor", "pressurized tether umbilical", "quilted thermal liner"],
      "Practical Effects": ["floating weightless droplets", "solar wind particle trails", "micro-meteorite impact sparkle", "ice crystals venting"]
    }
  }
];

// WHAT: Merges base and external thematic world arrays, deduplicating case-insensitively by world name.
// WHY: Allows expanding the library with external modules, custom files, or runtime payloads without duplicating world cards.
export const mergeThematicWorldLibraries = (baseLibrary = [], externalLibrary = []) => {
  const existingNames = new Set(baseLibrary.map(world => world.name.toLowerCase().trim()));
  const uniqueAdditions = externalLibrary.filter(world => {
    if (!world?.name) return false;
    const key = world.name.toLowerCase().trim();
    if (existingNames.has(key)) return false;
    existingNames.add(key);
    return true;
  });
  return [...baseLibrary, ...uniqueAdditions];
};

// WHAT: Asynchronously imports or fetches external thematic worlds from an ES module or JSON endpoint.
// WHY: Enables loading custom world definition files dynamically at runtime without restarting or re-bundling.
export async function loadExternalThematicWorlds(resourcePath = "./thematic-worlds-extended.js") {
  try {
    if (resourcePath.endsWith(".js")) {
      const module = await import(resourcePath);
      const items = module.EXTENDED_THEMATIC_WORLDS || module.default || module.THEMATIC_WORLDS || [];
      return Array.isArray(items) ? items : [];
    }
    const response = await fetch(resourcePath);
    if (!response.ok) return [];
    const parsedData = await response.json();
    return Array.isArray(parsedData) ? parsedData : [];
  } catch {
    return [];
  }
}

// WHAT: Canonical domain library of curated aesthetic worlds, keywords, and signature vocabulary pools.
// WHY: Acts as the reference knowledge base for semantic prompt scoring and vocabulary compilation across
// five production dimensions: Settings, Lighting, Mechanisms, Costume, and Practical Effects.
// Merges the core built-in worlds with extended worlds loaded from external modules or files.
export const THEMATIC_WORLDS_LIBRARY = mergeThematicWorldLibraries(
  BUILTIN_THEMATIC_WORLDS_LIBRARY,
  EXTENDED_THEMATIC_WORLDS
);

// WHAT: High-frequency English grammatical function words (articles, prepositions, conjunctions, pronouns, auxiliaries).
// WHY: In natural language prompt classification, these grammatical "glue" words appear universally regardless of
// subject matter. Removing them ensures the world scoring algorithm isolates domain-specific nouns, adjectives, and
// evocative visual keywords (e.g. "concrete", "fluorescent", "neon", "decay") rather than artificially inflating scores
// based on sentence length or triggering accidental prefix and substring matches against thematic keywords.
const PROMPT_STOPWORDS = new Set([
  "the", "and", "that", "this", "with", "from", "for", "through", "into", "over",
  "under", "about", "your", "they", "them", "their", "have", "been", "were",
  "will", "would", "could", "should", "some", "what", "when", "where", "which"
]);

// WHAT: Normalizes raw keyword/token match points into a calibrated 0.00–1.00 similarity score.
// WHY: Raw scores scale with prompt verbosity and keyword counts. Non-linear piecewise interpolation
// maps the score relative to the top candidate (maxRaw) into distinct tiers (0.80+, 0.55–0.80, 0.30–0.55),
// ensuring readable percentages on meters and clear separation between leading and trailing matches.
const normalizeRawScore = (rawScore, maxRaw, idx) => {
  if (maxRaw <= 0) {
    return Math.max(0.20, Number((0.75 - idx * 0.12).toFixed(2)));
  }
  const ratio = rawScore / maxRaw;
  if (ratio > 0.8) return 0.80 + (ratio - 0.8) * 0.75;
  if (ratio > 0.4) return 0.55 + (ratio - 0.4) * 0.625;
  if (ratio > 0) return 0.30 + ratio * 0.625;
  return Math.max(0.15, 0.28 - idx * 0.03);
};

// WHAT: Pre-computed lowercase keyword and signature pool term caches for high-frequency prompt scoring.
// WHY: Avoids re-mapping arrays, re-lowercasing strings, and flattening pool arrays on every keystroke/scoring call.
const worldScoreCache = new WeakMap();

const getWorldIndex = (world) => {
  let cached = worldScoreCache.get(world);
  if (!cached) {
    const keywords = (world.keywords || []).map(k => k.toLowerCase());
    const keywordsSet = new Set(keywords);
    const flattenedPools = Object.values(world.pools || {}).flat().map(t => t.toLowerCase());
    cached = {
      nameLower: world.name.toLowerCase(),
      keywords,
      keywordsSet,
      flattenedPools
    };
    worldScoreCache.set(world, cached);
  }
  return cached;
};

// WHAT: Calculates the composite raw semantic affinity score of a world against a user prompt.
// WHY: Combines three complementary retrieval signals:
//   1. Full multi-word and hyphenated keyword phrase occurrences in the raw text (highest confidence).
//   2. Individual token exact matches and prefix stems against world names and keywords.
//   3. Exact matches against signature vocabulary pool terms across all five dimensions.
const computeWorldRawScore = (world, rawText, meaningfulTokens) => {
  const { nameLower, keywords, keywordsSet, flattenedPools } = getWorldIndex(world);

  // WHAT: Score full multi-word or hyphenated keyword phrases found in the prompt string.
  // WHY: Multi-word phrases like "night-shift" or "evidence locker" carry stronger thematic specificity than single tokens.
  const keywordMatchScore = keywords.reduce(
    (sum, kw) => sum + (rawText.includes(kw) ? ((kw.includes(" ") || kw.includes("-")) ? 4.5 : 3.0) : 0),
    0
  );

  // WHAT: Score token overlap, exact keyword matches, and morphological prefix stems.
  // WHY: Rewards prompts containing exact tokens or shared root words (e.g., "brutal" matching "brutalist")
  // while weighting world title matches more heavily.
  const tokenMatchScore = meaningfulTokens.reduce((sum, tok) => {
    const nameBonus = nameLower.includes(tok) ? 2.5 : 0;
    const exactMatch = keywordsSet.has(tok);
    const prefixMatch = !exactMatch && tok.length >= 4 && keywords.some(kw => kw.startsWith(tok) || tok.startsWith(kw));
    const kwBonus = exactMatch ? 2.0 : prefixMatch ? 1.0 : 0;
    return sum + nameBonus + kwBonus;
  }, 0);

  // WHAT: Score exact matches against world signature pool items.
  // WHY: If a prompt mentions specific props or settings (e.g. "pneumatic tube"), that strongly anchors the world.
  const poolMatchScore = flattenedPools.reduce(
    (sum, termLower) => sum + (rawText.includes(termLower) ? 2.0 : 0),
    0
  );

  return keywordMatchScore + tokenMatchScore + poolMatchScore;
};

// WHAT: Classifies and ranks library worlds against input text, preserving director-locked selections.
// WHY: Enables automated stylistic world discovery from song briefs, director notes, or lyrics while
// guaranteeing that worlds manually locked by the user are never dropped or replaced during re-analysis.
export const scorePromptAgainstWorlds = (promptText, currentWorlds = [], library = THEMATIC_WORLDS_LIBRARY) => {
  const rawText = String(promptText || "").toLowerCase().trim();
  // WHAT: Fallback to baseline library ranking when prompt text is empty.
  // WHY: Keeps UI functional and predictable before the user enters analysis text.
  if (!rawText) {
    return library.slice(0, 4).map((w, i) => {
      const existing = currentWorlds.find(cw => cw.name === w.name);
      return {
        name: w.name,
        score: existing ? existing.score : Number((0.75 - i * 0.15).toFixed(2)),
        active: existing ? existing.active : i < 2,
        locked: existing ? existing.locked : false
      };
    });
  }

  // WHAT: Sanitize and tokenize input text into clean, content-bearing words.
  // WHY: Stripping punctuation, splitting on whitespace, discarding words of length <= 2, and filtering
  // out PROMPT_STOPWORDS isolates semantically rich visual tokens and eliminates false-positive world matches.
  const meaningfulTokens = rawText
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter(t => t.length > 2 && !PROMPT_STOPWORDS.has(t));

  const scored = library
    .map(world => ({
      world,
      rawScore: computeWorldRawScore(world, rawText, meaningfulTokens)
    }))
    .toSorted((a, b) => b.rawScore - a.rawScore);

  const maxRaw = Math.max(...scored.map(s => s.rawScore), 0);

  const ranked = scored.map((item, idx) => {
    const normalizedScore = normalizeRawScore(item.rawScore, maxRaw, idx);
    const finalScore = Number(Math.min(0.98, Math.max(0.12, normalizedScore)).toFixed(2));
    const existing = currentWorlds.find(cw => cw.name === item.world.name);

    return {
      name: item.world.name,
      score: finalScore,
      active: existing?.locked ? existing.active : idx < 2,
      locked: existing ? existing.locked : false
    };
  });

  // WHAT: Select the top 4 ranked candidate worlds plus any user-locked worlds.
  // WHY: Guarantees a minimum cluster of 4 worlds for comparison while honoring user overrides.
  const selectedFromRanked = ranked
    .filter((item, idx) => idx < 4 || item.locked)
    .map(item => ({ name: item.name, score: item.score, active: item.active, locked: item.locked }));

  // WHAT: Ensure all locked worlds from the previous state are preserved even if ranked outside the top 4.
  // WHY: A locked world is an explicit director choice and must remain active in the workspace.
  const addedNames = new Set(selectedFromRanked.map(item => item.name));
  const lockedWorlds = currentWorlds.filter(w => w.locked);
  const missingLocked = lockedWorlds
    .filter(locked => !addedNames.has(locked.name))
    .map(locked => ({
      name: locked.name,
      score: locked.score || 0.50,
      active: locked.active,
      locked: true
    }));

  return [...selectedFromRanked, ...missingLocked]
    .toSorted((a, b) => b.score - a.score)
    .slice(0, Math.max(4, lockedWorlds.length));
};

// WHAT: Standard visual vocabulary dimensions and baseline terms-per-dimension requirements.
// WHY: A balanced production requires diversity across environment, lighting, kinetic action, wardrobe,
// and practical effects. These target counts prevent vocabulary exhaustion during multi-passage generation.
const POOL_DIMENSIONS = [
  { name: "Settings", defaultNeed: 9 },
  { name: "Lighting", defaultNeed: 6 },
  { name: "Mechanisms", defaultNeed: 10 },
  { name: "Costume", defaultNeed: 6 },
  { name: "Practical Effects", defaultNeed: 5 }
];

// WHAT: Deduplicates an array of keyword strings case-insensitively, preserving original casing.
// WHY: Uses an internal Set lookup to achieve linear O(N) deduplication without allocating O(N^2) intermediate arrays.
const uniqueCaseInsensitive = (terms = []) => {
  const seen = new Set();
  return terms.filter(term => {
    const lower = String(term || "").toLowerCase().trim();
    if (!lower || seen.has(lower)) return false;
    seen.add(lower);
    return true;
  });
};

// WHAT: Merges and compiles visual vocabulary pools from all currently activated thematic worlds.
// WHY: When a director activates one or more worlds (e.g. "Brutalist Concrete" + "Bureaucratic"), their
// signature terms are extracted per dimension, deduplicated against existing pool terms, and sized against
// the target need count to provide a coherent visual aesthetic.
export const compilePoolsFromActiveWorlds = (activeWorldNames = [], currentPools = [], library = THEMATIC_WORLDS_LIBRARY) => {
  const activeSet = new Set(activeWorldNames);
  const activeWorlds = library.filter(w => activeSet.has(w.name));

  if (activeWorlds.length === 0) {
    return (currentPools.length ? currentPools : DEFAULT_POOLS).map(p => ({
      ...p,
      terms: [...p.terms],
      chipStates: p.chipStates ? { ...p.chipStates } : {}
    }));
  }

  return POOL_DIMENSIONS.map(dim => {
    const existingPool = currentPools.find(p => p.dimension.toLowerCase() === dim.name.toLowerCase());
    const existingTerms = existingPool ? existingPool.terms : [];
    const existingChipStates = existingPool?.chipStates ? { ...existingPool.chipStates } : {};
    const need = existingPool ? existingPool.need : dim.defaultNeed;

    const rawWorldTerms = activeWorlds.flatMap(world => world.pools?.[dim.name] || []);
    const worldTerms = [...new Set(rawWorldTerms)];

    const mergedTerms = uniqueCaseInsensitive([...worldTerms, ...existingTerms]);

    return {
      dimension: dim.name,
      pool: mergedTerms.length,
      need,
      terms: mergedTerms,
      baseTermCount: worldTerms.length,
      chipStates: existingChipStates
    };
  });
};

// WHAT: Standard song structure sections paired with their baseline juxtaposition coefficients (kappa, κ).
// WHY: Verse and outro sections have low baseline juxtaposition (κ = 0.05–0.20) to ground core imagery,
// while choruses and bridges allow elevated juxtaposition (κ = 0.75–0.90) for peak musical and visual energy.
export const DEFAULT_SECTIONS = [
  { name: "Verse 1", baseKappa: 0.08 },
  { name: "Pre-chorus", baseKappa: 0.35 },
  { name: "Chorus", baseKappa: 0.75 },
  { name: "Verse 2", baseKappa: 0.20 },
  { name: "Bridge", baseKappa: 0.90 },
  { name: "Final chorus", baseKappa: 0.80 },
  { name: "Outro", baseKappa: 0.05 }
];

// WHAT: Pre-seeded fallback vocabulary pools across the five dimensions with initial terms and targets.
// WHY: Provides valid initial chips and status badges before dynamic world compilation or project loading.
export const DEFAULT_POOLS = [
  {
    dimension: "Settings",
    pool: 14,
    need: 9,
    baseTermCount: 4,
    terms: ["evidence locker", "sodium-lit stairwell", "records annex", "flooded basement"]
  },
  {
    dimension: "Lighting",
    pool: 11,
    need: 6,
    baseTermCount: 3,
    terms: ["flickering fluorescent tube", "single desk lamp", "amber exit signs"]
  },
  {
    dimension: "Mechanisms",
    pool: 17,
    need: 10,
    baseTermCount: 3,
    terms: ["pneumatic tube dispatch", "card-catalogue drawers sliding", "stamp descending"]
  },
  {
    dimension: "Costume",
    pool: 4,
    need: 6,
    baseTermCount: 2,
    terms: ["grey wool cardigan", "laminated lanyard"]
  },
  {
    dimension: "Practical Effects",
    pool: 9,
    need: 5,
    baseTermCount: 2,
    terms: ["drifting paper dust", "steam from a vent"]
  }
];

// WHAT: Instructional copy describing the operational behavior of the three vocabulary sampling modes.
// WHY: Informs the director how world constraints influence random keyword selection in prompt generation.
export const MODE_DESCRIPTIONS = {
  off: "Sampling from the entire visual vocabulary pool. Thematic worlds and juxtaposition levels are ignored.",
  guided: "Matched thematic worlds are weighted up. Diverse strays remain possible across musical passages.",
  strict: "Strictly confined to matched anchor worlds plus kappa-governed strays on high-energy sections."
};

// WHAT: Sanitizes raw strings by replacing HTML metacharacters with XML entity references.
// WHY: Prevents XSS injection and DOM syntax breakages when interpolating user-supplied strings into markup.
const escapeHtml = (s = "") =>
  s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

// WHAT: Calculates the dynamic juxtaposition coefficient (κ) for a section scaled by the director slider.
// WHY: The UI slider acts as a 0.0x–2.0x multiplier centered at 50% (1.0x). Scaling base section kappa by
// 2 * (slider / 100) and clamping to [0.0, 1.0] gives smooth, musically responsive thematic variance.
export const computeEffectiveKappa = (baseKappa, sliderValue) => {
  const s = sliderValue / 100;
  return Math.max(0, Math.min(1, baseKappa * 2 * s));
};

// WHAT: Generates HTML markup for the thematic worlds list, similarity score meters, and lock controls.
// WHY: Pure template renderer that decouples markup generation from DOM attachment, maintaining zero side effects
// and deterministic rendering from input state.
export const renderWorldsHtml = (worlds, isOff) => {
  if (!worlds.length) return `<div class="sub">No worlds matched.</div>`;
  const items = worlds.map((w, i) => {
    const checked = w.active ? "checked" : "";
    const pct = Math.round(w.score * 100);
    const lockIcon = w.locked ? "🔒" : "🔓";
    const lockTitle = w.locked ? "Locked to prevent prompt overwrite" : "Lock this world";
    return `
      <div class="worlds-cluster-row" data-index="${i}">
        <label class="worlds-cluster-label">
          <input type="checkbox" class="worlds-cluster-check" data-index="${i}" ${checked} ${isOff ? "disabled" : ""}>
          <span class="worlds-cluster-name">${escapeHtml(w.name)}</span>
        </label>
        <div class="worlds-meter-track" data-tooltip="Semantic similarity score: ${w.score.toFixed(2)}">
          <span class="worlds-meter-fill" style="width:${pct}%;"></span>
        </div>
        <span class="worlds-score-val">${w.score.toFixed(2)}</span>
        <button type="button" class="worlds-lock-btn quiet" data-index="${i}" data-tooltip="${lockTitle}" ${isOff ? "disabled" : ""}>
          ${lockIcon}
        </button>
      </div>
    `;
  }).join("");

  const margin = worlds.length >= 2 ? (worlds[0].score - worlds[1].score).toFixed(2) : "0.00";
  const gapNote = `<div class="sub worlds-gap-note">Top match leads the next by ${margin}, indicating a strong thematic anchor.</div>`;

  return items + gapNote;
};

// WHAT: Generates HTML markup for the musical juxtaposition arc bar chart and slider multiplier badge.
// WHY: Visualizes the dynamic juxtaposition coefficient (κ) across song sections, highlighting sections
// with κ >= 0.90 ("hot-bar") where aesthetic tier adjacency rules are suspended for dramatic contrast.
export const renderBarsHtml = (sections, sliderValue, mode) => {
  const isOff = mode === "off";
  const s = sliderValue / 100;
  const multText = `x${(2 * s).toFixed(1)}`;

  const bars = sections.map((sec) => {
    const effKappa = isOff ? 0 : computeEffectiveKappa(sec.baseKappa, sliderValue);
    const heightPx = isOff ? 2 : Math.max(2, Math.round(effKappa * 72));
    const isHot = !isOff && effKappa >= 0.90;
    const hotClass = isHot ? " hot-bar" : "";
    const valDisplay = isOff ? "—" : effKappa.toFixed(2);
    const tooltipText = `${sec.name}: κ = ${valDisplay}${isHot ? " (Tier adjacency suspended)" : ""}`;

    return `
      <div class="worlds-bar-col" data-tooltip="${tooltipText}">
        <div class="worlds-bar-val">${valDisplay}</div>
        <div class="worlds-bar-visual-wrap">
          <div class="worlds-bar-visual${hotClass}" style="height:${heightPx}px;"></div>
        </div>
        <div class="worlds-bar-label">${escapeHtml(sec.name)}</div>
      </div>
    `;
  }).join("");

  return { barsHtml: bars, multiplierText: multText };
};

// WHAT: Maps UI dimension display labels (e.g. "Practical Effects") to snake_case category dictionary keys.
// WHY: Ensures uniform lookup keys when querying the core vocabulary catalog and compiling custom vocab payloads.
export const dimensionToCategoryKey = (dim) => {
  const normalized = String(dim || "").toLowerCase().trim();
  const map = {
    settings: "settings",
    lighting: "lighting",
    mechanisms: "mechanisms",
    costume: "costume",
    "practical effects": "practical_effects",
    practical_effects: "practical_effects"
  };
  return map[normalized] || normalized.replace(/\s+/g, "_");
};

// WHAT: Derives term counts (active, pinned, excluded), effective pool size, and shortage status for a pool.
// WHY: Centralizes pool arithmetic and shortage detection for status badges, borrowing triggers, and
// custom vocabulary compilation without reading from or writing to the DOM.
export const computePoolCounts = (pool, borrowed = false) => {
  const terms = pool.terms || [];
  const chipStates = pool.chipStates || {};
  const excludedCount = terms.reduce(
    (acc, term) => acc + (Number(chipStates[term] || 0) === 2 ? 1 : 0),
    0
  );
  const pinnedCount = terms.reduce(
    (acc, term) => acc + (Number(chipStates[term] || 0) === 1 ? 1 : 0),
    0
  );
  const activeTermCount = Math.max(0, terms.length - excludedCount);
  const isCostume = pool.dimension === "Costume";
  const baseCount = typeof pool.pool === "number" ? Math.max(pool.pool, terms.length) : terms.length;
  const currentPoolCount = Math.max(
    0,
    ((isCostume && borrowed) ? Math.max(9, baseCount) : baseCount) - excludedCount
  );
  const need = Number(pool.need || 0);
  const selectedTowardsNeed = pinnedCount;
  const remainingNeeded = Math.max(0, need - selectedTowardsNeed);
  return {
    currentPoolCount,
    activeTermCount,
    pinnedCount,
    selectedTowardsNeed,
    excludedCount,
    need,
    remainingNeeded,
    isLow: remainingNeeded > 0 && currentPoolCount < need
  };
};

// WHAT: Formats human-readable pool status strings showing available terms, required terms, and selection counts.
// WHY: Provides immediate feedback in the pool header on whether a dimension has sufficient term variety.
export const formatPoolStatusText = (pool, borrowed = false) => {
  const { currentPoolCount, selectedTowardsNeed, need, remainingNeeded } = computePoolCounts(pool, borrowed);
  const isCostume = pool.dimension === "Costume";
  const borrowedNote = (isCostume && borrowed) ? " (borrowed from Brutalist concrete)" : "";
  if (selectedTowardsNeed > 0) {
    if (remainingNeeded === 0) {
      return `${currentPoolCount} in pool, 0 needed (${selectedTowardsNeed} selected)${borrowedNote}`;
    }
    return `${currentPoolCount} in pool, ${remainingNeeded} needed (${selectedTowardsNeed}/${need} selected)${borrowedNote}`;
  }
  return `${currentPoolCount} in pool, ${need} needed${borrowedNote}`;
};

const CHIP_STATE_LABELS = ["Included (default)", "Pinned (forced into rotation)", "Excluded (blocked from rotation)"];
const CHIP_TOOLTIP = "Click to cycle: Included → Pinned (must appear) → Excluded";

// WHAT: Generates HTML markup for all five vocabulary pool rows, interactive term chips, and catalog dropdowns.
// WHY: Renders the complete visual vocabulary workbench based purely on input pools, borrowed state, and catalog data.
export const renderPoolsHtml = (pools, borrowed, catalog = null) => {
  return pools.map((p, poolIdx) => {
    const { isLow } = computePoolCounts(p, borrowed);
    const lowClass = isLow ? " pool-low" : "";
    const statusText = formatPoolStatusText(p, borrowed);
    const borrowBtn = isLow
      ? `<button type="button" class="quiet worlds-borrow-btn" data-pool="${poolIdx}" data-tooltip="Temporarily borrow terms from the nearest semantic world">Borrow from nearest world</button>`
      : "";

    const chips = p.terms.map((term, termIdx) => {
      const chipState = Number(p.chipStates?.[term] || 0);
      const stateClass = chipState === 1 ? " pin" : chipState === 2 ? " ex" : "";
      return `<button type="button" class="worlds-term-chip${stateClass}" data-pool="${poolIdx}" data-term="${termIdx}" data-state="${chipState}" data-tooltip="${CHIP_TOOLTIP}" title="${CHIP_STATE_LABELS[chipState] || CHIP_STATE_LABELS[0]}">${escapeHtml(term)}</button>`;
    }).join("");

    const catKey = dimensionToCategoryKey(p.dimension);
    const catalogItems = catalog?.base?.[catKey] || [];
    const existingTermsSet = new Set(p.terms.map(t => t.toLowerCase().trim()));
    const candidateTerms = catalogItems
      .filter(item => !existingTermsSet.has(item.toLowerCase().trim()))
      .toSorted((a, b) => a.localeCompare(b));

    const dropdownHtml = candidateTerms.length > 0
      ? `
        <select class="worlds-select-term-dropdown" data-pool="${poolIdx}" data-tooltip="Add a relevant built-in ${escapeHtml(p.dimension)} term to this pool" aria-label="Add built-in ${escapeHtml(p.dimension)} term">
          <option value="">+ Add from ${escapeHtml(p.dimension)} catalog (${candidateTerms.length})…</option>
          ${candidateTerms.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")}
        </select>
      `
      : "";

    return `
      <div class="worlds-pool-dimension-row">
        <div class="worlds-pool-dim-header">
          <span class="worlds-pool-dim-title">${escapeHtml(p.dimension)}</span>
          <span class="sub${lowClass}" data-pool-status="${poolIdx}">${statusText}</span>
          ${borrowBtn}
        </div>
        <div class="worlds-chips-wrap">
          ${chips}
          <button type="button" class="worlds-term-chip worlds-add-term-btn" data-pool="${poolIdx}" data-tooltip="Type a custom keyword to add to this world pool">+ Add custom</button>
          ${dropdownHtml}
        </div>
      </div>
    `;
  }).join("");
};

// WHAT: Partitions pool keywords into pinned, excluded, and standard included arrays based on chip states.
// WHY: Decouples UI chip button state from backend rule compilation, supporting DOM-rendered chips when present
// or in-memory pool data structures during headless execution.
const partitionPoolTerms = (pool, poolIdx, domContainer) => {
  const chips = domContainer
    ? [...domContainer.querySelectorAll(`.worlds-term-chip[data-pool="${poolIdx}"]`)]
        .filter(chip => !chip.classList.contains("worlds-add-term-btn"))
    : [];

  const entries = chips.length > 0
    ? chips.map(chip => ({
        term: chip.textContent.trim(),
        chipState: Number(chip.dataset.state || 0)
      }))
    : (pool.terms || []).map(term => ({
        term,
        chipState: Number(pool.chipStates?.[term] || 0)
      }));

  const pinned = [];
  const excluded = [];
  const included = [];
  for (const { term, chipState } of entries) {
    if (chipState === 2) excluded.push(term);
    else if (chipState === 1) pinned.push(term);
    else included.push(term);
  }
  return { pinned, excluded, included };
};

// WHAT: Compiles active pools, sampling mode, and chip states into engine-compatible custom vocabulary schema rules.
// WHY: In "strict" mode, replaces the category pool with pinned and included terms while enforcing exclusions.
// In "guided" mode, appends pinned terms to the catalog while excluding blacklisted items.
// In "off" mode, returns an empty mapping so standard vocabulary sampling is used.
export const compileWorldsToCustomVocab = (pools, mode, domContainer = null) => {
  if (mode === "off") return {};

  const result = {};
  for (let poolIdx = 0; poolIdx < pools.length; poolIdx++) {
    const pool = pools[poolIdx];
    const key = dimensionToCategoryKey(pool.dimension);
    const { pinned, excluded, included } = partitionPoolTerms(pool, poolIdx, domContainer);

    if (mode === "strict") {
      const activePool = [...pinned, ...included];
      if (activePool.length > 0) {
        result[key] = { mode: "replace", add: activePool, exclude: excluded };
      }
    } else if (mode === "guided") {
      result[key] = {
        mode: "append",
        add: [...pinned],
        exclude: excluded
      };
    }
  }
  return result;
};

// WHAT: Pure state transition toggling the locked status of a world by index.
// WHY: Locked worlds are protected from being discarded or overwritten during automated prompt re-analysis.
export const toggleWorldLock = (worlds, index) =>
  worlds.map((world, idx) => (idx === index ? { ...world, locked: !world.locked } : world));

// WHAT: Pure state transition toggling the active status of a world by index.
// WHY: Controls whether the world's signature terms are pooled into the active visual vocabulary.
export const setWorldActive = (worlds, index, active) =>
  worlds.map((world, idx) => (idx === index ? { ...world, active: Boolean(active) } : world));

// WHAT: Pure state transition cycling a term's chip state between default (0), pinned (1), and excluded (2).
// WHY: Updates keyword lifecycle rules without mutating the input pools array in place.
export const setPoolChipState = (pools, poolIdx, term, nextState) =>
  pools.map((pool, idx) => {
    if (idx !== poolIdx) return pool;
    const currentChipStates = { ...(pool.chipStates || {}) };
    if (nextState === 0) {
      const { [term]: _, ...remainingStates } = currentChipStates;
      return { ...pool, chipStates: remainingStates };
    }
    return { ...pool, chipStates: { ...currentChipStates, [term]: nextState } };
  });

// WHAT: Pure state transition adding a custom or catalog keyword to a pool and pinning it.
// WHY: Injects bespoke director terminology into a visual dimension and marks it pinned so it is guaranteed to rotate.
export const addTermToPool = (pools, poolIdx, rawTerm) => {
  const cleaned = String(rawTerm || "").trim();
  if (!cleaned) return pools;
  return pools.map((pool, idx) => {
    if (idx !== poolIdx) return pool;
    const currentChipStates = { ...(pool.chipStates || {}), [cleaned]: 1 };
    if (pool.terms.includes(cleaned)) {
      return {
        ...pool,
        chipStates: currentChipStates
      };
    }
    return {
      ...pool,
      terms: [...pool.terms, cleaned],
      pool: (typeof pool.pool === "number" ? pool.pool : pool.terms.length) + 1,
      chipStates: currentChipStates
    };
  });
};

// WHAT: Restores and normalizes the worlds array from saved project state or legacy pre-1.11.5 drafts.
// WHY: Guarantees backward compatibility when loading older project files that only stored active world names.
export const restoreWorlds = (saved, defaults = DEFAULT_WORLDS) => {
  if (Array.isArray(saved?.worlds) && saved.worlds.length) return saved.worlds.map(w => ({ ...w }));
  if (!Array.isArray(saved?.activeWorlds)) return defaults.map(w => ({ ...w }));
  const active = new Set(saved.activeWorlds);
  const known = new Set(defaults.map(w => w.name));
  return [
    ...defaults.map(w => ({ ...w, active: active.has(w.name) })),
    ...saved.activeWorlds.filter(name => !known.has(name)).map(name => ({ name, score: 0.5, active: true, locked: false }))
  ];
};

// WHAT: Deep clones a pools array and nested chip states dictionaries.
// WHY: Prevents UI interactions in the workbench from accidentally mutating global state or defaults.
const clonePools = (pools) =>
  pools.map(pool => ({
    ...pool,
    terms: [...(pool.terms || [])],
    chipStates: pool.chipStates ? { ...pool.chipStates } : {}
  }));

// WHAT: Initializes the interactive Thematic Worlds workspace, wiring UI events and mounting view components.
// WHY: Acts as the imperative shell boundary for this module: isolates DOM mutation, user click/input events,
// and async catalog fetching while delegating all computational logic and markup generation to pure functions.
export function initVocabWorlds() {
  const container = $("#vocab-worlds-workspace");
  if (!container) return;

  let catalogCache = null;

  // WHAT: Local mutable state container for the interactive workspace session.
  // WHY: Encapsulates draft adjustments (mode, slider, borrowed terms, pools) before the director applies them.
  const state = {
    mode: appState.thematicWorlds?.mode || "guided",
    slider: typeof appState.thematicWorlds?.slider === "number" ? appState.thematicWorlds.slider : 50,
    borrowed: false,
    worlds: restoreWorlds(appState.thematicWorlds),
    sections: DEFAULT_SECTIONS.map(s => ({ ...s })),
    pools: clonePools(
      Array.isArray(appState.thematicWorlds?.pools) ? appState.thematicWorlds.pools : DEFAULT_POOLS
    )
  };

  // WHAT: Pre-loads the full visual vocabulary catalog from the server.
  // WHY: Populates catalog dropdowns so directors can immediately browse and add built-in category terms.
  loadVocabularyCatalog()
    .then((cat) => {
      catalogCache = cat;
      updateView();
    })
    .catch(() => {});

  const promptInput = $("#worlds-prompt-input");
  if (promptInput) {
    if (appState.thematicWorlds?.prompt) {
      promptInput.value = appState.thematicWorlds.prompt;
    } else if (!promptInput.value.trim()) {
      const dirVal = document.querySelector("#video-form [name='direction']")?.value;
      if (dirVal) promptInput.value = dirVal.trim();
    }
    promptInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        const btn = $("#worlds-process-prompt-btn");
        if (btn) btn.click();
      }
    });
  }

  // WHAT: Renders and synchronizes all DOM sub-components against current local state.
  // WHY: Provides an idempotent render cycle called after any state transition (mode change, lock, chip cycle).
  const updateView = () => {
    const isOff = state.mode === "off";

    // Mode segmented buttons
    $$(".worlds-mode-btn").forEach(btn => {
      btn.classList.toggle("on", btn.dataset.mode === state.mode);
    });

    // Mode note
    const noteEl = $("#worlds-mode-note");
    if (noteEl) noteEl.textContent = MODE_DESCRIPTIONS[state.mode] || "";

    // Slider
    const sliderEl = $("#worlds-juxtaposition-slider");
    if (sliderEl) {
      sliderEl.value = String(state.slider);
      sliderEl.disabled = isOff;
    }

    // Clusters
    const clustersEl = $("#worlds-clusters-list");
    if (clustersEl) {
      clustersEl.innerHTML = renderWorldsHtml(state.worlds, isOff);
    }

    // Bars
    const barsContainer = $("#worlds-kappa-bars");
    const multSpan = $("#worlds-slider-multiplier");
    if (barsContainer && multSpan) {
      const { barsHtml, multiplierText } = renderBarsHtml(state.sections, state.slider, state.mode);
      barsContainer.innerHTML = barsHtml;
      multSpan.textContent = multiplierText;
    }

    // Pools
    const poolsContainer = $("#worlds-pools-list");
    if (poolsContainer) {
      poolsContainer.innerHTML = renderPoolsHtml(state.pools, state.borrowed, catalogCache);
    }

    // Footer summary pill
    const summaryStatus = $("#worlds-summary-status");
    if (summaryStatus) {
      if (state.mode === "off") {
        summaryStatus.textContent = "Mode: Off (Uniform visual vocabulary sampling)";
      } else {
        const modeLabel = state.mode.charAt(0).toUpperCase() + state.mode.slice(1);
        const activeCount = state.worlds.filter(w => w.active).length;
        const mult = (2 * (state.slider / 100)).toFixed(1);
        summaryStatus.textContent = `Mode: ${modeLabel} · ${activeCount} world(s) active · Juxtaposition x${mult}`;
      }
    }
  };

  // WHAT: Centralized click handler using event delegation on the root workspace container.
  // WHY: Efficiently routes user interactions (analysis, modes, locks, borrowing, chip cycling, saving, reset)
  // without attaching hundreds of listeners to individual dynamic elements.
  container.addEventListener("click", event => {
    const processBtn = event.target.closest("#worlds-process-prompt-btn");
    if (processBtn) {
      const promptEl = $("#worlds-prompt-input");
      const text = (promptEl?.value || "").trim();
      if (!text) {
        notice("Please enter a song premise or thematic direction to analyze.");
        if (promptEl) promptEl.focus();
        return;
      }

      const scoredWorlds = scorePromptAgainstWorlds(text, state.worlds, THEMATIC_WORLDS_LIBRARY);
      state.worlds = scoredWorlds;

      const activeNames = scoredWorlds.filter(w => w.active).map(w => w.name);
      state.pools = compilePoolsFromActiveWorlds(activeNames, state.pools, THEMATIC_WORLDS_LIBRARY);

      updateView();

      const topWorld = scoredWorlds[0];
      const secondWorld = scoredWorlds[1];
      if (topWorld && secondWorld) {
        notice(`⚡ Analyzed prompt: Matched "${topWorld.name}" (${topWorld.score.toFixed(2)}) & "${secondWorld.name}" (${secondWorld.score.toFixed(2)}).`);
      } else if (topWorld) {
        notice(`⚡ Analyzed prompt: Matched "${topWorld.name}" (${topWorld.score.toFixed(2)}).`);
      }
      return;
    }

    const modeBtn = event.target.closest(".worlds-mode-btn");
    if (modeBtn) {
      state.mode = modeBtn.dataset.mode;
      updateView();
      return;
    }

    const lockBtn = event.target.closest(".worlds-lock-btn");
    if (lockBtn) {
      const idx = Number(lockBtn.dataset.index);
      if (state.worlds[idx]) {
        state.worlds = toggleWorldLock(state.worlds, idx);
        updateView();
      }
      return;
    }

    const borrowBtn = event.target.closest(".worlds-borrow-btn");
    if (borrowBtn) {
      state.borrowed = true;
      notice("Borrowed 5 complementary wardrobe terms from adjacent Brutalist world.");
      updateView();
      return;
    }

    const termChip = event.target.closest(".worlds-term-chip");
    if (termChip && !termChip.classList.contains("worlds-add-term-btn")) {
      const currentState = Number(termChip.dataset.state || 0);
      const nextState = (currentState + 1) % 3;
      termChip.dataset.state = String(nextState);
      termChip.classList.toggle("pin", nextState === 1);
      termChip.classList.toggle("ex", nextState === 2);
      termChip.title = CHIP_STATE_LABELS[nextState];
      const poolIdx = Number(termChip.dataset.pool);
      const term = termChip.textContent.trim();
      const targetPool = state.pools[poolIdx];
      if (targetPool && term) {
        state.pools = setPoolChipState(state.pools, poolIdx, term, nextState);
        const updatedPool = state.pools[poolIdx];
        const statusEl = container.querySelector(`[data-pool-status="${poolIdx}"]`);
        if (statusEl && updatedPool) {
          const { isLow } = computePoolCounts(updatedPool, state.borrowed);
          if (isLow !== statusEl.classList.contains("pool-low")) {
            updateView();            // the Borrow button comes and goes with a shortage; chip states survive the redraw
          } else {
            statusEl.textContent = formatPoolStatusText(updatedPool, state.borrowed);
          }
        }
      }
      return;
    }

    const addBtn = event.target.closest(".worlds-add-term-btn");
    if (addBtn) {
      const poolIdx = Number(addBtn.dataset.pool);
      const targetPool = state.pools[poolIdx];
      const input = targetPool ? prompt(`Enter a custom term to add to the ${targetPool.dimension} pool:`) : "";
      if (input && input.trim() && targetPool) {
        const cleaned = input.trim();
        state.pools = addTermToPool(state.pools, poolIdx, cleaned);
        updateView();
        notice(`Added "${cleaned}" to ${targetPool.dimension} pool.`);
      }
      return;
    }

    const applyBtn = event.target.closest("#worlds-apply-btn");
    if (applyBtn) {
      const promptText = ($("#worlds-prompt-input")?.value || "").trim();
      const activeWorlds = state.worlds.filter(w => w.active).map(w => w.name);

      if (state.mode === "off") {
        appState.thematicWorlds = null;
        updateVocabCustomBadge();
        scheduleSave();
        notice("Thematic Worlds set to Off. Visual vocabulary reverted to standard sampling.");
        const videoNavBtn = $(".nav[data-panel='video']");
        if (videoNavBtn) videoNavBtn.click();
        return;
      }

      const compiledDraft = compileWorldsToCustomVocab(state.pools, state.mode, $("#worlds-pools-list"));
      appState.currentCustomVocab = compiledDraft;
      appState.currentVocabRandomKey = "";
      appState.thematicWorlds = {
        prompt: promptText,
        mode: state.mode,
        slider: state.slider,
        activeWorlds,
        worlds: state.worlds,
        pools: state.pools
      };

      updateVocabCustomBadge();
      scheduleSave();

      const modeLabel = state.mode.charAt(0).toUpperCase() + state.mode.slice(1);
      const mult = (2 * (state.slider / 100)).toFixed(1);
      notice(`🧭 Applied Thematic Worlds (${modeLabel}, juxtaposition x${mult}) to active video.`);

      const videoNavBtn = $(".nav[data-panel='video']");
      if (videoNavBtn) videoNavBtn.click();
      return;
    }

    const resetBtn = event.target.closest("#worlds-reset-btn");
    if (resetBtn) {
      if (!window.confirm("Reset Thematic Worlds back to defaults?")) return;
      state.mode = "guided";
      state.slider = 50;
      state.borrowed = false;
      state.worlds = DEFAULT_WORLDS.map(w => ({ ...w }));
      state.sections = DEFAULT_SECTIONS.map(s => ({ ...s }));
      state.pools = clonePools(DEFAULT_POOLS);
      updateView();
      notice("Thematic Worlds reset back to defaults.");
      return;
    }
  });

  // WHAT: Handles input change events for world checkboxes and catalog item dropdown selections.
  // WHY: Updates active world lists or pool membership directly as user form inputs change.
  container.addEventListener("change", event => {
    const check = event.target.closest(".worlds-cluster-check");
    if (check) {
      const idx = Number(check.dataset.index);
      if (state.worlds[idx]) {
        state.worlds = setWorldActive(state.worlds, idx, check.checked);
        const activeNames = state.worlds.filter(w => w.active).map(w => w.name);
        state.pools = compilePoolsFromActiveWorlds(activeNames, state.pools, THEMATIC_WORLDS_LIBRARY);
        updateView();
      }
      return;
    }

    const select = event.target.closest(".worlds-select-term-dropdown");
    if (select && select.value) {
      const poolIdx = Number(select.dataset.pool);
      const chosen = select.value.trim();
      const targetPool = state.pools[poolIdx];
      if (chosen && targetPool && !targetPool.terms.includes(chosen)) {
        state.pools = addTermToPool(state.pools, poolIdx, chosen);
        updateView();
        notice(`Added "${chosen}" to ${targetPool.dimension} pool.`);
      }
      return;
    }
  });

  // WHAT: Live slider handler updating juxtaposition bars as the user drags.
  // WHY: Rerenders only the juxtaposition bars and multiplier readout for 60fps responsive interaction.
  const slider = $("#worlds-juxtaposition-slider");
  if (slider) {
    slider.oninput = () => {
      state.slider = Number(slider.value);
      const { barsHtml, multiplierText } = renderBarsHtml(state.sections, state.slider, state.mode);
      const barsContainer = $("#worlds-kappa-bars");
      const multSpan = $("#worlds-slider-multiplier");
      if (barsContainer) barsContainer.innerHTML = barsHtml;
      if (multSpan) multSpan.textContent = multiplierText;
    };
  }

  // Switch between Keyword Pools (12 Tables) and Thematic Worlds (Classification)
  const navToWorldsBtn = $("#vocab-view-worlds-btn");
  const tabKeywords = $("#tab-vocab-keywords");
  const tabWorlds = $("#tab-vocab-worlds");
  const keywordWorkspace = $("#vocab-category-workspace");
  const worldsWorkspace = $("#vocab-worlds-workspace");

  // WHAT: Switches view from the 12 keyword category tables to the Thematic Worlds workspace.
  // WHY: Smoothly toggles panels, tab active classes, and pre-populates prompt input from active direction.
  const showWorldsView = () => {
    if (keywordWorkspace) keywordWorkspace.hidden = true;
    if (worldsWorkspace) worldsWorkspace.hidden = false;
    if (tabKeywords) tabKeywords.classList.remove("active");
    if (tabWorlds) tabWorlds.classList.add("active");
    if (navToWorldsBtn) {
      navToWorldsBtn.textContent = "📋 Keyword Pools (12 Tables)";
      navToWorldsBtn.dataset.tooltip = "Switch back to the 12 keyword category tables";
    }
    const promptEl = $("#worlds-prompt-input");
    if (promptEl && !promptEl.value.trim()) {
      const dirVal = document.querySelector("#video-form [name='direction']")?.value;
      if (dirVal) promptEl.value = dirVal.trim();
    }
    if (!catalogCache) {
      loadVocabularyCatalog()
        .then((cat) => {
          catalogCache = cat;
          updateView();
        })
        .catch(() => {});
    }
    updateView();
  };

  // WHAT: Switches view from Thematic Worlds back to the 12 keyword category tables.
  // WHY: Allows the director to inspect or modify granular category tables directly.
  const showKeywordView = () => {
    if (keywordWorkspace) keywordWorkspace.hidden = false;
    if (worldsWorkspace) worldsWorkspace.hidden = true;
    if (tabKeywords) tabKeywords.classList.add("active");
    if (tabWorlds) tabWorlds.classList.remove("active");
    if (navToWorldsBtn) {
      navToWorldsBtn.textContent = "🧭 Thematic Worlds & Classification";
      navToWorldsBtn.dataset.tooltip = "Switch to Thematic Worlds, semantic clustering, and juxtaposition control";
    }
  };

  if (navToWorldsBtn) {
    navToWorldsBtn.onclick = () => {
      if (worldsWorkspace && worldsWorkspace.hidden) {
        showWorldsView();
      } else {
        showKeywordView();
      }
    };
  }

  if (tabKeywords) tabKeywords.onclick = showKeywordView;
  if (tabWorlds) tabWorlds.onclick = showWorldsView;

  // Initialize view
  updateView();
}

