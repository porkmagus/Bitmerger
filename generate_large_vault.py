#!/usr/bin/env python3
"""Generate a truly random 5000-item vault for stress testing."""

import json
import random
import secrets
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Use the system's cryptographically strong RNG
random = secrets.SystemRandom()

WORDS = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
    "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey",
    "xray", "yankee", "zulu", "ninja", "dragon", "pirate", "wizard", "robot",
    "cloud", "matrix", "nebula", "quantum", "pixel", "circuit", "firewall",
    "kernel", "buffer", "stack", "heap", "syntax", "compile", "debug",
    "deploy", "server", "client", "proxy", "gateway", "router", "switch",
    "cable", "fiber", "satellite", "signal", "wave", "pulse", "laser",
    "portal", "gateway", "bridge", "tunnel", "vault", "cipher", "hash",
    "token", "cookie", "session", "cache", "index", "query", "schema",
    "table", "record", "field", "key", "value", "pair", "list", "tree",
    "graph", "node", "edge", "path", "route", "map", "zone", "region",
    "site", "node", "hub", "core", "edge", "rim", "base", "home", "work",
    "office", "lab", "studio", "shop", "store", "bank", "market", "trade",
    "exchange", "fund", "stock", "bond", "coin", "cash", "gold", "silver",
    "credit", "debit", "loan", "mortgage", "lease", "rent", "bill", "fee",
    "tax", "duty", "tariff", "quota", "limit", "cap", "ceiling", "floor",
    "wall", "gate", "door", "window", "roof", "floor", "stairs", "elevator",
    "hall", "room", "lobby", "deck", "patio", "yard", "garden", "park",
    "pool", "gym", "court", "field", "track", "lane", "road", "street",
    "avenue", "boulevard", "drive", "way", "path", "trail", "route", "course",
    "orbit", "loop", "ring", "circle", "sphere", "cube", "pyramid", "cone",
    "cylinder", "prism", "plane", "line", "point", "dot", "dash", "stroke",
    "mark", "sign", "symbol", "glyph", "rune", "icon", "image", "photo",
    "video", "film", "clip", "scene", "shot", "frame", "panel", "slide",
    "page", "sheet", "card", "ticket", "pass", "badge", "id", "tag",
    "label", "stamp", "seal", "stamp", "print", "copy", "scan", "fax",
    "mail", "post", "letter", "note", "memo", "draft", "file", "doc",
    "form", "report", "log", "journal", "diary", "blog", "feed", "stream",
    "flow", "river", "lake", "sea", "ocean", "bay", "gulf", "strait",
    "channel", "canal", "dam", "bridge", "pier", "dock", "port", "harbor",
    "marina", "anchorage", "haven", "refuge", "shelter", "camp", "base",
    "fort", "castle", "palace", "tower", "spire", "dome", "arch", "beam",
    "column", "pillar", "post", "pole", "mast", "boom", "crane", "lift",
    "jack", "winch", "pulley", "gear", "sprocket", "chain", "belt", "rope",
    "wire", "cable", "cord", "line", "thread", "string", "twine", "yarn",
    "fabric", "cloth", "textile", "linen", "silk", "wool", "cotton", "fiber",
    "mesh", "net", "web", "grid", "matrix", "array", "vector", "tensor",
    "scalar", "atom", "molecule", "cell", "tissue", "organ", "system",
    "body", "mind", "soul", "spirit", "ghost", "shadow", "shade", "light",
    "dark", "bright", "dim", "glow", "gleam", "glint", "spark", "flash",
    "beam", "ray", "flare", "burst", "blast", "bang", "boom", "crash",
    "smash", "crack", "snap", "pop", "click", "tick", "tock", "chime",
    "ring", "ding", "dong", "clang", "clank", "clink", "clunk", "thud",
    "thump", "bump", "jump", "hop", "skip", "leap", "bound", "spring",
    "bounce", "roll", "spin", "twirl", "swirl", "whirl", "curl", "twist",
    "turn", "rotate", "orbit", "revolve", "cycle", "loop", "repeat", "echo",
    "reverb", "resonance", "harmony", "melody", "rhythm", "beat", "tempo",
    "pace", "speed", "rate", "ratio", "proportion", "scale", "degree",
    "level", "tier", "rank", "grade", "class", "group", "set", "batch",
    "lot", "bundle", "pack", "kit", "box", "case", "crate", "chest",
    "trunk", "bin", "bucket", "pail", "pot", "pan", "dish", "plate",
    "bowl", "cup", "mug", "glass", "bottle", "jar", "jug", "flask",
    "vial", "tube", "pipe", "hose", "nozzle", "spout", "faucet", "tap",
    "valve", "pump", "plunger", "piston", "rod", "bar", "rail", "track",
    "trail", "trace", "track", "wake", "wave", "ripple", "surge", "swell",
    "crest", "peak", "summit", "apex", "top", "tip", "point", "head",
    "lead", "front", "face", "side", "edge", "rim", "lip", "brim",
    "border", "boundary", "limit", "edge", "margin", "fringe", "verge",
    "brink", "threshold", "doorway", "entry", "entrance", "exit", "gate",
    "portal", "opening", "hole", "gap", "space", "void", "vacuum", "emptiness",
    "blank", "clear", "clean", "pure", "fresh", "new", "novel", "original",
    "unique", "rare", "scarce", "precious", "valuable", "priceless", "costly",
    "expensive", "cheap", "inexpensive", "affordable", "free", "open",
    "public", "shared", "common", "universal", "global", "world", "earth",
    "land", "ground", "soil", "dirt", "mud", "clay", "sand", "gravel",
    "rock", "stone", "pebble", "boulder", "mountain", "hill", "ridge",
    "valley", "canyon", "gorge", "ravine", "cliff", "bluff", "crag",
    "peak", "summit", "plateau", "plain", "prairie", "steppe", "tundra",
    "taiga", "forest", "wood", "jungle", "bush", "thicket", "grove",
    "orchard", "vineyard", "field", "meadow", "pasture", "range", "ranch",
    "farm", "estate", "plantation", "colony", "settlement", "town", "city",
    "village", "hamlet", "suburb", "district", "zone", "sector", "area",
    "region", "territory", "province", "state", "county", "parish", "borough",
    "block", "lot", "plot", "patch", "spot", "place", "location", "site",
    "station", "stop", "depot", "terminal", "hub", "center", "core",
    "heart", "middle", "midst", "center", "focus", "nucleus", "kernel",
    "seed", "germ", "bud", "sprout", "shoot", "stem", "stalk", "trunk",
    "branch", "twig", "leaf", "needle", "blade", "frond", "petal", "bloom",
    "flower", "blossom", "bud", "cone", "nut", "fruit", "berry", "grain",
    "kernel", "pit", "seed", "spore", "pollen", "nectar", "sap", "resin",
    "gum", "latex", "oil", "juice", "water", "liquid", "fluid", "solution",
    "mixture", "compound", "alloy", "blend", "fusion", "synthesis", "combo",
    "union", "join", "link", "tie", "bond", "connection", "relation",
    "relationship", "association", "affiliation", "alliance", "coalition",
    "league", "guild", "club", "society", "association", "organization",
    "institution", "foundation", "corporation", "company", "firm", "business",
    "enterprise", "venture", "project", "program", "plan", "scheme", "strategy",
    "policy", "procedure", "process", "method", "system", "approach", "technique",
    "tactic", "maneuver", "operation", "mission", "task", "job", "work",
    "duty", "role", "function", "position", "post", "appointment", "assignment",
    "commission", "delegation", "mandate", "authority", "power", "force",
    "strength", "might", "energy", "vigor", "vitality", "life", "spirit",
    "spark", "flame", "fire", "heat", "warmth", "cold", "cool", "chill",
    "freeze", "frost", "ice", "snow", "sleet", "hail", "rain", "drizzle",
    "mist", "fog", "cloud", "vapor", "steam", "smoke", "ash", "dust",
    "sand", "grit", "powder", "granule", "flake", "chip", "shard", "fragment",
    "piece", "part", "section", "segment", "portion", "share", "slice", "chunk",
    "lump", "mass", "bulk", "volume", "weight", "heft", "load", "burden",
    "cargo", "freight", "shipment", "consignment", "delivery", "parcel",
    "package", "packet", "bundle", "bunch", "cluster", "group", "crowd",
    "throng", "mob", "horde", "swarm", "flock", "herd", "pack", "team",
    "crew", "squad", "unit", "division", "regiment", "battalion", "brigade",
    "corps", "army", "navy", "force", "fleet", "flotilla", "squadron", "wing",
    "group", "command", "hq", "base", "post", "camp", "barracks", "quarters",
    "lodging", "housing", "accommodation", "suite", "apartment", "flat",
    "condo", "townhouse", "duplex", "mansion", "manor", "villa", "cottage",
    "bungalow", "cabin", "chalet", "lodge", "hut", "shack", "shed", "garage",
    "barn", "stable", "pen", "coop", "kennel", "hive", "nest", "den", "lair",
    "burrow", "hole", "tunnel", "cave", "cavern", "grotto", "abyss", "pit",
    "well", "spring", "fountain", "geyser", "jet", "spout", "spray", "shower",
    "bath", "pool", "tub", "sink", "basin", "bowl", "basin", "reservoir",
    "tank", "cistern", "vat", "tun", "barrel", "keg", "cask", "drum", "can",
    "tin", "canister", "container", "vessel", "holder", "carrier", "bearer",
    "porter", "courier", "messenger", "runner", "rider", "driver", "pilot",
    "captain", "skipper", "commander", "leader", "chief", "head", "boss",
    "manager", "supervisor", "director", "executive", "officer", "official",
    "agent", "representative", "delegate", "envoy", "ambassador", "diplomat",
    "consul", "attaché", "aide", "assistant", "helper", "partner", "associate",
    "colleague", "peer", "equal", "match", "counterpart", "opposite", "rival",
    "competitor", "contender", "challenger", "opponent", "enemy", "foe",
    "adversary", "antagonist", "villain", "criminal", "thief", "robber",
    "burglar", "bandit", "outlaw", "fugitive", "refugee", "exile", "expat",
    "immigrant", "migrant", "traveler", "tourist", "visitor", "guest", "host",
    "resident", "citizen", "subject", "national", "native", "local", "alien",
    "foreigner", "stranger", "newcomer", "beginner", "novice", "amateur",
    "hobbyist", "enthusiast", "fan", "supporter", "advocate", "champion",
    "defender", "protector", "guardian", "warden", "keeper", "custodian",
    "curator", "steward", "manager", "administrator", "operator", "user",
    "client", "customer", "consumer", "buyer", "purchaser", "shopper",
    "bidder", "offerer", "seller", "vendor", "merchant", "trader", "dealer",
    "broker", "agent", "middleman", "intermediary", "mediator", "negotiator",
    "arbiter", "judge", "magistrate", "justice", "referee", "umpire", "official",
    "inspector", "examiner", "auditor", "reviewer", "critic", "analyst",
    "evaluator", "assessor", "appraiser", "estimator", "calculator", "computer",
    "counter", "teller", "cashier", "clerk", "secretary", "receptionist",
    "assistant", "attendant", "steward", "waiter", "server", "host", "hostess",
    "bartender", "chef", "cook", "baker", "butcher", "brewer", "winemaker",
    "distiller", "farmer", "grower", "planter", "sower", "reaper", "harvester",
    "gatherer", "collector", "hunter", "fisher", "trapper", "miner", "digger",
    "driller", "pumper", "extractor", "refiner", "processor", "manufacturer",
    "maker", "builder", "creator", "designer", "architect", "engineer",
    "inventor", "innovator", "pioneer", "founder", "originator", "author",
    "writer", "composer", "poet", "lyricist", "playwright", "screenwriter",
    "novelist", "journalist", "reporter", "correspondent", "columnist",
    "editor", "publisher", "producer", "director", "filmmaker", "actor",
    "performer", "musician", "singer", "dancer", "artist", "painter",
    "sculptor", "photographer", "cameraman", "cinematographer", "designer",
    "illustrator", "animator", "cartoonist", "comedian", "clown", "juggler",
    "acrobat", "gymnast", "athlete", "player", "sportsperson", "coach",
    "trainer", "instructor", "teacher", "professor", "lecturer", "tutor",
    "mentor", "guide", "counselor", "advisor", "consultant", "expert",
    "specialist", "professional", "practitioner", "therapist", "healer",
    "doctor", "physician", "surgeon", "nurse", "paramedic", "dentist",
    "pharmacist", "optician", "therapist", "psychologist", "psychiatrist",
    "counselor", "social", "worker", "clergy", "priest", "minister", "rabbi",
    "imam", "monk", "nun", "preacher", "evangelist", "missionary", "prophet",
    "oracle", "seer", "sage", "wise", "scholar", "academic", "intellectual",
    "thinker", "philosopher", "theorist", "scientist", "researcher", "explorer",
    "discoverer", "observer", "watcher", "witness", "spectator", "audience",
    "listener", "reader", "viewer", "subscriber", "member", "participant",
    "attendee", "delegate", "representative", "ambassador", "emissary",
    "messenger", "courier", "runner", "rider", "driver", "pilot", "captain",
    "navigator", "helmsman", "steersman", "guide", "leader", "chief", "head",
    "boss", "master", "lord", "ruler", "king", "queen", "prince", "princess",
    "duke", "duchess", "earl", "count", "countess", "baron", "baroness",
    "knight", "dame", "sir", "lady", "gentleman", "esquire", "commoner",
    "peasant", "serf", "slave", "servant", "vassal", "liege", "lord",
    "overlord", "suzerain", "monarch", "sovereign", "emperor", "empress",
    "tsar", "kaiser", "sultan", "caliph", "shah", "khan", "raja", "maharaja",
    "nawab", "pasha", "bey", "dey", "emir", "sheikh", "chief", "tribal",
    "clan", "family", "house", "dynasty", "lineage", "ancestry", "heritage",
    "legacy", "inheritance", "bequest", "gift", "present", "donation",
    "contribution", "offering", "sacrifice", "tribute", "tax", "levy",
    "tariff", "duty", "custom", "fee", "charge", "cost", "price", "rate",
    "fare", "toll", "rent", "lease", "hire", "wage", "salary", "pay",
    "stipend", "pension", "annuity", "allowance", "grant", "subsidy",
    "benefit", "perk", "bonus", "commission", "royalty", "dividend",
    "interest", "profit", "gain", "return", "yield", "earnings", "income",
    "revenue", "proceeds", "takings", "receipts", "collection", "fund",
    "pool", "kitty", "pot", "jackpot", "prize", "award", "reward", "honor",
    "distinction", "recognition", "fame", "renown", "reputation", "status",
    "standing", "rank", "position", "station", "place", "slot", "spot",
    "berth", "billet", "assignment", "appointment", "post", "position",
    "job", "work", "employment", "occupation", "profession", "vocation",
    "career", "calling", "mission", "purpose", "aim", "goal", "objective",
    "target", "mark", "bullseye", "quota", "norm", "standard", "benchmark",
    "criterion", "measure", "yardstick", "gauge", "metric", "indicator",
    "index", "sign", "signal", "symptom", "clue", "hint", "tip", "lead",
    "trace", "trail", "track", "spoor", "scent", "smell", "odor", "aroma",
    "fragrance", "perfume", "bouquet", "stench", "stink", "reek", "fume",
    "smoke", "vapor", "steam", "mist", "haze", "fog", "cloud", "murk",
    "gloom", "darkness", "night", "evening", "dusk", "twilight", "dawn",
    "sunrise", "daybreak", "morning", "noon", "midday", "afternoon",
    "evening", "night", "midnight", "witching", "hour", "time", "moment",
    "instant", "second", "minute", "hour", "day", "week", "fortnight",
    "month", "quarter", "year", "decade", "century", "millennium", "eon",
    "era", "epoch", "age", "period", "term", "span", "stretch", "spell",
    "bout", "run", "session", "round", "turn", "phase", "stage", "step",
    "level", "grade", "degree", "rank", "class", "order", "tier", "layer",
    "stratum", "zone", "region", "realm", "domain", "kingdom", "empire",
    "republic", "nation", "country", "land", "state", "province", "county",
    "city", "town", "village", "hamlet", "suburb", "district", "neighborhood",
    "block", "street", "avenue", "road", "highway", "freeway", "motorway",
    "turnpike", "tollway", "parkway", "driveway", "pathway", "walkway",
    "sidewalk", "trail", "track", "course", "route", "line", "railway",
    "subway", "metro", "underground", "tube", "elevated", "monorail",
    "tram", "trolley", "streetcar", "bus", "coach", "shuttle", "van",
    "minibus", "car", "automobile", "vehicle", "auto", "motor", "engine",
    "machine", "mechanism", "apparatus", "device", "gadget", "tool", "instrument",
    "implement", "utensil", "appliance", "equipment", "gear", "kit", "outfit",
    "rig", "setup", "system", "arrangement", "configuration", "layout",
    "design", "plan", "blueprint", "scheme", "diagram", "chart", "graph",
    "map", "plot", "drawing", "sketch", "draft", "outline", "summary",
    "abstract", "synopsis", "overview", "review", "report", "account",
    "record", "log", "journal", "diary", "chronicle", "annals", "history",
    "archive", "files", "documents", "papers", "records", "data", "information",
    "knowledge", "wisdom", "insight", "understanding", "comprehension",
    "grasp", "mastery", "expertise", "proficiency", "skill", "ability",
    "talent", "gift", "genius", "aptitude", "faculty", "power", "capacity",
    "capability", "potential", "possibility", "opportunity", "chance",
    "luck", "fortune", "destiny", "fate", "karma", " Providence", "chance",
    "accident", "incident", "event", "occurrence", "happening", "episode",
    "affair", "matter", "issue", "subject", "topic", "theme", "motif",
    "pattern", "design", "style", "fashion", "trend", "mode", "manner",
    "way", "method", "means", "medium", "channel", "vehicle", "instrument",
    "tool", "device", "agent", "agency", "force", "power", "energy",
    "strength", "vigor", "force", "might", "muscle", "brawn", "sinew",
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy",
    "did", "its", "let", "put", "say", "she", "too", "use", "dad", "mom",
    "act", "add", "age", "ago", "aid", "air", "all", "art", "ask", "bad",
    "bag", "bar", "bat", "bed", "bet", "bid", "big", "bit", "box", "bug",
    "bus", "buy", "car", "cat", "cow", "cry", "cup", "cut", "dog", "dry",
    "due", "ear", "eat", "egg", "end", "eye", "fan", "far", "fat", "fee",
    "few", "fit", "fix", "fly", "fun", "gap", "gas", "gay", "gel", "gem",
    "get", "gig", "god", "gum", "gun", "gut", "guy", "gym", "had", "has",
    "hat", "hay", "hen", "hid", "hip", "hit", "hog", "hop", "hot", "hub",
    "hug", "hut", "ice", "ill", "ink", "inn", "ion", "its", "jam", "jar",
    "jaw", "jay", "jet", "job", "jog", "joy", "jug", "jun", "keg", "key",
    "kid", "kit", "lab", "lad", "lag", "lam", "lap", "law", "lay", "led",
    "leg", "let", "lid", "lie", "lip", "lit", "log", "lot", "low", "mad",
    "man", "map", "mat", "may", "men", "mix", "mob", "mod", "mom", "mop",
    "mud", "mug", "mum", "nap", "net", "new", "nil", "nod", "nor", "not",
    "now", "nun", "nut", "oak", "odd", "off", "oft", "oil", "old", "one",
    "opt", "orb", "ore", "our", "out", "owe", "owl", "own", "pad", "pal",
    "pan", "par", "pat", "paw", "pay", "pea", "pen", "pep", "per", "pet",
    "pie", "pig", "pin", "pit", "pod", "pop", "pot", "pro", "pub", "pup",
    "put", "rag", "ram", "ran", "rap", "rat", "raw", "ray", "red", "ref",
    "rep", "rev", "rib", "rid", "rig", "rim", "rip", "rob", "rod", "roe",
    "rot", "row", "rub", "rug", "rum", "run", "sad", "sap", "sat", "saw",
    "sea", "set", "sew", "sex", "she", "shy", "sin", "sip", "sir", "sit",
    "six", "ski", "sky", "sly", "sob", "sod", "son", "sow", "soy", "spa",
    "spy", "sub", "sue", "sum", "sun", "tab", "tag", "tan", "tap", "tar",
    "tax", "tea", "tee", "ten", "the", "tie", "tin", "tip", "toe", "ton",
    "too", "top", "tow", "toy", "try", "tub", "tug", "tun", "two", "use",
    "van", "vet", "via", "vie", "vow", "wag", "war", "was", "wax", "way",
    "web", "wed", "wee", "wet", "who", "why", "wig", "win", "wit", "woe",
    "won", "woo", "wow", "wry", "yam", "yea", "yen", "yes", "yet", "yew",
    "zip", "zoo", "ace", "bad", "cad", "dad", "fad", "gad", "had", "jad",
    "lad", "mad", "pad", "rad", "sad", "tad", "add", "bed", "fed", "ged",
    "led", "med", "red", "ted", "wed", "zed", "aid", "bid", "did", "fid",
    "gid", "hid", "kid", "lid", "mid", "rid", "sid", "tid", "and", "end",
    "odd", "add", "ere", "ire", "ore", "use", "ale", "elf", "ilk", "elm",
    "arm", "aim", "ban", "can", "dan", "fan", "man", "pan", "ran", "tan",
    "van", "ben", "den", "fen", "gen", "hen", "ken", "men", "pen", "ten",
    "yen", "zen", "bin", "din", "fin", "gin", "kin", "pin", "sin", "tin",
    "win", "yin", "con", "don", "eon", "ion", "hon", "son", "ton", "won",
    "bun", "dun", "fun", "gun", "hun", "nun", "pun", "run", "sun", "tun"
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "protonmail.com", "zoho.com", "aol.com", "live.com", "msn.com",
    "me.com", "mac.com", "fastmail.com", "tutanota.com", "mail.com",
    "gmx.com", "yandex.com", "qq.com", "163.com", "126.com",
    "sean.com", "cookedham.llc", "vault.local", "bitwarden.test",
    "corp.example", "internal.net", "dev.localhost", "sys.admin"
]

