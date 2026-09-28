/* Player (phone) controller.

   Same WebSocket contract as before: join / submit_answer out, joined,
   join_error, removed, paused, resumed, question_live, round_result and final
   in. The device_token rejoin path is unchanged. Everything else here is the
   phone-first presentation. */

(function () {
    "use strict";

    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    var ws = new WebSocket(proto + "//" + window.location.host + "/ws/player");

    var screens = {
        join: UI.el("screen-join"),
        waiting: UI.el("screen-waiting"),
        question: UI.el("screen-question"),
        result: UI.el("screen-result"),
        final: UI.el("screen-final")
    };

    function setMode(mode) {
        if (mode) document.body.setAttribute("data-mode", mode);
    }

    function showScreen(name) {
        for (var key in screens) {
            screens[key].classList.toggle("is-active", key === name);
        }
        UI.show(UI.el("slot-tag"), name === "question");
    }

    var nicknameInput = UI.el("nickname");
    var joinBtn = UI.el("join-btn");
    var message = UI.el("message");
    var questionScreen = screens.question;

    var currentQuestionId = null;
    var questionSeconds = 20;
    var autoReconnecting = false;

    function storedDeviceToken() {
        try {
            return localStorage.getItem("device_token");
        } catch (e) {
            return null;
        }
    }

    function forgetDeviceToken() {
        try {
            localStorage.removeItem("device_token");
        } catch (e) {
            /* Ignore: private browsing or blocked storage. */
        }
    }

    function showMessage(text) {
        UI.clear(message);
        if (!text) {
            message.classList.remove("is-shown");
            return;
        }
        message.appendChild(UI.icon("x-circle"));
        message.appendChild(document.createTextNode(text));
        message.classList.add("is-shown");
    }

    joinBtn.addEventListener("click", function () {
        var nickname = nicknameInput.value.trim();
        if (!nickname) {
            nicknameInput.focus();
            return;
        }
        showMessage("");
        joinBtn.disabled = true;
        ws.send(JSON.stringify({
            type: "join",
            nickname: nickname,
            device_token: storedDeviceToken()
        }));
    });

    nicknameInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") joinBtn.click();
    });

    ws.addEventListener("open", function () {
        var token = storedDeviceToken();
        if (token) {
            /* Silently rejoin as the same player (Phase 6 reconnect). */
            autoReconnecting = true;
            ws.send(JSON.stringify({ type: "join", nickname: "", device_token: token }));
        }
    });

    ws.addEventListener("close", function () {
        UI.el("offline").classList.add("is-shown");
    });

    /* ---------------------------------------------------------------- timer */
    var bar = UI.el("pq-bar");
    var secs = UI.el("timer");

    var countdown = UI.Countdown(function (seconds, fraction) {
        secs.textContent = seconds;
        bar.style.width = fraction * 100 + "%";
        questionScreen.classList.toggle("is-urgent", seconds <= 5);
    });

    /* ------------------------------------------------------------- question */
    function renderQuestion(data) {
        currentQuestionId = data.question_id;

        UI.el("slot-num").textContent = data.slot;
        UI.el("slot-total").textContent = data.total_questions;
        UI.el("q-text").textContent = data.text;

        questionScreen.classList.remove("is-locked");

        var options = UI.el("q-options");
        UI.clear(options);

        data.options.forEach(function (option, index) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "answer " + UI.answerClass(index);
            button.appendChild(UI.shape(index));

            var text = document.createElement("span");
            text.className = "answer__text";
            text.textContent = option;
            button.appendChild(text);

            button.addEventListener("click", function () {
                if (questionScreen.classList.contains("is-locked")) return;
                ws.send(JSON.stringify({
                    type: "submit_answer",
                    question_id: currentQuestionId,
                    chosen_index: index
                }));
                /* Lock in place rather than swapping screens, so the student
                   can still see which one they picked. */
                button.classList.add("is-chosen");
                questionScreen.classList.add("is-locked");
            });

            options.appendChild(button);
        });

        showScreen("question");
    }

    /* --------------------------------------------------------------- result */
    function renderResult(data) {
        var verdict = UI.el("verdict");
        var mark = UI.el("verdict-mark");

        verdict.classList.toggle("verdict--correct", !!data.correct);
        verdict.classList.toggle("verdict--wrong", !data.correct);

        UI.clear(mark);
        mark.appendChild(UI.icon(data.correct ? "check" : "x"));

        UI.el("verdict-word").textContent = data.correct ? "Correct" : "Not this time";
        UI.el("verdict-points").textContent = data.correct ? "+" + data.points : "+0";
        UI.el("verdict-sub").textContent = "points this round";

        UI.el("result-rank").textContent = "#" + data.rank;
        UI.el("result-score").textContent = data.score;

        showScreen("result");
    }

    /* ---------------------------------------------------------------- final */
    function renderFinal(data) {
        UI.el("final-rank").textContent = "#" + data.rank;
        UI.el("final-score").textContent = data.score + " points";

        var notes = data.notes || [];
        var container = UI.el("final-notes");
        UI.clear(container);

        UI.el("final-notes-lead").textContent = notes.length
            ? "Worth a second look:"
            : "";

        if (!notes.length) {
            var clean = document.createElement("p");
            clean.className = "notes__empty";
            clean.appendChild(UI.icon("check-circle"));
            clean.appendChild(document.createTextNode("You got every question right. Nothing to revise."));
            container.appendChild(clean);
        } else {
            notes.forEach(function (note, index) {
                var card = document.createElement("div");
                card.className = "note";

                var number = document.createElement("span");
                number.className = "note__n";
                number.textContent = String(index + 1).padStart(2, "0");

                var text = document.createElement("span");
                text.textContent = note;

                card.appendChild(number);
                card.appendChild(text);
                container.appendChild(card);
            });
        }

        showScreen("final");
    }

    /* ------------------------------------------------------------- messages */
    ws.onmessage = function (event) {
        var data = JSON.parse(event.data);

        if (data.type === "joined") {
            try {
                localStorage.setItem("device_token", data.device_token);
            } catch (e) {
                /* Ignore: private browsing or blocked storage. */
            }
            autoReconnecting = false;
            joinBtn.disabled = false;

            setMode(data.mode);
            UI.el("me-name").textContent = data.nickname;
            UI.show(UI.el("me-tag"), true);

            UI.el("waiting-title").textContent = data.reconnected
                ? "You’re back in."
                : "You’re in, " + data.nickname + ".";
            UI.el("waiting-text").textContent = data.reconnected
                ? "Score so far: " + data.score + " points."
                : "Questions land here too, but the game is on the big screen.";

            showScreen("waiting");

        } else if (data.type === "join_error") {
            joinBtn.disabled = false;
            if (data.forget_token) forgetDeviceToken();
            /* Don't show a scary error for the silent auto-reconnect attempt;
               just fall back to the normal join form. */
            if (!autoReconnecting) showMessage(data.message);
            autoReconnecting = false;

        } else if (data.type === "removed") {
            countdown.stop();
            forgetDeviceToken();
            showScreen("join");
            UI.show(UI.el("me-tag"), false);
            showMessage("You were removed from the game by the presenter.");

        } else if (data.type === "paused") {
            countdown.stop();

        } else if (data.type === "resumed") {
            countdown.start(data.ends_at, questionSeconds);

        } else if (data.type === "mode_changed") {
            /* The presenter switched between the main game and the wrap-up
               quiz: a fresh game is about to start, so leave the old result. */
            setMode(data.mode);
            if (!screens.join.classList.contains("is-active")) {
                countdown.stop();
                UI.el("waiting-title").textContent =
                    data.mode === "wrap_up" ? "Next up: the wrap-up quiz." : "Next up: a new game.";
                UI.el("waiting-text").textContent = "Scores are back to zero. Watch the big screen.";
                showScreen("waiting");
            }

        } else if (data.type === "question_live") {
            setMode(data.mode);
            renderQuestion(data);
            questionSeconds = data.seconds || questionSeconds;
            countdown.start(data.ends_at, questionSeconds);

        } else if (data.type === "round_result") {
            countdown.stop();
            renderResult(data);

        } else if (data.type === "final") {
            countdown.stop();
            renderFinal(data);
        }
    };
})();
