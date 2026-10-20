"""A very small YAML subset reader and writer.

Supports nested mappings, block sequences, scalars, quoted strings and inline
flow collections. It exists so the toolkit has no third-party dependency.
Round-tripping loses comments (values are preserved).
- mappings, sequences (block style), scalars (null, bool, int, float, str)
- quoted strings (single and double)
- inline flow lists [a, b] and empty mappings {}
- block scalars: |, |-, >, >-, >+  (blank lines inside block scalars are NOT supported)
- comments (# to end of line, outside quotes)

Not supported: anchors, tags, multi-document streams, blank lines inside
block scalars, flow mappings beyond {}, tabs for indentation.

Round-tripping loses comments (values are preserved).
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple


class YAMLError(ValueError):
    """Raised when a document cannot be parsed or dumped under the subset."""


_NULL_WORDS = {"", "null", "Null", "NULL", "~"}
_TRUE_WORDS = {"true", "True", "TRUE"}
_FALSE_WORDS = {"false", "False", "FALSE"}

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$")


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment from ``line``.

    A ``#`` is treated as a comment start only when it is outside single or
    double quotes, so quoted scalars such as ``"a#b"`` survive intact.

    Args:
        line: A single logical line of YAML-subset source.

    Returns:
        The line with any trailing comment and surrounding space removed.
    """
    out = []
    j = 0
    in_single = False
    in_double = False
    while j < len(line):
        ch = line[j]
        if in_single:
            if ch == "'":
                in_single = False
            out.append(ch)
            j += 1
            continue
        if in_double:
            if ch == "\\":
                out.append(ch)
                if j + 1 < len(line):
                    out.append(line[j + 1])
                j += 2
                continue
            if ch == '"':
                in_double = False
            out.append(ch)
            j += 1
            continue
        if ch == "'":
            in_single = True
            out.append(ch)
            j += 1
            continue
        if ch == '"':
            in_double = True
            out.append(ch)
            j += 1
            continue
        if ch == "#" and (j == 0 or line[j - 1] in (" ", "\t")):
            break
        out.append(ch)
        j += 1
    return "".join(out).rstrip()


def _split_key_value(text: str) -> Optional[Tuple[str, Optional[str]]]:
    """Split a mapping entry into its key and the remaining text.

    Args:
        text: The text following the indentation of a mapping entry.

    Returns:
        A ``(key, rest)`` tuple where ``rest`` is ``None`` when the entry has
        no inline value, or ``""`` when the value is explicitly empty.
    """
    in_single = False
    in_double = False
    j = 0
    while j < len(text):
        ch = text[j]
        if in_single:
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\":
                j += 2
                continue
            if ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == ":" and (j + 1 >= len(text) or text[j + 1] in (" ", "\t")):
                key = text[:j].strip()
                rest = text[j + 1:].strip()
                return key, (rest if rest else None)
        j += 1
    return None


def _split_commas(text: str) -> List[str]:
    """Split on commas outside quotes and brackets. Returns raw parts."""
    parts = []
    buf = []
    depth = 0
    in_single = False
    in_double = False
    j = 0
    while j < len(text):
        ch = text[j]
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
        elif in_double:
            buf.append(ch)
            if ch == "\\" and j + 1 < len(text):
                buf.append(text[j + 1])
                j += 2
                continue
            if ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
                buf.append(ch)
            elif ch == '"':
                in_double = True
                buf.append(ch)
            elif ch == "[":
                depth += 1
                buf.append(ch)
            elif ch == "]":
                depth -= 1
                buf.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        j += 1
    parts.append("".join(buf))
    return parts


