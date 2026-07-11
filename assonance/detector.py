"""
Greek Assonance & Consonance Detector
=======================================
Two detection modes, both built on the same sliding-window engine:

  • Assonance  — repetition of a VOWEL sound (single vowel or diphthong)
                 anywhere within nearby words, across a sliding window of
                 N consecutive words.
  • Consonance — repetition of a CONSONANT sound anywhere within nearby
                 words. A sub-option restricts this to the strict classical
                 definition of ALLITERATION: only the word-INITIAL consonant
                 counts (vowel-initial words simply do not participate in
                 alliteration mode).

Architecture mirrors the hiatus & anaphora detectors: runs inside Pyodide;
options are passed via /options.json written by app.js.

Design notes
------------
- Diphthongs and single vowels are both represented as one "vowel cluster"
  per maximal run of vowel letters, exactly as the hiatus detector already
  treats them, so ⟨αι⟩ is one assonance unit, not two.
- Diaeresis (◌̈) breaks a would-be diphthong into two separate vowel
  clusters, matching its function in the hiatus detector.
- Iota subscript is preserved as a literal trailing "ι" in the comparison
  key (so ᾳ behaves like the diphthong αι), rather than being silently
  dropped or requiring a separate Unicode recomposition step.
- "Ignore vowel quantity" folds ω→ο and η→ε — the only two Greek vowel
  pairs with distinct short/long LETTERFORMS (α, ι, υ have no separate
  long/short letters in the script, so there is nothing to fold there).
- Consonance/alliteration keys are single base consonant letters (breathing
  marks stripped), not multi-letter clusters — a consonant cluster like
  στ is treated as two independent consonant sounds, σ and τ, since that
  matches how these sounds are actually perceived and cited in rhetorical
  analysis.
- Highlighting is whole-word, matching the granularity of the anaphora
  detector (not sub-word character spans, as in the hiatus detector).
"""

import unicodedata
import html as html_mod
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Greek stop-words (same list used by the anaphora detector)
# ---------------------------------------------------------------------------

STOP_WORDS_NFC = {
    # articles
    "ὁ","ἡ","τό","οἱ","αἱ","τά",
    "τοῦ","τῆς","τοῖς","ταῖς","τούς","τάς","τῶν","τῷ","τήν","τόν",
    # conjunctions & particles
    "καί","καὶ","δέ","δὲ","γάρ","γὰρ","μέν","μὲν","ἀλλά","ἀλλὰ",
    "ἀλλ","οὖν","ἄρα","ἆρα","ἤ","ἢ","οὐδέ","οὐδὲ","μηδέ","μηδὲ",
    "τε","γε","τοί","που","πού","νυν","νῦν","αὖ","αὖτε","αὖθις",
    "εἰ","εἴ","ὡς","ὥς","ὅτι","ὅτε","ὅτ","ἐπεί","ἐπεὶ","ἐπειδή",
    "ἐπειδὴ","ὄτε","ὄτι","ἵνα","ὄφρα","ὄφρ","ὁτε","ὁτι",
    # negations
    "οὐ","οὐκ","οὐχ","οὔ","μή","μὴ","μήτε","μήτ","οὔτε","οὔτ",
    # prepositions
    "ἐν","ἐκ","ἐξ","εἰς","ἐς","πρός","πρὸς","ἀπό","ἀπὸ","ὑπό","ὑπὸ",
    "ἐπί","ἐπὶ","περί","περὶ","παρά","παρὰ","κατά","κατὰ","διά","διὰ",
    "μετά","μετὰ","ἀντί","ἀντὶ","ἀμφί","ἀμφὶ",
    # pronouns
    "αὐτός","αὐτὸς","αὐτή","αὐτὴ","αὐτό","αὐτὸ",
    "αὐτοῦ","αὐτῆς","αὐτοῖς","αὐταῖς","αὐτούς","αὐτάς","αὐτῶν","αὐτῷ",
}

# ---------------------------------------------------------------------------
# Character classification
# ---------------------------------------------------------------------------

_VOWEL_BASE       = set("αεηιουω")
_ACCENT_MARKS     = {"\u0301", "\u0300", "\u0342"}   # acute, grave, circumflex
_BREATHING_MARKS  = {"\u0313", "\u0314"}              # smooth, rough
_DIAERESIS        = "\u0308"
_IOTA_SUBSCRIPT   = "\u0345"

_WORD_PUNCT = ".,·;:!?\"''\u2019\u02bc\u1fbd\u1fbf\u02bb\u2018—–\u2013\u2014-()[]⟨⟩"


