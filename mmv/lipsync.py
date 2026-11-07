"""Lip-sync mode: which passages sing, who sings, and a deterministic check on the written prompt.

Sealed lips stay the default for every passage; only passages whose audible slice carries sung
lyric lines switch to the singing prompt set. The sealed-lips rule, rigging tail and validators
are never altered; everything here sits outside the original engine.

SINGING_RULES and SINGING_AUDIO_SENTENCE were approved by the owner on 2026-10-19.
"""
from __future__ import annotations

import math
import random
import re

from .engine.grid import FPS
from .engine.schema import RIGGING_TAIL

OVERLAP_SECONDS = 0.75        # a passage sings when sung lines cover at least this much of its audible slice
SHOT_SECONDS = 0.5            # a shot must describe singing when sung lines cover at least this much of it
MAX_LINES = 500
MAX_LINE_CHARS = 300
MAX_SECONDS = 36000
TIMINGS = ('manual', 'matched', 'interpolated', 'uncertain')
UNCONFIRMED = ('interpolated', 'uncertain')   # guessed times never switch a passage to singing until confirmed

SINGING_RULES = (
    "This passage contains singing. The job carries a `singing` object naming the singer (a cast member), "
    "the picture tag bound to that member, and the sung lines with their times in seconds from the start of "
    "the passage. The `singing.shots` list says, for each shot, whether it is sung and which words fall inside "
    "it. The singer sings exactly those words. In every sung shot where the singer is visible, describe "
    "their lips, jaw and breath forming the words being sung at that moment, in time with the music, and "
    "quote exactly that shot's words in its action. Never invent, change or omit words. Every other cast "
    "member keeps lips firmly sealed and jaw relaxed and does not sing, speak or mouth words; this "
    "overrides any instruction not to force sealed lips. When the singer is not visible in a shot, state "
    "that no one on screen is singing."
)
SINGING_AUDIO_SENTENCE = (
    "{music_tag} is the song's audio for this passage: the singer's lip movements follow the sung vocal "
    "in it, and its beat and pacing guide the visuals."
)
SINGER_DIRECTION = "sings these lines in time with the song"


def clean_lines(lines):
    """Validated lyric lines [{start, end, text}] in seconds on the song clock, sorted by start."""
    if not lines:
        return []
    if not isinstance(lines, list) or len(lines) > MAX_LINES:
        raise ValueError(f'Lyric lines must be a list of at most {MAX_LINES} lines')
    cleaned = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError('Each lyric line needs start, end and text')
        start, end, text = line.get('start'), line.get('end'), line.get('text')
        for value in (start, end):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Lyric line times must be numbers of seconds')
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_LINE_CHARS:
            raise ValueError(f'Each lyric line needs text of 1 to {MAX_LINE_CHARS} characters')
        if not 0 <= start < end <= MAX_SECONDS:
            raise ValueError('Each lyric line must start before it ends, within the song')
        timing = line.get('timing', 'manual')
        if timing not in TIMINGS:
            raise ValueError('Lyric line timing must be one of ' + ', '.join(TIMINGS))
        entry = {'start': round(float(start), 3), 'end': round(float(end), 3), 'text': ' '.join(text.split()), 'timing': timing}
        section = line.get('section')
        if section:
            if not isinstance(section, str) or len(section) > 40:
                raise ValueError('A lyric line section label must be text of at most 40 characters')
            entry['section'] = section.strip().lower()
        cleaned.append(entry)
    return sorted(cleaned, key=lambda line: (line['start'], line['end']))


def _union_seconds(intervals, low, high):
    total, cursor = 0.0, low
    for start, end in sorted((max(a, low), min(b, high)) for a, b in intervals if min(b, high) > max(a, low)):
        if end > cursor:
            total += end - max(start, cursor)
            cursor = end
    return total


def passage_lines(lines, start_s, end_s):
    """Lines overlapping the audible slice, clipped to it, with times relative to the slice start."""
    result = []
    for line in lines:
        start, end = max(line['start'], start_s), min(line['end'], end_s)
        if end > start:
            item = {'start': round(start - start_s, 3), 'end': round(end - start_s, 3), 'text': line['text']}
            if line.get('section'):
                item['section'] = line['section']
            result.append(item)
    return result


def resolve_singer(roster_ids, singers, seed):
    """The main singer: the first chosen singer in the roster, otherwise a seeded pick."""
    roster = sorted(roster_ids)
    for actor_id in singers or []:
        if actor_id in roster:
            return actor_id
    return random.Random((seed ^ 0x51A6E) & 0x7FFFFFFF).choice(roster) if roster else None


