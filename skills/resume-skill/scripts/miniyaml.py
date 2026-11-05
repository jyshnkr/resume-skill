#!/usr/bin/env python3
"""A small YAML reader and writer for settings.yaml. Standard library only, no network.

    python3 miniyaml.py settings.yaml      # check the file and print what it holds as JSON (exit 1 with the line number on a mistake)

It reads the part of YAML that a settings file needs: nested mappings, lists (block "- item" or flow [a, b]), lists of
mappings, quoted strings ('single' keeps backslashes as they are, so use it for patterns; "double" understands \\n \\t \\" \\\\),
null / true / false / numbers, and # comments. Mapping keys are always text, so "5: 90" is the key "5".
Not supported (and reported as an error): tabs for indentation, anchors, multi-line strings, duplicate keys.

loads(text, comments=None) fills `comments` with {key path: [comment lines above that key]}; dumps(obj, comments) writes them back,
so a settings file keeps its hints when the program rewrites it.
"""
import json, os, re, sys


class _Line:
    def __init__(self, no, indent, text, pre):
        self.no, self.indent, self.text, self.pre = no, indent, text, pre


def _err(no, msg):
    return ValueError(f"line {no}: {msg}")


def _opens(s, i, in_s, in_d):
    """True when the quote character s[i] starts a quoted text: it sits at the start of a token (after a space, [ { or ,), not inside
    a word like Austin's. A quote that closes the current quoted text is handled by the caller."""
    return not in_s and not in_d and (i == 0 or s[i - 1] in " \t[{,")


def _strip_comment(s):
    """Drop a trailing ' # comment' that is not inside quotes."""
    in_s = in_d = False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_d and ch == "\\":
            i += 2
            continue
        if in_s and ch == "'" and s[i + 1:i + 2] == "'":  # '' inside single quotes is an escaped quote, not the end
            i += 2
            continue
        if ch == "'" and (in_s or _opens(s, i, in_s, in_d)):
            in_s = not in_s
        elif ch == '"' and (in_d or _opens(s, i, in_s, in_d)):
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
        i += 1
    return s.rstrip()


def _lines(text, comments):
    out, pending, header_done = [], [], False
    for no, raw in enumerate(text.split("\n"), 1):
        raw = raw.rstrip("\r")
        lead = raw[:len(raw) - len(raw.lstrip())]
        if "\t" in lead:
            raise _err(no, "tabs are not allowed for indentation; use spaces")
        stripped = raw.strip()
        if stripped == "":
            if not header_done and pending and not out:
                comments[()] = pending  # a comment block at the very top, followed by a blank line, is the file header
                pending, header_done = [], True
            continue
        if stripped.startswith("#"):
            pending.append(stripped[1:].strip())
            continue
        out.append(_Line(no, len(lead), _strip_comment(stripped), pending))
        pending, header_done = [], True
    return out


def _split_top(s, sep=","):
    """Split on `sep` outside quotes and brackets."""
    parts, depth, cur, in_s, in_d, i = [], 0, "", False, False, 0
    while i < len(s):
        ch = s[i]
        if in_d and ch == "\\":
            cur += s[i:i + 2]
            i += 2
            continue
        if in_s and ch == "'" and s[i + 1:i + 2] == "'":  # escaped quote inside single quotes
            cur += "''"
            i += 2
            continue
        if ch == "'" and (in_s or _opens(s, i, in_s, in_d)):
            in_s = not in_s
        elif ch == '"' and (in_d or _opens(s, i, in_s, in_d)):
            in_d = not in_d
        elif not in_s and not in_d:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == sep and depth == 0:
                parts.append(cur)
                cur = ""
                i += 1
                continue
        cur += ch
        i += 1
    if cur.strip() or parts:
        parts.append(cur)
    return parts


