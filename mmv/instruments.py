"""Opt-in instrument performance. Original engine prompts and actor casting stay intact."""
from __future__ import annotations

import re
from dataclasses import asdict, replace

from . import dance, instrument_assets
from .lipsync import casting_for, PRONOUN_START

VERSION = 1
PARTS = {'drums': 'drums', 'bass': 'bass', 'guitar': 'guitar', 'keyboards': 'piano'}
RULES = (
    'This passage has an instrument_performance job. Its performers bind an actor subject to one instrument. '
    'A player need not play in every shot; they may also stand, pose, move or react. Whenever a player is shown playing, explicitly name that subject and describe their own instrument action in a separate sentence: '
    'drums use sticks striking heads or cymbals with feet on pedals; bass plucks strings with one hand while the other frets; '
    'guitar picks or strums strings with one hand while the other frets; keyboards press keys with fingers of both hands. '
    'Follow each performer\'s shot cues for energy and pauses. In a paused shot explicitly describe that subject resting their hands '
    'or holding still without playing. Never invent a measured stem when source is mix; these cues do not specify notes. '
    'When an instrument_picture_tag is supplied, cite it with that performer and match its single design, finish and hardware. '
    'An instrument picture is a prop reference, never a new cast member or an additional numbered Subject. '
    'The sheet depicts several views of ONE instrument or drum kit: render one real instrument, never the sheet, labels or panel grid. '
    'Keep each instrument with its assigned player, with plausible contact, grip, strap or stand. Never swap instruments or make '
    'instrument players copy dance choreography. Instrument assignments cannot change casting, lyrics, singing or any mouth rule. '
    'An assigned singer may sing while playing only as the singing rules allow; every other mouth follows the existing mouth rules. '
    'Do not introduce players or instrument references absent from this passage job.')


def clean(request):
    if request.get('instrument_mode', 'off') == 'off':
        return None
    if request.get('instrument_mode') != 'perform' or request.get('kind', 'video') != 'video':
        raise ValueError('Instrument performance is available for music videos only')
    assignments = request.get('instrument_assignments') or {}
    if not isinstance(assignments, dict) or not assignments:
        raise ValueError('Assign at least one cast actor an instrument')
    for actor, kind in assignments.items():
        if not isinstance(actor, str) or not actor:
            raise ValueError('Instrument assignments map actor IDs to instruments')
        instrument_assets.valid_kind(kind)
    return assignments


def prop_options(request, assignments):
    """Keep OPP identities independent of the four current musical roles."""
    from .props import prop_identifier
    selected = set(assignments.values())
    ids, uses = request.get('instrument_props') or {}, request.get('instrument_prop_uses') or {}
    if not isinstance(ids, dict) or not isinstance(uses, dict) or any(k not in selected for k in (*ids, *uses)):
        raise ValueError('OPP instrument selections must match assigned instrument roles')
    if ids and not request.get('instrument_references', True):
        raise ValueError('Enable instrument references to use selected OPP props')
    for kind, prop_id in ids.items():
        instrument_assets.valid_kind(kind)
        prop_identifier(prop_id)
    for kind, use in uses.items():
        if kind not in ids or not isinstance(use, str) or len(use) > 200:
            raise ValueError('OPP instrument use must be short text for a selected prop')
    return ids, uses


def cached_scores(store, digest, score_path, assignments, quality, edits):
    """Only existing stems/analyses; guitar and piano use the six-stem cache, never guessed from other."""
    from .stems import cached_dance_part, model_for
    from .score_edit import apply_score_edits
    import subprocess
    result = {}
    for part in dict.fromkeys(PARTS[kind] for kind in assignments.values()):
        try:
            score = cached_dance_part(store, digest, score_path, model_for(part, quality), part)
            if score is not None:
                result[part] = asdict(apply_score_edits(score, edits))
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            pass
    return result


