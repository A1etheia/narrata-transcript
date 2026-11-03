"""Score runs against a hand-checked reference and print counts only.

    compare.py <reference.txt> <run.json> [<run.json> ...] [--names <names.txt>]

The reference covers `--start` to `--end` of the audio in seconds. Without a range the
whole run is scored. Text never reaches the console, so the output is safe to share.
"""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

_TOKEN = re.compile(r"[\w'-]+")


def tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text)]


def edit_counts(reference: list[str], hypothesis: list[str]) -> dict[str, int]:
    """Count edits on a difflib alignment, close to but not exactly a minimal WER."""
    counts = {"hits": 0, "substitutions": 0, "deletions": 0, "insertions": 0}
    matcher = SequenceMatcher(a=reference, b=hypothesis, autojunk=False)
    for tag, ref_start, ref_end, hyp_start, hyp_end in matcher.get_opcodes():
        ref_len, hyp_len = ref_end - ref_start, hyp_end - hyp_start
        if tag == "equal":
            counts["hits"] += ref_len
        else:
            paired = min(ref_len, hyp_len)
            counts["substitutions"] += paired
            counts["deletions"] += ref_len - paired
            counts["insertions"] += hyp_len - paired
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
    run = json.loads(path.read_text(encoding="utf-8"))
    kept = [
        segment["text"]
        for segment in run["segments"]
        if (start is None or segment["end"] > start)
        and (end is None or segment["start"] < end)
    ]
    return tokens(" ".join(kept))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--names", type=Path)
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    args = parser.parse_args()

    reference = tokens(args.reference.read_text(encoding="utf-8"))
    lines = args.names.read_text(encoding="utf-8").splitlines() if args.names else []
    names = [phrase for line in lines if (phrase := tokens(line))]
    for run_path in args.runs:
        hypothesis = run_tokens(run_path, args.start, args.end)
        counts = edit_counts(reference, hypothesis)
        errors = counts["substitutions"] + counts["deletions"] + counts["insertions"]
        print(
            f"{run_path.parent.name}: WER {errors / len(reference):.1%}, "
            f"S {counts['substitutions']}, D {counts['deletions']}, "
            f"I {counts['insertions']}, names {name_recall(reference, hypothesis, names)}"
        )


if __name__ == "__main__":
    main()
