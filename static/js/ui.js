/* Small shared front-end helpers used by both the host screen and the player
   phone: the answer identity system, the countdown, and the translation from
   a raw agent_event into one readable activity block.

   Nothing here talks to the WebSocket - host.js and player.js own that. */

var UI = (function () {
    "use strict";

    /* Fixed per-slot identity. Index 0-3 always gets the same colour AND the
       same shape on both screens, so "the orange triangle" means one thing in
       the room. */
    var ANSWER_CLASS = ["ans-a", "ans-b", "ans-c", "ans-d"];
    var ANSWER_SHAPE = ["tri", "diamond", "circle", "square"];

    function el(id) {
        return document.getElementById(id);
    }

    function icon(name) {
        var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", "icon");
        svg.setAttribute("aria-hidden", "true");
        var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", "#i-" + name);
        svg.appendChild(use);
        return svg;
    }

    function shape(index) {
        var span = document.createElement("span");
        span.className = "shape shape--" + (ANSWER_SHAPE[index] || "square");
        return span;
    }

    function answerClass(index) {
        return ANSWER_CLASS[index] || "ans-a";
    }

    function clear(node) {
        while (node.firstChild) node.removeChild(node.firstChild);
    }

    function show(node, visible) {
        if (node) node.classList.toggle("hidden", !visible);
    }

    function pct(part, whole) {
        if (!whole) return 0;
        return Math.round((100 * part) / whole);
    }

    /* ---------------------------------------------------------------- timer
       One countdown shared by both screens. onTick gets the whole second
       remaining and the fraction of the question still left (1 -> 0), which
       is what drives the ring and the phone's progress bar. */
    function Countdown(onTick) {
        var interval = null;
        var endsAt = 0;
        var total = 20;

        function tick() {
            var msLeft = Math.max(0, endsAt - Date.now());
            var seconds = Math.ceil(msLeft / 1000);
            var fraction = total > 0 ? Math.min(1, msLeft / (total * 1000)) : 0;
            onTick(seconds, fraction);
            if (msLeft <= 0) stop();
        }

        function start(endsAtIso, totalSeconds) {
            stop();
            endsAt = new Date(endsAtIso).getTime();
            total = totalSeconds || Math.max(1, Math.round((endsAt - Date.now()) / 1000));
            tick();
            interval = setInterval(tick, 200);
        }

        function stop() {
            if (interval) clearInterval(interval);
            interval = null;
        }

        return { start: start, stop: stop };
    }

    /* ------------------------------------------------------- agent activity
       Turns one agent_event into a short observable step. The server's event
       shape is untouched; this only decides how to say it out loud. Anything
       we can't classify still shows as a plain AGENT line, and the event's
       `detail` field (which can hold an exception) is never sent here. */
    function describeEvent(event) {
        var kind = event.kind;
        var tool = event.tool;
        var moment = event.moment;
        var summary = (event.summary || "").trim();

        if (tool === "search_web" && kind === "tool_call") {
            return {
                type: "search",
                label: "Search",
                icon: "search",
                text: quote(stripPrefix(summary, "Searching:"))
            };
        }

        if (tool === "search_web" && kind === "tool_result") {
            var found = summary.match(/(\d+)/);
            var n = found ? found[1] : "0";
            return {
                type: "sources",
                label: "Sources",
                icon: "check-circle",
                text: n + (n === "1" ? " source found" : " sources found")
            };
        }

        if (kind === "output") {
            if (moment === "commentary") {
                return { type: "question", label: "Commentary", icon: "sparkle", text: summary };
            }
            if (moment === "difficulty") {
                return { type: "question", label: "Decision", icon: "gauge", text: summary };
            }
            if (moment === "wrap_up") {
                return { type: "sources", label: "Notes", icon: "notes", text: summary };
            }
            return { type: "question", label: "Questions", icon: "pen", text: summary };
        }

        if (kind === "thought") {
            return { type: "analyze", label: "Analyze", icon: "analyze", text: summary };
        }

        if (kind === "tool_call" || kind === "tool_result") {
            return { type: "analyze", label: "Tool", icon: "target", text: summary };
        }

        return { type: "waiting", label: "Agent", icon: "activity", text: summary };
    }

    function stripPrefix(text, prefix) {
        return text.indexOf(prefix) === 0 ? text.slice(prefix.length).trim() : text;
    }

    function quote(text) {
        return text ? "“" + text + "”" : text;
    }

    /* Renders one activity block and demotes whatever was newest before. */
    function appendEvent(feed, event) {
        var step = describeEvent(event);

        var previous = feed.querySelector(".event.is-latest");
        if (previous) previous.classList.remove("is-latest");

        var row = document.createElement("div");
        row.className = "event event--" + step.type + " is-latest";

        var iconWrap = document.createElement("span");
        iconWrap.className = "event__icon";
        iconWrap.appendChild(icon(step.icon));

        var label = document.createElement("span");
        label.className = "event__kind";
        label.textContent = step.label;

        var text = document.createElement("span");
        text.className = "event__text";
        text.textContent = step.text;

        row.appendChild(iconWrap);
        row.appendChild(label);
        row.appendChild(text);
        feed.appendChild(row);

        /* Keep the feed short enough that the newest block is always on
           screen without a scrollbar appearing on the projection. */
        while (feed.querySelectorAll(".event").length > 9) {
            feed.removeChild(feed.querySelector(".event"));
        }

        feed.scrollTop = feed.scrollHeight;
        return step;
    }

    /* Highlights known nicknames inside the agent's commentary so the room
       can spot who was named. Text is inserted as text nodes, never HTML. */
    function renderCommentary(node, text, nicknames) {
        clear(node);
        if (!text) return;

        var names = (nicknames || [])
            .filter(function (n) { return n && n.length > 1; })
            .sort(function (a, b) { return b.length - a.length; });

        var remaining = text;
        var guard = 0;
        while (remaining && guard++ < 200) {
            var best = null;
            for (var i = 0; i < names.length; i++) {
                var at = remaining.toLowerCase().indexOf(names[i].toLowerCase());
                if (at !== -1 && (best === null || at < best.at)) {
                    best = { at: at, name: names[i] };
                }
            }
            if (!best) break;

            if (best.at > 0) node.appendChild(document.createTextNode(remaining.slice(0, best.at)));
            var mark = document.createElement("mark");
            mark.textContent = remaining.substr(best.at, best.name.length);
            node.appendChild(mark);
            remaining = remaining.slice(best.at + best.name.length);
        }
        if (remaining) node.appendChild(document.createTextNode(remaining));
    }

    return {
        el: el,
        icon: icon,
        shape: shape,
        answerClass: answerClass,
        clear: clear,
        show: show,
        pct: pct,
        Countdown: Countdown,
        describeEvent: describeEvent,
        appendEvent: appendEvent,
        renderCommentary: renderCommentary
    };
})();