def _find_colon(s):
    """Index of the ':' that ends a mapping key (outside quotes, followed by a space or the end), else -1."""
    in_s = in_d = False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_d and ch == "\\":
            i += 2
            continue
        if in_s and ch == "'" and s[i + 1:i + 2] == "'":  # escaped quote inside single quotes
            i += 2
            continue
        if ch == "'" and (in_s or _opens(s, i, in_s, in_d)):
            in_s = not in_s
        elif ch == '"' and (in_d or _opens(s, i, in_s, in_d)):
            in_d = not in_d
        elif ch == ":" and not in_s and not in_d and (i + 1 == len(s) or s[i + 1] == " "):
            return i
        i += 1
    return -1


_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/", "0": "\0"}


def _unquote(s, no):
    q = s[0]
    if len(s) < 2 or s[-1] != q:
        raise _err(no, f"a quoted text must end with {q}")
    body = s[1:-1]
    if q == "'":
        if re.search(r"(?<!')'(?!')", body.replace("''", "")):
            raise _err(no, "a single quote inside single quotes is written twice ('')")
        return body.replace("''", "'")
    out, i = "", 0
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            nxt = body[i + 1:i + 2]
            if nxt == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", body[i + 2:i + 6]):
                out += chr(int(body[i + 2:i + 6], 16))
                i += 6
                continue
            if nxt not in _ESC:
                raise _err(no, f"\\{nxt} is not an escape inside double quotes; put patterns in single quotes ('...') instead")
            out += _ESC[nxt]
            i += 2
            continue
        if ch == '"':
            raise _err(no, 'a double quote inside double quotes is written \\"')
        out += ch
        i += 1
    return out


def _value(s, no):
    s = s.strip()
    if s == "" or s in ("null", "~"):
        return None
    if s[0] in "'\"":
        return _unquote(s, no)
    if s[0] == "[":
        if s[-1] != "]":
            raise _err(no, "a list in [ ] must end with ]")
        return [_value(p, no) for p in _split_top(s[1:-1])]
    if s[0] == "{":
        if s[-1] != "}":
            raise _err(no, "a mapping in { } must end with }")
        d = {}
        for p in _split_top(s[1:-1]):
            c = _find_colon(p.strip())
            if c < 0:
                raise _err(no, "a { } entry needs 'key: value'")
            k = _key(p.strip()[:c], no)
            d[k] = _value(p.strip()[c + 1:], no)
        return d
    if s == "true":
        return True
    if s == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _key(k, no):
    k = k.strip()
    return _unquote(k, no) if k[:1] in "'\"" else k


class _Parser:
    def __init__(self, lines, comments):
        self.lines, self.i, self.comments = lines, 0, comments

    def block(self, path):
        ln = self.lines[self.i]
        return self.seq(ln.indent, path) if ln.text == "-" or ln.text.startswith("- ") else self.map(ln.indent, path)

    def child(self, indent, path):
        """The value under a 'key:' with nothing after it: a deeper block, a list at the same indent, or null."""
        if self.i < len(self.lines):
            nxt = self.lines[self.i]
            if nxt.indent > indent or (nxt.indent == indent and (nxt.text == "-" or nxt.text.startswith("- "))):
                return self.block(path)
        return None

    def map(self, indent, path):
        d = {}
        while self.i < len(self.lines):
            ln = self.lines[self.i]
            if ln.indent < indent:
                break
            if ln.indent > indent:
                raise _err(ln.no, "unexpected indentation")
            if ln.text == "-" or ln.text.startswith("- "):
                raise _err(ln.no, "a list item where a 'key: value' was expected")
            c = _find_colon(ln.text)
            if c < 0:
                raise _err(ln.no, "expected 'key: value'")
            key = _key(ln.text[:c], ln.no)
            if key in d:
                raise _err(ln.no, f"duplicate key {key!r}")
            if ln.pre:
                self.comments[path + (key,)] = ln.pre
            rest = ln.text[c + 1:].strip()
            self.i += 1
            d[key] = self.child(indent, path + (key,)) if rest == "" else _value(rest, ln.no)
        return d

    def seq(self, indent, path):
        items = []
        while self.i < len(self.lines):
            ln = self.lines[self.i]
            if ln.indent != indent or not (ln.text == "-" or ln.text.startswith("- ")):
                break
            rest = ln.text[1:].strip()
            if rest == "":
                self.i += 1
                items.append(self.child(indent, path))
            elif rest[0] not in "'\"[{" and _find_colon(rest) >= 0:  # "- key: value" starts a mapping item
                offset = len(ln.text) - len(rest)
                self.lines[self.i] = _Line(ln.no, indent + offset, rest, [])
                items.append(self.map(indent + offset, path))
            else:
                self.i += 1
                items.append(_value(rest, ln.no))
        return items


