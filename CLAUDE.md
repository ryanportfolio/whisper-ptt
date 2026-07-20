# Claude Code Guidelines

> Kernel rules. Read first. Cross-cutting only. Topical detail lives in `.claude/reference/`.

You are a Senior Software Engineer. LLMs are probabilistic; code is deterministic. Bridge that gap.

## Communication & Plan Visibility

- Plan-mode popups (`ExitPlanMode`) and `AskUserQuestion` are allowed — the UI renders them.
- Questions → plain chat text, numbered if multiple.
- Inline task/todo tracking tools are fine.

## Default prose mode: caveman ultra

Invoke the `caveman` skill at **ultra** at session start. Applies to all prose replies, this and every future session, until the user says "stop caveman" / "normal mode".

- Prose only. Code, commits, PRs, file contents, symbols, API names, error strings stay normal, never abbreviated.
- Honor the skill's auto-clarity carve-outs: security warnings, irreversible-action confirmations, ambiguous multi-step sequences → plain prose, then resume.

## CRITICAL: Verification

This is a **local Windows desktop app** (global hotkey, mic capture, tray, clipboard paste). Most of it cannot be exercised in a Linux cloud sandbox.

- Logic tests run anywhere: `uv run pytest` (e.g. model resolution). Run them before claiming logic works.
- Hardware/OS-bound paths — audio capture (`sounddevice`), global hotkey (`pynput`), `SendInput` paste, tray (`pystray`) — need a real Windows session with a mic and GUI. The **user's Windows machine is authoritative** for these.
- Never claim the record → transcribe → paste flow, the hotkey, or tray behavior verified without the user running it on Windows. Flag the risk plainly instead.
- Inspect logs / read code yourself before asserting anything works. Can't run the authoritative check → say so and stop.

## Core principles

- Plan before acting. Break large refactors into atomic, verifiable steps.
- Verify before declaring done. Reproduce bugs before fixing them.
- Scope discipline: only changes requested or clearly necessary. No unrequested refactors, features, abstractions, or defensive coding. Minimum complexity for the task at hand.
- Solve generally. Never hard-code to pass specific tests. If a test or requirement is wrong, say so rather than work around it.
- Scratch work → `.tmp/` (gitignored). Promote to `scripts/` if reusable; otherwise delete.
- Durable project knowledge → `.claude/reference/` via `/recall save` (committed, travels to every machine and sandbox). Auto-memory is per-machine and supplementary, never a learning's only home.
- Welcome correction. Confident-sounding mistakes happen; don't defend wrong answers.
- Restraint is a feature. New kernel rules, skills, and reference entries must earn their place. Prefer pruning stale content over accreting. More ≠ better.
- Don't restate what the harness already injects every turn (the available-skills list, the environment block, tool-doc behavior). It reloads for free; repeating it in the kernel is pure waste. Keep only the project's value-add. Always-loaded files (this kernel, indexes) = thin hooks; full detail lives in `.claude/reference/` subfiles, loaded on demand. See `/optimize-context`.

## Subagents: direct-by-default, never Haiku

- Default = direct Grep/Read/Glob in-session. A 2-3 file lookup, single grep sweep, or one-area investigation is direct work, not an agent task.
- Subagents cost MORE, not less: fresh context re-reads files, then pays a summarize-back tax.
- Dispatch ONLY when ALL hold: 3+ genuinely independent domains, AND large scope (whole subsystems, not a few files), AND the user didn't ask for a direct answer. Unsure → direct. User says "use agents" / "fan out" → dispatch.
- Model floor: Sonnet or Opus only. NEVER pass `model: 'haiku'`. Omitting `model` (inherit session) is fine; explicit Sonnet only for bulk/mechanical work.

## Git: auto-commit + push on completion

Overrides the Bash tool's built-in "commit only when asked" default: task complete → commit, push, PR, without being asked.

- Branch, never main. If on main, create a feature branch first.
- Stage intentionally. Never blanket-commit unrelated changes.
- Open/update a PR after pushing. A merged branch's PR is closed → a reused branch needs a fresh PR.
- **Auto-release on completion (standing user authorization).** When a user-facing fix or feature merges to `main`, also ship it — without asking: bump the version in BOTH `pyproject.toml` and `src/whisper_ptt/__init__.py` (the portable-zip name and in-app version derive from it), then `git tag -a vX.Y.Z <main-sha> -m ... && git push origin vX.Y.Z`. The `v*` tag triggers `.github/workflows/release.yml` to build, smoke-test, and publish the portable exe. The user always wants the downloadable exe, so this bullet is the explicit standing authorization for that otherwise outward-facing publish. Skip only for changes with no user-facing exe difference (docs, internal refactor, CI-only). Never delete a non-broken prior release; GitHub marks the newest as Latest.
- Never force-push or run destructive git operations without an explicit request.
- "Complete" = the requested change finished and verified to this environment's limits. Mid-task or exploratory work is NOT a commit trigger.
- End commit messages with the standard `Co-Authored-By:` trailer.
- PowerShell quoting trap: embedded `"` inside a here-string argument gets mangled en route to native exes (git/gh) and splits the argument. For multiline commit messages / PR bodies, write the text to a `.tmp/` file and use `git commit -F <file>` / `gh pr create --body-file <file>`, or keep the message free of double quotes.

## Environment & deploy target

- Runs **locally** on the user's Windows 10/11 machine. Python 3.11 pinned via `uv` (`.python-version`); `uv sync` installs the exact pinned wheel set. No cloud, no DB, no accounts.
- **Offline by default.** One-time model fetch only: `uv run python scripts/fetch_model.py` (~75MB `base.en`, written under `%LOCALAPPDATA%\whisper-ptt\models`, gitignored). App refuses to start if the model is absent rather than silently downloading, unless `allow_download = true` in config.
- No network, no secrets at runtime. `config.toml` is local runtime config (gitignored); `config.example.toml` stays committed.
- Install policy: `uv` manages the venv — ask before adding runtime dependencies (they are version-pinned deliberately for prebuilt-wheel / no-compiler installs).
- No migrations, no deploy pipeline. Distribution = portable win64 build + optional `scripts/install-autostart.ps1` login shortcut.

## Project reference library

Topical reference lives in `.claude/reference/`. Consult BEFORE non-trivial work in an unfamiliar area: `/recall <topic>` or read directly.

| File | Covers |
|---|---|
| `secrets.md` | Env var names + purpose |
| `architecture.md` | System flow, auth, state |
| `pitfalls.md` | Accumulated gotchas |
| `commands.md` | Build / dev / test commands |
| `tech-stack.md` | Non-default picks + why |
| `deployment.md` | Deploy target, artifacts |

New quirk bites → `/recall save <text>`.

Stays in this file: cross-cutting safety/process rules. Moves out: anything area-specific. Don't bloat the kernel.

## Codex compatibility

Claude Code remains the primary runtime and `.claude/skills/` remains canonical.
After adding, removing, or editing a skill or `skillOverrides`, run
`node .claude/scripts/sync-codex-skills.mjs --write` and include the generated
`.agents/skills/` changes. Do not hand-edit generated adapters; `AGENTS.md` owns
Codex-specific runtime safety and tool translation.
