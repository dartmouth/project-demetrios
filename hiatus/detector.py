import argparse
import csv
import html
import unicodedata
import json
from pathlib import Path
from collections import defaultdict

# ----- configuration -----
DIPHTHONGS = {"αι","αυ","ει","ευ","οι","ου","υι","ηυ","ῃ","ῳ","ᾳ"} 
PRECOMPOSED_DIAERESIS = set(["ϊ","ΐ","ϋ","ΰ","Ϊ","Ϋ"])
COMBINING_DIAERESIS = "\u0308"
IOTA_SUBSCRIPT = "\u0345"
BREATHINGS = {"\u0313", "\u0314"}  # combining smooth/rough

PRECOMPOSED_IOTA_SUBS = {
    'ᾳ','ᾴ','ᾲ','ᾷ','ᾀ','ᾁ','ᾂ','ᾃ','ᾄ','ᾅ','ᾆ','ᾇ',
    'ῃ','ῄ','ῂ','ῇ','ᾐ','ᾑ','ᾒ','ᾓ','ᾔ','ᾕ','ᾖ','ᾗ',
    'ῳ','ῴ','ῲ','ῷ','ᾠ','ᾡ','ᾢ','ᾣ','ᾤ','ᾥ','ᾦ','ᾧ'
}

BASE_VOWELS = "αεηιουω"

# ----- optional hiatus breakers (OFF by default) -----
DASHES = {"—", "–", "-"}
STRONG_PUNCTUATION = {".", ",", "·", ";", ":"}


# ---------------------------
# NEW: vowel nucleus helper
# ---------------------------
def vowel_nucleus(cluster_texts):
    combined = "".join(cluster_texts)
    nfd = unicodedata.normalize("NFD", combined)

    if COMBINING_DIAERESIS in nfd:
        return None

    base = "".join(
        c for c in nfd
        if unicodedata.combining(c) == 0 and c.lower() in BASE_VOWELS
    ).lower()

    if contains_iota_subscript(combined):
        base += "ι"

    return base or None

# ---------------------------
# Grapheme cluster helpers
# ---------------------------
def grapheme_clusters(s):
    clusters = []
    i = 0
    N = len(s)
    while i < N:
        start = i
        i += 1
        while i < N and unicodedata.combining(s[i]) != 0:
            i += 1
        clusters.append({"text": s[start:i], "start": start, "end": i})
    return clusters

def base_letter(cluster_text):
    """Return the first base codepoint (NFD) lowercased, or empty string."""
    nfd = unicodedata.normalize("NFD", cluster_text)
    for ch in nfd:
        if unicodedata.combining(ch) == 0:
            return ch.lower()
    return ""

def contains_accent(cluster_text):
    nfd = unicodedata.normalize("NFD", cluster_text)
    for ch in nfd:
        if unicodedata.category(ch) == "Mn":
            # acute, grave, circumflex
            if ch in {"\u0301", "\u0300", "\u0342"}:
                return True
    return False

def contains_combining_diaeresis(cluster_text):
    if any(ch in PRECOMPOSED_DIAERESIS for ch in cluster_text):
        return True
    return COMBINING_DIAERESIS in unicodedata.normalize("NFD", cluster_text)

def contains_iota_subscript(cluster_text):
    if IOTA_SUBSCRIPT in unicodedata.normalize("NFD", cluster_text):
        return True
    if IOTA_SUBSCRIPT in unicodedata.normalize("NFKD", cluster_text):
        return True
    for ch in cluster_text:
        decomp = unicodedata.decomposition(ch)
        if decomp and "0345" in decomp:
            return True
    if cluster_text in PRECOMPOSED_IOTA_SUBS:
        return True
    return False

def contains_breathing(cluster_text):
    nfd = unicodedata.normalize("NFD", cluster_text)
    for b in BREATHINGS:
        if b in nfd:
            return True
    return False

def contains_rough_breathing(cluster_text):
    nfd = unicodedata.normalize("NFD", cluster_text)
    return "\u0314" in nfd

def is_vowel_cluster(cluster_text):
    nfd = unicodedata.normalize("NFD", cluster_text)
    bases = [c for c in nfd if unicodedata.combining(c) == 0]
    return any(base.lower() in BASE_VOWELS for base in bases)

def is_punct_or_space_cluster(cluster_text):
    for ch in cluster_text:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            continue
        return False
    return True

def only_punct_space_between(text, a, b):
    for ch in text[a:b]:
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N"):
            return False
    return True

