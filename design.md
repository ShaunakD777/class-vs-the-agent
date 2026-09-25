# Class vs. The Agent — Frontend Design Specification

## 1. Purpose

This document defines the visual and responsive design system for **Class vs. The Agent**.

The product is a live classroom game-show experience used during the first ~8 minutes of a guest lecture on Agentic AI. It is not intended to look like a generic SaaS dashboard, developer tool, or AI-generated admin panel.

The interface must feel like a **real, polished interactive classroom/game-show product** while making the underlying agent behavior visible enough to support the teaching objective.

The visual identity already established in the current mockups is retained:

- Deep navy foundation
- Warm orange as the primary accent
- Off-white primary text
- Soft blue as the secondary accent
- Green for success/confirmed states
- Pink for incorrect/negative states
- Subtle gradients and ambient glows
- Rounded geometry, but not excessive pill-shaped UI

The redesign should substantially improve typography, spacing, hierarchy, composition, responsiveness, and consistency without changing the application's underlying game logic.

---

## 2. Product Context

There are three different audiences/devices:

### A. Presenter / Host

One presenter operates the application from a laptop browser.

The presenter's browser is duplicated/mirrored onto a classroom smart board or projector. Therefore the host interface is simultaneously:

1. a control surface for the presenter, and
2. a presentation surface for approximately 50 students.

The presenter must be able to operate the game without the visible UI becoming cluttered for the audience.

### B. Players / Students

Most students use phones. Some may use laptops, tablets, or desktop PCs.

Students join through a QR code or URL and do not need an account.

Their interface is a **participation UI**, not a miniature copy of the host screen.

### C. Classroom Audience

Students who are not currently looking at their own phone should be able to understand what is happening on the smart board at a glance.

The projector/smart-board experience therefore has much stronger typography and visual hierarchy than the player interface.

---

## 3. Design Goals

The frontend must satisfy these goals in this order:

1. **Readable from the back of a classroom.**
2. **Immediately understandable without explanation.**
3. **Fast to operate by one presenter under pressure.**
4. **Comfortable to use on a phone with one hand.**
5. **Feels like a real product rather than AI-generated UI.**
6. **Makes the agent's behavior visually understandable without exposing raw technical logs.**
7. **Looks like one coherent application across all game stages.**
8. **Remains usable at imperfect classroom resolutions and browser sizes.**

---

## 4. Reference Products / Design Research

The redesign should borrow interaction patterns from established live-presentation and classroom products, while keeping the project's own visual identity.

### Kahoot

Kahoot is a relevant reference for large-room quiz presentation, projector readability, live game states, answer/result transitions, leaderboard moments, and participant-device separation. Its current live-game documentation also explicitly supports showing questions and answers on player devices, which is useful for large classrooms where projector visibility varies. It also documents increased-contrast options for projector use.

Reference:
- https://support.kahoot.com/hc/en-us/articles/360039422694-How-to-host-a-live-kahoot
- https://support.kahoot.com/hc/en-us/articles/115016055107-Live-game-settings
- https://support.kahoot.com/hc/en-us/articles/115003197928-How-to-enable-See-questions-on-participant-s-screen-in-Kahoot-live-games
- https://support.kahoot.com/hc/en-us/articles/29968568026131-How-to-preview-and-test-your-kahoot-before-hosting-live

Design lessons to borrow:
- Large-room readability
- Distinct game states
- Strong answer cards
- Clear countdown/timing
- High-contrast presentation mode
- Separate participant experience
- Celebration without turning the entire UI into decoration

### Mentimeter

Mentimeter is relevant for its presentation-first model and because its participant experience is explicitly designed to work from phones, tablets, laptops, and other browser-capable devices. Its presentation view separates audience-facing content from presenter controls.

Reference:
- https://www.mentimeter.com/features/presentation-maker
- https://help.mentimeter.com/en/articles/375448-this-is-the-presentation-view
- https://help.mentimeter.com/en/articles/410950-what-device-to-use-for-participation
- https://help.mentimeter.com/en/articles/410899-how-the-presentation-mode-affects-your-menti-live

Design lessons to borrow:
- Presentation canvas as the main visual surface
- Device-independent participant UI
- Minimal presenter chrome
- Large, clean content areas
- Simple participation instructions

### Slido

Slido is useful as a reference for live audience interaction and host controls. Its current interface puts live interaction management in a compact control area rather than letting controls dominate the presentation surface.

