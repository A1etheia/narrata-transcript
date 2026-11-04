"""Score runs against a hand-checked reference and print counts only.

    compare.py <reference.txt> <run.json> [<run.json> ...] [--names <names.txt>]

The reference covers `--start` to `--end` of the audio in seconds. Without a range the
whole run is scored. Text never reaches the console, so the output is safe to share.

Reference conventions: every line may start with a one-word speaker label (`Name:`),
and notes in square brackets are not speech; both are dropped. `???` marks an
inaudible stretch. It becomes a gap in the reference: words a run puts there are
counted as `absorbed` instead of insertions, so every run is scored on the same words.
"""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

_TOKEN = re.compile(r"[\w'-]+")
_LABEL = re.compile(r"^\s*[^\s:]+:", re.MULTILINE)
_NOTE = re.compile(r"\[[^\]]*\]")
_UNKNOWN = re.compile(r"\?{3,}")


def tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text)]


def reference_tokens(text: str) -> tuple[list[str], set[int]]:
    """Reference words plus the word positions where an inaudible gap sits."""
    words, gaps = [], set()
    pieces = _UNKNOWN.split(_NOTE.sub(" ", _LABEL.sub(" ", text)))
    for index, piece in enumerate(pieces):
        if index:
            gaps.add(len(words))
        words += tokens(piece)
    return words, gaps


def edit_counts(
    reference: list[str], hypothesis: list[str], gaps: set[int] = frozenset()
) -> dict[str, int]:
    """Count edits on a difflib alignment, close to but not exactly a minimal WER.

    Surplus run words in a block that touches a gap are absorbed, not inserted.
    """
    counts = dict.fromkeys(
        ("hits", "substitutions", "deletions", "insertions", "absorbed"), 0
    )
    matcher = SequenceMatcher(a=reference, b=hypothesis, autojunk=False)
    for tag, ref_start, ref_end, hyp_start, hyp_end in matcher.get_opcodes():
        ref_len, hyp_len = ref_end - ref_start, hyp_end - hyp_start
        if tag == "equal":
            counts["hits"] += ref_len
            continue
        paired = min(ref_len, hyp_len)
        counts["substitutions"] += paired
        counts["deletions"] += ref_len - paired
        at_gap = any(ref_start <= gap <= ref_end for gap in gaps)
        counts["absorbed" if at_gap else "insertions"] += hyp_len - paired
    return counts


def occurrences(text: list[str], phrase: list[str]) -> int:
    size = len(phrase)
    return sum(text[i : i + size] == phrase for i in range(len(text) - size + 1))


def name_recall(
    reference: list[str], hypothesis: list[str], names: list[list[str]]
) -> str:
    """Compare occurrences per name or phrase, capped at the reference count."""
    expected = found = 0
    for name in names:
        wanted = occurrences(reference, name)
        expected += wanted
        found += min(wanted, occurrences(hypothesis, name))
    return f"{found}/{expected}"


def run_tokens(path: Path, start: float | None, end: float | None) -> list[str]:
    """Words in the range: a word counts where it starts; a segment without word
    times counts if it overlaps the range."""
    run = json.loads(path.read_text(encoding="utf-8"))
    after = (lambda t: True) if start is None else (lambda t: t >= start)
    before = (lambda t: True) if end is None else (lambda t: t < end)
    kept = []
    for segment in run["segments"]:
        if words := segment.get("words"):
            kept += [
                w["word"] for w in words if after(w["start"]) and before(w["start"])
            ]
        elif before(segment["start"]) and (start is None or segment["end"] > start):
            kept.append(segment["text"])
    return tokens(" ".join(kept))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--names", type=Path)
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    args = parser.parse_args()

    text = args.reference.read_text(encoding="utf-8-sig")
    reference, gaps = reference_tokens(text)
    lines = args.names.read_text(encoding="utf-8").splitlines() if args.names else []
    names = [phrase for line in lines if (phrase := tokens(line))]
    for run_path in args.runs:
        hypothesis = run_tokens(run_path, args.start, args.end)
        counts = edit_counts(reference, hypothesis, gaps)
        errors = counts["substitutions"] + counts["deletions"] + counts["insertions"]
        print(
            f"{run_path.parent.name}: WER {errors / len(reference):.1%}, "
            f"S {counts['substitutions']}, D {counts['deletions']}, "
            f"I {counts['insertions']}, absorbed {counts['absorbed']}, "
            f"names {name_recall(reference, hypothesis, names)}"
        )


if __name__ == "__main__":
    main()
