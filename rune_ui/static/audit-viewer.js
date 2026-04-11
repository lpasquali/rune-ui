// SPDX-License-Identifier: Apache-2.0
// Audit viewer — fetches compliance artifacts for a run and renders cards.
// Zero NPM; vanilla JS only. Targets rune-ui Solarized theme.
(function () {
    "use strict";

    var KIND_LABELS = {
        slsa_provenance: "SLSA",
        sbom: "SBOM",
        tla_report: "TLA+",
        sigstore_bundle: "SIGSTORE",
        rekor_entry: "REKOR",
        tpm_attestation: "TPM",
    };

    var INLINE_KINDS = ["slsa_provenance", "sbom", "tla_report"];

    function humanSize(bytes) {
        if (typeof bytes !== "number" || !isFinite(bytes) || bytes < 0) {
            return "unknown";
        }
        if (bytes < 1024) {
            return bytes + " B";
        }
        var units = ["KB", "MB", "GB", "TB"];
        var value = bytes / 1024;
        var idx = 0;
        while (value >= 1024 && idx < units.length - 1) {
            value /= 1024;
            idx += 1;
        }
        return value.toFixed(value >= 10 ? 0 : 1) + " " + units[idx];
    }

    function shortSha(sha) {
        if (typeof sha !== "string" || sha.length < 12) {
            return sha || "";
        }
        return sha.slice(0, 12) + "\u2026";
    }

    function formatTimestamp(ts) {
        if (typeof ts !== "number" || !isFinite(ts)) {
            return "unknown";
        }
        // API returns seconds-since-epoch as float.
        var d = new Date(ts * 1000);
        if (isNaN(d.getTime())) {
            return "unknown";
        }
        return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
    }

    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                if (k === "class") {
                    node.className = attrs[k];
                } else if (k === "text") {
                    node.textContent = attrs[k];
                } else if (k === "html") {
                    node.innerHTML = attrs[k];
                } else {
                    node.setAttribute(k, attrs[k]);
                }
            });
        }
        if (children) {
            children.forEach(function (c) {
                if (c) {
                    node.appendChild(c);
                }
            });
        }
        return node;
    }

    // ── JSON viewer (collapsible sections) ──────────────────────────────────
    function renderJsonValue(value) {
        if (value === null) {
            return el("span", { class: "audit-json-null", text: "null" });
        }
        var t = typeof value;
        if (t === "string") {
            return el("span", { class: "audit-json-string", text: JSON.stringify(value) });
        }
        if (t === "number") {
            return el("span", { class: "audit-json-number", text: String(value) });
        }
        if (t === "boolean") {
            return el("span", { class: "audit-json-boolean", text: String(value) });
        }
        if (Array.isArray(value)) {
            if (value.length === 0) {
                return el("span", { text: "[]" });
            }
            var arrBody = el("div", { class: "audit-json-body" });
            value.forEach(function (item, idx) {
                var row = el("div", null, [renderJsonValue(item)]);
                if (idx < value.length - 1) {
                    row.appendChild(document.createTextNode(","));
                }
                arrBody.appendChild(row);
            });
            var arrSection = el("div", { class: "audit-json-section" }, [
                el("span", { class: "audit-json-key", text: "[" + value.length + " items]" }),
                arrBody,
            ]);
            attachToggle(arrSection);
            return arrSection;
        }
        if (t === "object") {
            var keys = Object.keys(value);
            if (keys.length === 0) {
                return el("span", { text: "{}" });
            }
            var objBody = el("div", { class: "audit-json-body" });
            keys.forEach(function (k) {
                var row = el("div", null, [
                    el("strong", { class: "audit-json-string", text: JSON.stringify(k) + ": " }),
                    renderJsonValue(value[k]),
                ]);
                objBody.appendChild(row);
            });
            var objSection = el("div", { class: "audit-json-section" }, [
                el("span", { class: "audit-json-key", text: "{" + keys.length + " keys}" }),
                objBody,
            ]);
            attachToggle(objSection);
            return objSection;
        }
        return el("span", { text: String(value) });
    }

    function attachToggle(section) {
        var key = section.querySelector(":scope > .audit-json-key");
        if (!key) {
            return;
        }
        key.addEventListener("click", function () {
            section.classList.toggle("collapsed");
        });
    }

    function renderSlsaPreview(container, jsonText) {
        var parsed;
        try {
            parsed = JSON.parse(jsonText);
        } catch (err) {
            container.appendChild(el("p", { class: "audit-tla-fail", text: "Invalid JSON: " + err.message }));
            return;
        }
        var wrapper = el("div", { class: "audit-json" });
        wrapper.appendChild(renderJsonValue(parsed));
        container.appendChild(wrapper);
    }

    function renderSbomPreview(container, jsonText) {
        var parsed;
        try {
            parsed = JSON.parse(jsonText);
        } catch (err) {
            container.appendChild(el("p", { class: "audit-tla-fail", text: "Invalid SBOM JSON: " + err.message }));
            return;
        }
        var components = [];
        if (parsed && Array.isArray(parsed.components)) {
            components = parsed.components;
        } else if (parsed && Array.isArray(parsed.packages)) {
            components = parsed.packages;
        } else if (Array.isArray(parsed)) {
            components = parsed;
        }
        var count = components.length;
        container.appendChild(el("p", null, [
            document.createTextNode("Components: "),
            el("span", { class: "audit-sbom-count", text: String(count) }),
        ]));
        if (count === 0) {
            return;
        }
        var top = components.slice(0, 10);
        var list = el("ul", { class: "audit-sbom-list" });
        top.forEach(function (c) {
            var name = (c && (c.name || c.packageName || c.purl)) || "(unnamed)";
            var version = (c && (c.version || c.versionInfo)) || "";
            list.appendChild(el("li", { text: version ? name + " @ " + version : name }));
        });
        container.appendChild(list);
    }

    function renderTlaPreview(container, jsonText) {
        var parsed;
        try {
            parsed = JSON.parse(jsonText);
        } catch (err) {
            container.appendChild(el("p", { class: "audit-tla-fail", text: "Invalid TLA+ report: " + err.message }));
            return;
        }
        var pass = false;
        if (parsed && typeof parsed.passed === "boolean") {
            pass = parsed.passed;
        } else if (parsed && parsed.status === "pass") {
            pass = true;
        } else if (parsed && parsed.result === "ok") {
            pass = true;
        }
        var cls = pass ? "audit-tla-pass" : "audit-tla-fail";
        var label = pass ? "PASS" : "FAIL";
        container.appendChild(el("p", null, [
            document.createTextNode("Verification: "),
            el("span", { class: cls, text: label }),
        ]));
        var props = (parsed && parsed.properties) || (parsed && parsed.invariants) || null;
        if (props && typeof props === "object") {
            var keys = Object.keys(props);
            if (keys.length > 0) {
                var list = el("ul", { class: "audit-sbom-list" });
                keys.forEach(function (k) {
                    var v = props[k];
                    var ok = v === true || v === "pass" || (v && v.passed === true);
                    list.appendChild(el("li", null, [
                        document.createTextNode(k + ": "),
                        el("span", { class: ok ? "audit-tla-pass" : "audit-tla-fail", text: ok ? "PASS" : "FAIL" }),
                    ]));
                });
                container.appendChild(list);
            }
        }
    }

    // ── Card construction ───────────────────────────────────────────────────
    function buildCard(artifact, apiBase) {
        var tpl = document.getElementById("audit-card-template");
        var node = tpl.content.firstElementChild.cloneNode(true);
        node.setAttribute("data-kind", artifact.kind || "unknown");

        var badge = node.querySelector('[data-field="kind-badge"]');
        badge.textContent = KIND_LABELS[artifact.kind] || (artifact.kind || "UNKNOWN").toUpperCase();
        badge.setAttribute("data-kind", artifact.kind || "unknown");

        node.querySelector('[data-field="name"]').textContent = artifact.name || "(unnamed)";
        node.querySelector('[data-field="size"]').textContent = humanSize(artifact.size_bytes);
        node.querySelector('[data-field="sha-short"]').textContent = shortSha(artifact.sha256);
        node.querySelector('[data-field="sha-full"]').textContent = artifact.sha256 || "";
        node.querySelector('[data-field="created"]').textContent = formatTimestamp(artifact.created_at);

        var downloadUrl = artifact.download_url || "";
        if (downloadUrl && apiBase && /^\//.test(downloadUrl)) {
            downloadUrl = apiBase.replace(/\/$/, "") + downloadUrl;
        }
        var dl = node.querySelector('[data-field="download"]');
        dl.setAttribute("href", downloadUrl);
        dl.setAttribute("download", artifact.name || "artifact");

        var copyBtn = node.querySelector('[data-action="copy-sha"]');
        copyBtn.addEventListener("click", function () {
            var sha = artifact.sha256 || "";
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(sha).then(function () {
                    copyBtn.classList.add("copied");
                    copyBtn.textContent = "Copied!";
                    setTimeout(function () {
                        copyBtn.classList.remove("copied");
                        copyBtn.textContent = "Copy";
                    }, 1500);
                }).catch(function () {
                    copyBtn.textContent = "Failed";
                });
            } else {
                copyBtn.textContent = "N/A";
            }
        });

        var previewContainer = node.querySelector('[data-field="preview"]');
        if (INLINE_KINDS.indexOf(artifact.kind) !== -1) {
            previewContainer.hidden = false;
            var toggle = el("button", { type: "button", class: "audit-preview-toggle", text: "Load preview" });
            previewContainer.appendChild(toggle);
            var body = el("div", { class: "audit-preview-body" });
            previewContainer.appendChild(body);
            var loaded = false;
            toggle.addEventListener("click", function () {
                if (loaded) {
                    body.hidden = !body.hidden;
                    toggle.textContent = body.hidden ? "Show preview" : "Hide preview";
                    return;
                }
                toggle.textContent = "Loading\u2026";
                toggle.disabled = true;
                fetch(downloadUrl, { headers: { Accept: "application/json" } })
                    .then(function (r) {
                        if (!r.ok) {
                            throw new Error("HTTP " + r.status);
                        }
                        return r.text();
                    })
                    .then(function (txt) {
                        loaded = true;
                        toggle.disabled = false;
                        toggle.textContent = "Hide preview";
                        if (artifact.kind === "slsa_provenance") {
                            renderSlsaPreview(body, txt);
                        } else if (artifact.kind === "sbom") {
                            renderSbomPreview(body, txt);
                        } else if (artifact.kind === "tla_report") {
                            renderTlaPreview(body, txt);
                        }
                    })
                    .catch(function (err) {
                        toggle.disabled = false;
                        toggle.textContent = "Retry preview";
                        body.appendChild(el("p", { class: "audit-tla-fail", text: "Preview failed: " + err.message }));
                    });
            });
        }

        return node;
    }

    function groupByKind(artifacts) {
        var groups = {};
        artifacts.forEach(function (a) {
            var k = a.kind || "unknown";
            if (!groups[k]) {
                groups[k] = [];
            }
            groups[k].push(a);
        });
        return groups;
    }

    function renderSummary(summaryEl, summary) {
        summaryEl.innerHTML = "";
        if (!summary) {
            return;
        }
        summaryEl.hidden = false;
        var total = el("span", { class: "audit-summary-item" }, [
            document.createTextNode("Total artifacts: "),
            el("strong", { text: String(summary.total_count || 0) }),
        ]);
        summaryEl.appendChild(total);
        var kinds = summary.kinds_present || [];
        kinds.forEach(function (k) {
            var badge = el("span", { class: "audit-kind-badge" });
            badge.setAttribute("data-kind", k);
            badge.textContent = KIND_LABELS[k] || k.toUpperCase();
            summaryEl.appendChild(badge);
        });
    }

    function renderCards(cardsEl, artifacts, apiBase) {
        cardsEl.innerHTML = "";
        var grouped = groupByKind(artifacts);
        // Stable order: use documented kinds first, then anything else alphabetically.
        var ordered = [];
        ["slsa_provenance", "sbom", "tla_report", "sigstore_bundle", "rekor_entry", "tpm_attestation"].forEach(function (k) {
            if (grouped[k]) {
                ordered.push(k);
                delete grouped[k];
            }
        });
        Object.keys(grouped).sort().forEach(function (k) { ordered.push(k); });
        ordered.forEach(function (k) {
            var list = grouped[k] || [];
            if (!list.length) {
                // When kind came from the documented list we already deleted from grouped.
                // We re-fetch from original by iterating all artifacts matching kind.
                list = artifacts.filter(function (a) { return (a.kind || "unknown") === k; });
            }
            list.forEach(function (a) {
                cardsEl.appendChild(buildCard(a, apiBase));
            });
        });
    }

    function showStatus(statusEl, text, cls) {
        statusEl.textContent = text;
        statusEl.className = "audit-status" + (cls ? " " + cls : "");
        statusEl.hidden = false;
    }

    function init() {
        var shell = document.getElementById("audit-shell");
        if (!shell) {
            return;
        }
        var runId = shell.getAttribute("data-run-id");
        var apiBase = shell.getAttribute("data-api-url") || "";
        var statusEl = document.getElementById("audit-status");
        var summaryEl = document.getElementById("audit-summary");
        var cardsEl = document.getElementById("audit-cards");

        var runPath = String(runId || "").split("/").map(encodeURIComponent).join("/");
        var url = (apiBase ? apiBase.replace(/\/$/, "") : "") + "/v1/audits/" + runPath + "/artifacts";

        fetch(url, { headers: { Accept: "application/json" } })
            .then(function (r) {
                if (r.status === 404) {
                    throw new Error("Run not found");
                }
                if (!r.ok) {
                    throw new Error("HTTP " + r.status);
                }
                return r.json();
            })
            .then(function (data) {
                var artifacts = (data && data.artifacts) || [];
                if (!artifacts.length) {
                    showStatus(statusEl, "No audit artifacts collected for this run yet.", "audit-empty");
                    return;
                }
                statusEl.hidden = true;
                renderSummary(summaryEl, data.summary);
                renderCards(cardsEl, artifacts, apiBase);
            })
            .catch(function (err) {
                showStatus(statusEl, "Failed to load audit artifacts: " + err.message, "audit-error");
            });
    }

    // Expose internals for testability (accessible under window.__auditViewer).
    window.__auditViewer = {
        humanSize: humanSize,
        shortSha: shortSha,
        formatTimestamp: formatTimestamp,
        groupByKind: groupByKind,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