URL_DOMAINS = [
    "google.com", "github.com", "amazon.com", "netflix.com", "spotify.com",
    "apple.com", "microsoft.com", "facebook.com", "twitter.com", "linkedin.com",
    "reddit.com", "youtube.com", "instagram.com", "tiktok.com", "discord.com",
    "slack.com", "trello.com", "notion.so", "figma.com", "vercel.com",
    "stripe.com", "shopify.com", "wordpress.com", "medium.com", "substack.com",
    "bankofamerica.com", "chase.com", "wellsfargo.com", "citi.com", "usbank.com",
    "schwab.com", "fidelity.com", "vanguard.com", "etrade.com", "robinhood.com",
    "coinbase.com", "binance.com", "kraken.com", "gemini.com", "crypto.com",
    "healthcare.gov", "mychart.org", "kaiser.org", "cvs.com", "walgreens.com",
    "airbnb.com", "booking.com", "expedia.com", "uber.com", "lyft.com",
    "delta.com", "united.com", "southwest.com", "aa.com", "jetblue.com",
    "nasdaq.com", "nyse.com", "bloomberg.com", "cnbc.com", "wsj.com",
    "reuters.com", "ap.org", "bbc.com", "npr.org", "cnn.com",
    "cookedham.local", "vault.local", "intranet.corp", "admin.sys",
    "portal.internal", "wiki.dev", "docs.ops", "jira.team", "git.local"
]

