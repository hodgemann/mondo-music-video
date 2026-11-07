# Working together on Mondo Music Video

## First turn in a fresh terminal

1. Read AGENTS.md, this document, and TEAM_STATUS.md (create it from the template
   below if it does not exist); inspect `git status --short`
   and the current branch. Preserve any uncommitted work you did not make.
2. Read README.md and the relevant source and tests. Release and scope rules are
   in AGENTS.md, docs/SCOPE.md and docs/SOURCE_EXTRACTION.json.
3. Before working, tell the user which model and reasoning effort you are running
   as, which task is assigned, and which role you are taking, so the user can
   change the model first. A coordinator should be a medium-tier or better model;
   say so if you are a low-tier one. If no
   product task is assigned, report readiness and wait for the task.
4. Identify the coordinator and record your assigned writer/reviewer role in
   TEAM_STATUS.md before edits. Claim coordinator or main-checkout writer only
   when assigned that role. If a role is claimed by another session, coordinate
   with the user or use an explicitly assigned separate worktree; never overwrite
   the claim. Read-only helpers can return handoffs for the coordinator to record.

## Project guardrails (apply to every agent and helper)

AGENTS.md is authoritative; its release rules bind helpers too. In particular:

- HIGH PRIORITY: the goal is a program that works. Do not craft a refusal machine.
  When something cannot happen right now, make it happen: wait for the resource,
  queue the work, fall back to a sensible default, or carry on and finish. Do not
  add refusals, error messages or warnings as the easy answer, and do not bother the
  user with them. Keep a stop only where the owner has asked for one, such as paid
  consent, and raise any other proposed stop with the owner before building it.
- Only the four authorized starter actors and six style presets may be published;
  never stage, package or copy other local actors, styles, `data/` or
  `api-profiles.json`.
- No paid, GPU or Topaz work, publishing or pushing without explicit user
  authorization. Automated tests use temporary data and mock services.
- Do not retry paid submissions automatically.
- Do not import from a sibling studio checkout or share its Git object store.
- `docs/TEAM_STATUS.md` and `.collaboration/` are per-session state, ignored by
  git and excluded from packages; never commit them. Keep helper tasks to files
  inside this repository.

## Versioning

AGENTS.md governs version bumps. A delivered batch of program changes bumps
`MGL_APP_VERSION` in `webapp/mondo_web.py` once, with pyproject.toml, README and
version assertions together. Documentation-only work, including collaboration
and handoff files, never bumps. Only the coordinator bumps; helpers never edit
the version.

## Roles and model selection

Keep one coordinator responsible for the plan, integration, and final validation.
Use a smaller helper for narrow searches, explanations, and focused reviews.
The coordinator reviews helper output against source and tests. A second agent
is useful when its independent work saves more time than the handoff takes.

The coordinator is whatever model the user opened the terminal with. The helper
is meant to be a lower tier, so the pair is normally a medium coordinator and a
low helper. The launcher names tiers, not models: `--tier low` (default) or
`--tier medium` reads `MMV_PEER_<PROVIDER>_MODEL_<TIER>` (for example
`MMV_PEER_CLAUDE_MODEL_LOW=haiku`, `MMV_PEER_CODEX_MODEL_LOW=<a small model>`).
`--model` sets an exact model for one run and wins. `codex debug models` lists
the Codex models your account offers. If the variable is unset the
CLI's own default is used and the launcher says so, since that may not be a lower
tier than the coordinator. Helpers are asked to state their model, but that is
their own claim; the Claude receipt reports the model used, the Codex one does
not. None of this changes either open terminal. "Medium reasoning effort" and
"medium model" are separate settings; a reasoning slider does not select a
cheaper model.

Codex or Claude Code may coordinate. Do not recursively delegate from a helper or
run unbounded review/retry loops. Escalate to the coordinator after one failed
attempt. Record actual model, result, and limitations in the task handoff.

## Four concurrent interactive agents

The user can run Codex, Claude Code, Antigravity and Hermes at the same time.
Keep one named coordinator across the project. A typical assignment is:

| Agent | Default role | Scope |
| --- | --- | --- |
| Codex | Coordinator or implementation worker | Plan, integrate and validate when coordinating; otherwise assigned files/worktree |
| Claude Code | Implementation worker or coordinator | Independent assigned worktree, or main-checkout writer when assigned |
| Antigravity | Junior reviewer or worker | Read-only onboarding, then a bounded review or isolated assigned task |
| Hermes | Junior light worker | Read-only onboarding, then searches, documentation audits, focused reviews or small isolated fixes |

Roles are assignments, not automatic privileges of a model or provider. Four
concurrent sessions do not mean four writers in the same checkout, four production
operations, or permission to launch additional agents. Keep the app's single
active operation and all paid/GPU consent rules. Start with separate read-only
reviews if suitable worktree tasks are not available.

### Starting Hermes

From a new terminal, enter the project and start the installed CLI:

```bash
cd /path/to/mondo-music-video
hermes
```

Hermes 0.22.2 supports root `HERMES.md`; when present it takes precedence over
the AGENTS.md context. Our [HERMES.md](../HERMES.md) therefore explicitly requires
Hermes to read [AGENTS.md](../AGENTS.md) and this protocol. Do not assume Claude's
`@AGENTS.md` import syntax works in Hermes. Do not use `--ignore-rules` or
`--safe-mode` for project work: those modes skip project instructions. Normal
approval prompts must remain enabled; do not use `--yolo`.

For the first session, give Hermes this onboarding task:

```text
Read HERMES.md, AGENTS.md, docs/COLLABORATION.md, README.md and the local
docs/TEAM_STATUS.md. You are the light worker; this first session is read-only.
Report your configured model/provider, the current coordinator and writer,
and any missing context. Wait for one named task. Do not edit tracked files,
launch other agents, run renders or access credentials/private assets.
```

Choose the provider/model in the user's Hermes setup, not in tracked project
files. A free model name is not proof that every auxiliary model or hosted tool
is free. Check the account tier, helper/tool settings and fallback routes before
using them; stop on billing/quota failures instead of changing providers or
retrying automatically. Keep account tokens, local memory and user configuration
out of the repository. No live Hermes inference is needed to edit these docs.

### Assignments and handoffs

The coordinator records one task per worker in the main checkout's ignored
`docs/TEAM_STATUS.md`, with a unique task ID, owner/session, exact worktree and
base commit, allowed files, acceptance checks, status, report path and next owner.
Name the canonical main-checkout status path in each worktree handoff: a worktree
does not inherit this ignored file, and its own copy must not become a conflicting
assignment board. The coordinator maintains that board; workers return reports
rather than concurrently rewriting it. Do not copy its private history into
tracked files or remote chats; supply only the minimum task context needed.

Use a distinct report such as `.collaboration/reports/hermes-<task-id>.md` in the
assigned checkout, or return the report in the agent's reply. Include file/line
evidence, changes, checks actually run, blockers and next owner. These reports
are ignored and must never be staged. No agent polls or invokes the others merely
because a report exists; the user or coordinator delivers each explicit handoff.
Only assign independent edits concurrently; dependent work waits for the relevant
reviewed result. The coordinator integrates and validates results sequentially.

`tools/ask_peer.py` still supports only Codex and Claude and intentionally permits
one launched helper at a time. Its lock and billing guards are unchanged. Hermes
and Antigravity use interactive sessions under this protocol; they are not added
to that launcher, and its isolation guarantees do not apply to them. Instruction
files provide coordination, not technical read-only enforcement or automatic
messaging. Four-agent simultaneous operation has not been exercised by this
documentation change.

## Asking the other provider

### Claude Code asking Codex: the official plugin (recommended)

OpenAI's Codex plugin for Claude Code (`openai/codex-plugin-cc`) is the
maintained way for Claude to consult Codex. Install it at user scope:

```text
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

- `/codex:review` and `/codex:adversarial-review` are read-only reviews of the
  working tree or a branch (`--base main`). Prefer them for peer review.
  Untracked files over 24 KB are left out of the review context.
- `/codex:rescue` delegates work and is write-capable by default. Treat it as
  handing the main-checkout writer role to Codex: claim it in TEAM_STATUS.md
  first, or ask for read-only investigation explicitly.
- Keep the optional review gate (`/codex:setup --enable-review-gate`) off. It
  runs Codex on every Claude stop and can drain usage limits in a loop.
- The plugin uses your normal Codex login and `config.toml`, including model
  defaults and any API key. None of the launcher guards below apply to it. On a
  ChatGPT login it uses your Codex usage limits; with an API key it bills.
- Reviewed for this project: plugin 1.0.6, commit `db52e28`.

### Codex asking Claude, or a guarded read-only helper: the launcher

`tools/ask_peer.py` launches a bounded, read-only helper in either direction
with the cost guards described under "Costs and safety". From the repository
root:

```bash
python3 tools/ask_peer.py claude 'Review the update-check logic in webapp/ for one concrete correctness issue; cite file and line.'
python3 tools/ask_peer.py codex 'Review the update-check logic in webapp/ for one concrete correctness issue; cite file and line.'
```

Codex normally asks Claude through it; Claude may use it instead of the plugin
when the stricter guards matter. This launches a separate
bounded helper, not the already-open terminal. Claude receives only file-reading tools; Codex uses its read-only sandbox.
Both are instructed to avoid edits and tests. The Codex sandbox may allow
non-mutating shell commands; this is not a separate OS security boundary. Reports
are saved under ignored `.collaboration/runs/`, with nonzero exit status on
provider failure. Review the report before using it. Each report has a receipt: the model requested, the model
the CLI says answered, tokens, and (Claude) cost. Claude reports the model used.
The Codex CLI does not, so its receipt says "requested model only"; do not treat
that as confirmation. Use `--dry-run` to inspect
the command without calling a provider. The launcher uses normal CLI login,
permissions, and account usage; it does not configure API keys or bypass approvals.

For an already-open agent, the user must ask it to read TEAM_STATUS.md and its
assigned task. There is no automatic messaging or shared conversation history.
Shared files are project context, not automatic conversion of private memories
or provider-specific skills.

## Costs and safety

Helpers run on your own CLI login and are optional; the project works without
them. Nothing here runs automatically. On a subscription login a helper uses
your plan's usage allowance (for example a Codex 5-hour window) rather than
extra money; with an API key it bills per token. The launcher fails closed:

- It refuses to run unless a model is configured (`--model` or the tier
  variable); `--allow-default-model` accepts the CLI's own default knowingly.
- It refuses if a per-token credential or provider is in the environment
  (Claude: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`,
  `CLAUDE_CODE_USE_VERTEX`; Codex: `OPENAI_API_KEY`, `CODEX_API_KEY`), unless you
  pass `--accept-api-billing`. A CLI
  logged in with a key it stored itself cannot be detected; check how your login
  is billed.
- Claude runs get a spending cap (`--max-budget-usd`, else
  `MMV_PEER_MAX_BUDGET_USD`, else 0.50). The cap stops further work once
  reached; one model turn can overshoot it. The Codex CLI has no equivalent cap, so
  Codex runs are bounded by the timeout and low reasoning effort.
- Only one helper runs at a time (an OS lock on `.collaboration/peer.lock`).
- Each run times out after 300 seconds and is never retried automatically. On
  timeout, Ctrl-C or termination the launcher kills the helper's whole process
  group, and it does so after a normal finish too. On Windows it uses
  `taskkill /T`, which cannot reach processes that detached from the tree.
- Claude helpers have only file-reading tools and load no user, project or MCP
  settings. Codex helpers ignore the user's `config.toml`, run with
  `multi_agent` disabled in a read-only sandbox, and their shell commands see an
  empty home directory (no CLI logins), no `*API_KEY*`/`*TOKEN*` variables, and
  the marker that makes the launcher refuse to start a nested helper.

