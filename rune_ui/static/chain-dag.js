/* SPDX-License-Identifier: Apache-2.0
 *
 * chain-dag.js — vanilla JS SVG DAG renderer for /chains/{run_id} (Issue #99).
 *
 * Zero-NPM: no bundler, no framework. Exposes a few functions on
 * `window.RUNE_CHAIN_DAG` so they can be exercised by tests or the DevTools
 * console. The page template boots the renderer via DOMContentLoaded.
 */
(function () {
    "use strict";

    var SVG_NS = "http://www.w3.org/2000/svg";
    var POLL_INTERVAL_MS = 2000;

    // Layout constants. Pure numbers so the layout is deterministic and
    // testable without a browser.
    var NODE_WIDTH = 160;
    var NODE_HEIGHT = 60;
    var LEVEL_GAP_X = 220;
    var NODE_GAP_Y = 90;
    var MARGIN_X = 40;
    var MARGIN_Y = 40;

    var state = {
        current: null,
        pollTimer: null,
        polling: true,
        selectedNodeId: null,
    };

    /**
     * Compute topological levels for nodes given edges.
     * Returns a Map<string, number> from node id to level index.
     * Nodes that are part of a cycle (shouldn't happen for a DAG) fall
     * back to level 0 so the renderer stays resilient.
     */
    function computeLevels(nodes, edges) {
        var levels = new Map();
        var incoming = new Map();
        var outgoing = new Map();
        nodes.forEach(function (n) {
            incoming.set(n.id, 0);
            outgoing.set(n.id, []);
        });
        edges.forEach(function (e) {
            if (!incoming.has(e.to) || !outgoing.has(e.from)) { return; }
            incoming.set(e.to, incoming.get(e.to) + 1);
            outgoing.get(e.from).push(e.to);
        });

        // Kahn-style BFS by level.
        var frontier = [];
        nodes.forEach(function (n) {
            if (incoming.get(n.id) === 0) {
                frontier.push(n.id);
                levels.set(n.id, 0);
            }
        });

        var head = 0;
        while (head < frontier.length) {
            var nid = frontier[head++];
            var lvl = levels.get(nid);
            var outs = outgoing.get(nid) || [];
            for (var i = 0; i < outs.length; i++) {
                var next = outs[i];
                var nextLvl = (levels.has(next) ? Math.max(levels.get(next), lvl + 1) : lvl + 1);
                levels.set(next, nextLvl);
                incoming.set(next, incoming.get(next) - 1);
                if (incoming.get(next) === 0) {
                    frontier.push(next);
                }
            }
        }

        // Any node we missed (cycle or unreachable) → level 0.
        nodes.forEach(function (n) {
            if (!levels.has(n.id)) { levels.set(n.id, 0); }
        });
        return levels;
    }

    /**
     * Compute x/y pixel positions for every node given topological levels.
     * Returns a Map<string, {x, y}>. Exposed for testing.
     */
    function computePositions(nodes, edges) {
        var levels = computeLevels(nodes, edges);
        // Group node ids by level.
        var byLevel = new Map();
        nodes.forEach(function (n) {
            var lvl = levels.get(n.id);
            if (!byLevel.has(lvl)) { byLevel.set(lvl, []); }
            byLevel.get(lvl).push(n.id);
        });

        var positions = new Map();
        byLevel.forEach(function (ids, lvl) {
            ids.forEach(function (id, idx) {
                var x = MARGIN_X + lvl * LEVEL_GAP_X;
                var y = MARGIN_Y + idx * NODE_GAP_Y;
                positions.set(id, { x: x, y: y });
            });
        });
        return positions;
    }

    function svgEl(tag, attrs) {
        var el = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                el.setAttribute(k, String(attrs[k]));
            });
        }
        return el;
    }

    function clearChildren(node) {
        while (node && node.firstChild) {
            node.removeChild(node.firstChild);
        }
    }

    function truncate(str, max) {
        if (!str) { return ""; }
        if (str.length <= max) { return str; }
        return str.slice(0, Math.max(0, max - 1)) + "\u2026";
    }

    /**
     * Render (or re-render) the DAG for the given state document.
     * `svgRoot` is the <svg> element; `state` is `{nodes, edges, overall_status}`.
     */
    function renderChainDAG(svgRoot, chainState) {
        if (!svgRoot || !chainState) { return; }
        var nodes = Array.isArray(chainState.nodes) ? chainState.nodes : [];
        var edges = Array.isArray(chainState.edges) ? chainState.edges : [];

        var nodesLayer = svgRoot.querySelector("#chain-nodes");
        var edgesLayer = svgRoot.querySelector("#chain-edges");
        if (!nodesLayer || !edgesLayer) { return; }

        clearChildren(nodesLayer);
        clearChildren(edgesLayer);

        var positions = computePositions(nodes, edges);
        var nodeById = new Map();
        nodes.forEach(function (n) { nodeById.set(n.id, n); });

        // Resize viewBox to fit all placed nodes.
        var maxX = 0;
        var maxY = 0;
        positions.forEach(function (p) {
            if (p.x + NODE_WIDTH > maxX) { maxX = p.x + NODE_WIDTH; }
            if (p.y + NODE_HEIGHT > maxY) { maxY = p.y + NODE_HEIGHT; }
        });
        var vbW = Math.max(960, maxX + MARGIN_X);
        var vbH = Math.max(320, maxY + MARGIN_Y);
        svgRoot.setAttribute("viewBox", "0 0 " + vbW + " " + vbH);

        // Draw edges first so they render beneath nodes.
        edges.forEach(function (e) {
            var a = positions.get(e.from);
            var b = positions.get(e.to);
            if (!a || !b) { return; }
            var x1 = a.x + NODE_WIDTH;
            var y1 = a.y + NODE_HEIGHT / 2;
            var x2 = b.x;
            var y2 = b.y + NODE_HEIGHT / 2;
            var midX = (x1 + x2) / 2;
            var d = "M" + x1 + "," + y1 +
                    " C" + midX + "," + y1 + " " + midX + "," + y2 + " " + x2 + "," + y2;
            var path = svgEl("path", { "class": "chain-edge", "d": d });
            path.setAttribute("data-from", e.from);
            path.setAttribute("data-to", e.to);
            edgesLayer.appendChild(path);
        });

        // Draw nodes.
        nodes.forEach(function (n) {
            var p = positions.get(n.id);
            if (!p) { return; }
            var g = svgEl("g", {
                "class": "chain-node" + (n.id === state.selectedNodeId ? " selected" : ""),
                "data-node-id": n.id,
                "data-status": n.status || "pending",
                "transform": "translate(" + p.x + "," + p.y + ")",
                "role": "button",
                "tabindex": "0",
            });
            var rect = svgEl("rect", {
                "class": "chain-node-rect",
                "width": NODE_WIDTH,
                "height": NODE_HEIGHT,
                "rx": 6,
                "ry": 6,
            });
            var label = svgEl("text", {
                "class": "chain-node-label",
                "x": 12,
                "y": 24,
            });
            label.textContent = truncate(n.agent_name || n.id, 22);
            var sub = svgEl("text", {
                "class": "chain-node-sub",
                "x": 12,
                "y": 44,
            });
            sub.textContent = (n.status || "pending").toUpperCase();
            g.appendChild(rect);
            g.appendChild(label);
            g.appendChild(sub);

            g.addEventListener("click", function () {
                selectNode(n.id);
            });
            g.addEventListener("keydown", function (ev) {
                if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    selectNode(n.id);
                }
            });
            nodesLayer.appendChild(g);
        });

        updateOverallStatusBadge(chainState.overall_status);
        // Re-populate panel if a node is selected and still present.
        if (state.selectedNodeId && nodeById.has(state.selectedNodeId)) {
            populateSidePanel(nodeById.get(state.selectedNodeId));
        }
    }

    function updateOverallStatusBadge(status) {
        var badge = document.getElementById("chain-overall-status");
        if (!badge) { return; }
        var safe = (status || "pending").toLowerCase();
        badge.className = "status-badge status-" + safe;
        badge.textContent = safe.toUpperCase();
    }

    function formatTimestamp(ts) {
        if (ts === null || ts === undefined || ts === "") { return "—"; }
        var n = Number(ts);
        if (!isFinite(n)) { return String(ts); }
        try {
            var d = new Date(n * 1000);
            return d.toISOString();
        } catch (e) {
            return String(ts);
        }
    }

    function populateSidePanel(node) {
        if (!node) { return; }
        var panel = document.getElementById("chain-node-details");
        if (!panel) { return; }
        panel.hidden = false;
        var setText = function (id, val) {
            var el = document.getElementById(id);
            if (el) { el.textContent = val; }
        };
        setText("panel-node-id", node.id || "—");
        setText("panel-node-agent", node.agent_name || "—");
        setText("panel-node-status", (node.status || "pending").toUpperCase());
        setText("panel-node-started", formatTimestamp(node.started_at));
        setText("panel-node-finished", formatTimestamp(node.finished_at));
        setText("panel-node-error", node.error ? String(node.error) : "—");
        var closeBtn = document.getElementById("chain-panel-close");
        if (closeBtn) { closeBtn.hidden = false; }
    }

    function selectNode(nodeId) {
        state.selectedNodeId = nodeId;
        // Update selection style.
        var svgRoot = document.getElementById("chain-dag-svg");
        if (svgRoot) {
            var groups = svgRoot.querySelectorAll(".chain-node");
            for (var i = 0; i < groups.length; i++) {
                if (groups[i].getAttribute("data-node-id") === nodeId) {
                    groups[i].classList.add("selected");
                } else {
                    groups[i].classList.remove("selected");
                }
            }
        }
        if (state.current && Array.isArray(state.current.nodes)) {
            var match = state.current.nodes.find(function (n) { return n.id === nodeId; });
            if (match) { populateSidePanel(match); }
        }
    }

    function clearSelection() {
        state.selectedNodeId = null;
        var svgRoot = document.getElementById("chain-dag-svg");
        if (svgRoot) {
            var groups = svgRoot.querySelectorAll(".chain-node.selected");
            for (var i = 0; i < groups.length; i++) {
                groups[i].classList.remove("selected");
            }
        }
        var panel = document.getElementById("chain-node-details");
        if (panel) { panel.hidden = true; }
        var closeBtn = document.getElementById("chain-panel-close");
        if (closeBtn) { closeBtn.hidden = true; }
    }

    function showError(msg) {
        var el = document.getElementById("chain-error");
        if (!el) { return; }
        el.style.display = "block";
        el.textContent = msg;
    }

    function clearError() {
        var el = document.getElementById("chain-error");
        if (!el) { return; }
        el.style.display = "none";
        el.textContent = "";
    }

    async function fetchChainState() {
        var url = window.RUNE_CHAIN_STATE_URL;
        if (!url) { return null; }
        var resp = await fetch(url, { headers: { "Accept": "application/json" } });
        if (!resp.ok) {
            throw new Error("Fetch failed: HTTP " + resp.status);
        }
        return await resp.json();
    }

    async function refreshOnce() {
        try {
            var data = await fetchChainState();
            state.current = data;
            clearError();
            var svgRoot = document.getElementById("chain-dag-svg");
            renderChainDAG(svgRoot, data);
            return data;
        } catch (err) {
            showError("Failed to refresh chain state: " + err.message);
            return null;
        }
    }

    function schedulePoll() {
        if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }
        if (!state.polling) { return; }
        state.pollTimer = setTimeout(async function () {
            var data = await refreshOnce();
            if (data && data.overall_status === "running") {
                schedulePoll();
            }
        }, POLL_INTERVAL_MS);
    }

    function togglePoll() {
        state.polling = !state.polling;
        var btn = document.getElementById("chain-poll-toggle");
        if (btn) { btn.textContent = state.polling ? "Pause" : "Resume"; }
        if (state.polling && state.current && state.current.overall_status === "running") {
            schedulePoll();
        } else if (state.pollTimer) {
            clearTimeout(state.pollTimer);
            state.pollTimer = null;
        }
    }

    function boot() {
        var svgRoot = document.getElementById("chain-dag-svg");
        var initialScript = document.getElementById("chain-initial-state");
        var initial = null;
        if (initialScript && initialScript.textContent) {
            try {
                initial = JSON.parse(initialScript.textContent);
            } catch (e) {
                initial = null;
            }
        }
        if (initial) {
            state.current = initial;
            renderChainDAG(svgRoot, initial);
            if (initial.overall_status === "running") {
                schedulePoll();
            }
        } else {
            // No SSR state (error path) — still try a client-side fetch.
            refreshOnce().then(function (data) {
                if (data && data.overall_status === "running") {
                    schedulePoll();
                }
            });
        }

        var refreshBtn = document.getElementById("chain-refresh-btn");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", function () { refreshOnce(); });
        }
        var pollBtn = document.getElementById("chain-poll-toggle");
        if (pollBtn) {
            pollBtn.addEventListener("click", togglePoll);
        }
        var closeBtn = document.getElementById("chain-panel-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", clearSelection);
        }
    }

    // Expose helpers for tests / DevTools.
    window.RUNE_CHAIN_DAG = {
        renderChainDAG: renderChainDAG,
        computeLevels: computeLevels,
        computePositions: computePositions,
        selectNode: selectNode,
        clearSelection: clearSelection,
        refreshOnce: refreshOnce,
        togglePoll: togglePoll,
        _state: state,
    };

    if (typeof document !== "undefined") {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", boot);
        } else {
            boot();
        }
    }
})();
