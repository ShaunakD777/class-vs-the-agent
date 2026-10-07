# Class vs. The Agent

A snapshot of what this project is, how it works, and how far it has been built.
For the full requirements see [docs/spec.md](docs/spec.md); for the visual design see
[docs/design.md](docs/design.md).

## What it is

Class vs. The Agent is an 8-minute live quiz show that opens a 2-hour "Agentic AI"
guest lecture for 2nd-year CSE students. About 50 students join on their phones by
scanning a QR code and play against an AI "Game Master" shown on the projector.

The agent:

1. **Researches a topic the class shouts out**, searching the web live while
   students watch its steps in a "thoughts panel".
2. **Writes 3 medium-difficulty questions** from what it found.
3. **Comments on each round**, calling out real players by nickname.
4. **Checks how the class is doing after question 3**, decides on its own whether
   to make the last 2 questions easier or harder, says why, and writes them live.
5. **Wraps up** with a revision note per question and a drafted winners
   announcement, which it only shows after the presenter clicks Approve.

The point is not the quiz itself. It is to leave students asking "how did it do
that?", and the lecture then answers each question: web search as a tool, the
agent loop, short-term memory, human-in-the-loop, and long-term memory.

## How it works

One Python server does everything. There is no separate front-end build.

```
50 phones (/play)  <--WebSocket-->  FastAPI server  <-->  SQLite (game.db)
Projector (/host)  <--WebSocket-->        |
                                          +--> Game Master agent --> Groq (Gemini as backup)
                                                                 --> Tavily web search
```

- **The server is the single source of truth.** It keeps the clock, checks answers
  and calculates scores. Phones and the host screen only display what the server
  sends them, and the correct answer is never sent to phones before the reveal.
- **The AI only wakes up at 4 moments.** Timers, scoring, leaderboards and moving
  between stages are plain server code. That keeps a game to roughly 10 AI calls
  in total, not one per student.
- **Every agent step is logged** to the `agent_event` table and pushed to the host
  screen's thoughts panel as it happens.

### The four agent moments

| Moment | Code | What happens | Time limit | If it fails |
| --- | --- | --- | --- | --- |
| 1. Research | `research_topic` in [app/agent.py](app/agent.py) | A real tool-calling loop on Groq: the model calls `search_web` 2–4 times, then `write_questions` to submit 3 questions plus research notes | 15 s per turn, max 6 turns | Retry once with Gemini (one search + one call); if that fails too, use the safe-mode quiz |
| 2. After each question | `write_commentary` | One Groq call turns the round's stats into 1–2 lines naming players | 4 s | A ready-made line |
| 3. After question 3 | `run_difficulty_check` | One Groq call reads class accuracy, picks easy/medium/hard, gives a reason, and writes questions 4 and 5 from the saved research notes | 10 s | Two medium questions from the safe-mode quiz |
| 4. End of game | `write_wrap_up` | One Groq call writes 5 revision notes and a winners announcement draft | 15 s | Use the question explanations as notes and a plain announcement |

Only moment 1 falls back to Gemini, to save the Gemini key's rate limit. The
research loop is written as one readable function (perceive → reason → act →
observe) so it can be shown alongside the hands-on exercise in the lecture.

### A game, stage by stage

`lobby` → `researching` → `ready` → (`question` → `reveal` → `leaderboard`) × 3 →
`difficulty_check` → (`question` → `reveal` → `leaderboard`) × 2 → `final` →
`approval` → `notes`

Only the presenter's clicks and the question timer move the game forward.

### Scoring

A correct answer earns 500 points plus up to 500 more for speed, scaled by time
left on the 20-second clock. Wrong or missing answers earn 0. Answer time is taken
from the server's clock when the answer arrives, so a slow phone never gets extra
time.

## What has been built

The spec splits the work into 8 phases. Status as of this snapshot:

| Phase | Status | What exists |
| --- | --- | --- |
| 1. Skeleton | Done | FastAPI server, all 7 database tables, host and player pages, WebSocket connections, QR code |
| 2. Game engine | Done | Stages, 20 s timer, answer checking, scoring, reveal with answer split, top-10 leaderboard; playable with the safe-mode quiz and no AI |
| 3. Research agent | Done | Tavily search tool, Groq tool-calling loop, Gemini fallback, live thoughts panel |
| 4. Live agent moments | Done | Commentary after every question, difficulty check with a full-screen banner, questions 4 and 5 written live |
| 5. Wrap-up | Done | Revision notes, approval screen, announcement shown only after Approve; each phone gets its rank plus notes for the questions it missed |
| 6. Hardening | Done | Safe-mode button, reconnect by device token, time limits on every AI and search call, nickname length and blocklist check, presenter controls (pause/resume, skip, safe mode, remove player) |
| 7. Deploy and load test | Partly done | `Procfile` and `runtime.txt` are ready for hosting, and [scripts/load_test.py](scripts/load_test.py) simulates 50 players. The hosting provider and the real-phone / college Wi-Fi tests are still to do |
| 8. Polish and rehearse | Partly done | Host and phone screens are styled to [docs/design.md](docs/design.md), with confetti on the final screen. Reveal mode, sounds, rehearsals and a backup recording are not done yet |

## Project layout

| Path | What it is |
| --- | --- |
| [app/main.py](app/main.py) | Web routes (`/host`, `/play`, `/qr.png`), the two WebSocket endpoints, nickname joining and reconnecting |
| [app/game.py](app/game.py) | The game engine: stages, timer, scoring, reveal, leaderboard, presenter controls, wrap-up and approval |
| [app/agent.py](app/agent.py) | The four agent moments, their prompts and fallbacks, and `log_event` for the thoughts panel |
| [app/llm.py](app/llm.py) | Small wrappers around Groq (`openai/gpt-oss-120b`) and Gemini (`gemini-3.8-flash`) |
| [app/search.py](app/search.py) | Tavily web search with a 5-second limit |
| [app/db.py](app/db.py) | SQLite schema (`game`, `player`, `question`, `answer`, `revision_note`, `agent_event`, `approval`) |
| [app/connections.py](app/connections.py) | Keeps track of the host and player WebSocket connections |
| [app/nickname_filter.py](app/nickname_filter.py) | Nickname blocklist |
| [app/quiz_data.py](app/quiz_data.py), [data/](data/) | The 5-question emergency quiz that needs no internet or AI (`safe_mode_quiz.json`) and the end-of-lecture question bank (`wrap_up_quiz.json`) |
| [templates/](templates/) | Host screen (one partial per stage) and player page |
| [static/](static/) | CSS design tokens and components, plus `host.js`, `player.js`, `ui.js` |
| [scripts/load_test.py](scripts/load_test.py) | Simulates many players joining and answering a full game |
| [docs/mockups/](docs/mockups/) | Static HTML mockups of the host and lobby screens |

## Running it locally

1. Create `.env` (see [.env.example](.env.example)) with:
   `GROQ_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `PRESENTER_PIN`.
   `.env` is gitignored and must never be committed.
2. `pip install -r requirements.txt`
3. `uvicorn app.main:app --reload`
4. Open `http://localhost:8000/host?pin=<your PIN>` on the laptop and
   `http://localhost:8000/play` on phones (or scan the QR code on the host screen).

If `PRESENTER_PIN` is empty the host screen is not protected, which is fine
locally but must be set before deploying.

## Privacy

Only nicknames and answers are collected. There are no accounts, logins, emails
or phone numbers. Students are asked to pick a nickname, not their real name.

- Nicknames, answers and scores live only in the server's local SQLite file
  (`game.db`, gitignored). No student data survives the session: the database
  is cleared after the lecture.
- Some nicknames, with their scores and round results, are sent to Groq to
  write the commentary and the winners announcement. Only the quiz topic is
  sent to Tavily (web search) and Gemini (research backup).
- Each phone stores a random device token in its browser so a refresh rejoins
  the same player. It identifies nothing outside this game.

## Still to do

- Pick a hosting provider (Railway / Render / Fly.io), deploy, and run the real
  10–15 phone test on college Wi-Fi.
- Reveal mode: replaying the agent's full log after the lecture with each step
  labelled. The data is already logged in `agent_event`; only the screen is missing.
- Optional sounds (last-5-seconds tick, reveal sting).
- Wipe game data after the session. Right now `game.db` keeps nicknames and answers
  until it is deleted by hand, which the spec's "deleted after the session" rule
  still needs.
- Remove the temporary `DEBUG` traceback prints in `research_topic`.
- Tune the research prompt on 10+ topics, then do 2 full rehearsals and record a
  backup video.