def read_gui_options():
    """
    Reads GUI checkbox options if present.
    Safe no-op if file does not exist.
    """
    opts = {
        "break_on_rough_second": False,
        "break_on_dash": False,
        "break_on_punctuation": False,
        "same_sound_only": False,


        # NEW: which hiatus types to detect
        "detect_intra": True,
        "detect_inter": True,
        "detect_across": True,
    }

    opt_path = Path("/options.json")
    if opt_path.exists():
        try:
            import json
            data = json.loads(opt_path.read_text(encoding="utf-8"))
            for k in opts:
                if k in data:
                    opts[k] = bool(data[k])
        except Exception:
            pass

    return opts

def vowel_nucleus_from_indices(clusters, indices):
    texts = [clusters[i]['text'] for i in indices]
    return vowel_nucleus(texts)

# ---------------------------
# Core detection
# ---------------------------
def detect_hiatus_in_text(text,
    treat_iota_as_diphthong=False,
    max_cluster_lookahead=8,
    break_on_rough_second=False,
    break_on_dash=False,
    break_on_punctuation=False,
):
    """
    Detect hiatus occurrences. Returns:
      - annotated_text (HTML)
      - occurrences list
    """
    text = unicodedata.normalize("NFC", text)
    gui_opts = read_gui_options()
    break_on_rough_second = gui_opts["break_on_rough_second"]
    break_on_dash = gui_opts["break_on_dash"]
    break_on_punctuation = gui_opts["break_on_punctuation"]
    detect_intra = gui_opts["detect_intra"]
    detect_inter = gui_opts["detect_inter"]
    detect_across = gui_opts["detect_across"]
    clusters = grapheme_clusters(text)
    same_sound_only = gui_opts["same_sound_only"]

    def line_number_at(idx):
        return text.count("\n", 0, idx)
    for c in clusters:
        c['line'] = line_number_at(c['start'])

    # per-line first/last non-punct cluster idx
    line_to_idxs = defaultdict(list)
    for idx, c in enumerate(clusters):
        line_to_idxs[c['line']].append(idx)

    first_nonpunct = {}
    last_nonpunct = {}
    for ln, idxs in line_to_idxs.items():
        first = None
        last = None
        for idx in idxs:
            txt = clusters[idx]['text']
            if is_punct_or_space_cluster(txt):
                continue
            if first is None:
                first = idx
            last = idx
        first_nonpunct[ln] = first
        last_nonpunct[ln] = last

    def safe_base(idx):
        if 0 <= idx < len(clusters):
            return base_letter(clusters[idx]['text'])
        return ""

    def second_vowel_cluster_text(i_idx, j_idx):
        """
        Return the FULL vowel cluster text (diphthong-aware)
        for the second vowel at j_idx.
        """
        indices = [j_idx]

        # look left
        if j_idx - 1 > i_idx:
            if safe_base(j_idx - 1) + safe_base(j_idx) in DIPHTHONGS:
                indices = [j_idx - 1, j_idx]

        # look right
        if j_idx + 1 < len(clusters):
            if safe_base(j_idx) + safe_base(j_idx + 1) in DIPHTHONGS:
                if j_idx + 1 > i_idx:
                    indices.append(j_idx + 1)

        return "".join(clusters[k]['text'] for k in indices)
    
    occurrences = []
    for i, ci in enumerate(clusters):
        if not is_vowel_cluster(ci['text']):
            continue
        for j in range(i+1, min(i+1+max_cluster_lookahead, len(clusters))):
            cj = clusters[j]
            if not is_vowel_cluster(cj['text']):
                continue

            intervening = text[ci['end']:cj['start']]

            # classify kind
            kind = None
            if "\n" in intervening:
                if cj['line'] == ci['line'] + 1:
                    last_idx = last_nonpunct.get(ci['line'])
                    first_idx = first_nonpunct.get(cj['line'])
                    if last_idx is not None and first_idx is not None and last_idx == i and first_idx == j:
                        kind = "across-line"
                    else:
                        kind = None
                else:
                    kind = None
            elif intervening == "":
                kind = "intra-word"
            elif only_punct_space_between(text, ci['end'], cj['start']) and ci['line'] == cj['line']:
                kind = "interword"
            else:
                kind = None

            if kind is None:
                continue
                
            # ----- FILTER BY HIATUS TYPE (GUI CHECKBOXES) -----
            if kind == "intra-word" and not detect_intra:
                continue
            if kind == "interword" and not detect_inter:
                continue
            if kind == "across-line" and not detect_across:
                continue
            
            # ----- OPTIONAL HIATUS BREAKERS -----
            
            # 1) rough breathing break
            if break_on_rough_second:
                cj_full = second_vowel_cluster_text(i, j)
                if contains_rough_breathing(cj_full):
                    continue

            # 2) dash between vowels
            if break_on_dash and any(d in intervening for d in DASHES):
                continue

            # 3) strong punctuation between vowels
            if break_on_punctuation and any(p in intervening for p in STRONG_PUNCTUATION):
                continue


            # DIPHTHONG/HIATUS decision
            is_diph = False
            if kind == "intra-word":
                b1 = base_letter(ci['text'])
                b2 = base_letter(cj['text'])
                pair = b1 + b2
                if pair in DIPHTHONGS:
                    is_diph = True
                    
                    # accent on first vowel breaks diphthong
                    if contains_accent(ci['text']):
                        is_diph = False
                if treat_iota_as_diphthong and (contains_iota_subscript(ci['text']) or contains_iota_subscript(cj['text'])):
                    is_diph = True
                if contains_combining_diaeresis(cj['text']):
                    is_diph = False
                if contains_breathing(ci['text']):
                    is_diph = False

            if is_diph:
                break

            # ----- SAME-SOUND HIATUS FILTER -----
            if same_sound_only:
                # determine full vowel units (monophthong or diphthong)

                vowel_i_indices = [i]
                vowel_j_indices = [j]

                # expand first vowel (left and right)
                if i + 1 < j and safe_base(i) + safe_base(i + 1) in DIPHTHONGS:
                    vowel_i_indices = [i, i + 1]
                elif i - 1 >= 0 and safe_base(i - 1) + safe_base(i) in DIPHTHONGS:
                    vowel_i_indices = [i - 1, i]

                # expand second vowel (left and right)
                if j - 1 > i and safe_base(j - 1) + safe_base(j) in DIPHTHONGS:
                    vowel_j_indices = [j - 1, j]
                elif j + 1 < len(clusters) and safe_base(j) + safe_base(j + 1) in DIPHTHONGS:
                    vowel_j_indices = [j, j + 1]

                v1 = vowel_nucleus_from_indices(clusters, vowel_i_indices)
                v2 = vowel_nucleus_from_indices(clusters, vowel_j_indices)

                if not v1 or not v2 or v1 != v2:
                    continue


            occurrences.append({
                "kind": kind,
                "start_pos": ci['start'],
                "end_pos": cj['end'],
                "snippet": text[ci['start']:cj['end']],
                "cluster_i_text": ci['text'],
                "cluster_j_text": cj['text'],
                "line_i": ci['line'] + 1,
                "line_j": cj['line'] + 1,
                "i_index": i,
                "j_index": j,
                "intervening": intervening
            })
            break

    # --------- expand vowel segments (diphthong-aware) ----------

    for occ in occurrences:
        i_idx = occ['i_index']
        j_idx = occ['j_index']

        vowel_i_indices = [i_idx]
        vowel_j_indices = [j_idx]

        if i_idx + 1 < j_idx:
            if safe_base(i_idx) + safe_base(i_idx + 1) in DIPHTHONGS:
                vowel_i_indices = [i_idx, i_idx + 1]

        if i_idx - 1 >= 0:
            if safe_base(i_idx - 1) + safe_base(i_idx) in DIPHTHONGS:
                vowel_i_indices = [i_idx - 1, i_idx]

        if j_idx - 1 > i_idx:
            if safe_base(j_idx - 1) + safe_base(j_idx) in DIPHTHONGS:
                vowel_j_indices = [j_idx - 1, j_idx]

        if j_idx + 1 < len(clusters):
            if safe_base(j_idx) + safe_base(j_idx + 1) in DIPHTHONGS:
                if j_idx + 1 > i_idx:
                    vowel_j_indices.append(j_idx + 1)

        if set(vowel_i_indices) & set(vowel_j_indices):
            vowel_i_indices = [i_idx]
            vowel_j_indices = [k for k in vowel_j_indices if k != i_idx]

        occ['vowel_i_indices'] = vowel_i_indices
        occ['vowel_j_indices'] = vowel_j_indices
        occ['vowel_i_text'] = "".join(clusters[k]['text'] for k in vowel_i_indices)
        occ['vowel_j_text'] = "".join(clusters[k]['text'] for k in vowel_j_indices)

    # annotate clusters for HTML
    cluster_marks = defaultdict(list)
    for n, occ in enumerate(occurrences, 1):
        for k in occ['vowel_i_indices']:
            cluster_marks[k].append(n)
        for k in occ['vowel_j_indices']:
            cluster_marks[k].append(n)

    html_parts = []
    for k, cl in enumerate(clusters):
        esc = html.escape(cl['text'])
        if k in cluster_marks:
            occ_id = min(cluster_marks[k])
            occ = occurrences[occ_id - 1]
            if occ['kind'] == "across-line":
                cls = "hiatus-across"; title = "across-line hiatus"
            elif occ['kind'] == "interword":
                cls = "hiatus-inter"; title = "interword hiatus"
            else:
                cls = "hiatus-intra"; title = "intra-word hiatus"
            html_parts.append(f'<span class="{cls}" title="{html.escape(title)}">{esc}</span>')
        else:
            html_parts.append(esc)

    annotated_text = "".join(html_parts)
    return annotated_text, occurrences