def loads(text, comments=None):
    comments = {} if comments is None else comments
    lines = _lines(text, comments)
    if not lines:
        return {}
    p = _Parser(lines, comments)
    top = p.block(())
    if p.i < len(lines):
        raise _err(lines[p.i].no, "unexpected content (check the indentation)")
    if not isinstance(top, dict):
        raise _err(lines[0].no, "the file must be a list of 'key: value' entries")
    return top


def load(path, comments=None):
    """Read a .yaml/.yml file with loads(), anything else as JSON."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        try:
            return loads(text, comments)
        except ValueError as e:
            raise ValueError(f"{os.path.basename(path)}: {e}")
    return json.loads(text)


# ---------- writer ----------

_PLAIN = re.compile(r"^[A-Za-z_./][A-Za-z0-9 _./+()-]*$")
_RESERVED = {"null", "true", "false", "yes", "no", "on", "off", "y", "n"}


def _scalar(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if s == "":
        return "''"
    if _PLAIN.match(s) and not s.endswith(" ") and s.lower() not in _RESERVED:
        return s
    if "\n" in s or any(ord(c) < 32 for c in s):
        return json.dumps(s, ensure_ascii=False)
    return "'" + s.replace("'", "''") + "'"


def _keytext(k):
    k = str(k)
    return k if re.fullmatch(r"[A-Za-z0-9_.-]+", k) else "'" + k.replace("'", "''") + "'"


def _flow(v):
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_keytext(k)}: {_flow(x)}" for k, x in v.items()) + "}"
    return _scalar(v)


def _dump_map(d, ind, path, comments, out):
    pad = " " * ind
    for k, v in d.items():
        for c in comments.get(path + (k,), []):
            out.append(pad + ("# " + c if c else "#"))
        key = _keytext(k)
        if isinstance(v, dict) and v:
            out.append(f"{pad}{key}:")
            _dump_map(v, ind + 2, path + (k,), comments, out)
        elif isinstance(v, list) and v and any(isinstance(x, dict) for x in v):
            out.append(f"{pad}{key}:")
            for item in v:
                if isinstance(item, dict) and item:
                    sub = []
                    _dump_map(item, ind + 4, (), {}, sub)
                    out.append(pad + "  - " + sub[0].lstrip())
                    out.extend(sub[1:])
                else:
                    out.append(f"{pad}  - {_flow(item)}")
        elif isinstance(v, list) and v and len(f"{pad}{key}: {_flow(v)}") > 110:
            out.append(f"{pad}{key}:")
            out.extend(f"{pad}  - {_flow(x)}" for x in v)
        else:
            out.append(f"{pad}{key}: {_flow(v)}")


def dumps(obj, comments=None):
    comments = comments or {}
    out = []
    if comments.get(()):
        out += ["# " + c if c else "#" for c in comments[()]]
        out.append("")
    _dump_map(obj, 0, (), comments, out)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if sys.argv[1:] and sys.argv[1] in ("-h", "--help") else 2)
    try:
        print(json.dumps(load(sys.argv[1]), indent=2))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