Reference:
- https://www.slido.com/features-live-qa
- https://community.slido.com/product-news-announcements-108/new-slido-interface-faqs-3899

Design lessons to borrow:
- Focused live interaction
- Compact presenter controls
- Clear distinction between content and controls
- Clean activity/results presentation

### AhaSlides

AhaSlides is relevant for the combination of projected presentation content and phone participation. Its documented workflow supports a presenter running a presentation from a desktop while participants join from phones.

Reference:
- https://ahaslides.com/marketplace/microsoft-powerpoint-desktop/
- https://ahaslides.com/features/
- https://ahaslides.com/features/presentation-remote-control/

Design lessons to borrow:
- Presentation-first composition
- Phone-first participation
- Immediate live response feedback
- Strong visual result states

### Important constraint

Do **not** copy the branding, colors, illustrations, mascots, or exact layouts of these products. Borrow their proven interaction principles and information hierarchy, then apply this project's own visual system.

---

## 5. Overall Visual Direction

### Desired feeling

The application should feel like:

**AI laboratory + live quiz show + modern presentation system.**

It should feel technical and intelligent without becoming a developer console.

### Avoid

Do not use:

- Generic AI-dashboard layouts
- Excessive glassmorphism
- Huge blurred gradient blobs behind every component
- Excessive pill-shaped controls
- Monospace typography for everything
- Tiny metadata everywhere
- Dense dashboard grids
- Browser-looking sidebars
- Permanent scrollbars on the presentation surface
- Excessive icons with no information value
- Random decorative AI symbols
- Template-looking cards stacked inside cards
- Excessive neon/cyberpunk styling
- Excessive animations
- Stock AI imagery
- Generic robot illustrations

### Use

Use:

- Strong typography
- Large intentional whitespace
- Hierarchical composition
- Subtle borders
- Soft elevation
- Controlled gradients
- Small ambient glows
- Large, readable numbers
- Strong state changes
- Spatial grouping
- Consistent components
- Restrained motion

The UI should look designed by a strong product/design team, not assembled from random component libraries.

---

## 6. Color System

### Core palette

```text
Deep Navy       #14182B   Main page background
Navy Surface    #1B2038   Elevated surface
Navy Soft       #202746   Secondary surface / cards
Navy Border     #303858   Subtle borders
Off White       #F7F5F0   Primary text
Muted Text      #AEB4C8   Secondary text
Warm Orange     #FF7A45   Primary action / active state
Soft Blue       #4C7DFF   Secondary accent
Success Green   #2DCB91   Correct / completed / healthy
Error Pink      #FF5C87   Incorrect / attention

Optional atmospheric colors:
Orange Glow     rgba(255,122,69,.18)
Blue Glow       rgba(76,125,255,.16)
Green Glow      rgba(45,203,145,.14)
```

### Color rules

Orange should mean **active, important, primary, or currently happening**.

Blue should mean **secondary information, navigation, supporting state, or selected-but-not-primary**.

Green should mean **confirmed, correct, completed, or healthy**.

Pink should mean **incorrect, negative, or changed downward**.

Never rely on color alone to convey meaning. Pair color with text, iconography, shape, or position.

---

## 7. Typography

### Primary font

Use a modern geometric sans-serif:

```css
font-family: "Space Grotesk", "Inter", system-ui, sans-serif;
```

Recommended usage:

- Headings: Space Grotesk / Sora / equivalent
- Body: Inter / system sans-serif
- Numbers: same sans-serif, with tabular numerals where supported

### Technical font

Use a monospace font selectively:

```css
font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
```

Use it only for:

- Agent activity events
- Usernames when appropriate
- Technical status
- Small system labels
- Timings or source metadata

Do **not** use monospace for the primary question, major headings, buttons, or normal body copy.

### Scale — presentation/host

Target values for a 1920×1080 presentation surface:

```text
Page title             56–72 px
Primary game question  62–84 px
Major score            48–64 px
Countdown number       72–112 px
Section heading        32–44 px
Large supporting text  28–36 px
Normal body            24–30 px
Agent activity         22–28 px
Metadata               18–22 px minimum
```

Use `clamp()` rather than hard-coding every font size.

### Scale — mobile/player

```text
Page title             28–34 px
Question               26–34 px
Answer                 18–24 px
Primary number         32–48 px
Normal body            16–18 px
Secondary text         14–16 px
```