class _Parser:
    def __init__(self, text: str) -> None:
        self._lines: List[Tuple[int, str]] = []
        for lineno, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if stripped in ("---", "..."):
                continue
            self._lines.append((lineno, raw))
        self._idx = 0

    def _peek(self) -> Optional[Tuple[int, str]]:
        if self._idx < len(self._lines):
            return self._lines[self._idx]
        return None

    def _indent_of(self, raw: str) -> int:
        n = 0
        # Count leading whitespace including tabs so a tab can actually be
        # detected below; previously only spaces were counted, which made
        # `raw[:n]` incapable of ever containing a tab.
        while n < len(raw) and raw[n] in " \t":
            n += 1
        if "\t" in raw[:n]:
            raise YAMLError("tabs are not allowed for indentation")
        return n

    def _parse_block_scalar(
        self, key_indent: int, style: str
    ) -> Tuple[str, int]:
        """Read a literal (``|``) or folded (``>``) block scalar.

        Block scalars capture every following line that is indented deeper than
        the owning key. Chomping indicators are not supported; a blank line
        inside the block terminates it.

        Args:
            key_indent: Indentation of the owning mapping key.
            style: Either ``"literal"`` or ``"folded"``.

        Returns:
            A ``(text, next_index)`` tuple positioned at the first line after
            the scalar.
        """
        idx = self._idx
        lines: List[str] = []
        block_indent: Optional[int] = None
        while idx < len(self._lines):
            lineno, raw = self._lines[idx]
            if raw.strip() == "":
                break
            indent = self._indent_of(raw)
            if indent <= key_indent:
                break
            if block_indent is None:
                block_indent = indent
            content = raw[block_indent:] if indent >= block_indent else raw.lstrip(" ")
            if style[0] == ">":
                # folded: join with a single space (simple folding)
                if lines:
                    lines[-1] = lines[-1] + " " + content
                else:
                    lines.append(content)
            else:
                lines.append(content)
            idx += 1
        self._idx = idx
        chomp = style[1] if len(style) > 1 else ""
        text = "\n".join(lines)
        if chomp == "-":
            return text, idx
        return text + "\n", idx

    def _parse_map(
        self,
        first: Optional[Tuple[int, str, int]] = None,
    ) -> dict:
        """Parse a block mapping.

        Args:
            first: ``(lineno, line, indent)`` for a first key line the caller
                already consumed (the dash trick in :meth:`_parse_list` and the
                document entry in :meth:`parse`). The line is still *unsplit*, so
                the key/value is extracted here exactly as for lines read from
                the stream.

        Returns:
            A ``dict`` of the parsed keys and values.
        """
        result: dict = {}
        expected_indent: Optional[int] = None
        while True:
            if first is not None:
                lineno, line, indent = first
                first = None
            else:
                peek = self._peek()
                if peek is None:
                    break
                lineno, raw = peek
                indent = self._indent_of(raw)
                line = _strip_comment(raw.strip())
                if line == "":
                    self._idx += 1
                    continue
                if line.startswith("- ") or line == "-":
                    break  # a sibling sequence ends this mapping
                if expected_indent is not None and indent < expected_indent:
                    break  # a dedent returns to the parent mapping
                self._idx += 1

            kv = _split_key_value(line)
            if kv is None:
                raise YAMLError(
                    "line %d: expected 'key: value' in mapping" % lineno
                )
            key, rest = kv

            if expected_indent is None:
                expected_indent = indent

            if rest is None:
                # nested block or null
                peek = self._peek()
                if peek is not None:
                    plineno, praw = peek
                    pindent = self._indent_of(praw)
                    pline = _strip_comment(praw.strip())
                    if pline == "":
                        result[key] = None
                        continue
                    if pindent > indent:
                        self._idx += 1
                        if pline.startswith("- ") or pline == "-":
                            result[key] = self._parse_list(
                                (plineno, pline[2:].strip(), pindent + 2)
                            )
                        else:
                            result[key] = self._parse_map(
                                (plineno, pline, pindent)
                            )
                        continue
                result[key] = None
            else:
                if rest in ("|", "|-", "|+", ">", ">-", ">+"):
                    value, _ = self._parse_block_scalar(indent, rest)
                    result[key] = value
                else:
                    result[key] = _parse_value(rest, lineno)

        return result

    def _parse_list(
        self,
        first: Optional[Tuple[int, str, int]] = None,
    ) -> list:
        """Parse a block sequence.

        Args:
            first: An already-consumed ``- item`` line, when the caller read the
                first element before descending into this helper.

        Returns:
            The parsed list of Python objects.
        """
        result: list = []
        while True:
            if first is not None:
                lineno, rest, content_indent = first
                first = None
            else:
                peek = self._peek()
                if peek is None:
                    break
                lineno, raw = peek
                indent = self._indent_of(raw)
                line = _strip_comment(raw.strip())
                if line == "":
                    self._idx += 1
                    continue
                if not (line.startswith("- ") or line == "-"):
                    break
                self._idx += 1
                rest = line[2:].strip() if line != "-" else ""
                content_indent = indent + 2

            if rest == "":
                # bare dash: nested block or null
                peek = self._peek()
                if peek is not None:
                    plineno, praw = peek
                    pindent = self._indent_of(praw)
                    pline = _strip_comment(praw.strip())
                    if pline != "" and pindent >= content_indent:
                        self._idx += 1
                        if pline.startswith("- ") or pline == "-":
                            result.append(
                                self._parse_list(
                                    (plineno, pline[2:].strip(), pindent + 2)
                                )
                            )
                        else:
                            result.append(
                                self._parse_map((plineno, pline, pindent))
                            )
                        continue
                result.append(None)
            elif _split_key_value(rest) is not None:
                # '- key: value' item: the dict's keys sit at content_indent
                key, keyrest = _split_key_value(rest)
                item: dict = {}
                if keyrest is None:
                    peek = self._peek()
                    if peek is not None:
                        plineno, praw = peek
                        pindent = self._indent_of(praw)
                        pline = _strip_comment(praw.strip())
                        if pline != "" and pindent > content_indent:
                            self._idx += 1
                            if pline.startswith("- ") or pline == "-":
                                item[key] = self._parse_list(
                                    (plineno, pline[2:].strip(), pindent + 2)
                                )
                            else:
                                item[key] = self._parse_map((plineno, pline, pindent))
                        else:
                            item[key] = None
                    else:
                        item[key] = None
                else:
                    if keyrest in ("|", "|-", "|+", ">", ">-", ">+"):
                        value, _ = self._parse_block_scalar(content_indent, keyrest)
                        item[key] = value
                    else:
                        item[key] = _parse_value(keyrest, lineno)
                # remaining sibling keys of this dict item
                while True:
                    peek = self._peek()
                    if peek is None:
                        break
                    plineno, praw = peek
                    pindent = self._indent_of(praw)
                    pline = _strip_comment(praw.strip())
                    if pline == "":
                        self._idx += 1
                        continue
                    if pindent != content_indent:
                        break
                    kv = _split_key_value(pline)
                    if kv is None:
                        break
                    skey, srest = kv
                    self._idx += 1
                    if srest is None:
                        peek2 = self._peek()
                        if peek2 is not None:
                            qlineno, qraw = peek2
                            qindent = self._indent_of(qraw)
                            qline = _strip_comment(qraw.strip())
                            if qline != "" and qindent > content_indent:
                                self._idx += 1
                                if qline.startswith("- ") or qline == "-":
                                    item[skey] = self._parse_list(
                                        (qlineno, qline[2:].strip(), qindent + 2)
                                    )
                                else:
                                    item[skey] = self._parse_map(
                                        (qlineno, qline, qindent)
                                    )
                                continue
                        item[skey] = None
                    elif srest in ("|", "|-", "|+", ">", ">-", ">+"):
                        value, _ = self._parse_block_scalar(content_indent, srest)
                        item[skey] = value
                    else:
                        item[skey] = _parse_value(srest, plineno)
                result.append(item)
            elif rest.startswith("["):
                result.append(_parse_flow_list(rest, lineno))
            elif rest == "{}":
                result.append({})
            else:
                result.append(_parse_value(rest, lineno))
        return result

    def parse(self) -> Any:
        """Parse the buffered document and return plain Python objects.

        Returns:
            The parsed object: a dict, list, or scalar.
        """
        peek = self._peek()
        if peek is None:
            return None
        lineno, raw = peek
        indent = self._indent_of(raw)
        line = _strip_comment(raw.strip())
        if line == "":
            self._idx += 1
            return self.parse()
        if line.startswith("- ") or line == "-":
            self._idx += 1
            rest = line[2:].strip() if line != "-" else ""
            return self._parse_list((lineno, rest, indent + 2))
        kv = _split_key_value(line)
        if kv is None:
            # a bare scalar document
            self._idx += 1
            return _parse_value(line, lineno)
        self._idx += 1
        return self._parse_map((lineno, line, indent))


