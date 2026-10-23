"""JSONC parsing for canonical workflow files (`base44/workflows/*.jsonc`).

Base44 names the canonical files `.jsonc`; every observed file is plain JSON,
but the extension is a contract, so we accept the JSONC superset: `//` and
`/* */` comments plus trailing commas. String-aware — a `//` inside a JSON
string is content, not a comment.

Pure stdlib on purpose: this module is imported by the compiler, which the
grammar gate loads standalone (no app package, no deps).
"""

import json


def parse_jsonc(text: str):
    """Parse JSONC text into Python values. Raises ValueError on bad input."""
    return json.loads(_strip_jsonc(text))


def _strip_jsonc(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch == ",":
            # Trailing comma: a comma whose next non-whitespace, non-comment
            # character closes the container gets dropped.
            j = i + 1
            while j < n:
                c = text[j]
                if c in " \t\r\n":
                    j += 1
                elif c == "/" and j + 1 < n and text[j + 1] == "/":
                    while j < n and text[j] != "\n":
                        j += 1
                elif c == "/" and j + 1 < n and text[j + 1] == "*":
                    j += 2
                    while j + 1 < n and not (text[j] == "*" and text[j + 1] == "/"):
                        j += 1
                    j += 2
                else:
                    break
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)
