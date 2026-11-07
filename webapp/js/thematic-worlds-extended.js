// WHAT: Extended thematic worlds definitions defining aesthetic settings, lighting, mechanisms, costume, and practical effects.
// WHY: Decouples expandable domain world definitions into a standalone external data module, allowing studios
// to easily add, customize, or load additional worlds without altering core workspace logic.

export const EXTENDED_THEMATIC_WORLDS = [
  {
    name: "Subterranean / Mine",
    keywords: [
      "mine", "shaft", "subterranean", "cavern", "tunnel", "ore", "pickaxe", "canary",
      "timber", "shoring", "headlamp", "coal", "dust", "quarry", "strata", "limestone",
      "bedrock", "elevator", "cage", "stalactite", "geode", "damp", "drill", "blasting"
    ],
    pools: {
      Settings: ["timber-shored haulage drift", "flooded sump level", "vertical elevator cage shaft", "blasted limestone cavern", "narrow carbide-lit stope"],
      Lighting: ["flickering carbide flame", "narrow halogen beam from headlamp", "dull amber safety lantern", "shaft of daylight through ventilation bore"],
      Mechanisms: ["cable hoist cage rattling downward", "pneumatic rock drill chattering", "ore cart steel wheels screeching", "hand-cranked ventilation blower humming"],
      Costume: ["heavy duck canvas dungarees", "battered fiberglass hardhat with bracket", "mud-caked lace-up miner boots", "damp kerchief respirator"],
      "Practical Effects": ["chalky rock dust cloud", "slumping pulverized coal", "seeping groundwater trickling down rock face", "sparks from iron rail friction"]
    }
  },
  {
    name: "Arid / Desert Wasteland",
    keywords: [
      "desert", "arid", "wasteland", "dune", "sand", "heat", "scorch", "mirage", "salt",
      "playa", "canyon", "bleached", "sun", "sunbaked", "cacti", "dust", "caravan",
      "drought", "cracked", "wind", "sandstorm", "parched", "oasis", "mesa", "rust"
    ],
    pools: {
      Settings: ["cracked alkaline dry lake bed", "windswept sandstone slot canyon", "sun-bleached settlement perimeter", "shaded adobe colonnade", "abandoned pump outpost"],
      Lighting: ["oppressive high-noon white sun glare", "heat-haze shimmer horizon", "crimson desert sunset rim", "pale moonlit dune crest"],
      Mechanisms: ["rusted squeaking wind-pump vane", "fabric shade canopy snapping in gale", "hand-cranked well drum", "sand-scoured odometer ticking"],
      Costume: ["coarse linen keffiyeh wrap", "bleached cotton dust cloak", "tinted brass goggles with leather blinders", "scuffed split-leather hide wraps"],
      "Practical Effects": ["scudding sand drift", "swirling dust devil", "flaking dry mud crust", "heat-mirage atmospheric wave"]
    }
  },
  {
    name: "Gothic / Occult",
    keywords: [
      "gothic", "occult", "cathedral", "crypt", "relic", "parchment", "candle", "wax",
      "ossuary", "grimoire", "gargoyle", "incense", "tomb", "mausoleum", "cloister",
      "ironwork", "altar", "pentacle", "bell", "belfry", "cobweb", "ritual", "chalice"
    ],
    pools: {
      Settings: ["vaulted stone ossuary", "candlelit subterranean crypt", "rain-lashed cathedral belfry", "monastery scriptorium", "abandoned family mausoleum"],
      Lighting: ["guttering tallow candle cluster", "moonlight cutting through stained glass", "brazier coal glow", "dull silver twilight through arched lancet"],
      Mechanisms: ["heavy iron church key turning", "leaded glass casement rattling in wind", "belfry clapper striking bronze bell", "book clasps springing open"],
      Costume: ["wax-stained coarse wool cassock", "tarnished silver rosary beads", "heavy cowl hood obscuring brow", "black crushed velvet mourning gown"],
      "Practical Effects": ["drifting frankincense smoke coils", "running tallow wax rivulets", "disturbed bone dust", "moth flitting past candle flame"]
    }
  },
  {
    name: "Cold War / Sub-Zero",
    keywords: [
      "arctic", "subzero", "tundra", "ice", "radar", "outpost", "bunker", "snow",
      "blizzard", "frost", "cold", "permafrost", "dome", "antenna", "transceiver",
      "surveillance", "sonar", "glacier", "polar", "rations", "insulation", "generator"
    ],
    pools: {
      Settings: ["geodesic radar dome interior", "permafrost observation trench", "ice-locked radio listening post", "diesel generator shelter", "snow-drifted perimeter fence"],
      Lighting: ["stark green radar CRT phosphor bounce", "blizzard whiteout diffusion", "red instrument warning bulb", "low winter sun grazing ice shelf"],
      Mechanisms: ["oscilloscope needle twitching", "rotary antenna mast grinding through ice", "diesel generator surging and coughing", "teletype printer chattering"],
      Costume: ["coyote-fur trimmed snorkel parka", "quilted nylon flight trousers", "heavy insulated vapor barrier boots", "wool fingerless radio gloves"],
      "Practical Effects": ["plumes of freezing breath vapor", "frost feathering on double-pane glass", "wind-whipped snow spindrift", "diesel exhaust soot on snowpack"]
    }
  },
  {
    name: "Clockwork / Steampunk",
    keywords: [
      "clockwork", "steampunk", "brass", "gear", "cog", "escapement",
      "steam", "pendulum", "flywheel", "spring", "rivet", "gauge", "valves",
      "manometer", "boiler", "copper", "watchmaker", "horology", "bellows", "automaton"
    ],
    pools: {
      Settings: ["multistory clock tower interior", "master watchmaker vaulted workshop", "copper-piped boiler galley", "pneumatic tube transit concourse", "automaton assembly bay"],
      Lighting: ["warm burnished brass specular glint", "oil lamp beam cutting furnace haze", "furnace door orange flare", "pale gas lamp fixture glow"],
      Mechanisms: ["interlocking tooth brass cogs rotating", "escapement wheel ticking rhythmically", "pressure gauge needle vibrating", "governor flyballs spinning under load"],
      Costume: ["tailored tweed vest with watch fob", "leather armorer's apron with brass studs", "multi-lens jeweler's loupe", "pin-striped high-collar boiled shirt"],
      "Practical Effects": ["feathering white steam jet", "fine spray of lubricating mineral oil", "escapement gear tick vibrations", "brass filings dusting velvet tray"]
    }
  },
  {
    name: "Suburban Retro / Liminal",
    keywords: [
      "suburban", "retro", "culdesac", "liminal", "mall", "asphalt", "shag", "lawn",
      "sprinkler", "curtains", "diner", "supermarket", "parking", "motel", "station",
      "woodgrain", "carpet", "station-wagon", "driveway", "linoleum", "patio", "screen-door"
    ],
    pools: {
      Settings: ["empty midnight shopping mall concourse", "sun-faded shag carpet living room", "rain-slicked motel parking lot", "linoleum supermarket aisle at closing", "cul-de-sac under amber streetlights"],
      Lighting: ["buzzing sodium-vapor streetlamp amber", "humming turquoise neon motel sign", "faded daylight through lace curtains", "flickering cathode ray TV glow in a dark room"],
      Mechanisms: ["lawn sprinkler oscillating click-click-swish", "woodgrain console television knob clunking", "mesh screen door slamming shut", "ice machine dispensing into plastic bin"],
      Costume: ["striped acrylic polo shirt", "faded high-waisted corduroy trousers", "scuffed canvas deck sneakers", "thin windbreaker with brass zipper"],
      "Practical Effects": ["spray mist from oscillating lawn sprinkler", "cigarette smoke curling over TV dinner foil", "neon sign electrical hum vibration", "puddle ripple under sodium light"]
    }
  },
  {
    name: "Deep Trench / Abyssal",
    keywords: [
      "abyssal", "trench", "bathysphere", "submersible", "pressure", "hydrothermal",
      "vent", "black", "depths", "sonar", "hull", "titanium", "porthole", "bioluminescence",
      "crustacean", "ooze", "benthic", "current", "cable", "salinity", "crush-depth"
    ],
    pools: {
      Settings: ["titanium bathysphere interior", "black smoker hydrothermal vent field", "benthic sediment seabed", "tethered deep-sea rig gantry", "flooded decompression airlock"],
      Lighting: ["narrow high-intensity exterior quartz floodlight", "eerie cyan bioluminescent flashes in blackness", "sonar screen green sweep", "red emergency cabin flood"],
      Mechanisms: ["hydraulic manipulator claw clenching", "hull pressure gauge needle trembling", "sonar ping echoing off titanium hull", "ballast tank valve blowing"],
      Costume: ["fire-resistant nomex crew jumpsuit", "neoprene dive harness with brass buckles", "oxygen rebreather chest counterlung", "thermal fleece undergarment layer"],
      "Practical Effects": ["marine snow particles drifting through beam", "shimmering mineral plumes from vent chimney", "condensation bead running down thick quartz glass", "creaking hull groans under pressure"]
    }
  },
  {
    name: "Agrarian / Crop Horror",
    keywords: [
      "cornfield", "crop", "silo", "barn", "scarecrow", "chaff", "thresher", "rural",
      "combine", "stalks", "harvest", "dusk", "cicadas", "burlap", "pitchfork",
      "weathered", "hay", "tractor", "grain", "locust", "windbreak", "irrigation"
    ],
    pools: {
      Settings: ["towering cornfield rows at dusk", "empty cathedral-like grain silo interior", "weathered timber barn hayloft", "abandoned combine harvester chassis", "gravel farm access lane"],
      Lighting: ["blood-orange setting harvest sun", "single halogen floodlight on rusted barn gable", "raking headlight beams through tall stalks", "deep moonlit field shadows"],
      Mechanisms: ["rusting tin wind-vane screeching", "combine thresher blade belt turning slowly", "tin roof panels rattling in evening wind", "irrigation pipe pressure valve clicking"],
      Costume: ["weathered denim bib overalls", "frayed burlap sack mask with twine stitch", "grease-stained chore jacket", "heavy cracked leather work boots"],
      "Practical Effects": ["drifting golden grain chaff", "dry corn husks scraping in wind", "swarms of evening moths around halogen flood", "settling dust over tractor ruts"]
    }
  }
];

export default EXTENDED_THEMATIC_WORLDS;