def _graphemes(word: str):
    """
    NFD-decompose `word` and group each base letter with the set of
    combining marks attached to it.  Returns a list of [base_char, marks_set]
    pairs in original order. Non-letter characters (stray punctuation that
    survived tokenisation) are included as their own grapheme with an empty
    marks set; they simply won't match _VOWEL_BASE/consonant checks below.

    Final sigma (ς, U+03C2) is normalised to medial sigma (σ, U+03C3) here,
    since they represent the same letter/sound and differ only by
    word-position convention — treating them as distinct would silently
    fragment every consonance/alliteration match involving sigma.
    """
    nfd = unicodedata.normalize("NFD", word.lower())
    out = []
    for c in nfd:
        if c == "\u03c2":  # final sigma -> medial sigma
            c = "\u03c3"
        if unicodedata.category(c) == "Mn":
            if out:
                out[-1][1].add(c)
            # stray combining mark with no preceding base — ignore
        else:
            out.append([c, set()])
    return out


def _normalize_for_stopword_check(word: str) -> str:
    """Accent/breathing/iota-subscript-insensitive key, used only to test
    whether a token matches an entry in STOP_WORDS_NFC."""
    nfd = unicodedata.normalize("NFD", word.lower())
    kept = "".join(
        c for c in nfd
        if c not in _ACCENT_MARKS and c not in _BREATHING_MARKS and c != _IOTA_SUBSCRIPT
    )
    return unicodedata.normalize("NFC", kept)


def vowel_cluster_keys(word: str, opts: dict) -> set:
    """
    Return the SET of distinct vowel-cluster keys present in `word`.

    A "vowel cluster" is a maximal run of vowel base-letters — a single
    vowel or a diphthong. Diaeresis breaks a cluster in two. Iota subscript
    is represented as a literal trailing "ι" appended to the cluster key
    (so ᾳ behaves as the diphthong "αι"). If ignore_vowel_quantity is set,
    ω folds to ο and η folds to ε within every cluster, including inside
    diphthongs (so ηυ and ευ become the same key under that option).
    """
    ignore_q = opts.get("ignore_vowel_quantity", False)
    graphemes = _graphemes(word)
    keys = set()
    current = []

    def flush():
        if current:
            keys.add("".join(current))
            current.clear()

    for base, marks in graphemes:
        if base in _VOWEL_BASE:
            if _DIAERESIS in marks:
                flush()  # diaeresis: this vowel does NOT join the previous one
            b = base
            if ignore_q:
                if b == "ω":
                    b = "ο"
                elif b == "η":
                    b = "ε"
            current.append(b)
            if _IOTA_SUBSCRIPT in marks:
                current.append("ι")
        else:
            flush()
    flush()

    return keys


def consonant_keys(word: str, opts: dict, alliteration_only: bool) -> set:
    """
    Return the SET of distinct consonant keys present in `word`.

    If alliteration_only is True, this instead returns AT MOST ONE key:
    the word's initial consonant, and ONLY if the word actually begins
    with a consonant (vowel-initial words return an empty set — traditional
    alliteration is specifically about the initial consonant sound, so a
    vowel-initial word simply does not participate).

    Breathing marks are stripped (ῥ and ρ share the same key). Consonant
    clusters (e.g. στ) are NOT merged into a single unit — each letter is
    its own independent consonant sound, matching how consonance is
    conventionally cited in rhetorical analysis.
    """
    graphemes = _graphemes(word)
    if not graphemes:
        return set()

    if alliteration_only:
        base, _marks = graphemes[0]
        if base and base not in _VOWEL_BASE and base.isalpha():
            return {base}
        return set()

    keys = set()
    for base, _marks in graphemes:
        if base and base not in _VOWEL_BASE and base.isalpha():
            keys.add(base)
    return keys


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def tokenize_text(text: str) -> list:
    """
    Flat, line-break-spanning token stream (sound effects are heard across
    enjambment, so the sliding window is not confined to a single line).
    Each token carries: text, raw, char_start, line_num, norm (for
    stop-word matching).
    """
    tokens = []
    pos = 0
    line_num = 1

    for raw_chunk in re.split(r'(\s+)', text):
        if not raw_chunk:
            continue
        if re.match(r'^\s+$', raw_chunk):
            line_num += raw_chunk.count('\n')
            pos += len(raw_chunk)
            continue

        word = raw_chunk.strip(_WORD_PUNCT)
        if word:
            word_offset = raw_chunk.find(word)
            tokens.append({
                "text": word,
                "raw": raw_chunk,
                "char_start": pos + word_offset,
                "line_num": line_num,
                "norm": _normalize_for_stopword_check(word),
            })
        pos += len(raw_chunk)

    return tokens