def _parse_flow_list(text: str, lineno: int) -> list:
    if not text.startswith("[") or not text.endswith("]"):
        raise YAMLError("line %d: malformed inline list: %r" % (lineno, text))
    inner = text[1:-1].strip()
    if inner == "":
        return []
    result = []
    for part in _split_commas(inner):
        part = part.strip()
        if part == "":
            result.append(None)
        elif part == "{}":
            result.append({})
        elif part.startswith("["):
            result.append(_parse_flow_list(part, lineno))
        else:
            result.append(_parse_value(part, lineno))
    return result


def _parse_value(text: str, lineno: int) -> Any:
    if text in _NULL_WORDS:
        return None
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    if text.startswith("["):
        return _parse_flow_list(text, lineno)
    if text == "{}":
        return {}
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        try:
            return json.loads(text)
        except Exception as exc:
            raise YAMLError("line %d: bad quoted string: %s" % (lineno, exc))
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


def loads(text: str) -> Any:
    """Parse a YAML-subset document into Python objects."""
    if not isinstance(text, str):
        raise YAMLError("loads() expects a string")
    return _Parser(text).parse()


def load_file(path: str) -> Any:

    """Implement load file.
    Args:
        path: File to read.

    Returns:
        The parsed object.
    """
    with open(path, "r", encoding="utf-8") as fh:
        return loads(fh.read())


