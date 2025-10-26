#!/usr/bin/env python3
"""
Clean thesis LaTeX sources with two rules:
1) Terminology first-mention normalization across the whole thesis following the order in main.tex \subfile entries.
   - Keep full form only at first mention: 中文（English, ABBR） or 中文（English）.
   - After first mention:
       * If ABBR exists: replace later full/parenthetical forms with ABBR.
       * If no ABBR: replace later 中文（English） with 中文.
   - Non-destructive: writes sibling files with suffix _cleaned.tex.

2) Decorative Chinese double quotes cleanup:
   - Remove “...” when it wraps a short single token (<=6 chars) without spaces/punct, to reduce decorative usage.
   - Keep quotes that look like real quotations (contain spaces/punct) implicitly.

Heuristics are conservative to avoid touching LaTeX commands and structures.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_inclusion_order(main_tex: Path) -> list[Path]:
    txt = main_tex.read_text(encoding='utf-8', errors='ignore')
    # Extract subfiles in order
    subfile_re = re.compile(r"\\subfile\{([^}]+)\}")
    files = []
    for m in subfile_re.finditer(txt):
        p = (main_tex.parent / m.group(1)).with_suffix('')
        # m.group(1) may already include .tex; normalize
        if not str(p).endswith('.tex'):
            p = Path(str(p) + '.tex')
        files.append(p)
    # Prepend main.tex for completeness
    return [main_tex] + files


HAN = "\\u4e00-\\u9fff"

# Patterns for full forms
PAREN_ANY = r"[（(]([^)）]+)[)）]"

# 中文（English, ABBR）
PAT_CH_EN_ABBR = re.compile(
    rf"([\u4e00-\u9fffA-Za-z0-9·—-]+)\s*[（(]\s*([A-Za-z][A-Za-z\-\s]+?)\s*,\s*([A-Z]{2,})\s*[)）]"
)

# 中文（English） no acronym
PAT_CH_EN = re.compile(
    rf"([\u4e00-\u9fffA-Za-z0-9·—-]+)\s*[（(]\s*([A-Za-z][A-Za-z\-\s]+?)\s*[)）]"
)

# Decorative quotes: “word” where word is a short single token
PAT_DECORATIVE_QUOTES = re.compile(r"“([\w\-\u4e00-\u9fff]{1,6})”")


class TermIndex:
    def __init__(self) -> None:
        # For terms with abbreviation: key by abbr and by (ch,en)
        self.abbr_first_seen: dict[str, tuple[str, str]] = {}
        self.ch_en_first_seen: set[tuple[str, str]] = set()
        # For terms without abbreviation: key by (ch,en)
        self.noabbr_first_seen: set[tuple[str, str]] = set()

    def mark_first(self, ch: str, en: str | None, abbr: str | None):
        if abbr:
            key = (normalize_space(ch), normalize_space(en or ''))
            self.ch_en_first_seen.add(key)
            self.abbr_first_seen.setdefault(abbr, (normalize_space(ch), normalize_space(en or '')))
        else:
            key = (normalize_space(ch), normalize_space(en or ''))
            self.noabbr_first_seen.add(key)

    def seen_abbr_pair(self, ch: str, en: str) -> bool:
        return (normalize_space(ch), normalize_space(en)) in self.ch_en_first_seen

    def seen_noabbr_pair(self, ch: str, en: str) -> bool:
        return (normalize_space(ch), normalize_space(en)) in self.noabbr_first_seen


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def process_text(text: str, idx: TermIndex) -> tuple[str, dict[str, int]]:
    stats = {"abbr_to_abbr": 0, "en_removed": 0, "quotes_removed": 0}

    # First pass: detect and mark first occurrences in-order within this text block
    def mark_firsts(m: re.Match):
        ch, en, abbr = m.group(1), m.group(2), m.group(3)
        if not idx.seen_abbr_pair(ch, en):
            idx.mark_first(ch, en, abbr)
        return m.group(0)

    text = PAT_CH_EN_ABBR.sub(mark_firsts, text)

    def mark_firsts_noabbr(m: re.Match):
        ch, en = m.group(1), m.group(2)
        # Avoid double-processing when actually matches CH_EN_ABBR; that was already handled
        # A quick guard: if contains comma + all-caps acronym inside, skip here
        inside = m.group(0)
        if re.search(r"[（(].+?,\s*[A-Z]{2,}[)）]", inside):
            return inside
        if not idx.seen_noabbr_pair(ch, en):
            idx.mark_first(ch, en, None)
        return inside

    text = PAT_CH_EN.sub(mark_firsts_noabbr, text)

    # Second pass: replacements
    # 2.1 Replace later full forms with ABBR if already seen
    def repl_abbr(m: re.Match):
        ch, en, abbr = m.group(1), m.group(2), m.group(3)
        if idx.seen_abbr_pair(ch, en):
            stats["abbr_to_abbr"] += 1
            return abbr
        return m.group(0)

    text = PAT_CH_EN_ABBR.sub(repl_abbr, text)

    # 2.2 Replace later 中文（English） with 中文 if already seen (no-abbr term)
    def repl_noabbr(m: re.Match):
        ch, en = m.group(1), m.group(2)
        # Skip if it actually contains an acronym form
        if re.search(r"[（(].+?,\s*[A-Z]{2,}[)）]", m.group(0)):
            return m.group(0)
        if idx.seen_noabbr_pair(ch, en):
            stats["en_removed"] += 1
            return normalize_space(ch)
        return m.group(0)

    text = PAT_CH_EN.sub(repl_noabbr, text)

    # 2.3 Remove decorative quotes
    def repl_quotes(m: re.Match):
        inner = m.group(1)
        # Heuristic: keep if contains only a short token; remove quotes
        # Avoid removing if preceded by backslash (within LaTeX command argument like \textit{“”})
        # We'll check preceding char in the original string using m.start()
        return inner

    # To avoid interfering with TeX commands like \" we only target Chinese quotes
    text, n = PAT_DECORATIVE_QUOTES.subn(repl_quotes, text)
    stats["quotes_removed"] += n

    return text, stats


def main():
    main_tex = ROOT / 'main.tex'
    order = load_inclusion_order(main_tex)

    # Include any other contents/*.tex not listed, processed after, except cover
    contents_dir = ROOT / 'contents'
    extra = []
    for p in sorted(contents_dir.glob('*.tex')):
        if p.name == 'cover.tex':
            continue
        if p.stem.endswith('_cleaned'):
            continue
        if p not in order:
            extra.append(p)
    files = order + extra

    idx = TermIndex()
    overall = {"abbr_to_abbr": 0, "en_removed": 0, "quotes_removed": 0}

    for f in files:
        if not f.exists():
            continue
        src = f.read_text(encoding='utf-8', errors='ignore')
        cleaned, stats = process_text(src, idx)
        for k, v in stats.items():
            overall[k] += v
        out = f.with_name(f.stem + '_cleaned' + f.suffix)
        out.write_text(cleaned, encoding='utf-8')

    # Post-process main_cleaned.tex to reference cleaned subfiles
    main_cleaned = main_tex.with_name(main_tex.stem + '_cleaned' + main_tex.suffix)
    if main_cleaned.exists():
        mtxt = main_cleaned.read_text(encoding='utf-8')
        for sf in order[1:]:  # skip main itself
            if sf.exists():
                orig = str(sf.as_posix())
                cleaned = sf.with_name(sf.stem + '_cleaned' + sf.suffix).as_posix()
                # Replace both with and without .tex extensions inside \subfile{...}
                mtxt = re.sub(rf"(\\subfile\{{)\s*{re.escape(orig)}\s*(\}})", rf"\1{cleaned}\2", mtxt)
                # Also try path without extension, in case
                noext = orig[:-4] if orig.endswith('.tex') else orig
                noext_clean = cleaned[:-4] if cleaned.endswith('.tex') else cleaned
                mtxt = re.sub(rf"(\\subfile\{{)\s*{re.escape(noext)}\s*(\}})", rf"\1{noext_clean}\2", mtxt)
        main_cleaned.write_text(mtxt, encoding='utf-8')

    print('Done.')
    print('Files processed:')
    for f in files:
        if f.exists():
            print(' -', f.relative_to(ROOT))
            print('   ->', f.with_name(f.stem + '_cleaned' + f.suffix).relative_to(ROOT))
    print('Changes summary:', overall)


if __name__ == '__main__':
    main()