---

## 8. Layout System

### Presentation canvas

The host/projector UI is a **16:9 presentation canvas**.

Design for:

- 1920×1080
- 1600×900
- 1536×864
- 1366×768
- 1280×720

Do not depend on a specific monitor resolution.

Use a responsive layout constrained by the browser viewport:

```css
min-height: 100dvh;
width: 100%;
```

Use safe outer margins rather than allowing content to touch the edges.

Recommended presentation horizontal padding:

```text
1920px viewport: 56–72px
1366px viewport: 40–56px
1280px viewport: 32–48px
```

### Host/presentation structure

Default composition:

```text
┌──────────────────────────────────────────────────────────────┐
│ Brand / game status / participant count                     │
├───────────────────────────────────────────────┬──────────────┤
│                                               │              │
│                                               │   AGENT      │
│             MAIN GAME AREA                   │   ACTIVITY   │
│                                               │              │
│                                               │              │
├───────────────────────────────────────────────┴──────────────┤
│ Minimal presenter controls / status                         │
└──────────────────────────────────────────────────────────────┘
```

Agent activity should generally occupy **25–30%** of the presentation width.

Main game content should occupy **70–75%**.

However, the activity panel may collapse or reduce on some states where the game itself needs more width.

### No permanent page scrolling

The 8 presentation states must fit inside the viewport.

Do not design pages that require scrolling vertically or horizontally to understand the game.

If a live activity feed grows beyond the available panel height, it should:

- auto-scroll internally,
- display the latest relevant event,
- or collapse older events into a compact history indicator.

Never allow a browser scrollbar to appear as part of the intended presentation design.

---

## 9. Header

Use a consistent header across all eight states.

The header should contain only information that helps orientation:

Left:
- Class vs. The Agent

Center/right when relevant:
- Current topic
- Q3 / 5
- Participant count

Do not turn the header into a navigation bar.

The header should remain visually stable between states so that state changes happen primarily in the main content area.

Recommended height: approximately 84–104px depending on viewport size.

The brand should use the existing styling concept:

**Class vs.** in off-white
**The Agent** in warm orange

---

## 10. Agent Activity Panel

The current "AGENT THOUGHTS" panel is conceptually important but visually too close to a raw developer log.

Rename the visual treatment to:

**AGENT ACTIVITY**

or

**AGENT LIVE ACTIVITY**

The database/event terminology can remain `agent_event` internally.

### Visual model

Use a chronological event feed with small semantic icons and clear hierarchy.

Example:

```text
AGENT ACTIVITY

◉ SEARCH
  "Europa Clipper latest news"

✓ SOURCES
  3 sources found

◈ ANALYZE
  Checking facts against sources

→ QUESTION
  Q3 drafted · Medium

● WAITING
  Watching the class
```

### Rules

- Latest event gets strongest emphasis.
- Older events fade slightly.
- Use monospace sparingly within events.
- Keep individual events to 1–3 lines.
- Never show giant blocks of raw JSON.
- Never show internal stack traces.
- Never expose system prompts.
- Never claim the UI is showing private chain-of-thought.
- Treat displayed entries as concise **agent activity summaries**.

The purpose is to reveal the observable workflow, not technical internals.

---

## 11. Presenter Controls

The presenter is operating the same screen that students see.

Therefore controls must be present but visually subordinate.

### Preferred behavior

Use a compact presenter control bar or small control area at the lower edge of the presentation.

Primary controls:

- Start
- Next
- Pause
- Resume
- Skip
- Safe mode
- Remove player, where applicable
- Approve, where applicable

### Visual rules

- Primary action: orange
- Destructive/exception action: muted unless needed
- Controls should be large enough to click quickly
- Controls must never compete with the question/result
- Avoid a full admin sidebar
- Avoid exposing implementation details to students

Keyboard shortcuts may supplement buttons, but the interface must remain usable without them.

---

## 12. Player UI — Mobile First

The player interface is a separate responsive experience.

It must NOT simply scale the projector UI down.

### Phone target

Optimize primarily for:

- 360×800
- 390×844
- 412×915
- similar Android/iOS browser sizes

### Desktop player target

Also support:

- 768px+
- laptops
- tablets
- desktop browser windows

### Player design principles

The player should contain only what the player needs at that moment.

During a question:

