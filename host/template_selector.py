"""Deterministic source-only retrieval for profile-scoped teaching examples."""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=2)
def _template_validators():
    """Build cached Draft 2020-12 validators for the authored teaching schemas."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schema_dir = ROOT / "shared" / "template_schemas_v1_5_2"
    registry = Registry()
    resources = {}
    for path in sorted(schema_dir.glob("*.schema.json")):
        uri = "https://vln.local/shared/template_schemas_v1_5_2/" + path.name
        data = json.loads(path.read_bytes())
        resources[uri] = Resource.from_contents(data)
        registry = registry.with_resource(uri, resources[uri])
    validators = {}
    for role in ("generator", "reviewer"):
        path = schema_dir / (role + "_template.schema.json")
        data = json.loads(path.read_bytes())
        data["$id"] = "https://vln.local/shared/template_schemas_v1_5_2/" + path.name
        validators[role] = Draft202012Validator(data, registry=registry)
    return validators


def validate_dynamic_identity(role, profile, row):
    """Shared fail-closed identity gate for every Profile's Dynamic library."""
    if role not in ("generator", "reviewer") or profile not in PROFILES:
        raise ValueError("Unsupported role/profile")
    dataset = PROFILES[profile]
    language = "en" if profile == "r2r-en" else "en-US"
    prefixes = {
        ("R2R", "generator"): ("R2R-GEN-",),
        ("R2R", "reviewer"): ("R2R-REV-", "R2R-DIAG-"),
        ("RxR", "generator"): ("RxR-GEN-",),
        ("RxR", "reviewer"): ("RxR-REV-", "RxR-DIAG-"),
    }
    if (row.get("role") != role or row.get("dataset_scope") != dataset
            or row.get("language") != language):
        raise ValueError(f"Invalid {dataset} {role} dynamic template identity: {row.get('template_id')}")
    if not row.get("template_id", "").startswith(prefixes[(dataset, role)]):
        raise ValueError(f"Invalid {dataset} {role} dynamic template ID: {row.get('template_id')}")


def validate_template(role, row, *, source_path=""):
    """Fail closed on malformed teaching records before they reach Prompt Assembly."""
    if role not in ("generator", "reviewer"):
        raise ValueError(f"Unknown template role: {role}")
    validator = _template_validators()[role]
    error = next(validator.iter_errors(row), None)
    if error is not None:
        location = "/".join(str(part) for part in error.absolute_path)
        raise ValueError(
            f"Invalid {role} teaching template {row.get('template_id')} at "
            f"{source_path or '<unknown>'}:{location}: {error.message}"
        )
DEFAULT_EXAMPLES = None  # Profile-aware: R2R 6-8; RxR 2-4 in addition to its fixed core.
PROFILES = {'r2r-en': 'R2R', 'rxr-en-us': 'RxR'}
PATTERNS = {
    'ordinal_target_selection': r'first|second|third|fourth|last|1st|2nd|3rd',
    'stairs_or_level_change': r'stairs?|staircase|stairway|landing|upstairs|downstairs',
    'return_or_revisit': r'return|again|retrace|backtrack|same|back to',
    'conditional_observation': r'if|otherwise|unless',
    'bounded_motion': r'steps?|halfway|paces?|feet|meters?',
    'doorway_selection_and_crossing': r'doors?|doorway|archway|entrance|threshold',
    'orientation_or_reference_frame': r'left|right|behind|facing|clockwise',
    'room_transition': r'enter|exit|leave|room|hallway',
    'intermediate_stop_or_wait': r'stop|wait|stand',
    'while': r'while|during', 'until': r'until', 'before': r'before', 'after': r'after|once|when',
    'correction': r'actually|sorry|i mean|instead', 'negation': r"not|never|without|don't",
    'endpoint': r'edge|end|base|bottom|top|foot|near|beside',
    'description': r'you will see|on your|there is|there are',
}
STOP = set('the an a is are it you your will of and to on with then that in at from there have be for this'.split())


def source(row):
    return (row.get('input') or row['review_input'])['original_instruction']


def normalized(text):
    return ' '.join(text.casefold().split())