TWOFA_PROVIDERS = [
    "google.com", "github.com", "amazon.com", "apple.com", "microsoft.com",
    "facebook.com", "twitter.com", "linkedin.com", "discord.com", "slack.com",
    "stripe.com", "shopify.com", "coinbase.com", "binance.com", "bankofamerica.com",
    "chase.com", "schwab.com", "fidelity.com", "healthcare.gov", "mychart.org"
]

FOLDERS = [
    "Personal", "Work", "Finance", "Social", "Shopping", "Travel", "Health",
    "Dev", "Servers", "Clients", "Family", "Media", "Education", "Legal",
    "Taxes", "Investments", "Crypto", "Freelance", "Home", "Auto", "Insurance",
    "Utilities", "Subscriptions", "Gaming", "Streaming", "Food", "Fitness",
    " uncategorized"
]

COLLECTIONS = [
    "default", "shared", "emergency", "team-alpha", "team-beta", "contractors",
    "vendors", "family-shared", "finance-committee", "dev-ops", "security",
    "oncall", "archived", "pending-review", "sensitive", "public"
]

COMMON_WEAK_PASSWORDS = [
    "password", "123456", "12345678", "qwerty", "abc123", "letmein",
    "welcome", "admin", "login", "passw0rd", "password1", "123456789",
    "111111", "123123", "qwerty123", "1q2w3e", "sunshine", "princess",
    "dragon", "football", "baseball", "monkey", "master", "shadow",
    "superman", "michael", "mustang", "access", "love", "pussy", "696969",
    "qwertyuiop", "123321", "password123", "1234567890", "admin123"
]


