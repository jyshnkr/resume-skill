#!/usr/bin/env python3
"""Write a resume as the recruiter-ready .docx and check its page count.

    python3 export.py full-time ~/Documents/resumes                  # ~/Documents/resumes/Jordan_Ellis_full-time.docx
    python3 export.py tailoring:acme-backend ~/Documents/resumes     # .../Jordan_Ellis_Acme-backend.docx
    python3 export.py file:/tmp/draft.json ~/Documents/resumes --label Acme   # a draft outside the data folder
    python3 export.py full-time ~/Documents/resumes --no-contact     # placeholder contact line: paste the real one before sending
    add --json to print one JSON object (docx, copy, pages, page_cap, pages_status, reason) instead of lines

The name is the contact name with underscores; the label is the version name, or the tailoring slug with a capital
letter, unless --label is given (v0.1 builds .docx only: no PDF). The font is settings.json output.font. Rebuilding the
same resume overwrites the same file with the same bytes. It prints the .docx path, then the page line, which comes from
render_check.py and needs LibreOffice (`soffice` or `libreoffice` on PATH):
    PAGES OK: 2 (cap 2)  |  PAGES FAIL: 4 (cap 3)  |  PAGES not checked: LibreOffice not installed
Setting output.copy_resumes_to: a folder path; the .docx is also copied there and its path printed. The folder is created
when its parent exists. Nothing else is written outside OUTDIR (the temporary render folder is removed).
OUTDIR, and the copy folder, must not be inside the skill folder (a skill update would erase it): the run stops with a
one-line error before writing anything.
Exit 0 within the cap (or no cap), 1 over the cap or on an error (one line on stderr; a copy error comes after the main
file was written), 2 pages not checked (LibreOffice missing or failed; the .docx is still written: say pages are "not checked").
"""
import io, json, os, re, shutil, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_docx  # noqa: E402
import render_check  # noqa: E402
import resume_data as rd  # noqa: E402


def label_for(target):
    """File-name label: the version name, or the tailoring's slug (or draft file name) with a capital letter."""
    kind, _, ref = target.partition(":")
    if not ref:
        return kind
    slug = os.path.splitext(os.path.basename(ref))[0]
    return slug[:1].upper() + slug[1:]


def atomic_write(path, data):
    """Temp file in the same folder, then rename: a reader never sees half a file."""
    fd, tmp = tempfile.mkstemp(prefix=".export-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def export(target, outdir, label=None, allow_placeholder=False, root=None):
    """Write the .docx into outdir. Returns (docx path, resolved resume)."""
    render_check.refuse_skill_folder(outdir, "OUTDIR")
    copy_dest = rd.settings(root)["output"].get("copy_resumes_to")
    if copy_dest:
        render_check.refuse_skill_folder(os.path.expanduser(copy_dest), "output.copy_resumes_to")
    try:
        r = rd.resolve(target, root)
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"error: cannot read {target}: {e}")
    buf = io.BytesIO()
    build_docx.build(r, buf, build_docx.default_font(root), allow_placeholder=allow_placeholder)  # stops here without contact details
    base = re.sub(r"\W+", "_", r["name"]).strip("_") + "_" + re.sub(r"[^\w.-]+", "_", label or label_for(target))
    os.makedirs(outdir, exist_ok=True)
    docx = os.path.join(os.path.abspath(outdir), base + ".docx")
    atomic_write(docx, buf.getvalue())
    return docx, r


def copy_to_setting(docx, root=None):
    """Copy to settings output.copy_resumes_to when set. Returns the copy's path or None; raises SystemExit on a bad folder."""
    dest = rd.settings(root)["output"].get("copy_resumes_to")
    if not dest:
        return None
    dest = os.path.abspath(os.path.expanduser(dest))
    if not os.path.isdir(dest):
        if not os.path.isdir(os.path.dirname(dest)):
            raise SystemExit(f"error: output.copy_resumes_to {dest} does not exist and neither does its parent folder; "
                             "the .docx was written to OUTDIR only")
        os.mkdir(dest)
    target = os.path.join(dest, os.path.basename(docx))
    if os.path.realpath(target) == os.path.realpath(docx):
        return None
    with open(docx, "rb") as f:
        atomic_write(target, f.read())
    return target


def main(a):
    flags = {x for x in a if x.startswith("--")}
    if "--label" in a and a.index("--label") + 1 >= len(a):
        raise SystemExit("error: --label needs a name")
    label = a[a.index("--label") + 1] if "--label" in a else None
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and not (i and a[i - 1] == "--label")]
    if len(pos) != 2:
        raise SystemExit("error: usage: export.py TARGET OUTDIR [--label X] [--no-contact] [--json]")
    docx, r = export(pos[0], pos[1], label, allow_placeholder="--no-contact" in flags)
    cap = r.get("page_cap")
    res = {"docx": docx, "copy": None, "pages": None, "page_cap": cap, "pages_status": None, "reason": None}
    lines = [docx]
    try:
        res["copy"] = copy_to_setting(docx)
    except SystemExit as e:  # the main file is already written
        print(e.code, file=sys.stderr)
        sys.exit(1)
    if res["copy"]:
        lines.append(res["copy"])
    try:
        res["pages"] = render_check.docx_pages(docx)
        res["pages_status"] = "ok" if not cap or res["pages"] <= cap else "fail"
        lines.append(f"PAGES {res['pages_status'].upper()}: {res['pages']} ({'cap %d' % cap if cap else 'no cap'})")
    except render_check.NotChecked as e:
        res["pages_status"], res["reason"] = "not_checked", str(e)
        lines.append(f"PAGES not checked: {e}")
    print(json.dumps(res, indent=2) if "--json" in flags else "\n".join(lines))
    sys.exit({"ok": 0, "fail": 1, "not_checked": 2}[res["pages_status"]])


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__); sys.exit(0)
    main(sys.argv[1:])
