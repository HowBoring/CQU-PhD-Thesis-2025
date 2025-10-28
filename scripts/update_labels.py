import argparse
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class LabelChange:
    file_path: Path
    line_no: int
    old_label: str
    new_label: str


HEADING_PATTERN = re.compile(r"\\(mychapter|mysection|mysubsection)\{")
LABEL_INLINE_PATTERN = re.compile(r"\\label\{([^}]*)\}")


def natural_key(name: str) -> List[object]:
    parts: List[object] = []
    for chunk in re.split(r"(\d+)", name):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(chunk.lower())
    return parts


def load_slug_map(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    mapping: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in raw_line:
            raise ValueError(f"Invalid slug map line (missing tab): {raw_line!r}")
        original, slug = raw_line.split("\t", 1)
        mapping[original.strip()] = slug.strip()
    return mapping


def clean_title(text: str) -> str:
    # Remove simple LaTeX spacing commands like \hskip {...}
    cleaned = re.sub(r"\\[a-zA-Z]+(?:\s*\{[^{}]*\})*", "", text)
    cleaned = cleaned.replace("~", " ")
    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def slugify(text: str) -> str:
    lowered = text.lower()
    normalized = (
        unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    )
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if len(normalized) > 60:
        normalized = normalized[:60].rstrip("-")
    return normalized or "section"


def ensure_reports_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def find_heading(line: str) -> Optional[Tuple[str, int, str]]:
    match = HEADING_PATTERN.search(line)
    if not match:
        return None
    command = match.group(1)
    brace_start = match.end() - 1  # index of '{'
    depth = 0
    title_chars: List[str] = []
    for idx in range(brace_start, len(line)):
        ch = line[idx]
        if ch == "{":
            depth += 1
            if depth == 1:
                continue
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return command, idx, "".join(title_chars)
        if depth >= 1:
            title_chars.append(ch)
    raise ValueError(f"Unmatched braces in line: {line!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update custom section labels.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without modifying files.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    contents_dir = repo_root / "contents"
    target_files = sorted(
        [
            path
            for path in contents_dir.iterdir()
            if path.is_file() and re.match(r"^\d-[\w-]+?_cleaned\.tex$", path.name)
        ],
        key=lambda p: natural_key(p.name),
    )

    slug_map = load_slug_map(repo_root / "tools" / "slug_map.tsv")
    generated_slugs: Dict[str, str] = {}
    changes: List[LabelChange] = []

    chapter = section = subsection = 0

    for path in target_files:
        with path.open("r", encoding="utf-8", newline="") as f:
            lines = f.readlines()

        modified = False
        idx = 0
        while idx < len(lines):
            original_line = lines[idx]
            stripped = original_line.lstrip()
            if not stripped or stripped.startswith("%"):
                idx += 1
                continue

            heading_info = find_heading(original_line)
            if not heading_info:
                idx += 1
                continue

            command, closing_pos, title = heading_info

            if command == "mychapter":
                chapter += 1
                section = 0
                subsection = 0
            elif command == "mysection":
                section += 1
                subsection = 0
            else:  # mys
                subsection += 1

            title_key = title.strip()
            slug = slug_map.get(title_key)
            if not slug:
                cleaned = clean_title(title_key)
                slug = slugify(cleaned)
                generated_slugs.setdefault(title_key, slug)

            index_suffix = ""
            if command == "mysection":
                index_suffix = f"-{section}"
            elif command == "mysubsection":
                index_suffix = f"-{section}-{subsection}"

            new_label_value = f"sec:ch{chapter}{index_suffix}-{slug}"

            current_line = original_line
            inline_match = LABEL_INLINE_PATTERN.search(current_line, pos=closing_pos + 1)
            label_line_no: int
            old_label = ""

            if inline_match:
                old_label = inline_match.group(1)
                if old_label == new_label_value:
                    idx += 1
                    continue
                start, end = inline_match.span()
                replacement = f"\\label{{{new_label_value}}}"
                current_line = current_line[:start] + replacement + current_line[end:]
                lines[idx] = current_line
                label_line_no = idx + 1
                modified = True
                changes.append(LabelChange(path, label_line_no, old_label, new_label_value))
            else:
                next_line_idx = idx + 1
                if next_line_idx < len(lines):
                    next_line = lines[next_line_idx]
                    stripped_next = next_line.lstrip()
                    if stripped_next.startswith("\\label{"):
                        inline_match = LABEL_INLINE_PATTERN.search(stripped_next)
                        if inline_match:
                            old_label = inline_match.group(1)
                            if old_label == new_label_value:
                                idx += 1
                                continue
                            indent_length = len(next_line) - len(next_line.lstrip(" \t"))
                            indent = next_line[:indent_length]
                            newline = "\r\n" if next_line.endswith("\r\n") else "\n"
                            lines[next_line_idx] = f"{indent}\\label{{{new_label_value}}}{newline}"
                            label_line_no = next_line_idx + 1
                            modified = True
                            changes.append(LabelChange(path, label_line_no, old_label, new_label_value))
                            idx += 1
                            continue

                # Insert new label line
                indent_length = len(original_line) - len(original_line.lstrip(" \t"))
                indent = original_line[:indent_length]
                newline = "\r\n" if original_line.endswith("\r\n") else "\n"
                label_line = f"{indent}\\label{{{new_label_value}}}{newline}"
                lines.insert(idx + 1, label_line)
                label_line_no = idx + 2
                modified = True
                changes.append(LabelChange(path, label_line_no, old_label, new_label_value))
                idx += 1  # Skip the inserted label line

            idx += 1

        if modified and not args.dry_run:
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copyfile(path, backup_path)
            with path.open("w", encoding="utf-8", newline="") as f:
                f.writelines(lines)

    if args.dry_run:

        for change in changes:
            rel = change.file_path.relative_to(repo_root)
            print(f"{rel}:{change.line_no} {change.old_label or '(none)'} -> {change.new_label}")
        return

    reports_dir = repo_root / "reports"
    ensure_reports_dir(reports_dir)

    changes_report = reports_dir / "labels-changes.tsv"
    with changes_report.open("w", encoding="utf-8", newline="") as f:
        f.write("file\tline\told_label\tnew_label\n")
        for change in changes:
            rel = change.file_path.relative_to(repo_root)
            old = change.old_label.replace("\t", " ") if change.old_label else ""
            new = change.new_label.replace("\t", " ")
            f.write(f"{rel}\t{change.line_no}\t{old}\t{new}\n")

    missing_report = reports_dir / "missing-slug.tsv"
    with missing_report.open("w", encoding="utf-8", newline="") as f:
        f.write("title\tslug\n")
        for title, slug in sorted(generated_slugs.items()):
            f.write(f"{title}\t{slug}\n")


if __name__ == "__main__":
    main()