```text
┌─────────────────────┐
│ Q3 / 5        14s   │
│                     │
│ Which spacecraft    │
│ ...?                │
│                     │
│ ┌─────────────────┐ │
│ │ Europa Clipper  │ │
│ └─────────────────┘ │
│                     │
│ ┌─────────────────┐ │
│ │ Juno            │ │
│ └─────────────────┘ │
│                     │
│ ┌─────────────────┐ │
│ │ Cassini         │ │
│ └─────────────────┘ │
│                     │
│ ┌─────────────────┐ │
│ │ New Horizons    │ │
│ └─────────────────┘ │
└─────────────────────┘
```

Use large touch targets.

Minimum interactive target: **44×44px**, preferably 52px+ for primary answer controls.

Avoid tiny text and tight card clusters.

### Player question behavior

The player should see the question and answers on their own device. This follows a pattern used by classroom/live quiz products and prevents students at the back of the room from depending entirely on the projected screen.

After answering:

- clearly indicate their selected answer,
- disable accidental double submission,
- show a waiting state,
- show result information when the server releases it.

### Player leaderboard

The player may see:

- own score
- own rank
- nearby ranks

Do not force every student to read a giant top-10 leaderboard on a phone.

---

## 13. Responsive Breakpoints

Use behavior-based breakpoints rather than designing exclusively around device names.

```text
0–599px        Mobile player
600–899px      Large mobile / tablet
900–1199px     Small desktop / tablet landscape
1200–1599px    Laptop / standard host
1600px+        Large presentation / smart board
```

At mobile widths:

- single-column layout
- agent activity hidden or collapsed unless explicitly needed
- answer options full-width
- larger touch targets
- reduced decoration
- no horizontal scrolling

At desktop player widths:

- centered content with a comfortable maximum width
- answer grid may become 2 columns
- status/sidebar can appear if useful

At host/presentation widths:

- maintain 16:9 composition
- large typography
- persistent orientation header
- agent activity panel visible

---

## 14. Spacing System

Use a consistent spacing scale:

```text
4   8   12   16   24   32   40   48   64   80
```

Do not create arbitrary spacing values for every component.

Large presentation elements should usually use:

- 32px minimum internal spacing
- 40–64px between major groups
- 64–96px for hero-level separation

Mobile should use:

- 12–20px card padding
- 16–24px section spacing

---

## 15. Borders, Radius, and Elevation

The current interface uses too many rounded capsules.

Move toward a more mature component language.

### Radius

```text
Small controls       10–12px
Cards                16–20px
Large hero surfaces  20–28px
Answer cards         16–20px
```

Do not make everything a pill.

Pills should be reserved for:

- compact status
- topic badge
- participant count
- small categorical labels

### Borders

Use thin, low-contrast borders:

```text
1px solid #303858
```

Use orange borders mainly for active/attention states.

### Elevation

Use extremely subtle shadows. Prefer contrast and border separation over heavy shadows.

---

## 16. Motion

Motion should support the live-game feeling but never become distracting.

Use:

- 150–250ms hover/press transitions
- 250–400ms state transitions
- subtle answer-card entrance
- countdown progress animation
- soft activity-feed entry animation
- restrained celebration on final state

Do not use:

- constant bouncing
- excessive particle effects
- large screen shakes
- continuous background animation
- animations that make text hard to read

Respect `prefers-reduced-motion`.

---

## 17. Iconography

Use one consistent icon family.

Icons should be simple line or compact filled icons with consistent stroke weight.

Do not mix multiple unrelated icon styles.

Icons should reinforce meaning, not decorate empty space.

Useful semantic icons:

- Search
- Source/check
- Brain/analysis
- Question
- Timer
- People
- Trophy
- Up/down movement
- Approval/check
- Notes
- Waiting/pause

---

## 18. Eight Host/Presentation States

The eight redesigned states are:

1. **Lobby** — students joining, waiting for topic
2. **Researching** — agent searching and preparing questions
3. **Question** — live timed question
4. **Reveal** — answer/result + agent commentary
5. **Leaderboard** — post-question standings
6. **Difficulty Check** — agent adapts difficulty after Q3
7. **Approval** — presenter approves winners announcement
8. **Final / Notes** — podium, class stats, revision notes

Each state must feel like part of the same application.

Do not redesign each state as an independent visual theme.

---

## 19. State-Specific Guidance