# ---------------------------------------------------------------------------
# Options reader
# ---------------------------------------------------------------------------

def read_options() -> dict:
    defaults = {
        "detect_assonance":       True,
        "detect_consonance":      True,
        "alliteration_only":      False,
        "window_size":            4,
        "min_occurrences":        3,
        "ignore_vowel_quantity":  False,
        "skip_stopwords":         True,
    }
    opt_path = Path("/options.json")
    if opt_path.exists():
        try:
            data = json.loads(opt_path.read_text(encoding="utf-8"))
            for k in defaults:
                if k in data:
                    defaults[k] = data[k]
        except Exception:
            pass
    return defaults


# ---------------------------------------------------------------------------
# Sliding-window sound-group finder (shared by assonance & consonance)
# ---------------------------------------------------------------------------

def find_sound_groups(tokens, key_fn, window_size, min_occ, kind, skip, norm_stops):
    """
    tokens  : flat token list from tokenize_text()
    key_fn  : function(token) -> set of sound keys for that token
              (assonance: 0+ vowel-cluster keys; consonance: 0+ consonant
              keys, or at most 1 if alliteration_only)
    window_size : span of N consecutive (content) words within which
              min_occ or more words sharing a key constitute a match.
              Follows the same "gap ≤ window_size - 1" convention used by
              the anaphora detector's distance window.
    skip    : if True, stop-words are removed entirely before windowing,
              so the window counts only content words and stop-words can
              neither trigger nor break a match.

    Returns a list of group dicts: kind, key, word_indices (into `tokens`),
    line_nums.
    """
    filtered = [
        (i, t) for i, t in enumerate(tokens)
        if not (skip and t["norm"] in norm_stops)
    ]

    key_positions = defaultdict(list)   # key -> list of filtered-list positions
    for fi, (orig_i, t) in enumerate(filtered):
        for k in key_fn(t):
            if k:
                key_positions[k].append(fi)

    groups = []
    for key, positions in key_positions.items():
        used = set()
        n = len(positions)
        for i in range(n):
            if positions[i] in used:
                continue
            start_fi = positions[i]
            group_fis = [start_fi]
            for j in range(i + 1, n):
                if positions[j] - start_fi > window_size - 1:
                    break
                group_fis.append(positions[j])

            if len(group_fis) < min_occ:
                continue

            for fi in group_fis:
                used.add(fi)

            orig_indices = [filtered[fi][0] for fi in group_fis]
            groups.append({
                "kind": kind,
                "key": key,
                "word_indices": orig_indices,
                "line_nums": sorted(set(tokens[oi]["line_num"] for oi in orig_indices)),
            })

    return groups


# ---------------------------------------------------------------------------
# HTML-building
# ---------------------------------------------------------------------------

def _build_line_html(raw_line: str, line_tokens: list, highlight: dict, line_num: int) -> str:
    """
    Rebuild a raw line as HTML, wrapping each token that appears in
    `highlight` (keyed by (line_num, char_start)) in a <span> carrying the
    union of all matched sound-figure CSS classes for that word.
    """
    parts = []
    remaining = raw_line
    for t in line_tokens:
        tok_text = t["text"]
        idx = remaining.find(tok_text)
        if idx == -1:
            continue
        parts.append(html_mod.escape(remaining[:idx]))
        escaped = html_mod.escape(tok_text)
        classes = highlight.get((line_num, t["char_start"]))
        if classes:
            css = " ".join(sorted(classes))
            parts.append(f'<span class="{css}">{escaped}</span>')
        else:
            parts.append(escaped)
        remaining = remaining[idx + len(tok_text):]
    parts.append(html_mod.escape(remaining))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Main detection entry point
# ---------------------------------------------------------------------------