def rand_word():
    return random.choice(WORDS)


def rand_phrase(min_words=2, max_words=5):
    return " ".join(random.choices(WORDS, k=random.randint(min_words, max_words)))


def rand_email():
    user = rand_word() + "_" + rand_word() + str(random.randint(1, 9999))
    return f"{user}@{random.choice(EMAIL_DOMAINS)}"


def rand_url():
    scheme = random.choice(["https", "http"])
    domain = random.choice(URL_DOMAINS)
    path = "/" + "/".join(random.choices(WORDS, k=random.randint(0, 3)))
    if path == "/":
        path = ""
    return f"{scheme}://{domain}{path}"


def rand_password():
    # Mix of weak and strong passwords
    choice = random.random()
    if choice < 0.15:
        return random.choice(COMMON_WEAK_PASSWORDS)
    elif choice < 0.35:
        return rand_word() + str(random.randint(1, 99))
    elif choice < 0.55:
        # Medium
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=random.randint(8, 12)))
    else:
        # Strong
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(random.choices(chars, k=random.randint(16, 32)))


def rand_date():
    year = random.randint(2018, 2026)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}.{random.randint(0,999):03d}Z"


def make_login():
    has_2fa = random.random() < 0.25
    provider = random.choice(TWOFA_PROVIDERS) if has_2fa else None
    uris = []
    for _ in range(random.randint(0, 3)):
        uris.append({
            "uri": rand_url(),
            "match": random.choice([None, 0, 1, 2, 3, 4, 5])
        })
    return {
        "type": 1,
        "name": rand_phrase(2, 4).title(),
        "notes": rand_phrase(5, 15) if random.random() < 0.4 else None,
        "favorite": random.random() < 0.08,
        "login": {
            "fido2Credentials": [],
            "uris": uris,
            "username": rand_email() if random.random() < 0.7 else rand_word(),
            "password": rand_password(),
            "totp": f"otpauth://totp/{rand_word()}?secret={secrets.token_hex(10).upper()}&issuer={provider or rand_word()}" if has_2fa else None,
        },
        "passwordHistory": None,
    }


