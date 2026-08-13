#!/usr/bin/env python3
"""mini_yaml.py

A **very small** YAML subset loader, standard library only.

Why this exists
---------------
This skill renders ``index.yaml`` / ``lesson.yaml`` / ``evidence.yaml`` into HTML, and the
plugin's rule is *standard library only* — no PyYAML, no install step. The three schemas it
has to read are narrow and machine-written, so a subset loader is enough.

Supported
---------
- block mappings (``key: value``) nested by indentation
- block sequences (``- item``), including ``- key: value`` (a mapping inline after the dash)
  and sequences nested under a key at the same indentation as the key
- block scalars: ``|``, ``|-``, ``|+``, ``>``, ``>-``, ``>+`` (an explicit indent digit is
  accepted)
- quoted scalars (``'…'`` with ``''`` escaping, ``"…"`` with ``\\n`` / ``\\t`` / ``\\"`` /
  ``\\\\`` escapes)
- flow sequences (``[a, b]``) and flow mappings (``{a: b}``), one level, no nesting inside
  quotes tricks
- plain scalars typed as ``true`` / ``false`` / ``null`` (``~``) / int / float / str
- ``#`` comments (whole-line and trailing, outside quotes) and a leading ``---``
- plain scalars continued on more-indented following lines

NOT supported (deliberately)
----------------------------
anchors/aliases (``&`` / ``*``), tags (``!!``), multiple documents, complex keys, merge keys.
Hitting one raises ``YamlError`` with a line number rather than silently mis-parsing.
"""

from __future__ import annotations

import re
from typing import Any


class YamlError(ValueError):
    """Raised when the input uses YAML this loader deliberately does not support."""


# a line that starts a mapping entry: `key:` or `key: value` (key may be quoted)
_KEY_RE = re.compile(r"""^(?:"(?P<dq>(?:[^"\\]|\\.)*)"|'(?P<sq>(?:[^']|'')*)'|(?P<plain>[^:#\s][^:]*?))\s*:(?:\s+(?P<rest>.*))?$""")
_BLOCK_RE = re.compile(r"^(?P<style>[|>])(?P<mods>[+-]?\d?|\d?[+-]?)\s*$")
_UNSUPPORTED_RE = re.compile(r"^(?:[&*]\S|!!)")


# ---------------------------------------------------------------------------
# scalars
# ---------------------------------------------------------------------------