load = loads
dump_file = load_file  # replaced below


def _needs_quote(s: str) -> bool:
    if s == "":
        return True
    if s != s.strip():
        return True
    low = s.lower()
    if low in ("null", "~", "true", "false"):
        return True
    if _INT_RE.match(s) or _FLOAT_RE.match(s):
        return True
    if s[0] in "[{#&*!|>'\"%@`?":
        return True
    if s.startswith("- ") or s.endswith(":"):
        return True
    if '": ' in s or " #" in s or "\n" in s or "\t" in s:
        return True
    return False


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        if _needs_quote(value):
            return json.dumps(value, ensure_ascii=False)
        return value
    if isinstance(value, (int, float)):
        return str(value)
    raise YAMLError("cannot dump scalar of type %s" % type(value).__name__)


def _dump_flow_list(items: list) -> str:
    parts = []
    for item in items:
        if isinstance(item, (dict, list)):
            raise YAMLError("nested containers inside inline lists are not supported")
        parts.append(_format_scalar(item))
    return "[" + ", ".join(parts) + "]"


def _dump_map(mapping: dict, indent: int, lines: List[str]) -> None:
    pad = " " * indent
    for key, value in mapping.items():
        if not isinstance(key, str):
            key = str(key)
        if isinstance(value, dict):
            if not value:
                lines.append("%s%s: {}" % (pad, key))
            else:
                lines.append("%s%s:" % (pad, key))
                _dump_map(value, indent + 2, lines)
        elif isinstance(value, list):
            if not value:
                lines.append("%s%s: []" % (pad, key))
            else:
                lines.append("%s%s:" % (pad, key))
                _dump_list(value, indent + 2, lines)
        elif isinstance(value, str) and "\n" in value:
            sub = value.split("\n")
            if any(part.strip() == "" for part in sub):
                raise YAMLError(
                    "block scalar strings must not contain empty lines"
                )
            lines.append("%s%s: |" % (pad, key))
            spad = " " * (indent + 2)
            for part in sub:
                lines.append(spad + part if part else spad.rstrip())
        else:
            lines.append("%s%s: %s" % (pad, key, _format_scalar(value)))


def _dump_list(items: list, dash_indent: int, lines: List[str]) -> None:
    pad = " " * dash_indent
    content = " " * (dash_indent + 2)
    for item in items:
        if isinstance(item, dict):
            if not item:
                lines.append("%s- {}" % pad)
                continue
            fk = next(iter(item))
            fv = item[fk]
            rest = {k: v for k, v in item.items() if k != fk}
            if isinstance(fv, dict) or isinstance(fv, list) or (
                isinstance(fv, str) and "\n" in fv
            ):
                lines.append("%s-" % pad)
                _dump_map({fk: fv}, dash_indent + 2, lines)
            else:
                lines.append(
                    "%s- %s: %s" % (pad, fk, _format_scalar(fv))
                    if fv is not None
                    else "%s- %s:" % (pad, fk)
                )
            if rest:
                _dump_map(rest, dash_indent + 2, lines)
        elif isinstance(item, list):
            lines.append("%s-" % pad)
            _dump_list(item, dash_indent + 2, lines)
        elif item is None:
            lines.append("%s-" % pad)
        else:
            lines.append("%s- %s" % (pad, _format_scalar(item)))


def dumps(obj: Any) -> str:
    """Serialize Python objects to a YAML-subset document."""
    lines: List[str] = []
    if obj is None:
        lines.append("null")
    elif isinstance(obj, dict):
        if obj:
            _dump_map(obj, 0, lines)
        else:
            lines.append("{}")
    elif isinstance(obj, list):
        if obj:
            _dump_list(obj, 0, lines)
        else:
            lines.append("[]")
    else:
        lines.append(_format_scalar(obj))
    return "\n".join(lines) + "\n"


def dump_file(path: str, obj: Any) -> None:

    """Implement dump file.
    Args:
        path: Destination file.
        obj: Object to serialise.
    """
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(obj))


dump = dumps