def make_note():
    return {
        "type": 2,
        "name": rand_phrase(2, 5).title(),
        "notes": rand_phrase(20, 80) if random.random() < 0.8 else rand_phrase(5, 10),
        "favorite": random.random() < 0.05,
        "secureNote": {"type": 0},
        "passwordHistory": None,
    }


def make_card():
    return {
        "type": 3,
        "name": f"{random.choice(['Visa', 'MasterCard', 'Amex', 'Discover', 'Chase', 'Citi', 'Capital One'])} {random.choice(['Personal', 'Business', 'Credit', 'Debit', 'Platinum', 'Gold', 'Blue'])}",
        "notes": rand_phrase(3, 8) if random.random() < 0.3 else None,
        "favorite": random.random() < 0.05,
        "card": {
            "cardholderName": f"{rand_word().title()} {rand_word().title()}",
            "brand": random.choice(["Visa", "Mastercard", "Amex", "Discover", "JCB", "Diners Club", None]),
            "number": "".join(random.choices(string.digits, k=16)),
            "expMonth": f"{random.randint(1, 12):02d}",
            "expYear": str(random.randint(2025, 2032)),
            "code": "".join(random.choices(string.digits, k=3)),
        },
        "passwordHistory": None,
    }


def make_identity():
    return {
        "type": 4,
        "name": f"{rand_word().title()} {rand_word().title()} Identity",
        "notes": rand_phrase(3, 8) if random.random() < 0.3 else None,
        "favorite": random.random() < 0.05,
        "identity": {
            "title": random.choice(["Mr", "Mrs", "Ms", "Dr", "Prof", None]),
            "firstName": rand_word().title(),
            "middleName": rand_word().title() if random.random() < 0.3 else None,
            "lastName": rand_word().title(),
            "address1": f"{random.randint(1, 9999)} {rand_word().title()} {random.choice(['St', 'Ave', 'Blvd', 'Rd', 'Ln', 'Dr', 'Way'])}",
            "address2": f"Apt {random.randint(1, 500)}" if random.random() < 0.4 else None,
            "address3": None,
            "city": random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte", "San Francisco", "Indianapolis", "Seattle", "Denver", "Washington", "Boston", "El Paso", "Nashville", "Detroit", "Oklahoma City", "Portland", "Las Vegas", "Louisville", "Baltimore", "Milwaukee", "Albuquerque", "Tucson", "Fresno", "Mesa", "Sacramento", "Atlanta", "Kansas City", "Colorado Springs", "Omaha", "Raleigh", "Miami", "Long Beach", "Virginia Beach", "Oakland", "Minneapolis", "Tulsa", "Arlington", "Wichita", "Bakersfield"]),
            "state": random.choice(["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"]),
            "postalCode": f"{random.randint(10000, 99999):05d}",
            "country": "US",
            "company": f"{rand_word().title()} {random.choice(['Inc', 'LLC', 'Corp', 'Ltd', 'Co', 'Group', 'Partners'])}" if random.random() < 0.6 else None,
            "email": rand_email(),
            "phone": f"{random.randint(200, 999):03d}-{random.randint(200, 999):03d}-{random.randint(1000, 9999):04d}",
            "ssn": f"{random.randint(100, 999):03d}-{random.randint(10, 99):02d}-{random.randint(1000, 9999):04d}" if random.random() < 0.15 else None,
            "username": rand_word() if random.random() < 0.3 else None,
            "passportNumber": None,
            "licenseNumber": None,
        },
        "passwordHistory": None,
    }


