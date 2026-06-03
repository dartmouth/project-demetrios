let pyodideReadyPromise = loadPyodide();

// store outputs for download buttons
let lastHtmlOutput = null;
let lastCsvOutput = null;
let lastPerLineCsv = null;
let lastPerLineData = null;

// the loaded text — set by either file input or paste area
let loadedText = null;

// sorting state
let perLineSort = { col: "line", asc: true };

// remember open/closed state of per-line table
let perLineTableOpen = false;

/* ----------------------------
   RUN BUTTON ENABLE / DISABLE
   Requires: text loaded AND at least one hiatus type checked
----------------------------- */

function updateRunButtonState() {
    const hasText  = !!loadedText;
    const hasType  = document.getElementById("detectIntra").checked
                  || document.getElementById("detectInter").checked
                  || document.getElementById("detectAcross").checked;

    document.getElementById("runBtn").disabled = !(hasText && hasType);
}

/* ----------------------------
   INPUT LISTENERS
   File input and paste area are mutually exclusive:
   using one clears the other.
----------------------------- */

document.addEventListener("DOMContentLoaded", () => {
    updateRunButtonState();

    // Hiatus-type checkboxes
    ["detectIntra", "detectInter", "detectAcross"].forEach(id => {
        document.getElementById(id).addEventListener("change", updateRunButtonState);
    });

    // File input
    document.getElementById("fileInput").addEventListener("change", () => {
        const file = document.getElementById("fileInput").files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = e => {
            loadedText = e.target.result;
            // clear paste area
            document.getElementById("pasteArea").value = "";
            setStatus(`Loaded "${file.name}" (${loadedText.length.toLocaleString()} chars).`);
            updateRunButtonState();
        };
        reader.readAsText(file, "utf-8");
    });

    // Paste area
    document.getElementById("pasteArea").addEventListener("input", () => {
        const val = document.getElementById("pasteArea").value.trim();
        if (val) {
            loadedText = document.getElementById("pasteArea").value;
            // clear file input
            document.getElementById("fileInput").value = "";
        } else {
            loadedText = null;
        }
        updateRunButtonState();
    });
});

/* ----------------------------
   STATUS HELPER
----------------------------- */

function setStatus(msg, isError = false) {
    const el = document.getElementById("status");
    el.textContent = msg;
    el.className = isError ? "error" : "";
}

/* ----------------------------
   CSV → HIATUS COUNTS
----------------------------- */

function countHiatusFromCsv(csvText) {
    const lines = csvText.trim().split("\n");
    lines.shift();

    const counts = { I: 0, B: 0, V: 0, total: 0 };

    for (const line of lines) {
        if (!line.trim()) continue;
        const kind = line.split(",")[1];
        if (counts[kind] !== undefined) {
            counts[kind]++;
            counts.total++;
        }
    }
    return counts;
}

/* ----------------------------
   CSV → PER-LINE COUNTS
----------------------------- */

function countHiatusPerLine(csvText, lineCount) {
    const perLine = {};
    for (let i = 1; i <= lineCount; i++) perLine[i] = 0;

    const rows = csvText.trim().split("\n");
    rows.shift();

    for (const row of rows) {
        if (!row.trim()) continue;
        const field = row.split(",")[2];
        if (!field) continue;

        if (field.includes("-")) {
            const [a, b] = field.split("-").map(Number);
            if (perLine[a] !== undefined) perLine[a]++;
            if (perLine[b] !== undefined) perLine[b]++;
        } else {
            const n = parseInt(field, 10);
            if (perLine[n] !== undefined) perLine[n]++;
        }
    }
    return perLine;
}

function heatColor(value, max) {
    if (max === 0) return "#ffffff";
    const t = value / max;
    return `rgb(255, ${Math.round(255 * (1 - t))}, ${Math.round(255 * (1 - t))})`;
}

function addLineNumbersToAnnotatedHTML(html) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");

    const pre = doc.querySelector("pre.source");
    if (!pre) return html;

    const lines = pre.innerHTML.split("\n");
    pre.innerHTML = lines
        .map(line => `<span class="line">${line || "&nbsp;"}</span>`)
        .join("\n");

    const style = doc.createElement("style");
    style.textContent = `
        pre.source {
            counter-reset: line;
        }
        pre.source .line {
            display: block;
            padding-left: 3.5em;
            position: relative;
        }
        pre.source .line::before {
            counter-increment: line;
            content: counter(line);
            position: absolute;
            left: 0;
            width: 3em;
            text-align: right;
            color: #888;
            font-family: monospace;
            user-select: none;
        }
    `;
    doc.head.appendChild(style);

    return "<!DOCTYPE html>\n" + doc.documentElement.outerHTML;
}