def plan_passages(segments, casting, score, request, assets=None, part_scores=None):
    assignments = clean(request)
    if assignments is None:
        return None
    prop_ids, prop_uses = prop_options(request, assignments)
    roster = {m['actor_id']: m for m in (casting or {}).get('roster', [])}
    if any(actor not in request.get('actors', []) or actor not in roster for actor in assignments):
        raise ValueError('Instrument players must be selected cast actors')
    passages = {}
    for segment in segments:
        cast = casting_for(casting, segment.segment_id)
        performers, references = [], []
        for index, member in enumerate(cast):
            actor = member['actor_id']
            if actor not in assignments:
                continue
            kind = assignments[actor]
            cue = dance.part_cues(segment, PARTS[kind], score, part_scores or {})
            measured = (part_scores or {}).get(PARTS[kind], {})
            for shot, info in zip(segment.shots, cue['shots']):
                low = segment.song_start_frame + shot.start_frame
                high = low + shot.frames
                known = cue['source'] == 'stem' and any(low <= frame < high for frame in measured.get('beat_frames', []))
                info['activity'] = ('paused' if info['paused'] else 'playing') if known else 'unknown'
                if not known:
                    info['paused'] = False  # A quiet mix or a gap between beats does not establish an instrument pause.
            # No measured samples in a shot means unknown activity, not silence.
            active = any(not shot['paused'] for shot in cue['shots'])
            if active and request.get('instrument_references', True) and kind not in references:
                references.append(kind)
            performers.append({'actor_id': actor, 'display_name': roster[actor]['display_name'],
                               'subject': index + 1, 'picture_tag': member.get('picture_tag'),
                               'instrument': kind, 'description': instrument_assets.DESIGNS[kind][1],
                               'active': active, **cue})
        passages[segment.segment_id] = {'performers': performers, 'references': references, 'actor_slots': len(cast)}
    result = {'version': VERSION, 'assignments': dict(assignments), 'references_enabled': request.get('instrument_references', True),
            'assets': assets or {},
            'passages': passages}
    if prop_ids:
        result['prop_ids'] = dict(prop_ids)
        result['prop_uses'] = dict(prop_uses)
    return result


def check_replay(request, performance):
    if (clean(request) != performance['assignments'] or
            request.get('instrument_references', True) != performance['references_enabled']):
        raise ValueError('Instrument settings differ from the saved plan; start a new production preview')
    ids, uses = prop_options(request, performance['assignments'])
    if ids != performance.get('prop_ids', {}) or uses != performance.get('prop_uses', {}):
        raise ValueError('OPP prop selection differs from the saved plan; start a new production preview')


def apply_slots(plan, performance, maximum):
    if not performance:
        return plan
    segments = []
    for segment in plan.segments:
        passage = performance['passages'][segment.segment_id]
        if segment.ref_image_slots != passage['actor_slots']:
            raise ValueError('Original actor/reference-slot contract disagrees; start a fresh preview')
        count = passage['actor_slots'] + len(passage['references'])
        if count > maximum:
            raise ValueError(f'{segment.segment_id}: {passage["actor_slots"]} actor references + '
                             f'{len(passage["references"])} instrument references exceed the renderer limit of {maximum}; '
                             'reduce actors on screen or turn consistent instrument references off')
        segments.append(replace(segment, ref_image_slots=count))
    return replace(plan, segments=segments)


def job(passage, performance, tags):
    pictures = {kind: tags.images[passage['actor_slots'] + index] for index, kind in enumerate(passage['references'])} if tags.images else {}
    return {'performers': [{**item, 'subject': f'<Subject {item["subject"]}>',
                             'instrument_picture_tag': pictures.get(item['instrument'])} for item in passage['performers']],
            'reference_identity': {kind: {'sha256': asset['sha256']}
                                   for kind, asset in performance['assets'].items() if kind in passage['references']}}


def images(passage, performance):
    return [('__instrument_' + kind, performance['assets'][kind]['path']) for kind in passage['references']]


def verify_assets(performance):
    """At replay/render boundaries reject changed files even if metadata was left alone."""
    from pathlib import Path
    for kind, asset in performance.get('assets', {}).items():
        path = Path(asset['path'])
        if not path.is_file() or instrument_assets.sha256(path) != asset['sha256']:
            raise ValueError(f'{kind} instrument reference changed; restore the original sheet and preview again')
        if asset.get('bundle_path'):
            bundle = Path(asset['bundle_path'])
            if not bundle.is_file() or instrument_assets.sha256(bundle) != asset['bundle_sha256']:
                raise ValueError(f'{kind} OPP package changed; restore it and preview again')