def make_ssh():
    return {
        "type": 5,
        "name": f"{rand_word().title()} SSH Key — {rand_word().title()}",
        "notes": rand_phrase(3, 8) if random.random() < 0.3 else None,
        "favorite": random.random() < 0.05,
        "sshKey": {
            "privateKey": f"-----BEGIN OPENSSH PRIVATE KEY-----\n{secrets.token_hex(64)}\n{secrets.token_hex(64)}\n{secrets.token_hex(64)}\n-----END OPENSSH PRIVATE KEY-----" if random.random() < 0.3 else None,
            "publicKey": f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI{secrets.token_urlsafe(32)} {rand_email()}" if random.random() < 0.7 else None,
            "fingerprint": f"SHA256:{secrets.token_hex(16)}" if random.random() < 0.7 else None,
        },
        "passwordHistory": None,
    }


def make_custom_fields(item):
    if random.random() < 0.3:
        return item
    fields = []
    for _ in range(random.randint(1, 4)):
        ftype = random.choice([0, 1, 2, 3])
        name = rand_phrase(1, 2).title()
        if ftype == 0:
            value = rand_phrase(1, 3)
        elif ftype == 1:
            value = rand_password()
        elif ftype == 2:
            value = str(random.randint(0, 1))
        else:
            value = rand_phrase(1, 3)
        fields.append({
            "name": name,
            "value": value,
            "type": ftype,
            "linkedId": None,
        })
    item["fields"] = fields
    return item