/* ----------------------------
   SORTABLE PER-LINE TABLE
----------------------------- */

function renderSparklineFromData(data) {
    if (!data || data.length === 0) return "";

    const width = 1000;
    const height = 220;
    const margin = { top: 15, right: 20, bottom: 40, left: 45 };

    const counts = data.map(d => d.count);
    const lineCount = counts.length;
    const yMax = Math.max(...counts, 1);

    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const scaleX = i => margin.left + (i / (lineCount - 1)) * innerW;
    const scaleY = v => margin.top + innerH - (v / yMax) * innerH;

    const points = counts.map((v, i) => `${scaleX(i)},${scaleY(v)}`).join(" ");

    const x0 = margin.left;
    const x1 = margin.left + innerW;
    const y0 = margin.top + innerH;
    const y1 = margin.top;

    const yTicks = Math.min(yMax, 6);
    const yStep  = Math.max(1, Math.ceil(yMax / yTicks));

    let xStep =
        lineCount <= 200 ? 25 :
        lineCount <= 500 ? 50 : 100;

    const xLabels = [];
    for (let i = 1; i <= lineCount; i += xStep) {
        const frac = (i - 1) / (lineCount - 1);
        xLabels.push({ x: margin.left + frac * innerW, label: i });
    }
    if (xLabels.at(-1)?.label !== lineCount) {
        xLabels.push({ x: margin.left + innerW, label: lineCount });
    }

    return `
        <h4>Hiatus Density per Line</h4>
        <svg viewBox="0 0 ${width} ${height}"
             style="width:100%; height:${height}px; display:block">
            <line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y0}" stroke="#000"/>
            <line x1="${x0}" y1="${y0}" x2="${x0}" y2="${y1}" stroke="#000"/>
            ${Array.from({ length: Math.floor(yMax / yStep) + 1 }, (_, i) => {
                const v = i * yStep;
                return `<text x="${x0 - 6}" y="${scaleY(v)}"
                              text-anchor="end" dominant-baseline="middle"
                              font-size="10">${v}</text>`;
            }).join("")}
            ${xLabels.map(l => `
                <text x="${l.x}" y="${y0 + 18}"
                      text-anchor="middle" font-size="10">${l.label}</text>
            `).join("")}
            <polyline fill="none" stroke="#444" stroke-width="1" points="${points}"/>
        </svg>
    `;
}

function renderPerLineTable(forceOpen = null) {
    if (!lastPerLineData) return "";

    const data = [...lastPerLineData];
    const max  = Math.max(...data.map(d => d.count));

    data.sort((a, b) => {
        const key = perLineSort.col;
        const dir = perLineSort.asc ? 1 : -1;
        return (a[key] - b[key]) * dir;
    });

    const shouldBeOpen =
        forceOpen !== null ? forceOpen : lastPerLineData.length <= 50;

    const rows = data.map(d => `
        <tr style="background:${heatColor(d.count, max)}">
            <td>${d.line}</td>
            <td>${d.count}</td>
        </tr>
    `).join("");

    const arrow = c =>
        perLineSort.col === c ? (perLineSort.asc ? " ▲" : " ▼") : "";

    return `
        <details ${shouldBeOpen ? "open" : ""}>
            <summary style="cursor:pointer; font-weight:600;">
                Hiatus per Line (click to expand)
            </summary>
            <table border="1" cellpadding="6" style="margin-top:8px;">
                <tr>
                    <th style="cursor:pointer" onclick="sortPerLine('line')">Line${arrow("line")}</th>
                    <th style="cursor:pointer" onclick="sortPerLine('count')">#${arrow("count")}</th>
                </tr>
                ${rows}
            </table>
        </details>
        ${renderSparklineFromData(lastPerLineData)}
    `;
}

function sortPerLine(col) {
    const details = document.querySelector("#perLineContainer details");
    perLineTableOpen = details ? details.open : false;

    if (perLineSort.col === col) {
        perLineSort.asc = !perLineSort.asc;
    } else {
        perLineSort.col = col;
        perLineSort.asc = true;
    }

    document.getElementById("perLineContainer").innerHTML =
        renderPerLineTable(perLineTableOpen);
}

/* ----------------------------
   CORE DETECTOR RUN
----------------------------- */

