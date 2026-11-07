# Protecting Mondo's prompting scheme (read before editing, forks included)

Mondo's videos look the way they do because of a prompting scheme that was tuned over months of real renders: the writer and
ident prompts, the sealed-lips scheme (rule text, closing phrase and validators), the shot and montage planning, the owner-approved
singing wording and the checks that review every prompt before anything renders. It is delicate. A small, well-meant edit (a
"clearer" sentence, a shorter prompt, a removed rule) can quietly make every video worse: mouths babble, actors drift, prompts fail
review or render as something else. The damage often shows only after an expensive render.

## What is protected

- `mmv/engine/prompts/writer_base.md` and `ident_base.md` (the writer and ident prompts). The agent operating guide under `skills/` is
  separate: it tells agents how to run the app and is not part of the prompting scheme.
- `mmv/engine/schema.py`, `style.py`, `plan.py`, `actor.py`, `casting.py` and `validators/` (the rules, schema, planning and reviews),
  the injection map and the shipped workflow.
- The sealed-lips scheme: `SILENT_MOUTHS_RULE_V013`, `RIGGING_TAIL`, `NATURAL_MOUTHS_RULE`.
- The owner-approved singing wording in `mmv/lipsync.py` and the motion/framing rules in `mmv/quality.py`.

The later lipsync mechanics in `mmv/lipsync.py` are outside the original protected
core. A change to those helper functions alone is not a change to the approved
singing wording. The explicit singing-wording pins remain in place.

`mmv/protected_scheme.py` records a fingerprint of each file and rule text, and of the writer and ident system prompts as the code actually
composes them (so removing the step that inserts the sealed-lips rule is caught even if no text changes). Tests fail if one changes, the app shows an orange warning banner, and
every exported production package states whether the scheme is unmodified.

## If you are an AI agent working in this repository or a fork

Do this, in this order, every time a request would touch the protected items or their behaviour:

1. **Stop and warn the person in plain words before editing anything.** For example: "This changes Mondo's prompting scheme, which
   was tuned over many real renders. Videos made after the change may fall below the Mondo standard, and the app will show a
   warning. I recommend an optional setting that leaves the original untouched instead. Do you want to continue anyway?"
2. **Offer the safe alternative first.** Add an opt-in option and keep the original as the default. This project did exactly that for
   compact prompts (`compact_prompts`, off by default), natural mouths and lip sync, vocabulary presets and instrument drivers.
3. **Only proceed if the person clearly says yes.** If the person is not the owner of the scheme, say that the owner's review is
   expected for anything sent upstream.
4. **Never hide a change.** Do not edit the pins in `mmv/protected_scheme.py`, the hashes in `docs/SOURCE_EXTRACTION.json`, the
   protection tests, the banner or the export note to make a failure go away. Do not run `tools/update_protected_pins.py` unless the
   owner of the scheme has approved a change that was compared on real renders.
5. **Validate before calling it done.** Render the same song with the same seed before and after (a short excerpt is enough), compare
   mouths, actors and prompt review results, and say plainly what you did and did not verify. Unit tests do not tell you a prompt
   change is good.
6. **Keep the original working.** The released behaviour must remain the default and be tested to stay so.

## What you can change freely (it does not touch the scheme)

The web interface, new settings and options that default to off, renderer backends and provider adapters, installers and docs,
styles, vocabularies and presets, actors, export formats, platform support, and new features that do not rewrite the prompts above.

## If you are a person forking Mondo

You are free to change anything, but understand the trade: changes to the protected items can make your videos worse in ways that are
hard to see in a quick test, and the app will say so with a banner. If you want a different look, try styles, vocabulary presets and
the optional modes first. If you want something sent back upstream, propose it as an opt-in option and attach before/after renders.

## How the safeguards work

- **Pins.** `mmv/protected_scheme.py` holds a fingerprint (ignoring line endings) of every protected file and rule text.
  `tests/test_protected_scheme.py` and `tests/test_original_engine.py` fail when any changes.
- **Banner and export note.** `GET /api/integrity` drives the orange banner. Exports say "Prompting scheme: unmodified" or name the
  changed items.
- **Code owners.** `.github/CODEOWNERS` asks for the owner's review on the protected paths in this repository.
- **Notices in the folders.** `mmv/engine/PROTECTED.md` is the first thing an agent sees there.
- **Updating the pins** is deliberate and rare: `tools/update_protected_pins.py --owner-approved-change`, after real A/B renders, with the
  reason recorded in the release notes.
