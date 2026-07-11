/*
 * Greek Assonance & Consonance Detector — app.js
 * Mirrors the anaphora-detector Pyodide pattern:
 *   1. Load Pyodide + detector.py into the browser
 *   2. Write /input.txt and /options.json into Pyodide FS
 *   3. Call detector.process() → read back HTML + CSV
 *   4. Render results + enable downloads
 */

"use strict";

// ── DOM refs ────────────────────────────────────────────────────────────────
const fileInput          = document.getElementById("fileInput");
const pasteArea          = document.getElementById("pasteArea");
const runBtn             = document.getElementById("runBtn");
const statusEl           = document.getElementById("status");
const outputEl           = document.getElementById("output");

const dlHtmlBtn          = document.getElementById("downloadHtmlBtn");
const dlCsvBtn           = document.getElementById("downloadCsvBtn");

// Options
const optAssonance       = document.getElementById("optAssonance");
const optConsonance      = document.getElementById("optConsonance");
const optAlliterationOnly = document.getElementById("optAlliterationOnly");
const optIgnoreQuantity  = document.getElementById("optIgnoreQuantity");
const optStopwords       = document.getElementById("optStopwords");
const optWindow          = document.getElementById("optWindow");
const optWindowVal       = document.getElementById("optWindowVal");
const optMinOcc          = document.getElementById("optMinOcc");
const optMinOccVal       = document.getElementById("optMinOccVal");

// The "alliteration only" checkbox is a sub-option of Consonance — disable
// it whenever Consonance itself is unchecked.
function updateAlliterationSubOption() {
    optAlliterationOnly.disabled = !optConsonance.checked;
}
optConsonance.addEventListener("change", updateAlliterationSubOption);

// The "ignore vowel quantity" checkbox is a sub-option of Assonance.
function updateIgnoreQuantitySubOption() {
    optIgnoreQuantity.disabled = !optAssonance.checked;
}
optAssonance.addEventListener("change", updateIgnoreQuantitySubOption);

// ── State ───────────────────────────────────────────────────────────────────
let pyodide      = null;
let pyLoaded     = false;
let textContent  = null;
let lastHtmlBlob = null;
let lastCsvBlob  = null;

// ── Slider labels ───────────────────────────────────────────────────────────
optWindow.addEventListener("input", () => {
    optWindowVal.textContent = optWindow.value;
});
optMinOcc.addEventListener("input", () => {
    optMinOccVal.textContent = optMinOcc.value;
});

// ── File / paste input ───────────────────────────────────────────────────────
fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
        textContent = e.target.result;
        pasteArea.value = "";
        updateRunBtn();
        setStatus(`Loaded "${file.name}" (${textContent.length.toLocaleString()} chars).`);
    };
    reader.readAsText(file, "utf-8");
});

pasteArea.addEventListener("input", () => {
    textContent = pasteArea.value.trim() || null;
    if (textContent) fileInput.value = "";
    updateRunBtn();
});

function updateRunBtn() {
    runBtn.disabled = !(textContent && pyLoaded);
}

// ── Pyodide loading ──────────────────────────────────────────────────────────
async function loadPyodideAndDetector() {
    setStatus("Loading Pyodide… (first load may take ~10 s)");
    try {
        pyodide = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.24.1/full/" });
        // Cache-bust so a redeployed detector.py is never masked by a stale
        // browser/CDN cache of the previous version.
        const resp = await fetch("detector.py?v=" + Date.now());
        const code = await resp.text();
        pyodide.FS.writeFile("/detector.py", code);
        await pyodide.runPythonAsync(`exec(open('/detector.py').read())`);
        pyLoaded = true;
        updateRunBtn();
        setStatus("Ready. Load a text file or paste Greek text above.");
    } catch (err) {
        setStatus("Error loading Pyodide: " + err.message, true);
    }
}

loadPyodideAndDetector();

// ── Run ──────────────────────────────────────────────────────────────────────
runBtn.addEventListener("click", async () => {
    if (!textContent || !pyLoaded) return;

    if (!optAssonance.checked && !optConsonance.checked) {
        setStatus("Please select at least one detection type (Assonance or Consonance).", true);
        return;
    }

    runBtn.disabled = true;
    dlHtmlBtn.disabled = true;
    dlCsvBtn.disabled = true;
    outputEl.innerHTML = "";
    setStatus("Analysing…");

    pyodide.FS.writeFile("/input.txt", textContent);

    const options = {
        detect_assonance:       optAssonance.checked,
        detect_consonance:      optConsonance.checked,
        alliteration_only:      optAlliterationOnly.checked,
        window_size:            parseInt(optWindow.value),
        min_occurrences:        parseInt(optMinOcc.value),
        ignore_vowel_quantity:  optIgnoreQuantity.checked,
        skip_stopwords:         optStopwords.checked,
    };
    pyodide.FS.writeFile("/options.json", JSON.stringify(options));

    try {
        await pyodide.runPythonAsync(`
exec(open('/detector.py').read())
occs = process('/input.txt', '/output.html', '/output.csv')
`);

        const htmlBytes = pyodide.FS.readFile("/output.html");
        const csvBytes  = pyodide.FS.readFile("/output.csv");
        const htmlStr   = new TextDecoder("utf-8").decode(htmlBytes);

        const occPy  = pyodide.globals.get("occs");
        const occLen = occPy && occPy.length !== undefined ? occPy.length : "?";

        renderOutput(htmlStr);

        lastHtmlBlob = new Blob([htmlBytes], { type: "text/html;charset=utf-8" });
        lastCsvBlob  = new Blob([csvBytes],  { type: "text/csv;charset=utf-8" });
        dlHtmlBtn.disabled = false;
        dlCsvBtn.disabled  = false;

        setStatus(`Done. ${occLen} sound figure${occLen === 1 ? "" : "s"} found.`);
    } catch (err) {
        setStatus("Detection error: " + err.message, true);
        console.error(err);
    } finally {
        runBtn.disabled = false;
    }
});

// ── Render output ─────────────────────────────────────────────────────────────
function renderOutput(fullHtml) {
    const parser = new DOMParser();
    const doc    = parser.parseFromString(fullHtml, "text/html");

    const pre   = doc.querySelector("pre.source");
    const table = doc.querySelector("table");

    outputEl.innerHTML = "";

    if (pre) {
        const section = document.createElement("div");
        section.className = "output-section";
        const h = document.createElement("h3");
        h.textContent = "Annotated Text";
        section.appendChild(h);
        section.appendChild(pre.cloneNode(true));
        outputEl.appendChild(section);
    }

    if (table) {
        const section = document.createElement("div");
        section.className = "output-section";
        const h = document.createElement("h3");
        h.textContent = "Occurrence Table";
        section.appendChild(h);
        section.appendChild(table.cloneNode(true));
        outputEl.appendChild(section);
    }
}

// ── Downloads ─────────────────────────────────────────────────────────────────
dlHtmlBtn.addEventListener("click", () => {
    if (!lastHtmlBlob) return;
    triggerDownload(lastHtmlBlob, "assonance_consonance.html");
});
dlCsvBtn.addEventListener("click", () => {
    if (!lastCsvBlob) return;
    triggerDownload(lastCsvBlob, "assonance_consonance.csv");
});

function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a   = document.createElement("a");
    a.href    = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// ── Status helper ─────────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
    statusEl.textContent = msg;
    statusEl.className   = isError ? "status error" : "status";
}