async function runDetector(text) {
    const pyodide = await pyodideReadyPromise;

    await pyodide.FS.writeFile(
        "detector.py",
        await (await fetch("detector.py")).text()
    );
    await pyodide.runPythonAsync(`import detector`);

    const options = {
        break_on_dash:        document.getElementById("breakOnDash").checked,
        break_on_punctuation: document.getElementById("breakOnPunctuation").checked,
        break_on_rough_second:document.getElementById("breakOnRoughSecond").checked,
        detect_intra:         document.getElementById("detectIntra").checked,
        detect_inter:         document.getElementById("detectInter").checked,
        detect_across:        document.getElementById("detectAcross").checked,
        same_sound_only:      document.getElementById("sameSoundOnly")?.checked ?? false,
    };

    pyodide.FS.writeFile("/options.json", JSON.stringify(options));
    pyodide.FS.writeFile("/app_input.txt", text);

    await pyodide.runPythonAsync(`
from pathlib import Path
from detector import detect_hiatus_in_text, write_outputs
text = Path("/app_input.txt").read_text(encoding="utf-8")
annotated, occ = detect_hiatus_in_text(text)
write_outputs(annotated, occ, Path("/out.html"), Path("/out.csv"))
    `);

    return {
        html: pyodide.FS.readFile("/out.html", { encoding: "utf8" }),
        csv:  pyodide.FS.readFile("/out.csv",  { encoding: "utf8" }),
    };
}

/* ----------------------------
   FILE DOWNLOADS
----------------------------- */

function downloadFile(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/* ----------------------------
   RUN BUTTON HANDLER
----------------------------- */

document.getElementById("runBtn").onclick = async () => {
    if (!loadedText) {
        setStatus("Please upload a file or paste Greek text first.", true);
        return;
    }

    const output = document.getElementById("output");
    output.innerHTML = "";
    setStatus("Running detector…");

    try {
        const text      = loadedText;
        const lineCount = text.split(/\r?\n/).filter(l => l.trim()).length;
        const result    = await runDetector(text);

        lastHtmlOutput = result.html;
        lastCsvOutput  = result.csv;

        const counts = countHiatusFromCsv(result.csv);
        const hiatusPerLine = lineCount
            ? (counts.total / lineCount).toFixed(3)
            : "0.000";

        let perLineSection = "";
        lastPerLineCsv  = null;
        lastPerLineData = null;

        if (document.getElementById("showPerLineTable").checked) {
            const perLine = countHiatusPerLine(result.csv, lineCount);
            const csvRows = ["line,hiatus_count"];
            lastPerLineData = [];

            for (let i = 1; i <= lineCount; i++) {
                lastPerLineData.push({ line: i, count: perLine[i] });
                csvRows.push(`${i},${perLine[i]}`);
            }

            lastPerLineCsv = csvRows.join("\n");
            perLineSection = `<div id="perLineContainer">
                ${renderPerLineTable()}
            </div>`;
        }

        document.getElementById("downloadPerLineCsvBtn").disabled = !lastPerLineCsv;

        setStatus("Done!");
        output.innerHTML = `
            <h3>Hiatus Counts</h3>
            <ul>
                <li>I: ${counts.I}</li>
                <li>B: ${counts.B}</li>
                <li>V: ${counts.V}</li>
                <li><strong>Total: ${counts.total}</strong></li>
                <li># of hiatus instances per line: ${hiatusPerLine}</li>
            </ul>
            ${perLineSection}
            <iframe
                style="width:100%; height:600px; border:1px solid #ccc;"
                srcdoc="${addLineNumbersToAnnotatedHTML(result.html).replace(/"/g, '&quot;')}">
            </iframe>
        `;

        document.getElementById("downloadHtmlBtn").disabled = false;
        document.getElementById("downloadCsvBtn").disabled  = false;

    } catch (err) {
        setStatus("Error running detector.", true);
        console.error(err);
    }
};

/* ----------------------------
   DOWNLOAD BUTTONS
----------------------------- */

document.getElementById("downloadHtmlBtn").onclick = () => {
    if (lastHtmlOutput)
        downloadFile("hiatus_output.html", lastHtmlOutput, "text/html");
};

document.getElementById("downloadCsvBtn").onclick = () => {
    if (lastCsvOutput)
        downloadFile("hiatus_output.csv", lastCsvOutput, "text/csv");
};

document.getElementById("downloadPerLineCsvBtn").onclick = () => {
    if (lastPerLineCsv)
        downloadFile("hiatus_per_line.csv", lastPerLineCsv, "text/csv");
};