def features(text):
    words = re.findall(r"[a-z]+", text.casefold())
    lex = {w for w in words if w not in STOP}
    cues = {name for name, pat in PATTERNS.items()
            if re.search(r'\b(?:' + pat + r')\b', text, re.I)}
    return cues, lex


@lru_cache(maxsize=4)
def library(role, profile):
    if role not in ('generator', 'reviewer') or profile not in PROFILES:
        raise ValueError('Unsupported role/profile')
    folder = ROOT/role/'templates'/PROFILES[profile]
    # Shared profile-driven allowlist: both datasets use the same loader.
    dynamic_dirs = ('val_seen',) if role == 'generator' else ('paired', 'diagnostics')
    files = []
    for kind in dynamic_dirs:
        files.extend(sorted((folder/kind).glob('*.json')))

    rows = [json.loads(path.read_bytes()) for path in files]
    if not rows or len({row['template_id'] for row in rows}) != len(rows):
        raise ValueError('Empty library or duplicate template IDs')
    for path, row in zip(files, rows):
        validate_template(role, row, source_path=path.relative_to(ROOT).as_posix())

    dataset = PROFILES[profile]
    for row in rows:
        validate_dynamic_identity(role, profile, row)

    # R2R's historical val_seen Core promotions are excluded from its Dynamic
    # pool. RxR Core is migrated from train-guide material and is not duplicated
    # in the val_seen Dynamic pool; the same loader still validates both.
    if dataset == 'R2R':
        core_folder = folder/'core'
        core_rows = [json.loads(path.read_bytes()) for path in sorted(core_folder.glob('*.json'))]
        promoted_ids = [row.get('provenance', {}).get('core_curated_from') for row in core_rows]
        if len(core_rows) != 10 or any(not item for item in promoted_ids) or len(set(promoted_ids)) != 10:
            raise ValueError(f'{dataset} {role} Core provenance must identify ten unique source templates')
        if not set(promoted_ids).issubset({row['template_id'] for row in rows}):
            raise ValueError(f'{dataset} {role} Core provenance references missing Dynamic source templates')
        rows = [row for row in rows if row['template_id'] not in set(promoted_ids)]

    expected_counts = {
        ('R2R', 'generator'): 25, ('R2R', 'reviewer'): 52,
        ('RxR', 'generator'): 35, ('RxR', 'reviewer'): 64,
    }
    if len(rows) != expected_counts[(dataset, role)]:
        raise ValueError(f'{dataset} {role} Dynamic count mismatch: expected {expected_counts[(dataset, role)]}, found {len(rows)}')

    if role == 'reviewer':
        promoted_gen_ids = set()
        if dataset == 'R2R':
            gen_core_dir = ROOT/'generator'/'templates'/dataset/'core'
            gen_core = [json.loads(path.read_bytes()) for path in sorted(gen_core_dir.glob('*.json'))]
            promoted_gen_ids = {row.get('provenance', {}).get('core_curated_from') for row in gen_core}
            if len(promoted_gen_ids) != 10 or None in promoted_gen_ids:
                raise ValueError(f'{dataset} Generator Core provenance is incomplete')
        paired = [row for row in rows if row.get('pair_id')]
        diagnostics = [row for row in rows if not row.get('pair_id')]
        paired_ids = [row['pair_id'] for row in paired]
        expected_pairs = {f'{dataset}-GEN-{i:03d}' for i in range(1, 36)} - promoted_gen_ids
        expected_paired = 29 if dataset == 'R2R' else 35
        expected_diagnostics = 23 if dataset == 'R2R' else 29
        if len(paired) != expected_paired or len(diagnostics) != expected_diagnostics:
            raise ValueError(f'{dataset} Reviewer pool count mismatch: paired={len(paired)}, diagnostics={len(diagnostics)}')
        if len(set(paired_ids)) != len(paired_ids) or not expected_pairs.issubset(set(paired_ids)):
            raise ValueError(f'{dataset} Reviewer Dynamic pairs are duplicated or missing non-Core Generator pairs')

    return rows

