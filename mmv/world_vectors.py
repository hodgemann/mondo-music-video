"""Semantic world vector clustering, domain prefixing, and percentile-calibrated distance matrices.

Implements the mathematical directives for visual worldbuilding:
- Contextual domain prefixing (`"setting: ..."`, `"lighting: ..."`, `"mechanism: ..."`)
- Normalized cluster centroid computation:
  c_k = (1 / N) * sum(E(category || t_i) / ||E(category || t_i)||)
- Pairwise cosine distance D(C_i, C_j) = 1 - (c_i . c_j) / (||c_i|| * ||c_j||)
- Dynamic percentile calibration (P15 harmonic adjacency <-> P85 polar opposition)
- Deterministic Gaussian dissonance probability:
  P(C_k | C_base, kappa) ~ exp(-(D(C_base, C_k) - kappa * D_max)^2 / (2 * sigma^2))
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Callable, Dict, List, Mapping, Sequence, Tuple

import numpy as np

# Canonical domain prefixes used before vectorization to prevent short-phrase semantic drift.
DOMAIN_PREFIX_MAP: Mapping[str, str] = {
    "settings": "setting",
    "setting": "setting",
    "lighting": "lighting",
    "mechanisms": "mechanism",
    "mechanism": "mechanism",
    "costume": "costume",
    "practical_effects": "practical_effect",
    "practical effects": "practical_effect",
    "subject_types": "subject_type",
    "subject_type": "subject_type",
    "tonal_registers": "tonal_register",
    "tonal_register": "tonal_register",
}

DEFAULT_SIGMA = 0.22
DEFAULT_DIMS = 64
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


# Built-in Thematic Worlds catalog mirroring the studio workspace.
BUILTIN_THEMATIC_WORLDS: Mapping[str, Mapping[str, Sequence[str]]] = {
    "Bureaucratic / Carceral": {
        "settings": ("evidence locker", "sodium-lit stairwell", "records annex", "flooded basement", "linoleum corridor", "interrogation room", "card-catalogue annex"),
        "lighting": ("flickering fluorescent tube", "single desk lamp", "amber exit signs", "cold green cathode hum", "overhead strip glare"),
        "mechanisms": ("pneumatic tube dispatch", "card-catalogue drawers sliding", "stamp descending", "manual typewriter carriage", "rotary dial spin"),
        "costume": ("grey wool cardigan", "laminated lanyard", "rumpled polyester tie", "oversized metal badge", "stiff cotton clerk coat"),
        "practical_effects": ("drifting paper dust", "steam from a vent", "yellowing water stain", "buzzing ballast flicker", "coffee ring on parchment"),
    },
    "Brutalist Concrete": {
        "settings": ("monolithic atrium", "shear concrete underpass", "subterranean bunker", "recessed pedestrian tunnel", "brutalist civic plaza"),
        "lighting": ("stark raking sidelight", "deep geometric shadow", "cold halogen wash", "single slit aperture sunbeam"),
        "mechanisms": ("hydraulic blast door", "counterweight pulley", "heavy steel turnstile", "concrete core drill", "cable-stayed winch"),
        "costume": ("heavy charcoal trench", "rough wool greatcoat", "steel-toe boots", "utilitarian boiler suit", "dark canvas parka"),
        "practical_effects": ("chalky concrete dust", "dripping condensation", "cold breath mist", "wind whipping fine gravel"),
    },
    "Industrial Decay": {
        "settings": ("abandoned assembly floor", "rusted catwalk", "inactive blast furnace", "scrap yard crane bay", "dripping steam conduit"),
        "lighting": ("flickering sodium vapor", "welding flash reflection", "amber hazard strobe", "dull rusted twilight"),
        "mechanisms": ("cracked flywheel spinning", "pneumatic piston hiss", "rusty chain hoist", "loose drive belt flapping"),
        "costume": ("grease-stained canvas overalls", "battered leather apron", "pitted welding goggles", "frayed cloth gloves"),
        "practical_effects": ("curling iron filings", "oily puddle rainbow", "soot fallout", "high-pressure steam leak"),
    },
    "Maritime / Salt": {
        "settings": ("fog-choked timber pier", "rusted trawler deck", "fish cannery slipway", "salt-crusted watchtower", "low-tide mudflat"),
        "lighting": ("revolving lighthouse beam", "grey overcast sea mist", "lantern reflecting in wet planks", "sickly yellow deck floodlight"),
        "mechanisms": ("winch drum groaning", "rusty capstan turning", "foghorn bellows breathing", "bilge pump chugging"),
        "costume": ("yellow rubber slicker", "salt-stiffened denim", "heavy knit fisherman sweater", "sou'wester oilskin hat"),
        "practical_effects": ("cold sea spray", "thick sea fog rolling", "dripping brine", "scattered wet fish scales"),
    },
    "Cyberpunk / High-Tech": {
        "settings": ("crowded server bank", "neon-lit rainy alleyway", "subterranean cyber clinic", "cramped terminal booth", "optic cabling conduit"),
        "lighting": ("saturated magenta neon", "pulsing cyan diode glow", "scanning laser grid", "stuttering CRT monitor flicker"),
        "mechanisms": ("robotic actuator arm", "cooling fan spin-up", "optic cable rack patching", "motorized iris camera lens"),
        "costume": ("transparent vinyl coat", "modular techwear harness", "reflective visor", "fingerless grounding gloves"),
        "practical_effects": ("circuit board smoke", "holographic glitch artifact", "fiber optic sparks", "pooling oily neon reflection"),
    },
    "Nocturnal Noir": {
        "settings": ("rain-slicked back alley", "venetian-blinded private office", "empty 2am diner", "fire escape landing", "telephone booth under streetlight"),
        "lighting": ("slanted venetian blind shadow", "single sodium streetlight", "glowing cigarette tip", "wet pavement neon bounce"),
        "mechanisms": ("rotary phone cradle click", "revolver cylinder spin", "ceiling fan turning slowly", "coin clinking in jukebox"),
        "costume": ("damp gabardine trenchcoat", "tilted felt fedora", "loosened silk tie", "leather shoulder holster"),
        "practical_effects": ("curling cigarette smoke", "rain pouring off metal awning", "wet tire hiss", "windshield wiper drag"),
    },
    "Pastoral Nature": {
        "settings": ("moss-carpeted forest clearing", "ruined stone chapel overgrown with ivy", "sun-dappled creek bed", "ancient hollow oak grove"),
        "lighting": ("dappled canopy sunlight", "amber golden-hour slant", "glowing bioluminescent moss", "soft morning mist"),
        "mechanisms": ("creaking tree bough", "timber water wheel turning", "seed pod bursting", "deep root cracking stone"),
        "costume": ("hand-spun linen tunic", "dirt-stained hem", "woven willow crown", "unbleached cotton smock"),
        "practical_effects": ("floating airborne pollen", "falling dried leaves", "rising soil dew", "spore cloud drifting"),
    },
    "Baroque / Theatrical": {
        "settings": ("decaying opera house balcony", "gilded mirror gallery", "empty orchestra pit", "dusty backstage dressing room"),
        "lighting": ("gas footlights flickering", "multi-tiered crystal chandelier", "single amber spotlight cone", "flickering beeswax candles"),
        "mechanisms": ("counterweighted stage rope", "velvet grand drape rising", "trapdoor latch releasing", "mechanical music box cylinder"),
        "costume": ("heavy crimson velvet cape", "tarnished filigree mask", "gold brocade waistcoat", "ruffled lace collar"),
        "practical_effects": ("billowing stage rosin dust", "drifting red rose petals", "melting wax drip", "floating theatrical haze"),
    },
    "Clinical / Medical": {
        "settings": ("glazed white tile operating theater", "silent quarantine corridor", "specimen preservation vault", "sterile recovery ward"),
        "lighting": ("harsh shadowless surgical ring light", "pale blue inspection beam", "cold white fluorescent glare"),
        "mechanisms": ("centrifuge spinning", "pneumatic syringe valve", "stainless gurney caster rolling", "ECG tape feeding"),
        "costume": ("pale mint surgical scrubs", "translucent examination gloves", "starch-white lab coat", "disposable paper mask"),
        "practical_effects": ("condensation inside oxygen tent", "dripping saline chamber", "antiseptic mist spray", "frost on cryogenic vial"),
    },
    "Cosmic / Void": {
        "settings": ("deep space observation cupola", "radio telescope dish rim", "obsidian asteroid crater", "pressurized airlock chamber"),
        "lighting": ("distant blue starlight pinpricks", "earth-rise specular rim light", "cold solar flare glare", "monochrome instrument backlight"),
        "mechanisms": ("airlock decompression cycle", "reaction control thruster puff", "gyroscope spinning in gimbal", "solar array unrolling"),
        "costume": ("multilayer EVA spacesuit", "gold-tinted reflective helmet visor", "pressurized tether umbilical", "quilted thermal liner"),
        "practical_effects": ("floating weightless droplets", "solar wind particle trails", "micro-meteorite impact sparkle", "ice crystals venting"),
    },
}


def prefix_domain_term(category: str, term: str) -> str:
    """Format a vocabulary entry with its canonical operational domain label.

    Example: prefix_domain_term('settings', 'subterranean maglev platform')
             -> 'setting: subterranean maglev platform'
    """
    cat_clean = str(category or "").strip().lower()
    prefix = DOMAIN_PREFIX_MAP.get(cat_clean, cat_clean.rstrip("s") or "term")
    term_clean = re.sub(r"\s+", " ", str(term or "").strip())
    return f"{prefix}: {term_clean}"


def l2_normalize(vector: Sequence[float] | np.ndarray) -> np.ndarray:
    """Return a unit-length float64 vector (or zeros if norm is 0)."""
    arr = np.asarray(vector, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 1e-12 else np.zeros_like(arr)


def deterministic_lexical_embed(texts: Sequence[str], dims: int = DEFAULT_DIMS) -> np.ndarray:
    """Deterministic feature-hashing embedder when an external GPU embedding server is not active.

    Projects domain-prefixed tokens and character n-grams into a fixed-dimensional vector space
    so semantic similarity and centroid math operate deterministically offline.
    """
    matrix = np.zeros((len(texts), dims), dtype=np.float64)
    for row_idx, text in enumerate(texts):
        lowered = str(text or "").lower()
        tokens = _TOKEN_RE.findall(lowered)
        # Include bigrams and stems for richer semantic overlap across related clusters
        features: List[Tuple[str, float]] = []
        for tok in tokens:
            features.append((f"tok:{tok}", 1.0))
            if len(tok) >= 5:
                features.append((f"stem:{tok[:4]}", 0.6))
        for i in range(len(tokens) - 1):
            features.append((f"bi:{tokens[i]}_{tokens[i + 1]}", 0.8))
        for feat, weight in features:
            digest = hashlib.sha256(feat.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % dims
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            matrix[row_idx, slot] += sign * weight
        matrix[row_idx] = l2_normalize(matrix[row_idx])
    return matrix


def compute_cluster_centroid(
    pools: Mapping[str, Sequence[str]],
    embedder: Callable[[List[str]], np.ndarray] = deterministic_lexical_embed,
) -> np.ndarray:
    """Compute the normalized contextual centroid vector c_k for a world cluster C_k:

    c_k = (1 / N) * sum_{i=1}^N ( E(category || t_i) / ||E(category || t_i)|| )
    Followed by L2 normalization of c_k for unit-sphere cosine geometry.
    """
    prefixed_terms: List[str] = []
    for category, terms in sorted(pools.items()):
        if not isinstance(terms, (list, tuple)):
            continue
        for term in terms:
            if isinstance(term, str) and term.strip():
                prefixed_terms.append(prefix_domain_term(category, term))
    if not prefixed_terms:
        return np.zeros(DEFAULT_DIMS, dtype=np.float64)

    raw_embeddings = np.asarray(embedder(prefixed_terms), dtype=np.float64)
    if raw_embeddings.ndim == 1:
        raw_embeddings = raw_embeddings.reshape(1, -1)

    # Vectorized row normalization avoiding iterative Python list comprehensions
    norms = np.linalg.norm(raw_embeddings, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    unit_vectors = raw_embeddings / norms
    mean_centroid = np.mean(unit_vectors, axis=0)
    return l2_normalize(mean_centroid)


def cosine_distance(vec_a: Sequence[float] | np.ndarray, vec_b: Sequence[float] | np.ndarray) -> float:
    """Compute normalized pairwise semantic distance D(C_i, C_j) = 1 - (c_i . c_j) / (||c_i|| * ||c_j||)."""
    unit_a = l2_normalize(vec_a)
    unit_b = l2_normalize(vec_b)
    if not np.any(unit_a) or not np.any(unit_b):
        return 1.0
    sim = float(np.clip(np.dot(unit_a, unit_b), -1.0, 1.0))
    return float(max(0.0, min(2.0, 1.0 - sim)))


def calibrate_distance_matrix(
    centroids: Mapping[str, Sequence[float] | np.ndarray],
    low_pct: float = 15.0,
    high_pct: float = 85.0,
) -> Dict[str, object]:
    """Compute pairwise cosine distances and calibrate against empirical P15 and P85 bounds.

    Uses BLAS matrix multiplication to calculate the complete pairwise cosine distance
    matrix in a single vectorized operation rather than N^2 Python loops.
    """
    names = list(centroids.keys())
    if not names:
        return {"raw": {}, "calibrated": {}, "p15": 0.0, "p85": 1.0, "d_max": 1.0}

    # Vectorized centroid matrix: D = 1.0 - clip(A @ A.T, -1.0, 1.0)
    unit_matrix = np.array([l2_normalize(centroids[name]) for name in names], dtype=np.float64)
    sim_matrix = np.clip(unit_matrix @ unit_matrix.T, -1.0, 1.0)
    dist_matrix = np.clip(1.0 - sim_matrix, 0.0, 2.0)
    np.fill_diagonal(dist_matrix, 0.0)

    # Build raw dictionary and extract upper-triangle distances for percentile calibration
    raw: Dict[str, Dict[str, float]] = {}
    off_diagonal: List[float] = []
    n = len(names)
    for i, name_i in enumerate(names):
        raw[name_i] = {}
        for j, name_j in enumerate(names):
            d = float(dist_matrix[i, j])
            raw[name_i][name_j] = d
            if i < j:
                off_diagonal.append(d)

    if not off_diagonal:
        return {"raw": raw, "calibrated": raw, "p15": 0.0, "p85": 1.0, "d_max": 1.0}

    arr = np.asarray(off_diagonal, dtype=np.float64)
    p15 = float(np.percentile(arr, low_pct))
    p85 = float(np.percentile(arr, high_pct))
    d_max = float(np.max(arr))
    span = max(1e-9, p85 - p15)

    # Vectorized piecewise linear calibration clamped to [0.0, 1.0]
    calibrated_arr = np.clip((dist_matrix - p15) / span, 0.0, 1.0)
    np.fill_diagonal(calibrated_arr, 0.0)

    calibrated: Dict[str, Dict[str, float]] = {
        name_i: {name_j: float(calibrated_arr[i, j]) for j, name_j in enumerate(names)}
        for i, name_i in enumerate(names)
    }

    return {
        "raw": raw,
        "calibrated": calibrated,
        "p15": p15,
        "p85": p85,
        "d_max": d_max if d_max > 0 else 1.0,
    }


# Pre-compiled immutable centroids and calibrated distance matrix for the built-in 10 Thematic Worlds.
BUILTIN_WORLD_CENTROIDS: Mapping[str, np.ndarray] = {
    name: compute_cluster_centroid(pools)
    for name, pools in BUILTIN_THEMATIC_WORLDS.items()
}
BUILTIN_CALIBRATED_MATRIX: Mapping[str, object] = calibrate_distance_matrix(BUILTIN_WORLD_CENTROIDS)


def compute_effective_kappa(base_kappa: float, slider_percent: float = 50.0) -> float:
    """Compute effective section dissonance kappa_eff bounded in [0.0, 1.0].

    M = 2 * (s / 100)
    kappa_eff = min(1.0, max(0.0, kappa_base * M))
    """
    multiplier = 2.0 * (float(slider_percent) / 100.0)
    return float(min(1.0, max(0.0, float(base_kappa) * multiplier)))


def gaussian_cluster_weights(
    base_cluster: str,
    distance_map: Mapping[str, Mapping[str, float]],
    kappa_eff: float,
    d_max: float = 1.0,
    sigma: float = DEFAULT_SIGMA,
    exclude_base: bool = False,
) -> Dict[str, float]:
    """Compute normalized Gaussian probability weights P(C_k | C_base, kappa) for candidate clusters:

    P(C_k | C_base, kappa) ~ exp( - (D(C_base, C_k) - kappa * D_max)^2 / (2 * sigma^2) )
    """
    row = distance_map.get(base_cluster)
    if not row:
        return {}
    clamped_kappa = max(0.0, min(1.0, float(kappa_eff)))
    target_d = clamped_kappa * float(d_max)
    denom = 2.0 * max(1e-6, float(sigma)) ** 2

    weights: Dict[str, float] = {}
    for candidate, dist in row.items():
        if exclude_base and candidate == base_cluster and len(row) > 1:
            continue
        diff = float(dist) - target_d
        weights[candidate] = math.exp(-(diff * diff) / denom)

    total = sum(weights.values())
    if total > 0:
        return {k: v / total for k, v in weights.items()}
    return {k: 1.0 / len(weights) for k in weights} if weights else {}


def classify_dissonance_band(kappa_eff: float) -> str:
    """Classify kappa_eff into one of the five architectural dissonance bands."""
    k = max(0.0, min(1.0, float(kappa_eff)))
    if k < 0.20:
        return "harmonic"           # 0.00 - 0.15: Zero Clash (all 5 dimensions in primary cluster)
    if k < 0.42:
        return "soft_accent"        # 0.25 - 0.35: Subtle Intrusion (1 dimension from adjacent D <= P20)
    if k < 0.68:
        return "motivated_tension"  # 0.50 - 0.65: Medium Clash (setting/lighting in A; mechanism/costume in B)
    if k < 0.90:
        return "surreal_clash"      # 0.70 - 0.85: Hard Clash (wardrobe & mechanism from opposite D >= P85)
    return "hot_bars"               # 0.90 - 1.00: Maximal Collision (D -> max, adjacency suspended)


def dimensional_binding_for_kappa(
    kappa_eff: float,
    present_keys: Sequence[str],
    seed_draw: int = 0,
) -> Dict[str, str]:
    """Return which cluster tier ('base', 'adjacent', 'tension', 'opposite', 'maximal') each shot key binds to.

    Follows the Dimensional Binding Rules table across the 5 kappa bands.
    """
    band = classify_dissonance_band(kappa_eff)
    keys = list(present_keys)
    binding = {k: "base" for k in keys}

    if band == "harmonic":
        return binding

    if band == "soft_accent":
        # Base environment remains in Cluster A; exactly one accent dimension (lighting or mechanism) borrows from adjacent
        accent_candidates = [k for k in ("lighting", "mechanism") if k in binding]
        if accent_candidates:
            chosen_key = accent_candidates[seed_draw % len(accent_candidates)]
            binding[chosen_key] = "adjacent"
        return binding

    if band == "motivated_tension":
        # Setting and lighting stay in base; mechanism and costume draw from contrasting cluster
        for k in ("mechanism", "costume", "tonal_register"):
            if k in binding:
                binding[k] = "tension"
        return binding

    if band == "surreal_clash":
        # Environment shifts to adjacent; wardrobe and mechanisms draw from diametrically opposed cluster (D >= P85)
        for k in ("setting", "lighting"):
            if k in binding:
                binding[k] = "adjacent"
        for k in ("mechanism", "costume", "tonal_register"):
            if k in binding:
                binding[k] = "opposite"
        return binding

    # hot_bars (kappa >= 0.90): Maximal collision across all dimensions simultaneously
    for k in keys:
        binding[k] = "maximal"
    return binding