def detect_sound_figures(text: str):
    opts   = read_options()
    window = max(2, int(opts.get("window_size", 4)))
    min_occ = max(2, int(opts.get("min_occurrences", 3)))
    do_assonance  = opts.get("detect_assonance", True)
    do_consonance = opts.get("detect_consonance", True)
    alliteration_only = opts.get("alliteration_only", False)
    skip = opts.get("skip_stopwords", True)

    norm_stops = {_normalize_for_stopword_check(w) for w in STOP_WORDS_NFC}

    tokens = tokenize_text(text)

    occurrences = []

    if do_assonance:
        def assonance_key_fn(t):
            return vowel_cluster_keys(t["text"], opts)
        occurrences += find_sound_groups(
            tokens, assonance_key_fn, window, min_occ, "assonance", skip, norm_stops
        )

    if do_consonance:
        def consonance_key_fn(t):
            return consonant_keys(t["text"], opts, alliteration_only)
        kind_label = "alliteration" if alliteration_only else "consonance"
        occurrences += find_sound_groups(
            tokens, consonance_key_fn, window, min_occ, kind_label, skip, norm_stops
        )

    # ── Build highlight map: (line_num, char_start) -> set of css classes ──
    _CSS_FOR_KIND = {
        "assonance":    "snd-assonance",
        "consonance":   "snd-consonance",
        "alliteration": "snd-alliteration",
    }
    highlight = defaultdict(set)
    for occ in occurrences:
        css = _CSS_FOR_KIND[occ["kind"]]
        for oi in occ["word_indices"]:
            t = tokens[oi]
            highlight[(t["line_num"], t["char_start"])].add(css)

    # ── Render annotated HTML line by line ──────────────────────────────────
    raw_lines = text.split("\n")
    tokens_by_line = defaultdict(list)
    for t in tokens:
        tokens_by_line[t["line_num"]].append(t)

    html_lines = []
    for ln_idx, raw_line in enumerate(raw_lines):
        ln = ln_idx + 1
        line_tokens = tokens_by_line.get(ln, [])
        has_highlight = any((ln, t["char_start"]) in highlight for t in line_tokens)
        if not has_highlight:
            html_lines.append(html_mod.escape(raw_line))
        else:
            html_lines.append(_build_line_html(raw_line, line_tokens, highlight, ln))

    annotated_html = "\n".join(html_lines)

    for n, occ in enumerate(occurrences, 1):
        occ["index"] = n

    return annotated_html, occurrences, tokens


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Greek Assonance & Consonance Highlights</title>
<style>
body {{ font-family: serif; padding: 1.5rem; max-width: 900px; margin: auto; }}
pre.source {{ white-space: pre-wrap; font-size: 18px; line-height: 1.7; }}
.snd-assonance   {{ background: rgba(138,105,150,0.30); border-bottom: 2px solid #6d4f78; }}
.snd-consonance  {{ background: rgba(38,122,186,0.28);  border-bottom: 2px solid #1d5f8f; }}
.snd-alliteration{{ background: rgba(38,122,186,0.28);  border-bottom: 2px solid #1d5f8f; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1.5rem; font-size: 0.95rem; }}
td,th {{ border: 1px solid #bbb; padding: 6px 10px; vertical-align: top; }}
th {{ background: #f4f4f4; }}
</style>
</head>
<body>
<h1>Greek Assonance &amp; Consonance Highlights</h1>
<p>
  <span style="background:rgba(138,105,150,0.30);padding:2px 6px;">Violet</span> = Assonance &nbsp;
  <span style="background:rgba(38,122,186,0.28);padding:2px 6px;">Blue</span> = Consonance / Alliteration
</p>
<h2>Annotated Text</h2>
<pre class="source">{annotated}</pre>
<h2>Occurrences</h2>
<table>
<tr><th>#</th><th>Type</th><th>Sound</th><th>Words</th><th>Count</th><th>Lines</th></tr>
{rows}
</table>
</body></html>
"""

_KIND_LABEL = {
    "assonance": "Assonance",
    "consonance": "Consonance",
    "alliteration": "Alliteration",
}


def write_outputs(annotated: str, occurrences: list, tokens: list, html_path, csv_path):
    rows = []
    csv_rows = []
    for occ in occurrences:
        n = occ["index"]
        kind_label = _KIND_LABEL.get(occ["kind"], occ["kind"])
        sound_display = occ["key"]
        words_display = ", ".join(tokens[oi]["text"] for oi in occ["word_indices"])
        count = len(occ["word_indices"])
        lines_str = ", ".join(str(l) for l in occ["line_nums"])

        rows.append(
            f"<tr><td>{n}</td><td>{kind_label}</td>"
            f"<td>{html_mod.escape(sound_display)}</td>"
            f"<td>{html_mod.escape(words_display)}</td>"
            f"<td>{count}</td><td>{lines_str}</td></tr>"
        )
        csv_rows.append({
            "index": n,
            "type": kind_label,
            "sound": sound_display,
            "words": words_display,
            "count": count,
            "lines": lines_str,
        })

    html_text = HTML_TEMPLATE.format(annotated=annotated, rows="\n".join(rows))
    Path(html_path).write_text(html_text, encoding="utf-8")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "type", "sound", "words", "count", "lines"])
        writer.writeheader()
        writer.writerows(csv_rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def process(input_path: str, html_path: str, csv_path: str):
    text = Path(input_path).read_text(encoding="utf-8")
    annotated, occurrences, tokens = detect_sound_figures(text)
    write_outputs(annotated, occurrences, tokens, html_path, csv_path)
    return occurrences