### Lobby

Primary objective: get students into the room quickly.

Priorities:

1. QR code
2. Join URL
3. Participant count
4. Student names
5. Waiting/ready status
6. Presenter topic control

The QR code should be visually prominent but should not overwhelm the title or participant count.

### Researching

Primary objective: make the agent's process visible.

Priorities:

1. Topic
2. Current agent phase
3. Search/source activity
4. Drafting progress
5. Live activity feed

The viewer should understand that the AI is doing work, not loading a page.

### Question

Primary objective: get everyone answering.

Priorities:

1. Question
2. Timer
3. Answer choices
4. Answered count
5. Q number
6. Minimal agent activity

### Reveal

Primary objective: create an information/celebration moment.

Priorities:

1. Correct answer
2. Response distribution
3. Short agent commentary
4. Source

### Leaderboard

Primary objective: show competition and movement.

Priorities:

1. Top players
2. Scores
3. Rank movement
4. Current player highlight when relevant

### Difficulty Check

Primary objective: visibly demonstrate adaptive behavior.

Priorities:

1. Class-performance evidence
2. Agent decision
3. New difficulty
4. Short explanation

### Approval

Primary objective: demonstrate human-in-the-loop behavior.

Priorities:

1. Draft
2. Human approval status
3. Approve button
4. Skip/alternative action

### Final / Notes

Primary objective: close the game and transition into the lecture.

Priorities:

1. Winners/podium
2. Class performance
3. Revision notes
4. Clear completion state

---

## 20. Information Density Rules

The projected interface should pass the **3-second test**:

A student glancing at the smart board for three seconds should know:

- what stage the game is in,
- what they need to do,
- what the important number/result is.

Anything else is secondary.

Do not show all available data simply because the application has it.

Data belongs in the UI only if it helps the current game state or reinforces the teaching moment.

---

## 21. Accessibility and Readability

Minimum requirements:

- Strong text/background contrast
- Never use color as the sole indicator
- Minimum 44×44px touch target
- Focus states for keyboard users
- Visible selected/pressed states
- Large tap areas on mobile
- Support reduced motion
- Do not rely solely on tiny icons
- Avoid long lines of text on mobile
- Maintain clear reading order for screen readers where practical

The host presentation should remain legible under imperfect projector brightness and classroom lighting.

---

## 22. Browser and Deployment Constraints

The frontend is served by the existing FastAPI application and should remain compatible with the current plain HTML/CSS/JS architecture unless the implementation explicitly decides otherwise.

Do not introduce a large frontend build system solely for visual polish.

The interface must function in current Chrome/Edge/Safari-class browsers.

Do not depend on external assets that are essential for the game to function.

Fonts should have reliable local/system fallbacks.

The game itself must remain functional if decorative assets fail to load.

---

## 23. Implementation Rules for the Redesign

The redesign must preserve:

- Existing routes
- Existing WebSocket behavior
- Existing game stages
- Existing scoring
- Existing player identity/reconnect behavior
- Existing agent events
- Existing safe mode
- Existing presenter controls
- Existing game functionality

Visual work must not silently alter game semantics.

Refactor shared UI components where practical instead of duplicating eight unrelated implementations.

Recommended shared components:

- `Header`
- `AgentActivity`
- `ParticipantCount`
- `TopicBadge`
- `Timer`
- `AnswerCard`
- `StatusBadge`
- `LeaderboardRow`
- `ProgressIndicator`
- `PresenterControls`
- `Toast/TransientMessage`

---

## 24. Final Quality Bar

Before considering the redesign complete, inspect every state at:

- 1920×1080 host/presentation
- 1366×768 laptop
- 390×844 mobile
- 412×915 mobile
- ~768px tablet

Every state must be visually coherent at all relevant sizes.

The final result should answer **yes** to all of these:

- Does it look like a real product?
- Can students at the back of a classroom read the important information?
- Can the presenter operate it without hunting for controls?
- Can a student answer comfortably from a phone?
- Does the app look consistent as the stage changes?
- Does the agent activity feel understandable rather than like a terminal log?
- Is the visual design distinctive without looking gimmicky?
- Does the interface feel intentionally designed rather than generated from a generic AI dashboard template?

The goal is not to make the interface prettier.

The goal is to make the live experience feel **credible, polished, fast, and memorable enough that students immediately wonder how the agent works.**