# These features describe a local clause, not a navigation plan. They only rank demonstrations.
MARKER = re.compile(r"\b(before|after|while|until|once|when)\b", re.I)
ACTION = re.compile(r"\b(enter|exit|leave|pass|turn|walk|go|veer|reach|stop|wait)(?:ing|ed|s)?\b", re.I)
TYPE_CUES = {
    "ordinal_target_selection": {"ordinal", "count"}, "bounded_motion": {"bounded", "halfway"},
    "return_or_revisit": {"return", "revisit"}, "before": {"before", "temporal"},
    "after": {"after", "handoff", "temporal"}, "until": {"until", "temporal"},
    "while": {"ongoing", "temporal"}, "conditional_observation": {"conditional", "branch"},
    "negation": {"negation", "prohibition"}, "correction": {"correction"},
    "room_transition": {"transition"}, "intermediate_stop_or_wait": {"stop", "endpoint"},
    "orientation_or_reference_frame": {"orientation", "direction", "reference"},
}


def relations(text):
    result = set()
    for clause in re.split(r"[.;!?]", text.lower()):
        for marker in MARKER.finditer(clause):
            # A fronted condition may end at a comma. Retain the event after the
            # marker and the turn governed by that condition as separate signals.
            condition, comma, following = clause[marker.end():].partition(",")
            event = ACTION.search(condition)
            if event:
                result.add((marker[1], "event", event[1]))
            landmark = re.search(r"\b(doors?|doorway|stairs?|staircase|kitchen|hallway|bedroom|bathroom|landing|archway)\b", condition)
            if landmark:
                result.add((marker[1], "landmark", landmark[1].rstrip("s")))
            main = following if comma else clause[:marker.start()]
            turn = re.search(r"\b(?:turn|veer|go)\s+(?:to\s+the\s+)?(left|right)\b", main)
            if turn:
                result.add((marker[1], "turn", turn[1]))
    return result


def task_type(row):
    notes = row["teaching_notes"]
    return (notes.get("segmentation_pattern") or notes.get("review_pattern")
            or (row["provenance"].get("corruption_pattern") if isinstance(row["provenance"], dict) else None)
            or "")


def rank_examples(rows, text, count, excluded=()):
    cues, words = features(text)
    query_relations = relations(text)
    type_terms = set().union(*(TYPE_CUES.get(c, set()) for c in cues))
    if len(re.findall(r"\b(?:stop|wait|stand|stay|remain)\b", text, re.I)) > 1:
        type_terms.update(("refinement", "intermediate", "stop"))
    if re.search(r",\s*(?:veering|turning|keeping|facing)\b", text, re.I):
        type_terms.update(("temporal", "ongoing", "dependency"))
    if len(words) < 12 and not query_relations:
        type_terms.add("single")
    if "room_transition" in cues and len(ACTION.findall(text)) >= 3:
        type_terms.add("distinct")
    options = []
    df = Counter()
    blocked = {normalized(text), *excluded}
    for row in rows:
        identity = normalized(source(row))
        if identity in blocked:
            continue
        tags, terms = features(source(row))
        tags.update(row.get("retrieval_tags", []))
        df.update(tags | terms)
        options.append((row, tags, terms, identity))
    weight = {t: 1 + math.log((len(options)+1)/(freq+1)) for t, freq in df.items()}
    candidates = []
    for row, tags, terms, identity in options:
        common = cues & tags
        relation_hits = query_relations & relations(source(row))
        annotations = [task_type(row), *row.get("retrieval_tags", [])]
        type_hits = type_terms & set("_".join(annotations).lower().split("_"))
        score = (sum(weight[t] for t in common)
                 + sum(weight[t] for t in words & terms)/math.sqrt(max(1,len(terms)))
                 + 4*len(relation_hits) + 2*len(type_hits) - .12*len(tags-cues))
        coverage = common | relation_hits | {("type", t) for t in type_hits}
        candidates.append((row, identity, score, coverage))
    chosen, covered = [], set()
    while candidates and len(chosen) < count:
        row, identity, _, coverage = max(candidates, key=lambda c: c[2]+1.5*len(c[3]-covered))
        chosen.append(row)
        covered.update(coverage)
        candidates = [c for c in candidates if c[1] != identity]
    return chosen