def make_item():
    r = random.random()
    if r < 0.55:
        item = make_login()
    elif r < 0.75:
        item = make_note()
    elif r < 0.85:
        item = make_card()
    elif r < 0.95:
        item = make_identity()
    else:
        item = make_ssh()
    item = make_custom_fields(item)
    item["id"] = str(uuid.uuid4())
    item["folderId"] = str(random.choice(FOLDERS)) if random.random() < 0.8 else None
    item["reprompt"] = 1 if random.random() < 0.05 else 0
    item["collectionIds"] = [random.choice(COLLECTIONS)] if random.random() < 0.15 else None
    item["creationDate"] = rand_date()
    item["revisionDate"] = rand_date()
    return item


def generate_vault(n=5000):
    folders = []
    for f in FOLDERS:
        folders.append({
            "id": f,
            "name": f,
        })
    items = [make_item() for _ in range(n)]
    # Create ~100 intentional duplicates with varying confidence
    dup_sources = random.sample(items, 100)
    for src in dup_sources:
        dup = json.loads(json.dumps(src))
        dup["id"] = str(uuid.uuid4())
        dup["name"] = src["name"]  # same name
        if "login" in dup and "login" in src:
            dup["login"]["username"] = src["login"].get("username", "")
            if random.random() < 0.5:
                dup["login"]["password"] = src["login"].get("password", "")
            if random.random() < 0.3:
                dup["login"]["uris"] = src["login"].get("uris", [])
        items.append(dup)
    return {"folders": folders, "items": items}


if __name__ == "__main__":
    vault = generate_vault(5000)
    out_path = Path("/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(vault, f, indent=None, ensure_ascii=False)
    print(f"Generated {len(vault['items'])} items -> {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024 / 1024:.2f} MB")