# ---------------------------
# Output template (UPDATED)
# ---------------------------
HTML_TEMPLATE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Hiatus highlights</title>
<style>
body {{ font-family: serif; padding: 1rem; }}
pre.source {{ white-space: pre-wrap; font-size: 18px; line-height: 1.25; }}
.hiatus-intra {{ background: rgba(255,50,50,0.35); }}
.hiatus-inter {{ background: rgba(80,220,80,0.35); }}
.hiatus-across {{ background: rgba(80,120,255,0.35); }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
td,th {{ border:1px solid #aaa; padding:6px; }}
</style>
</head>
<body>
<h1>Hiatus highlights</h1>
<p>Red = Word Internal (I); Green = Between Words (B); Blue = Between Verses (V).</p>

<h2>Annotated Text</h2>
<pre class="source">{annotated}</pre>

<h2>Occurrences</h2>
<table>
<tr><th>#</th><th>Type</th><th>Line</th><th>Vowel 1</th><th>Vowel 2</th></tr>
{rows}
</table>

</body></html>
"""


# ---------------------------
# write output (UPDATED)
# ---------------------------
def write_outputs(annotated, occurrences, html_path, csv_path):

    def kind_short(k):
        if k == "intra-word": return "I"
        if k == "interword": return "B"
        if k == "across-line": return "V"
        return k

    rows = []
    csv_rows = []

    for n, occ in enumerate(occurrences, 1):
        k = kind_short(occ['kind'])

        # new Line column rules
        if k == "V":
            line_display = f"{occ['line_i']}-{occ['line_j']}"
        else:
            line_display = str(occ['line_i'])

        v1_html = html.escape(occ['vowel_i_text'])
        v2_html = html.escape(occ['vowel_j_text'])

        rows.append(
            f"<tr><td>{n}</td>"
            f"<td>{k}</td>"
            f"<td>{line_display}</td>"
            f"<td>{v1_html}</td>"
            f"<td>{v2_html}</td></tr>"
        )

        csv_rows.append({
            "index": n,
            "kind": k,
            "line": line_display,
            "start_pos": occ["start_pos"],
            "end_pos": occ["end_pos"],
            "vowel_i": occ["vowel_i_text"],
            "vowel_j": occ["vowel_j_text"]
        })

    html_text = HTML_TEMPLATE.format(annotated=annotated, rows="\n".join(rows))
    html_path.write_text(html_text, encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["index","kind","line","start_pos","end_pos","vowel_i","vowel_j"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in csv_rows:
            writer.writerow(r)


# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--html", default="hiatus.html")
    ap.add_argument("--csv", default="hiatus.csv")
    ap.add_argument("--max-lookahead", type=int, default=8)
    ap.add_argument("--iota-as-diphthong", action="store_true")
    args = ap.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    annotated, occ = detect_hiatus_in_text(
        text,
        treat_iota_as_diphthong=args.iota_as_diphthong,
        max_cluster_lookahead=args.max_lookahead,
        break_on_dash=options.get("break_on_dash", False),
        break_on_punctuation=options.get("break_on_punctuation", False),
        break_on_rough_second=options.get("break_on_rough_second", False),
    )
    write_outputs(annotated, occ, Path(args.html), Path(args.csv))
    print(f"Done. {len(occ)} hiatus occurrences.")
    print("HTML:", Path(args.html).resolve())
    print("CSV :", Path(args.csv).resolve())

def process(input_path: str, html_path: str, csv_path: str):
    """
    Minimal wrapper for the GUI / packaged app.

    Reads input_path, runs detect_hiatus_in_text, writes HTML+CSV,
    and RETURNS the occurrences list (so the GUI can inspect counts).
    """
    text = Path(input_path).read_text(encoding="utf-8")
    annotated, occ = detect_hiatus_in_text(text)
    write_outputs(annotated, occ, Path(html_path), Path(csv_path))
    return occ


if __name__ == "__main__":
    main()
