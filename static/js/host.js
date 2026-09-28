/* Host screen controller.

   The WebSocket contract is unchanged from the version this replaces: the
   same host_control actions go out, and the same server messages come in.
   Everything new here is presentation - which state is on screen, and a few
   numbers (rank movement, class accuracy) derived on this screen from data
   the server already sends, so the backend stays as it is. */

(function () {
    "use strict";

    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    var pinParam = encodeURIComponent(window.PRESENTER_PIN || "");
    var ws = new WebSocket(proto + "//" + window.location.host + "/ws/host?pin=" + pinParam);

    var frame = UI.el("host-frame");
    var feed = UI.el("activity-feed");
    var idle = UI.el("activity-idle");

    var RING_LENGTH = 270.18; /* 2 * pi * r, with r = 43 in the timer SVG */

    /* ---------------------------------------------------------------- state */
    var currentQuestion = null;   /* the live question's text and options */
    var questionSeconds = 20;     /* the full length of the live question */
    var rounds = [];              /* one {correct, answered} per finished round */
    var previousRanks = {};       /* nickname -> rank at the last leaderboard */
    var nicknames = {};           /* every nickname we've seen, for commentary */
    var playerCount = Number(UI.el("player-count").textContent) || 0;

    /* "main" or "wrap_up". The page is rendered with the current one, and
       mode_changed switches it; host.css reads data-mode for the look. */
    function currentMode() {
        return frame.getAttribute("data-mode");
    }

    /* Modes can only be switched between games (the server enforces the
       same rule), so the header button is off everywhere else. */
    var SWITCHABLE_STATES = ["lobby", "ready", "final"];

    function showState(stage) {
        frame.setAttribute("data-stage", stage);
        UI.el("mode-btn").disabled = SWITCHABLE_STATES.indexOf(stage) === -1;
        var sections = document.querySelectorAll(".state");
        for (var i = 0; i < sections.length; i++) {
            sections[i].classList.toggle(
                "is-active",
                sections[i].getAttribute("data-state") === stage
            );
        }
    }

    function setPlayerCount(n) {
        playerCount = n;
        UI.el("player-count").textContent = n;
        UI.el("lobby-count").textContent = n;
    }

    function setTopic(topic) {
        if (!topic) return;
        UI.el("topic-pill-text").textContent = topic;
        UI.show(UI.el("topic-pill"), true);
        UI.el("research-topic").textContent = topic;
    }

    /* ------------------------------------------------------- agent activity */
    function pushEvent(event) {
        UI.show(idle, false);
        var step = UI.appendEvent(feed, event);
        updateResearchProgress(event, step);
    }

    /* The researching state's three phases and counters are read off the same
       event stream, so nothing extra has to be sent for them. */
    var research = { searches: 0, sources: 0, drafted: 0 };

    function setPhase(name) {
        var phases = document.querySelectorAll("#research-phases .phase");
        var order = ["search", "analyze", "build"];
        var target = order.indexOf(name);
        for (var i = 0; i < phases.length; i++) {
            var at = order.indexOf(phases[i].getAttribute("data-phase"));
            phases[i].classList.toggle("is-active", at === target);
            phases[i].classList.toggle("is-done", at < target);
        }
    }

    function updateResearchProgress(event, step) {
        if (event.moment !== "research") return;

        if (step.label === "Search") {
            research.searches += 1;
            setPhase("search");
        } else if (step.label === "Sources") {
            var n = parseInt(step.text, 10);
            research.sources += isNaN(n) ? 0 : n;
            setPhase("analyze");
        } else if (step.label === "Analyze") {
            setPhase("analyze");
        } else if (step.label === "Questions") {
            research.drafted = 3;
            setPhase("build");
            document.querySelector('#research-phases [data-phase="build"]').classList.add("is-done");
        }

        UI.el("research-searches").textContent = research.searches;
        UI.el("research-sources").textContent = research.sources;
        UI.el("research-drafted").textContent = research.drafted + " / 3";
    }

    /* --------------------------------------------------------------- lobby */
    var playerList = UI.el("player-list");

    function addPlayerRow(playerId, nickname) {
        nicknames[nickname] = true;

        var li = document.createElement("li");
        li.className = "participant";
        li.dataset.playerId = playerId;

        var name = document.createElement("span");
        name.className = "participant__name";
        name.textContent = nickname;

        var remove = document.createElement("button");
        remove.className = "participant__remove remove-player-btn";
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove " + nickname);
        remove.appendChild(UI.icon("x"));

        li.appendChild(name);
        li.appendChild(remove);
        playerList.appendChild(li);
    }

    /* Seed the nickname list from whatever the page was rendered with. */
    (function seedNicknames() {
        var existing = playerList.querySelectorAll(".participant__name");
        for (var i = 0; i < existing.length; i++) {
            nicknames[existing[i].textContent] = true;
        }
    })();

    playerList.addEventListener("click", function (event) {
        var button = event.target.closest(".remove-player-btn");
        if (!button) return;
        var li = button.closest("li");
        var playerId = li && li.dataset.playerId;
        if (!playerId) return;
        send("remove_player", { player_id: playerId });
    });

    /* ------------------------------------------------------------ question */
    function renderQuestion(data) {
        currentQuestion = { text: data.text, options: data.options };

        UI.el("q-text").textContent = data.text;

        var options = UI.el("q-options");
        UI.clear(options);
        data.options.forEach(function (option, i) {
            var card = document.createElement("div");
            card.className = "option " + UI.answerClass(i);
            card.appendChild(UI.shape(i));
            var text = document.createElement("span");
            text.className = "option__text";
            text.textContent = option;
            card.appendChild(text);
            options.appendChild(card);
        });

        UI.el("question-pill-slot").textContent = data.slot;
        UI.el("question-pill-total").textContent = data.total_questions;
        UI.show(UI.el("question-pill"), true);

        UI.el("answered-count").textContent = "0";
        UI.el("answered-total").textContent = data.player_count;
    }

    var timerEl = UI.el("timer");
    var timerNum = UI.el("timer-num");
    var timerProgress = UI.el("timer-progress");

    var countdown = UI.Countdown(function (seconds, fraction) {
        timerNum.textContent = seconds;
        timerProgress.style.strokeDasharray =
            RING_LENGTH * fraction + " " + RING_LENGTH;
        timerEl.classList.toggle("is-urgent", seconds <= 5);
    });

    /* -------------------------------------------------------------- reveal */
    function renderReveal(data) {
        var options = (currentQuestion && currentQuestion.options) || [];
        var counts = data.option_counts || [];
        var answered = counts.reduce(function (a, b) { return a + b; }, 0);
        var correct = counts[data.correct_index] || 0;

        rounds.push({ correct: correct, answered: answered });

        UI.el("reveal-correct").textContent =
            options[data.correct_index] || "Option " + (data.correct_index + 1);

        var dist = UI.el("reveal-dist");
        UI.clear(dist);
        counts.forEach(function (count, i) {
            var isCorrect = i === data.correct_index;

            var row = document.createElement("div");
            row.className =
                "dist__row " + UI.answerClass(i) +
                (isCorrect ? " dist__row--correct" : " dist__row--muted");

            row.appendChild(UI.shape(i));

            var label = document.createElement("span");
            label.className = "dist__label";
            label.textContent = options[i] || "Option " + (i + 1);
            row.appendChild(label);

            var track = document.createElement("div");
            track.className = "dist__track";
            var fill = document.createElement("div");
            fill.className = "dist__fill";
            track.appendChild(fill);
            row.appendChild(track);

            var value = document.createElement("span");
            value.className = "dist__pct";
            value.textContent = UI.pct(count, answered) + "%";
            row.appendChild(value);

            dist.appendChild(row);

            /* Grow the bars a frame later so the transition actually runs. */
            requestAnimationFrame(function () {
                fill.style.width = UI.pct(count, answered) + "%";
            });
        });

        UI.el("reveal-pct").textContent = UI.pct(correct, answered) + "%";
        UI.el("reveal-explanation").textContent = data.explanation || "";
        UI.el("reveal-source").textContent = data.source_url || "";

        var box = UI.el("reveal-commentary-box");
        box.classList.add("is-pending");
        UI.el("reveal-commentary").textContent = "Reading the room…";
    }

    /* --------------------------------------------------------- leaderboard */
    function renderLeaderboard(top) {
        var list = UI.el("leaderboard-list");
        UI.clear(list);

        var shown = top.slice(0, 5);
        shown.forEach(function (player, index) {
            var rank = index + 1;
            nicknames[player.nickname] = true;

            var was = previousRanks[player.nickname];
            var moved = was === undefined ? 0 : was - rank;

            var row = document.createElement("li");
            row.className = "lb__row lb__row--" + rank;
            if (moved >= 3) row.classList.add("lb__row--jumped");

            var rankEl = document.createElement("span");
            rankEl.className = "lb__rank";
            rankEl.textContent = rank;

            var nameEl = document.createElement("span");
            nameEl.className = "lb__name";
            nameEl.textContent = player.nickname;

            var scoreEl = document.createElement("span");
            scoreEl.className = "lb__score";
            scoreEl.textContent = player.score;

            var moveEl = document.createElement("span");
            moveEl.className = "lb__move" + (moved > 0 ? " lb__move--up" : moved < 0 ? " lb__move--down" : "");
            if (moved > 0) {
                moveEl.appendChild(UI.icon("arrow-up"));
                moveEl.appendChild(document.createTextNode(String(moved)));
            } else if (moved < 0) {
                moveEl.appendChild(UI.icon("arrow-down"));
                moveEl.appendChild(document.createTextNode(String(-moved)));
            } else {
                moveEl.appendChild(UI.icon("minus"));
            }

            row.appendChild(rankEl);
            row.appendChild(nameEl);
            row.appendChild(scoreEl);
            row.appendChild(moveEl);
            list.appendChild(row);
        });

        UI.el("lb-eyebrow").textContent = rounds.length
            ? "Standings after Q" + rounds.length
            : "Standings";

        previousRanks = {};
        top.forEach(function (player, index) {
            previousRanks[player.nickname] = index + 1;
        });
    }

    /* ----------------------------------------------------------- accuracy */
    function accuracyOverFirst(n) {
        var slice = rounds.slice(0, n);
        var correct = 0;
        var answered = 0;
        slice.forEach(function (round) {
            correct += round.correct;
            answered += round.answered;
        });
        return answered ? UI.pct(correct, answered) : null;
    }

    /* ------------------------------------------------------ difficulty check */
    var DIAL_FRACTION = { easy: 0.17, medium: 0.5, hard: 0.85 };
    var DIAL_ANGLE = { easy: -60, medium: 0, hard: 60 };
    var DIAL_LENGTH = 282.7;

    function renderDifficulty(data) {
        var level = (data.difficulty || "medium").toLowerCase();
        var fraction = DIAL_FRACTION[level] === undefined ? 0.5 : DIAL_FRACTION[level];
        var angle = DIAL_ANGLE[level] === undefined ? 0 : DIAL_ANGLE[level];

        var wrapUp = currentMode() === "wrap_up";

        UI.el("difficulty-headline").textContent = wrapUp
            ? wrapUpHeadlineFor(data.previous || "medium", level)
            : headlineFor(level);
        UI.el("difficulty-reason").textContent = data.reason || "";

        /* The wrap-up quiz can check more than once, so the server sends the
           number to show and what it measures; the main game's one check is
           always over the first three questions. */
        var accuracy = wrapUp ? data.accuracy : accuracyOverFirst(3);
        UI.el("difficulty-accuracy").textContent =
            accuracy === null || accuracy === undefined ? "—" : accuracy + "%";
        UI.el("difficulty-evidence").textContent = wrapUp
            ? data.evidence || ""
            : "of the class got the first three questions right.";

        UI.el("dial-level").textContent = wrapUp ? WRAP_UP_LEVEL_NAMES[level] || level : level;
        UI.el("dial-needle").style.transform = "rotate(" + angle + "deg)";

        var scale = document.querySelectorAll(".dial__scale span");
        for (var i = 0; i < scale.length; i++) {
            scale[i].classList.toggle("is-on", scale[i].getAttribute("data-level") === level);
        }

        /* Fill the arc a frame later so it animates into place. */
        var fill = UI.el("dial-fill");
        fill.style.strokeDashoffset = DIAL_LENGTH;
        requestAnimationFrame(function () {
            fill.style.strokeDashoffset = DIAL_LENGTH * (1 - fraction);
        });
    }

    var WRAP_UP_LEVEL_NAMES = { easy: "Easy", medium: "Moderate", hard: "Difficult" };
    var LEVEL_ORDER = ["easy", "medium", "hard"];

    function wrapUpHeadlineFor(previous, level) {
        var change = LEVEL_ORDER.indexOf(level) - LEVEL_ORDER.indexOf(previous);
        if (change > 0) return "Raising the difficulty.";
        if (change < 0) return "Easing off.";
        return "Holding the difficulty steady.";
    }

    function headlineFor(level) {
        if (level === "hard") return "Raising the difficulty.";
        if (level === "easy") return "Easing off for the last two.";
        return "Holding the difficulty steady.";
    }

    /* -------------------------------------------------------------- final */
    function renderFinal(data) {
        var top = data.top || [];
        var order = [1, 0, 2]; /* second, first, third - podium reading order */

        var podium = UI.el("podium");
        UI.clear(podium);

        order.forEach(function (index) {
            var player = top[index];
            if (!player) return;
            var place = index + 1;

            var col = document.createElement("div");
            col.className = "podium__col podium__col--" + place;

            var name = document.createElement("div");
            name.className = "podium__name";
            name.textContent = player.nickname;

            var score = document.createElement("div");
            score.className = "podium__score";
            score.textContent = player.score;

            var slot = document.createElement("div");
            slot.className = "podium__slot";
            var bar = document.createElement("div");
            bar.className = "podium__bar";
            bar.appendChild(UI.icon(place === 1 ? "trophy" : "medal"));
            slot.appendChild(bar);

            col.appendChild(name);
            col.appendChild(score);
            col.appendChild(slot);
            podium.appendChild(col);
        });

        var accuracy = accuracyOverFirst(rounds.length);
        UI.el("final-accuracy").textContent = accuracy === null ? "—" : accuracy + "%";
        UI.el("final-players").textContent = playerCount;

        var announcement = UI.el("final-announcement");
        if (data.announcement) {
            UI.renderCommentary(announcement, data.announcement, Object.keys(nicknames));
        } else {
            announcement.textContent = "";
        }

        celebrate();
    }

    function celebrate() {
        var layer = UI.el("confetti");
        UI.clear(layer);
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

        var colours = ["#FF7A45", "#4C7DFF", "#2DCB91", "#FF5C87"];
        var shapes = ["0", "50%", "3px"];
        for (var i = 0; i < 44; i++) {
            var piece = document.createElement("span");
            piece.className = "confetti__piece";
            piece.style.left = Math.random() * 100 + "%";
            piece.style.background = colours[i % colours.length];
            piece.style.borderRadius = shapes[i % shapes.length];
            piece.style.animationDuration = 2.6 + Math.random() * 1.4 + "s";
            piece.style.animationDelay = Math.random() * 1.1 + "s";
            layer.appendChild(piece);
        }
        setTimeout(function () { UI.clear(layer); }, 6000);
    }

    /* ---------------------------------------------------- presenter controls */
    var startBtn = UI.el("start-btn");
    var nextBtn = UI.el("next-btn");
    var pauseBtn = UI.el("pause-btn");
    var resumeBtn = UI.el("resume-btn");
    var skipQuestionBtn = UI.el("skip-question-btn");
    var safeModeBtn = UI.el("safe-mode-btn");
    var researchBtn = UI.el("research-btn");
    var topicInput = UI.el("topic-input");
    var approveBtn = UI.el("approve-btn");
    var skipBtn = UI.el("skip-btn");

    function send(action, extra) {
        var message = { type: "host_control", action: action };
        if (extra) {
            for (var key in extra) message[key] = extra[key];
        }
        ws.send(JSON.stringify(message));
    }

    researchBtn.addEventListener("click", function () {
        var topic = topicInput.value.trim();
        if (!topic) return;
        UI.clear(feed);
        UI.show(idle, false);
        research = { searches: 0, sources: 0, drafted: 0 };
        setTopic(topic);
        send("research", { topic: topic });
    });

    topicInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") researchBtn.click();
    });

    startBtn.addEventListener("click", function () {
        send("start");
        UI.show(startBtn, false);
    });

    nextBtn.addEventListener("click", function () {
        send("next");
        UI.show(nextBtn, false);
    });

    pauseBtn.addEventListener("click", function () { send("pause"); });
    resumeBtn.addEventListener("click", function () { send("resume"); });
    skipQuestionBtn.addEventListener("click", function () { send("skip"); });
    safeModeBtn.addEventListener("click", function () { send("safe_mode"); });
    UI.el("mode-btn").addEventListener("click", function () { send("switch_mode"); });

    /* A mode switch starts a fresh game from the lobby, so clear everything
       the last game left on screen. Joined players stay in the list. */
    function resetForMode(mode) {
        frame.setAttribute("data-mode", mode);
        rounds = [];
        previousRanks = {};
        research = { searches: 0, sources: 0, drafted: 0 };
        UI.clear(feed);
        feed.appendChild(idle); /* the idle line lives inside the feed */
        UI.show(idle, true);
        topicInput.value = "";
        UI.show(UI.el("topic-pill"), false);
        UI.show(UI.el("question-pill"), false);
        UI.show(UI.el("safe-mode-pill"), false);
        showState("lobby");
        questionControls(false);
        UI.show(nextBtn, false);
        UI.show(startBtn, true);
    }

    approveBtn.addEventListener("click", function () {
        send("approval_decision", { decision: "approve" });
        approveBtn.disabled = true;
        skipBtn.disabled = true;
    });

    skipBtn.addEventListener("click", function () {
        send("approval_decision", { decision: "skip" });
        approveBtn.disabled = true;
        skipBtn.disabled = true;
    });

    /* Shortcuts, so the presenter never has to hunt for the dock mid-sentence.
       The buttons remain the primary way in - these only supplement them. */
    document.addEventListener("keydown", function (event) {
        var tag = document.activeElement && document.activeElement.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || event.metaKey || event.ctrlKey) return;

        var key = event.key.toLowerCase();
        if (key === "s" && !startBtn.classList.contains("hidden")) startBtn.click();
        else if (key === "n" && !nextBtn.classList.contains("hidden")) nextBtn.click();
        else if (key === "p") {
            if (!pauseBtn.classList.contains("hidden")) pauseBtn.click();
            else if (!resumeBtn.classList.contains("hidden")) resumeBtn.click();
        } else if (key === "k" && !skipQuestionBtn.classList.contains("hidden")) {
            skipQuestionBtn.click();
        }
    });

    function questionControls(live) {
        UI.show(pauseBtn, live);
        UI.show(resumeBtn, false);
        UI.show(skipQuestionBtn, live);
    }

    /* The page loads into the lobby; every later state arrives by message. */
    showState("lobby");

    /* ------------------------------------------------------------- messages */
    ws.onmessage = function (event) {
        var data = JSON.parse(event.data);

        if (data.type === "stage_changed") {
            if (data.stage === "researching") {
                showState("researching");
                setTopic(data.topic);
                setPhase("search");
            } else if (data.stage === "ready") {
                showState("ready");
                UI.show(startBtn, true);
                /* A successful research run clears the safe-mode flag server
                   side, so keep the badge in step with it rather than
                   leaving it on for the rest of the game. */
                if (data.safe_mode !== undefined) {
                    UI.show(UI.el("safe-mode-pill"), !!data.safe_mode);
                }
            }

        } else if (data.type === "mode_changed") {
            resetForMode(data.mode);

        } else if (data.type === "agent_event") {
            pushEvent(data);

        } else if (data.type === "player_joined") {
            addPlayerRow(data.player_id, data.nickname);
            setPlayerCount(data.player_count);

        } else if (data.type === "player_removed") {
            var li = playerList.querySelector('li[data-player-id="' + data.player_id + '"]');
            if (li) li.remove();
            setPlayerCount(data.player_count);

        } else if (data.type === "safe_mode_on") {
            showState("ready");
            UI.show(UI.el("safe-mode-pill"), true);
            UI.show(startBtn, true);

        } else if (data.type === "paused") {
            countdown.stop();
            timerEl.classList.add("is-paused");
            UI.show(pauseBtn, false);
            UI.show(resumeBtn, true);

        } else if (data.type === "resumed") {
            timerEl.classList.remove("is-paused");
            UI.show(pauseBtn, true);
            UI.show(resumeBtn, false);
            countdown.start(data.ends_at, questionSeconds);

        } else if (data.type === "question_live") {
            showState("question");
            UI.show(startBtn, false);
            renderQuestion(data);
            timerEl.classList.remove("is-paused");
            questionSeconds = data.seconds || questionSeconds;
            countdown.start(data.ends_at, questionSeconds);
            questionControls(true);
            UI.show(nextBtn, false);

        } else if (data.type === "answer_count") {
            UI.el("answered-count").textContent = data.answered;
            UI.el("answered-total").textContent = data.total;

        } else if (data.type === "reveal") {
            countdown.stop();
            showState("reveal");
            renderReveal(data);
            questionControls(false);
            UI.show(nextBtn, true);

        } else if (data.type === "commentary") {
            var box = UI.el("reveal-commentary-box");
            box.classList.toggle("is-pending", !data.commentary);
            UI.renderCommentary(
                UI.el("reveal-commentary"),
                data.commentary || "",
                Object.keys(nicknames)
            );

        } else if (data.type === "difficulty_banner") {
            showState("difficulty_check");
            renderDifficulty(data);
            UI.show(nextBtn, false);

        } else if (data.type === "leaderboard") {
            showState("leaderboard");
            renderLeaderboard(data.top || []);
            UI.show(nextBtn, true);

        } else if (data.type === "approval_request") {
            showState("approval");
            UI.el("approval-draft").textContent = data.draft || "";
            approveBtn.disabled = false;
            skipBtn.disabled = false;
            UI.show(nextBtn, false);

        } else if (data.type === "final") {
            showState("final");
            renderFinal(data);
            UI.show(nextBtn, false);
        }
    };
})();