Verified on Linux (Codex 0.163, Claude Code 2.1.302): the Codex sandbox blocked
writes and network access, so nested `claude`/`codex` calls failed even with the
real home directory restored. macOS and Windows sandboxes have not been tested;
the environment measures are defense in depth, not a security boundary.

Paid generation inside the application has its own consent rules in AGENTS.md.

## Status file

`docs/TEAM_STATUS.md` is local and ignored by git. Create it when starting and
keep it current. Suggested sections: Current objective; Ownership (coordinator,
main-checkout writer); Last handoff; and per task: owner, objective, allowed
files, acceptance checks, base commit/worktree, status, changed files/commits,
validation, blockers, version bump (yes/no, which), and next owner. Never record
secrets in it.

## Implementing changes

Only one agent edits the main checkout at a time. The others can perform a
read-only review. For genuinely independent implementation tasks, create a
named branch/worktree with `git worktree add -b <branch> <path> HEAD` and launch
an interactive agent there with the intended model. Record the owner, base
commit, allowed files, and acceptance checks before it starts.

Worktrees contain committed files only. Ensure collaboration instructions and
needed context are present in the new worktree; copy only explicitly required
uncommitted files, never secrets or API keys. Do not commit another session's work merely
to make it visible. The coordinator reviews diffs and integrates agreed commits
sequentially; no automatic merges or pushes. Git worktrees separate edits but
are not security boundaries. Do not modify another worker's worktree.

### Committing and pushing when other sessions may be active

More than one terminal or agent can work in the same checkout, and one commit can sweep up another session's unfinished work.
Before any commit or push:

1. Run `git status` and `git log -5`, and check `docs/TEAM_STATUS.md` for an active claim. If there are changes you did not make, new
   commits you did not make, or the user mentions another terminal, **stop and ask the user** before committing.
2. Stage **only the files you changed, by name**. Do not use `git add -A`, `git add .`, `git commit -a` or `git stash` in a shared
   checkout, except when you have just confirmed the tree holds only your own work.
3. Fetch before you push, never force-push, and never rewrite or amend a commit another session made.
4. Commit and push only when the user has said to. A request to "commit everything" still means confirming what that includes when work
   from another session is present.

Publication authorization persists for its stated scope. When the owner asks to publish a completed release, carry it through
commit, push, tag and GitHub Release without asking again at each step. A confirmed file scope also satisfies the shared-checkout
check above; do not repeat that question. Leave unrelated pre-existing untracked files unstaged and untouched. Ask again only if
the scope has genuinely changed or a new decision is required.

## Handoffs and verification

Before handing off, update TEAM_STATUS.md with changed files, validation actually
run, unresolved concerns, and next owner. Release the main-checkout writer claim.
Do not claim tests passed or collaboration is connected without evidence.

Use the project's `.venv` and the dependencies in pyproject.toml. For
implementation changes run the relevant tests, normally `.venv/bin/python -m
pytest`, and the whole suite before a program-change delivery. Do not install
dependencies or run the suite merely for a documentation handoff. For a delivered
program change, verify the version through a fresh import of the `/api/version`
handler (and the live endpoint if claiming a running process), as AGENTS.md
requires. Preserve consent, one-active-operation and OAP verification guarantees.

For a local user-facing app change, finish the handoff with the updated app
running so the user can review it in their browser. Check whether the existing
app has an active operation before a restart; leave it alone while busy. Reuse
its data directory, port and settings, keep automatic updates off unless already
enabled, and confirm the live version and page after startup. Include the URL
and refresh instruction in the handoff. Document any blocker instead of calling
the app ready on the strength of a fresh handler import alone. This live-review
step does not start a production or a paid/GPU operation.

## References

- Codex plugin for Claude Code: https://github.com/openai/codex-plugin-cc
- Codex scripted execution: https://learn.chatgpt.com/docs/non-interactive-mode
- Claude scripted execution: https://code.claude.com/docs/en/headless
- Claude model configuration: https://code.claude.com/docs/en/model-config