ACTION = {
    'drums': re.compile(r'\b(strik(?:e|es|ing)|struck|hit(?:s|ting)?|tap(?:s|ped|ping)?|drumming)\b', re.I),
    'bass': re.compile(r'\b(pluck(?:s|ed|ing)?|pick(?:s|ed|ing)?|slap(?:s|ped|ping)?|play(?:s|ed|ing)?|'
                       r'strik(?:e|es|ing)|struck|hit(?:s|ting)?|thump(?:s|ed|ing)?|fingerpick\w*)\b', re.I),
    'guitar': re.compile(r'\b(strum(?:s|med|ming)?|pick(?:s|ed|ing)?|pluck(?:s|ed|ing)?|play(?:s|ed|ing)?|'
                         r'strik(?:e|es|ing)|struck|hit(?:s|ting)?|rak(?:e|es|ing)|thrum(?:s|med|ming)?|fingerpick\w*)\b', re.I),
    'keyboards': re.compile(r'\b(press(?:es|ed|ing)?|play(?:s|ed|ing)?|tap(?:s|ped|ping)?|'
                            r'strik(?:e|es|ing)|struck|hit(?:s|ting)?|pound(?:s|ed|ing)?|depress\w*)\b', re.I),
}
# The assigned instrument in words: one explicit picture tag binds it, later shots may say "the guitar".
NAMED = {
    'drums': re.compile(r'\b(drum\w*|kit|snare|cymbal\w*)\b', re.I),
    'bass': re.compile(r'\bbass\b', re.I),
    'guitar': re.compile(r'\bguitar\w*\b', re.I),
    'keyboards': re.compile(r'\b(keyboard\w*|piano|synth\w*|keys)\b', re.I),
}
CONTACT = {
    'drums': re.compile(r'\b(stick\w*|cymbal\w*|snare|pedal\w*|drumhead\w*)\b', re.I),
    'bass': re.compile(r'\b(string\w*|fret\w*)\b', re.I),
    'guitar': re.compile(r'\b(string\w*|fret\w*)\b', re.I),
    'keyboards': re.compile(r'\b(key\w*|finger\w*)\b', re.I),
}
# One physically plausible sentence per instrument, shown to the writer when a shot lacks contact.
EXAMPLE = {
    'drums': 'right stick strikes the snare while the left stick hits the hi-hat and the right foot works the bass pedal',
    'bass': 'right-hand fingers pluck the bass strings while the left hand frets notes along the neck',
    'guitar': 'right hand strums the guitar strings while the left hand frets chords on the neck',
    'keyboards': 'fingers of both hands press the keys',
}
# Gestures that belong to a different instrument, quoted back to the writer so it removes them.
WRONG = {
    'drums': re.compile(r'\b(strings?|frets?\w*|strum\w*|keys?|keyboard\w*|piano)\b', re.I),
    'bass': re.compile(r'\b(keys?|keyboard\w*|piano|drumsticks?|sticks?|snare|cymbal\w*|strum\w*)\b', re.I),
    'guitar': re.compile(r'\b(keys?|keyboard\w*|piano|drumsticks?|sticks?|snare|cymbal\w*)\b', re.I),
    'keyboards': re.compile(r'\b(strings?|frets?\w*|strum\w*|drumsticks?|sticks?|snare|cymbal\w*)\b', re.I),
}
IDLE = re.compile(r'\b(rest\w*|idle\w*|hold\w*|still|paus\w*)\b', re.I)
NEGATED = re.compile(r"\b(?:no|not|never|without|doesn't|don't|isn't|cannot|can't)\b[^,.;]*", re.I)
CONTINUING = re.compile(r"\b(?:(?:does|do) not|doesn't|don't|never) stop(?:s)?\b|\bwithout (?:stopping|pausing)\b", re.I)
ABSENT = re.compile(r'\b(off[ -]?screen|absent|out of (?:the )?frame)\b', re.I)
_QUOTED_INLINE = re.compile(r'"[^"\n]*"|“[^”]*”')
_SHOT_GUITAR_ISSUE = re.compile(r'Shot (\d+): (<Subject \d+>) must visibly play the guitar:')
_SHOT_CONNECT = re.compile(r'Shot \d+: connect ')


