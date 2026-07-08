# Project Demetrios

**Open-source computational tools for the phonological and rhetorical analysis of Ancient Greek verse**

[![Live site](https://img.shields.io/badge/live%20site-projectdemetrios.dartmouth.edu-00693e?style=flat-square)](https://projectdemetrios.dartmouth.edu)
[![License: MIT](https://img.shields.io/badge/license-MIT-12312b?style=flat-square)](LICENSE)
[![Dartmouth College](https://img.shields.io/badge/supported%20by-Dartmouth%20College-00693e?style=flat-square)](https://dartmouth.edu)

---

## About

Project Demetrios is a suite of browser-based analytical tools for classical philologists working with Ancient Greek verse. The project takes its name from **Demetrius of Phaleron** (c. 350–280 BCE) — Athenian orator, Peripatetic philosopher, and first director of the Library of Alexandria, probable author of *Περὶ Ἑρμηνείας* (*On Style*), the earliest surviving systematic treatise on Greek rhetorical figures.

Our tools are designed to assist in the close reading of Greek poetry by making visible patterns that lie beneath the threshold of unaided attention over extended texts. They do not replace philological judgement — they augment it. Every normalisation step is opt-in, fully documented, and reversible.

All tools run entirely in the browser via [Pyodide](https://pyodide.org) (a WebAssembly port of CPython). No server, no installation, and no data ever leaves the user's machine.

**Developed at Dartmouth College and the University of Oxford.**

---

## Tools

### I — Hiatus Detector
**Live:** [projectdemetrios.dartmouth.edu/hiatus](https://projectdemetrios.dartmouth.edu/hiatus)

Detects and highlights every instance of vowel hiatus in an uploaded or pasted Ancient Greek text — the sequence of a word-final vowel immediately followed by a word-initial vowel without forming a diphthong.

**Features:**
- Three detection modes: word-internal (I), inter-word (B), and across-verse (V)
- Full polytonic Unicode support with correct diphthong and diaeresis handling
- Optional rules: break on dash, break on punctuation, break on rough breathing, same-sound-only mode
- Per-line hiatus counts with heat-map table and density sparkline
- Outputs: annotated HTML with colour-coded highlights, CSV occurrence table, per-line CSV

---

### II — Anaphora & Epiphora Detector
**Live:** [projectdemetrios.dartmouth.edu/anaphora](https://projectdemetrios.dartmouth.edu/anaphora)

Detects rhetorical repetition at verse-line boundaries and across clause-delimiting punctuation in Ancient Greek verse.

**Three detection modes:**
- **Anaphora** — repetition of the same phrase at the *start* of consecutive verse lines (highlighted in gold)
- **Epiphora** — repetition at the *end* of consecutive verse lines (highlighted in teal)
- **Word Repetition** — clause-initial repetition across punctuation boundaries (`.`, `·`, `;`, `,`), capturing figures like Apollonius's *πολλὰ δ᾽* recurring across periods (highlighted in violet)

**Features:**
- User-configurable phrase length (1–5 words) and distance window (2–10 lines)
- Stop-word transparency: particles, articles, and prepositions (καί, δέ, ὁ, γάρ, …) are skipped when determining the comparison phrase, but flagged in output
- Highlight extension: once a match is found, the full common prefix/suffix is highlighted rather than only the minimum matching phrase
- Normalisation pipeline: accent stripping, breathing removal, iota subscript, elision handling, nu-movable — each step independently toggleable
- Outputs: annotated HTML, CSV occurrence table

---

## Repository Structure

```
project-demetrios/
│
├── index.html                  # Homepage
├── about.html                  # Project description, grants, team
├── tools.html                  # Tool catalogue with full documentation
├── contact.html                # Contact form (Formspree)
│
├── style.css                   # Shared design system (nav, footer, buttons)
├── home.css                    # Homepage-specific styles
├── about.css                   # About page styles
├── tools.css                   # Tools page styles
├── contact.css                 # Contact page styles
├── main.js                     # Shared JS (nav, scroll-reveal, mobile menu)
│
├── favicon.ico                 # Multi-size favicon (16 / 32 / 48 px)
├── favicon-32x32.png
├── apple-touch-icon.png        # iOS home screen icon (180 × 180)
├── android-chrome-512x512.png  # Android / PWA icon
├── site.webmanifest            # Web app manifest
│
├── CNAME                       # GitHub Pages custom domain
├── LICENSE                     # MIT
│
├── hiatus/                     # Tool I
│   ├── index.html
│   ├── style.css
│   ├── app.js                  # Pyodide orchestration + UI logic
│   └── detector.py             # Core detection logic (runs via Pyodide)
│
└── anaphora/                   # Tool II
    ├── index.html
    ├── style.css
    ├── app.js
    └── detector.py
```

---

## Technical Architecture

Each tool follows the same pattern:

1. **Python core** (`detector.py`) — all linguistic analysis is written in Python 3, using `unicodedata` for polytonic Greek normalisation. This runs directly in the browser via Pyodide (WebAssembly CPython).
2. **JavaScript orchestration** (`app.js`) — loads Pyodide, writes the uploaded/pasted text and a JSON options object to the Pyodide virtual filesystem, calls the Python detection function, and reads back the HTML and CSV outputs.
3. **Static HTML/CSS** — no frameworks, no build step. The entire site is deployable as-is to GitHub Pages.

This architecture means:
- Zero server infrastructure required
- No user data transmitted anywhere
- Fully reproducible: the detection logic is a single readable Python file
- Works offline once Pyodide has loaded (~10 MB, cached by the browser)

---

## Design

The site uses a **neo-classical editorial** visual language consistent with the Dartmouth institutional identity:

- **Dartmouth Green** `#00693e` and **Forest Green** `#12312b` as primary colours, per the [Dartmouth visual identity guidelines](https://communications.dartmouth.edu/guides-and-tools/design-guidelines/dartmouth-colors)
- **Cormorant Garamond** for display type; **Cinzel** for all-caps labels and navigation
- Parchment-warm backgrounds (`#faf7f0`), meander-pattern ornaments, ghost Greek letterforms

---

## Running Locally

No build step is required. Simply serve the repository root with any static file server, for example:

```bash
# Python
python3 -m http.server 8000

# Node
npx serve .
```

Then open `http://localhost:8000` in a browser. Pyodide requires a network connection on first load.

> **Note:** opening `index.html` directly via `file://` will not work for the tools, because `fetch("detector.py")` is blocked by browser security on `file://` origins. Always use a local server.

---

## Contributing

Bug reports and feature requests are welcome as [GitHub Issues](https://github.com/dartmouth/project-demetrios/issues). For questions about the philological methodology or collaboration proposals, use the [contact form](https://projectdemetrios.dartmouth.edu/contact) or write to [POET.admin@dartmouth.edu](mailto:POET.admin@dartmouth.edu).

If you find an error in the detection logic — a false positive, a missed instance, or incorrect normalisation behaviour — please include the text fragment that produces it, the options you had selected, and the expected vs. actual output.

---

## Acknowledgements

Project Demetrios is supported by the **Neukom Institute for Computational Science, Dartmouth College**. Development was carried out by [Atanas G. Iliev](https://github.com/atanasgiliev) with support from the project team.

The detection tools make use of [Pyodide](https://pyodide.org), an open-source project maintained by the Pyodide contributors.

---

## License

[MIT](LICENSE) © 2026 Atanas Iliev