def _strip_comment(text: str) -> str:
    """Remove a trailing ``# comment`` that starts outside quotes."""
    out: list[str] = []
    quote: str | None = None
    prev = ""
    for ch in text:
        if quote:
            out.append(ch)
            if ch == quote and prev != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _unescape_double(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/",
                        "0": "\0"}.get(nxt, "\\" + nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_flow(body: str) -> list[str]:
    """Split ``a, b, "c, d"`` on top-level commas."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    current: list[str] = []
    for ch in body:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch in "[{":
            depth += 1
            current.append(ch)
        elif ch in "]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def _scalar(text: str, line_no: int) -> Any:
    """Parse one scalar / flow collection that sits on a single line."""
    text = _strip_comment(text).strip()
    if not text:
        return None
    if _UNSUPPORTED_RE.match(text):
        raise YamlError(f"line {line_no}: anchors, aliases and tags are not supported: {text!r}")
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return _unescape_double(text[1:-1])
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(p, line_no) for p in _split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        result: dict[str, Any] = {}
        for part in _split_flow(text[1:-1]):
            key, _, value = part.partition(":")
            result[str(_scalar(key, line_no))] = _scalar(value, line_no)
        return result
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "~"):
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", text):
        return float(text)
    return text


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


class _Reader:
    def __init__(self, text: str) -> None:
        self.lines = [l.rstrip("\n").replace("\t", "    ") for l in text.splitlines()]
        self.i = 0

    # -- low level ---------------------------------------------------------

    def _is_skippable(self, idx: int) -> bool:
        stripped = self.lines[idx].strip()
        return not stripped or stripped.startswith("#") or stripped == "---" or stripped == "..."

    def peek(self) -> tuple[int, str, int] | None:
        """Return (indent, content, line_no) of the next significant line, or None."""
        idx = self.i
        while idx < len(self.lines) and self._is_skippable(idx):
            idx += 1
        if idx >= len(self.lines):
            return None
        self.i = idx
        line = self.lines[idx]
        return _indent_of(line), line.strip(), idx + 1

    def advance(self) -> None:
        self.i += 1

    # -- block scalars -----------------------------------------------------

    def read_block_scalar(self, header: str, parent_indent: int, line_no: int) -> str:
        match = _BLOCK_RE.match(header)
        if not match:
            raise YamlError(f"line {line_no}: unsupported block scalar header {header!r}")
        style = match.group("style")
        mods = match.group("mods") or ""
        chomp = "-" if "-" in mods else ("+" if "+" in mods else "")
        digits = "".join(c for c in mods if c.isdigit())
        explicit_indent = parent_indent + int(digits) if digits else None

        raw: list[str] = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip() and _indent_of(line) <= parent_indent:
                break
            raw.append(line)
            self.i += 1
        trailing_blanks = 0
        while raw and not raw[-1].strip():
            raw.pop()
            trailing_blanks += 1
        if not raw:
            return "" if chomp == "-" else "\n"

        content_indent = explicit_indent
        if content_indent is None:
            content_indent = min(_indent_of(l) for l in raw if l.strip())
        body = [l[content_indent:] if len(l) > content_indent else "" for l in raw]

        if style == "|":
            text = "\n".join(body)
        else:  # folded
            folded: list[str] = []
            for line in body:
                if not line.strip():
                    folded.append("\n")
                elif folded and folded[-1] not in ("\n", ""):
                    folded.append(" " + line.strip())
                else:
                    folded.append(line.strip())
            text = "".join(folded).replace("\n ", "\n")

        if chomp == "-":
            return text.rstrip("\n")
        if chomp == "+":
            return text.rstrip("\n") + "\n" * (1 + trailing_blanks)
        return text.rstrip("\n") + "\n"

    # -- plain scalar continuation ----------------------------------------

    def read_continuation(self, first: str, own_indent: int) -> str:
        """Absorb more-indented plain lines that continue a plain scalar."""
        parts = [first.strip()]
        while True:
            token = self.peek()
            if token is None:
                break
            indent, content, _ = token
            if indent <= own_indent or content.startswith("- ") or content == "-":
                break
            if _KEY_RE.match(content):
                break
            parts.append(_strip_comment(content).strip())
            self.advance()
        return " ".join(p for p in parts if p)

    # -- nodes -------------------------------------------------------------

    def parse_node(self, indent: int) -> Any:
        token = self.peek()
        if token is None:
            return None
        _, content, _ = token
        if content.startswith("- ") or content == "-":
            return self.parse_sequence(indent)
        return self.parse_mapping(indent)

    def parse_mapping(self, indent: int) -> dict:
        result: dict[str, Any] = {}
        while True:
            token = self.peek()
            if token is None:
                break
            line_indent, content, line_no = token
            if line_indent < indent:
                break
            if line_indent > indent:
                raise YamlError(f"line {line_no}: unexpected indentation in mapping: {content!r}")
            if content.startswith("- ") or content == "-":
                break
            match = _KEY_RE.match(content)
            if not match:
                raise YamlError(f"line {line_no}: expected 'key: value', got {content!r}")
            key = match.group("dq")
            if key is not None:
                key = _unescape_double(key)
            elif match.group("sq") is not None:
                key = match.group("sq").replace("''", "'")
            else:
                key = match.group("plain").strip()
            rest = (match.group("rest") or "").strip()
            self.advance()

            if rest.startswith("|") or rest.startswith(">"):
                result[key] = self.read_block_scalar(rest, line_indent, line_no)
                continue
            if rest and not rest.startswith("#"):
                stripped = _strip_comment(rest).strip()
                if stripped and not stripped[0] in "[{\"'":
                    result[key] = _scalar(self.read_continuation(stripped, line_indent), line_no)
                else:
                    result[key] = _scalar(stripped, line_no)
                continue

            nxt = self.peek()
            if nxt is None:
                result[key] = None
                continue
            next_indent, next_content, _ = nxt
            if next_indent > line_indent:
                result[key] = self.parse_node(next_indent)
            elif next_indent == line_indent and (next_content.startswith("- ")
                                                 or next_content == "-"):
                result[key] = self.parse_sequence(line_indent)
            else:
                result[key] = None
        return result

    def parse_sequence(self, indent: int) -> list:
        items: list[Any] = []
        while True:
            token = self.peek()
            if token is None:
                break
            line_indent, content, line_no = token
            if line_indent != indent or not (content.startswith("- ") or content == "-"):
                break
            raw_line = self.lines[self.i]
            rest = content[1:].lstrip()
            column = len(raw_line) - len(rest) if rest else line_indent + 2

            if not rest:
                self.advance()
                nxt = self.peek()
                if nxt is not None and nxt[0] > line_indent:
                    items.append(self.parse_node(nxt[0]))
                else:
                    items.append(None)
                continue

            if rest.startswith("|") or rest.startswith(">"):
                self.advance()
                items.append(self.read_block_scalar(rest, line_indent, line_no))
                continue

            if rest.startswith("- ") or rest == "-" or _KEY_RE.match(rest):
                # rewrite the dash away and re-read the line as a nested node
                self.lines[self.i] = " " * column + rest
                items.append(self.parse_node(column))
                continue

            self.advance()
            items.append(_scalar(self.read_continuation(rest, line_indent), line_no))
        return items


def load(text: str) -> Any:
    """Parse a YAML subset document into Python data (dict / list / scalars)."""
    reader = _Reader(text)
    token = reader.peek()
    if token is None:
        return None
    return reader.parse_node(token[0])


def load_file(path: str) -> Any:
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        raise YamlError(f"file not found: {path}")
    return load(p.read_text(encoding="utf-8"))