def player_clauses(body, performers):
    """Attribute independent clauses to their named actor; lyrics and other players cannot supply an action."""
    body = _QUOTED_INLINE.sub(' ', body)
    targets = [[p['subject'], p.get('picture_tag'), p['display_name']] for p in performers]
    pattern = '|'.join(re.escape(ref) if ref.startswith('<') else r'(?<!\w)' + re.escape(ref) + r'(?!\w)'
                       for refs in targets for ref in refs if ref)
    body = re.sub(r'(?:[,;]\s*|\b(?:and|while|whereas)\s+)(?=(?:' + pattern + '))', '\n', body, flags=re.I)
    clauses = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n', body) if s.strip()]
    target_matchers = [
        [
            (ref, None) if ref.startswith('<') else (ref, re.compile(r'(?<!\w)' + re.escape(ref) + r'(?!\w)', re.I))
            for ref in refs if ref
        ]
        for refs in targets
    ]
    out, previous = [[] for _ in targets], []
    for clause in clauses:
        named = [
            index for index, matchers in enumerate(target_matchers)
            if any(ref in clause if pat is None else bool(pat.search(clause)) for ref, pat in matchers)
        ]
        if not named and PRONOUN_START.match(clause) and len(previous) == 1:
            named = previous
        for index in named:
            out[index].append(clause)
        previous = named
    return out


def wrong_note(kind, clauses):
    """Quote the first clause using another instrument's gesture so the writer deletes it."""
    for clause in clauses:
        if WRONG[kind].search(clause):
            return f'delete the non-{kind} gesture in "{clause.strip()[:110]}" and '
    return ''


def retry_feedback(problems):
    """Short instrument-only correction for a full-response retry: failing shots first, nothing else changes."""
    unique = list(dict.fromkeys(problems))[:8]
    return ('\n\nInstrument fixes only. Rewrite just the named shots; keep every other shot, its length, lyrics, '
            'actors and wording as they are. Each player holds only their assigned instrument; remove any gesture '
            'of another instrument. Striking or hitting the instrument body is not playing: show hands on strings, '
            'keys, heads or pedals as the instrument requires.\n' + '\n'.join('- ' + x for x in unique))


GUITAR_VAGUE = re.compile(r'\b(?:strikes?|hits?|plays?|holds?)\s+(?:the\s+)?guitar\b', re.I)
GUITAR_CONTACT = 'strums the guitar strings while fretting the neck'
SUBJECT_TAG = re.compile(r'<Subject \d+>')


def repair_shot_bodies(shot_bodies, segment, passage, performance, tags):
    """Make a narrow, auditable guitar-contact edit when one player's intent is unambiguous.

    Wrong-instrument gestures, lyrics, pauses and ambiguous actor attribution stay
    untouched for the writer to correct. Every edited response still faces the
    regular schema, instrument and Laya validation in the worker.
    """
    performers = job(passage, performance, tags)['performers']
    before = problems('', shot_bodies, segment, passage, performance, tags)
    candidates = {int(match.group(1)): match.group(2) for issue in before
                  if (match := _SHOT_GUITAR_ISSUE.match(issue))}
    if not candidates:
        return list(shot_bodies), []
    repaired, edits = list(shot_bodies), []
    for index, (shot, body) in enumerate(zip(segment.shots, shot_bodies)):
        subject = candidates.get(shot.n)
        if not subject:
            continue
        performer = next((item for item in performers if item['subject'] == subject and item['instrument'] == 'guitar'), None)
        if performer is None or next(c for c in performer['shots'] if c['n'] == shot.n)['paused']:
            continue
        matches = []
        for sentence in re.finditer(r'[^.!?\n]+(?:[.!?]|$)', body):
            text = sentence.group()
            if '"' in text or '“' in text or WRONG['guitar'].search(text) or NEGATED.search(text):
                continue
            for action in GUITAR_VAGUE.finditer(text):
                preceding = list(SUBJECT_TAG.finditer(text, 0, action.start()))
                if preceding and preceding[-1].group() == subject:
                    matches.append((sentence.start() + action.start(), sentence.start() + action.end()))
        if len(matches) != 1:
            continue
        start, end = matches[0]
        changed = body[:start] + GUITAR_CONTACT + body[end:]
        trial = repaired.copy()
        trial[index] = changed
        after = problems('', trial, segment, passage, performance, tags)
        if len(after) < len(problems('', repaired, segment, passage, performance, tags)):
            repaired[index] = changed
            edits.append(shot.n)
    return repaired, edits