def plan_passages(segments, casting, lines, singers, seed):
    """Which passages sing and who sings each: resolved once at preview and replayed on resume."""
    roster = [member['actor_id'] for member in (casting or {}).get('roster', [])]
    singer = resolve_singer(roster, singers, seed)
    unconfirmed = [line for line in lines if line.get('timing') in UNCONFIRMED]
    lines = [line for line in lines if line.get('timing') not in UNCONFIRMED]     # only confirmed lines can unseal a passage
    passages = {}
    for segment in segments:
        sid = segment.segment_id
        sung = passage_lines(lines, segment.audio_slice_start_s, segment.audio_slice_end_s)
        covered = _union_seconds([(item['start'], item['end']) for item in sung], 0.0,
                                 segment.audio_slice_end_s - segment.audio_slice_start_s)
        entry = {'singing': False, 'reason': 'no sung lines in this passage', 'actor_id': None, 'picture_tag': None,
                 'lines': [], 'sung_seconds': round(covered, 3)}
        if covered >= OVERLAP_SECONDS:
            cast = casting_for(casting, sid)
            chosen = next((member for member in cast if member.get('actor_id') == singer), None)
            if not cast:
                entry['reason'] = 'sung lines here, but no actor is cast in this passage'
            elif chosen is None:
                # Only the main singer sings (a male vocal is not lip-synced by another actor); the passage stays sealed.
                entry['reason'] = 'sung lines here, but the main singer is not on screen'
            else:
                entry.update(singing=True, reason='main singer', actor_id=chosen.get('actor_id'),
                             picture_tag=chosen.get('picture_tag'), lines=sung)
        passages[sid] = entry
    names = {member['actor_id']: member.get('display_name') or member['actor_id'] for member in (casting or {}).get('roster', [])}
    return {'mode': 'lip_sync', 'singer': singer, 'overlap_seconds': OVERLAP_SECONDS, 'actors': names, 'passages': passages,
            'unconfirmed_lines': len(unconfirmed)}


def shot_lyrics(segment, lines):
    """For every shot of a passage: whether it is sung and the words falling inside it (each overlapping line is
    split by time, so a long line is shared out across its shots). `lines` are passage-relative."""
    out = []
    for shot in segment.shots:
        start, end = shot.start_frame / FPS, (shot.start_frame + shot.frames) / FPS
        words, spans = [], []
        for line in lines:
            low, high = max(line['start'], start), min(line['end'], end)
            if high <= low:
                continue
            spans.append((low, high))
            tokens = line['text'].split()
            span = line['end'] - line['start']
            first = int(round((low - line['start']) / span * len(tokens)))
            last = int(round((high - line['start']) / span * len(tokens)))
            if last <= first:
                last = min(len(tokens), first + 1)
                first = max(0, last - 1)
            words += tokens[first:last]
        sung = _union_seconds(spans, start, end)
        out.append({'n': shot.n, 'sung': sung >= SHOT_SECONDS, 'words': ' '.join(words) if sung >= SHOT_SECONDS else ''})
    return out


def cast_refs(cast, singer_id):
    """(singer references, other references): each cast member is `<Subject N>` (position, 1-based) and their picture tag."""
    singer, others = [], []
    for index, member in enumerate(cast):
        refs = [member.get('picture_tag'), f'<Subject {index + 1}>']
        (singer if member.get('actor_id') == singer_id else others).extend(r for r in refs if r)
    return singer, others


def casting_for(casting, segment_id):
    entry = ((casting or {}).get('segments') or {}).get(segment_id) or {}
    return list(entry.get('cast') or [])


def with_singer_lines(cast, actor_id, lines):
    """The cast for a singing passage's job: only the singer carries lines (the natural-mode lines field)."""
    return [{**member, 'lines': [item['text'] for item in lines], 'direction': SINGER_DIRECTION}
            if member.get('actor_id') == actor_id else member for member in cast]


def singing_audio_sentence(music_tag):
    return SINGING_AUDIO_SENTENCE.format(music_tag=music_tag)


def swap_audio_sentence(prompt, music_tag):
    """Replace the engine's rhythm-only audio sentence in an assembled prompt (engine untouched)."""
    original = (f"{music_tag} is the rhythmic and tempo reference for the target "
                f"video, providing the beat and pacing the visuals follow.")
    return prompt.replace(original, singing_audio_sentence(music_tag))


_WORDS_RE = re.compile(r"[a-z0-9']+")


def _words(text):
    return _WORDS_RE.findall(text.lower())


SEALED_TERMS = re.compile(r"\b(sealed|closed mouth|mouth (is )?(closed|shut)|lips (are |stay |remain )?(shut|closed|together|pressed)|"
                          r"silent|silently|mute|mouthless|tight-lipped)\b", re.I)
SINGING_TERMS = re.compile(r"\b(sing|sings|singing|sang|sung|vocals?|lyrics?|lip-?sync\w*|mouths? the words|mouthing|croons?|belts?|"
                           r"chants?|hums?|speaks?|speaking|spoke|talks?|talking|says?|shouts?|whispers?|rapping|raps?)\b", re.I)