def select_examples(role, profile, source_text, count=DEFAULT_EXAMPLES, mode="adaptive"):
    rows = library(role, profile)
    if mode == "all":
        return [r["template_id"] for r in rows]
    if mode != "adaptive":
        raise ValueError("Unknown example selection mode")
    gen = library("generator", profile)
    if count is not None:
        minimum, maximum = (2, 4) if profile == "rxr-en-us" else (1, len(gen))
        if type(count) is not int or not minimum <= count <= maximum:
            raise ValueError(
                f"Invalid {profile} dynamic Generator count; expected {minimum}..{maximum}"
            )
    cues, _ = features(source_text)
    distinct = cues - {"orientation_or_reference_frame","room_transition","intermediate_stop_or_wait"}
    extra = min(2, len(distinct)//3 + int(len(source_text.split())>=65))
    if profile == "rxr-en-us":
        # RxR receives a smaller, complementary dynamic set because ten
        # fixed core cases are always injected by the compiler.
        base_count = (2 + extra) if count is None else count
        if type(base_count) is not int or not 2 <= base_count <= 4:
            raise ValueError("RxR dynamic Generator count must be between 2 and 4")
        diagnostic_count = min(2, int(len(distinct) >= 3) + int(len(source_text.split()) >= 65))
    else:
        base_count = 6 + extra if count is None else count
        diagnostic_count = 2 + extra
    base = rank_examples(gen, source_text, base_count)
    ids = [r["template_id"] for r in base]
    if role == "generator":
        return ids
    pairs = {}
    for row in rows:
        pair = row.get("pair_id")
        if pair:
            if pair in pairs:
                raise ValueError(f"Duplicate paired reviewer for {pair}")
            pairs[pair] = row
    missing = [i for i in ids if i not in pairs]
    if missing:
        raise ValueError(f"Missing paired Reviewer templates for Generator IDs: {missing}")
    paired = [pairs[i] for i in ids]
    diagnostics = rank_examples([r for r in rows if not r.get("pair_id")], source_text,
                                diagnostic_count, excluded=[normalized(source(r)) for r in paired])
    return [r["template_id"] for r in paired+diagnostics]


def selection_evidence(role, profile, text, ids):
    cues, _ = features(text)
    anchors = relations(text)
    by_id = {row["template_id"]: row for row in library(role,profile)}
    result = []
    for template_id in ids:
        row = by_id[template_id]
        example = source(row)
        tags, _ = features(example)
        result.append(dict(template_id=template_id, authored_type=task_type(row),
                           pair_id=row.get("pair_id"), matched_cues=sorted(cues & (tags | set(row.get("retrieval_tags", [])))),
                           matched_relations=sorted(anchors & relations(example))))
    return result


def write_type_index(role):
    """Build an explicit fixed-core / dynamic inventory from runtime-eligible assets."""
    folder = ROOT/role/"templates"
    lines = ["# Template Library Index", "",
             "Fixed Core is loaded unconditionally in stable ID order. Dynamic entries are eligible for profile-scoped retrieval. Legacy entries are provenance-only and are not runtime inputs.",
             "", "## Fixed Core", "",
             "|Dataset|Template|Pair|Authored pattern|Retrieval tags|",
             "|---|---|---|---|---|"]
    for profile, dataset in PROFILES.items():
        for path in sorted((folder/dataset/"core").glob("*.json")):
            row = json.loads(path.read_bytes())
            lines.append("|{}|[{}]({})|{}|{}|{}|".format(
                dataset, row["template_id"], path.relative_to(folder).as_posix(),
                row.get("pair_id") or "—", task_type(row) or "—",
                ", ".join(row.get("retrieval_tags", [])) or "—"))
    lines.extend(["", "## Dynamic Library", "",
                  "|Dataset|Template|Kind|Pair|Authored pattern|Retrieval tags|",
                  "|---|---|---|---|---|---|"])
    for profile, dataset in PROFILES.items():
        allowed = ("val_seen",) if role == "generator" else ("paired", "diagnostics")
        for kind in allowed:
            for path in sorted((folder/dataset/kind).glob("*.json")):
                row = json.loads(path.read_bytes())
                lines.append("|{}|[{}]({})|{}|{}|{}|{}|".format(
                    dataset, row["template_id"], path.relative_to(folder).as_posix(), kind,
                    row.get("pair_id") or "—", task_type(row) or "—",
                    ", ".join(row.get("retrieval_tags", [])) or "—"))
    (folder/"INDEX.md").write_bytes(("\n".join(lines)+"\n").encode("utf-8"))