def is_blocking(problem):
    """Prompt integrity stops a prompt: every shot described, the player present, and the instrument reference cited so the renderer
    uses it. Whether the playing is convincingly worded is advice for Laya's review, never a rewrite."""
    return (problem.startswith(('Instrument performance requires', 'Instrument player '))
            or bool(_SHOT_CONNECT.match(problem)))


def problems(prompt, shot_bodies, segment, passage, performance, tags):
    """Shot-level lexical guard, not proof of rendered contact or synchronization."""
    if len(shot_bodies) != len(segment.shots):
        return ['Instrument performance requires every planned shot description']
    performers = job(passage, performance, tags)['performers']
    result = []
    appearances = player_clauses('\n'.join(shot_bodies), performers)
    for performer, clauses in zip(performers, appearances):
        if not any(not ABSENT.search(clause) for clause in clauses):
            result.append(f'Instrument player {performer["subject"]} must appear in at least one shot of this passage')
    bound = set()
    for shot, body in zip(segment.shots, shot_bodies):
        by_player = player_clauses(body, performers)
        unquoted = _QUOTED_INLINE.sub(' ', body)
        for clause in re.split(r'(?<=[.!?])\s+|\n', unquoted):
            if PRONOUN_START.match(clause.strip()) and not any(clause.strip() in own for own in by_player):
                if any(ACTION[p['instrument']].search(clause) and CONTACT[p['instrument']].search(clause) for p in performers):
                    result.append(f'Shot {shot.n}: name the actor performing this instrument action instead of an ambiguous pronoun')
        for performer, own in zip(performers, by_player):
            # Casting is per passage; a shot can frame another actor or an object.
            if not own or all(ABSENT.search(s) for s in own):
                continue
            cue = next(c for c in performer['shots'] if c['n'] == shot.n)
            kind = performer['instrument']
            affirmative = [NEGATED.sub('', CONTINUING.sub('', s)) for s in own if not ABSENT.search(s)]
            if cue['paused']:
                if not any(IDLE.search(s) for s in affirmative):
                    result.append(f'Shot {shot.n}: {performer["subject"]} must rest or hold during the {kind} pause')
                if any(ACTION[kind].search(s) and CONTACT[kind].search(s) for s in affirmative):
                    result.append(f'Shot {shot.n}: {performer["subject"]} must not play during the {kind} pause')
                continue
            playing = any(ACTION[kind].search(s) and CONTACT[kind].search(s) for s in affirmative)
            if not playing:
                # A player may be shown doing something else; a vague attempt to play or another instrument's gesture is wrong.
                attempting = any(ACTION[kind].search(s) for s in affirmative)
                if (note := wrong_note(kind, affirmative)) or attempting:
                    result.append(f'Shot {shot.n}: {performer["subject"]} must visibly play the {kind}: {note}'
                                  f'write one sentence like "{performer["subject"]} {EXAMPLE[kind]}"')
                continue
            picture = performer.get('instrument_picture_tag')
            if picture:
                if any(picture in s for s in affirmative):
                    bound.add(performer['subject'])
                elif performer['subject'] not in bound:
                    result.append(f'Shot {shot.n}: connect {performer["subject"]} to instrument reference {picture}')
                elif not any(NAMED[kind].search(s) for s in affirmative):
                    result.append(f'Shot {shot.n}: name the {kind} {performer["subject"]} plays or cite {picture}')
    return result
