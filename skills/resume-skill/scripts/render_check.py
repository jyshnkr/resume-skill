#!/usr/bin/env python3
"""Build a version or tailoring, render it with LibreOffice and report pages; optionally diff its text.

    python3 render_check.py full-time                      # build + render, print the page count vs the page cap
    python3 render_check.py tailoring:acme-backend --against resume.txt --expect-pages 2
    python3 render_check.py file:/tmp/draft.json --spare   # a draft outside the data folder; also report spare bullet lines
    add --out FILE to keep the built .docx (otherwise it is built in a temporary folder and removed)

--against compares the built text with a plain-text file in the shape `resume_data.py TARGET --with-contact` prints
(tab = 8 spaces, bullets start with "* "). Nothing is written to the data folder.
Stdlib only. Rendering needs LibreOffice (`soffice` or `libreoffice` on PATH); the font is settings.json output.font, and
page counts match Word only when that font is installed (Times New Roman needs Microsoft's core fonts).
Exit 0 when every requested check passes, 1 when one fails or the command line is wrong (message on stderr), 2 when
LibreOffice is missing or fails (the line says "PAGES not checked: <reason>"; pages are never guessed).
"""
import json, os, re, shutil, subprocess, sys, tempfile, zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_docx  # noqa: E402
import resume_data as rd  # noqa: E402

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def docx_lines(path):
    """Paragraph text as resume_data.py prints it: tab -> 8 spaces, list paragraphs prefixed '* '."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(f"{{{NS['w']}}}p"):
        bits = []
        for r in p.iter(f"{{{NS['w']}}}r"):  # runs only, so tab stops in the paragraph properties are skipped
            for el in r:
                if el.tag == f"{{{NS['w']}}}t":
                    bits.append(el.text or "")
                elif el.tag == f"{{{NS['w']}}}tab":
                    bits.append("        ")
        style = p.find("w:pPr/w:pStyle", NS)
        text = "".join(bits)
        if style is not None and style.get(f"{{{NS['w']}}}val") == "B":
            text = "* " + text
        if text.strip():
            out.append(text.rstrip())
    return out


class NotChecked(Exception):
    """LibreOffice is missing or failed: pages are "not checked" (exit 2), never guessed."""


def to_pdf(docx):
    """Render a copy of docx in a new temporary folder (the caller removes it); returns the PDF path."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise NotChecked("LibreOffice not installed")
    d = os.path.abspath(tempfile.mkdtemp())  # a relative TMPDIR would break the profile URL
    profile = "file://" + os.path.join(d, "lo-profile")  # own profile: parallel runs and odd HOMEs don't collide
    src = os.path.join(d, os.path.basename(docx))  # render a copy: LibreOffice's lock file never lands next to the user's file
    try:
        shutil.copyfile(docx, src)
        subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf", "--outdir", d, src],
                       env={**os.environ, "TMPDIR": d}, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        pdf = os.path.join(d, os.path.splitext(os.path.basename(docx))[0] + ".pdf")
        if not os.path.isfile(pdf):
            raise NotChecked("LibreOffice wrote no PDF")
        return pdf
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        shutil.rmtree(d, ignore_errors=True)
        raise NotChecked(f"LibreOffice failed ({type(e).__name__})")
    except NotChecked:
        shutil.rmtree(d, ignore_errors=True)
        raise


def pdf_pages(pdf):
    with open(pdf, "rb") as f:
        return len(re.findall(rb"/Type\s*/Page(?![a-z])", f.read()))


def docx_pages(docx):
    """Page count of a .docx through LibreOffice; raises NotChecked. The temporary PDF folder is always removed."""
    pdf = to_pdf(docx)
    try:
        return pdf_pages(pdf)
    finally:
        shutil.rmtree(os.path.dirname(pdf), ignore_errors=True)


def pages_of(r, path, font):
    build_docx.build(r, path, font, allow_placeholder=True)  # page counts don't depend on the contact text
    return docx_pages(path)


def spare_lines(r, cap, d, font):
    """How many one-line bullets fit before the cap is passed: filler bullets appended to the last role."""
    def fits(k):
        t = json.loads(json.dumps(r))
        t["roles"][-1]["bullets"] += ["Filler line"] * k
        return pages_of(t, os.path.join(d, f"spare{k}.docx"), font) <= cap
    lo, hi = 0, 1
    while hi <= 64 and fits(hi):
        lo, hi = hi, hi * 2
    if hi > 64:
        return lo
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    return lo


def option(a, name):
    """Value after --name, or None; a missing value is a one-line error."""
    if name not in a:
        return None
    i = a.index(name) + 1
    if i >= len(a):
        raise SystemExit(f"error: {name} needs a value")
    return a[i]


def main(a):
    target = a[0]
    against, out = option(a, "--against"), option(a, "--out")
    expect = option(a, "--expect-pages")
    if expect is not None:
        try:
            expect = int(expect)
        except ValueError:
            raise SystemExit("error: --expect-pages needs a whole number")
    try:
        r = rd.resolve(target)
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"error: cannot read {target}: {e}")
    font, cap = build_docx.default_font(), r.get("page_cap")
    with tempfile.TemporaryDirectory() as tmp:
        built = out or os.path.join(tmp, re.sub(r"\W+", "_", os.path.splitext(os.path.basename(target))[0]) + ".docx")
        build_docx.build(r, built, font, allow_placeholder=True)  # page counts don't depend on the contact text
        ok = True
        if target.startswith("file:"):
            print(f"(draft {target[5:]}: resolved against your bank; nothing in the data folder was written)")
        if against:
            try:
                with open(against, encoding="utf-8") as f:
                    want = [l.rstrip() for l in f.read().split("\n") if l.strip()]
            except OSError as e:
                raise SystemExit(f"error: cannot read {against}: {e.strerror}")
            got = docx_lines(built)
            diffs = [(i, w, g) for i, (w, g) in enumerate(zip(want, got)) if w != g]
            if diffs or len(want) != len(got):
                ok = False
                print(f"TEXT FAIL {target}: {len(got)} lines vs {len(want)} expected, {len(diffs)} differ")
                for i, w, g in diffs[:5]:
                    print(f"  line {i + 1}\n    want: {w[:120]}\n    got:  {g[:120]}")
            else:
                print(f"TEXT OK {target}: {len(got)} lines identical")
        try:
            n = docx_pages(built)
        except NotChecked as e:
            print(f"PAGES not checked {target}: {e}")
            sys.exit(2 if ok else 1)
        good = n == expect if expect else (cap is None or n <= cap)
        print(f"PAGES {'OK' if good else 'FAIL'} {target}: {n} pages ({'expected ' + str(expect) if expect else f'cap {cap}'})"
              + (f" -> {out}" if out else ""))
        if "--spare" in a and good and cap:
            try:
                k = spare_lines(r, cap, tmp, font)
                print(f"SPARE {target}: about {k} one-line bullet{'s' if k != 1 else ''} fit before page {cap + 1}"
                      f"{' (64 or more)' if k >= 64 else ''}; a 2-line bullet needs 2")
            except NotChecked as e:
                print(f"SPARE not checked {target}: {e}")
        sys.exit(0 if ok and good else 1)


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__); sys.exit(0)
    if not sys.argv[1:]:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