PRONOUN_START = re.compile(r"^(he|she|it|they|his|her|its|their|him|them)\b", re.I)
OPEN_MOUTH = re.compile(r"\b(lips? (part|parts|parted|open|opens|opened|moving|moves?)|mouth (open|opens|opened|agape|moving|moves?)|opens? (his|her|its|their) mouth)\b", re.I)
NEGATION = re.compile(r"\b(not|never|no|without|nor|doesn't|don't|isn't|neither|cannot|can't)\b", re.I)
SINGER_ACTION = re.compile(r"\b(sing|sings|singing|sang|sung|lips?|mouth|mouths|mouthing|jaw|teeth|tongue|breath|note|voice|vocals?)\b", re.I)


_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|(?<!\w)'[^']*'(?!\w)")
_MASK = {c: chr(1 + i) for i, c in enumerate('.!?,;:')}
_UNMASK = {v: k for k, v in _MASK.items()}
_MASK_TRANS = str.maketrans(_MASK)
_UNMASK_TRANS = str.maketrans(_UNMASK)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE_SPLIT = re.compile(r"[;:]| while | whereas | as | but | then |, ")


def _units(body, singer_refs, other_refs):
    """(clause, owner) pairs: owner is 'singer', 'other', 'both' or None. A clause with no cast reference ("He sings
    'I am'") belongs to whoever the previous clause was about. Quoted lyrics are never cut at their punctuation."""
    masked = _QUOTED.sub(lambda m: m.group(0).translate(_MASK_TRANS), body)
    units, subject = [], None
    for sentence in (p.strip() for p in _SENTENCE_SPLIT.split(masked) if p.strip()):
        for clause in (c.strip() for c in _CLAUSE_SPLIT.split(sentence) if c.strip()):
            has_singer, has_other = any(r in clause for r in singer_refs), any(r in clause for r in other_refs)
            continued = subject if PRONOUN_START.match(clause) else None      # only "He sings..." continues the last actor
            owner = 'both' if has_singer and has_other else 'singer' if has_singer else 'other' if has_other else continued
            subject = owner if owner in ('singer', 'other') else None if owner == 'both' else subject   # scene clauses keep the antecedent
            units.append((clause.translate(_UNMASK_TRANS), owner))
    return units


def _quotes_line(body, lines):
    body_words = ' '.join(_words(body))
    for line in lines:
        words = _words(line['text'])
        if not words:
            continue
        size = min(2, len(words))
        for i in range(len(words) - size + 1):
            if ' '.join(words[i:i + size]) in body_words:
                return True
    return False


ABSENT = re.compile(r"\b(no one (on screen )?is singing|nobody is singing|is absent|is not visible|out of frame|off-?screen)\b", re.I)


def lipsync_problems(prompt, shot_bodies, segment, singing, singer_refs=None, other_refs=()):
    """Deterministic, shot-level guard for a singing passage. It cannot prove the model will lip-sync; it rejects prompts
    that contradict the plan: a sealed or silent singer in a sung shot, a singing bystander, the shot's words not quoted
    in the sentence about the singer, or the sealed-lips closing phrase. Actors appear in shots as `<Subject N>`
    (their position in the cast), so both that and the picture tag count as references to them."""
    problems = []
    if RIGGING_TAIL.rstrip('.').lower() in prompt.lower():
        problems.append('This passage sings, so it must not use the sealed-lips closing phrase.')
    refs = list(singer_refs or [singing['picture_tag']])
    others = [r for r in other_refs if r and r not in refs]
    label = refs[-1]
    plan = shot_lyrics(segment, singing['lines'])
    for shot, body, wanted in zip(segment.shots, shot_bodies, plan):
        sung = wanted['sung']
        units = _units(body, refs, others)
        for clause, owner in units:
            mouth_claim = SEALED_TERMS.search(clause) or SINGING_TERMS.search(clause)
            if owner == 'both' and mouth_claim:
                problems.append(f'Shot {shot.n}: describe {label} and the other cast members in separate sentences.')
            elif owner == 'singer' and sung and SEALED_TERMS.search(clause) and not NEGATION.search(clause):
                problems.append(f'Shot {shot.n} is sung, so {label} cannot have sealed or silent lips in it.')
            elif owner == 'other' and (SINGING_TERMS.search(clause) or OPEN_MOUTH.search(clause)) and not NEGATION.search(clause):
                problems.append(f'Shot {shot.n}: only {label} sings; other cast members must keep lips sealed and not sing, speak or open their mouths.')
        if not sung or ABSENT.search(body):
            continue
        singer_clauses = [clause for clause, owner in units if owner == 'singer' and SINGER_ACTION.search(clause)]
        if not singer_clauses:
            problems.append(f'Shot {shot.n} is sung ({wanted["words"]!r}) but does not describe {label} singing it; '
                            f'if {label} is not in the shot, say that no one on screen is singing.')
        elif len(wanted['words'].split()) >= 2 and not _quotes_line(' '.join(singer_clauses), [{'text': wanted['words']}]):
            problems.append(f'Shot {shot.n} must quote the words sung in it ({wanted["words"]!r}) in the sentence about {label}.')
    return list(dict.fromkeys(problems))
