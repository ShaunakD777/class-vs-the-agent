# Class vs. The Agent — build guide for Claude Code

This is a live quiz-show demo for a 2-hour "Agentic AI" guest lecture to 2nd-year
CSE students. About 50 students play on their phones against an AI game-show host.
Full spec: `spec.md` in this folder (PRD, TRD, app flow, UI/UX, schema, implementation
plan). Read it before writing any code, and re-check it whenever a decision is unclear.

## How to work with me

- **One phase at a time.** `spec.md` has 8 phases. Before starting a phase, write a
  short plan (files you'll touch, what "done" looks like) and wait for my go-ahead.
  Don't start the next phase until I've run and confirmed the current one.
- **Stop and ask before:** adding a new library or paid service, changing the schema
  in `spec.md`, or changing anything in the PRD's feature list.
- **No filler code.** If something in the spec is ambiguous, ask me rather than
  guessing and moving on.
- **Explain what you built in plain language** after each phase, not just a list of
  files changed. I'm not deeply technical yet — I'm learning agents by building this.

## Non-negotiables from the spec

- **Individual mode only.** No team mode. Don't add it "for later."
- **LLM: Groq first, Gemini as backup** for the one call that can run long (research +
  search results). Never hard-code which one is used — make it a fallback, not a toggle
  I have to flip by hand.
- **Exactly 5 questions per game.** 3 written during research, at medium difficulty.
  2 written after question 3, at whatever difficulty the agent picks. Never pre-write
  more than that and filter — the agent should actually write questions 4 and 5 live,
  because that's the "wait, how?" moment the demo depends on.
- **The agent only wakes up at 4 moments** (research, after each question, after
  question 3, end of game). Everything else — timers, scoring, moving between stages —
  is plain server code, not an LLM call. Don't add more AI calls than the spec lists.
- **Log every agent step from day one**, even before the thoughts panel UI exists.
  This log is what the thoughts panel reads, and it's also our debugging tool.
- **Keep the agent's loop code simple and readable.** Students see a version of this
  same loop in the hands-on part of the lecture ("perceive → reason → act → observe").
  If our code is a tangle of abstractions, that connection breaks. Prefer one obvious
  function per agent moment over a generic "agent framework."
- **No student data survives the session.** Nicknames and answers only, nothing else
  collected, and say so in the README.
- **Never commit secrets.** Groq/Gemini/Tavily keys and the presenter PIN go in `.env`,
  which is gitignored. Tell me the exact variable names you expect so I can fill them in.

## Definition of done, each phase

Copy the "Done when" line from the Phases table in `spec.md` and treat it literally —
if I can't do that exact thing, the phase isn't done yet, even if the code looks complete.

## Questions still open (ask me, don't assume)

- Which exact Groq model to use (must support tool calling) — I'll confirm before Phase 3.
- Hosting provider (Railway / Render / Fly.io) — I'll confirm before Phase 7.
- The agent's commentary tone/personality — I'll give example lines before Phase 4.
- Nickname blocklist wording — I'll provide the list before Phase 6.
