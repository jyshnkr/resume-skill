#!/usr/bin/env python3
"""Build a resume .docx from the data folder (a version or a tailoring). Stdlib only.

    python3 build_docx.py full-time out.docx
    python3 build_docx.py tailoring:acme-backend out.docx
    python3 build_docx.py full-time out.docx --no-contact   # placeholder contact line: paste the real one before sending

Without private/contact.json the build stops unless --no-contact is given: the file would carry "<phone>" and no
email or links.

Format (references/tailoring.md): Times New Roman 11pt, letter, 0.5in margins; bold title, italic location, dates on a
right tab at 7.5in; bold uppercase section headings with a bottom border; ● bullets at the margin with text at 0.25in;
black hyperlinks; "keep with next" on every job title and its sub-line. Bullets use one paragraph style ("B").
"""
# PDFs: CI installs Microsoft's core fonts (ttf-mscorefonts-installer), so LibreOffice embeds Times New Roman, not Liberation Serif.
import os, sys, zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_data as rd  # noqa: E402

W = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
TAB = '<w:r><w:tab/></w:r>'


def build(r, out, font="Times New Roman", allow_placeholder=False):
    if r["contact"].get("placeholder") and not allow_placeholder:
        raise SystemExit("no contact details in private/contact.json: add them, or rerun with --no-contact and replace the "
                         "placeholder contact line before sending")
    rels = []

    def run(t, b=False, i=False, sz=None):
        rp = ("<w:b/>" if b else "") + ("<w:i/>" if i else "") + (f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>' if sz else "")
        return f'<w:r>{f"<w:rPr>{rp}</w:rPr>" if rp else ""}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>'

    def link(t, url, b=False):
        if not url:
            return run(t, b=b)
        rels.append(url)
        rp = ("<w:b/>" if b else "") + '<w:color w:val="000000"/>'
        return (f'<w:hyperlink r:id="rIdL{len(rels)}" w:history="1"><w:r><w:rPr>{rp}</w:rPr>'
                f'<w:t xml:space="preserve">{escape(t)}</w:t></w:r></w:hyperlink>')

    def p(runs, style=None, jc=None, before=0, tabs=False, border=False, keep=False, after=0):
        pp = ('<w:keepNext/>' if keep else '') + (f'<w:pStyle w:val="{style}"/>' if style else '')
        if not style:
            pp += ('<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>' if border else '')
            pp += ('<w:tabs><w:tab w:val="right" w:pos="10800"/></w:tabs>' if tabs else '')
            pp += f'<w:spacing w:before="{before}" w:after="{after}" w:line="240" w:lineRule="auto"/>' if (before or after) else ''
            pp += f'<w:jc w:val="{jc}"/>' if jc else ''
        return f"<w:p>{f'<w:pPr>{pp}</w:pPr>' if pp else ''}{''.join(runs)}</w:p>"

    body = [p([run(r["name"], b=True, sz=32)], jc="center")]
    c, cr = r["contact"], [run(r["contact"]["phone"])]
    for l in c.get("links", []):
        cr += [run(" | "), link(l["text"], l.get("href"))]
    body.append(p(cr, jc="center"))

    def heading(t):
        body.append(p([run(t.upper(), b=True)], before=120, after=40, border=True))

    heading("Summary")
    body.append(p([run(r["summary"])]))
    heading("Professional Experience")
    for n, role in enumerate(r["roles"]):
        body.append(p([run(role["title"], b=True), run(" – "), run(role["location"], i=True), TAB, run(role["dates"], b=True)],
                      tabs=True, keep=True, before=0 if n == 0 else 60))
        if role["sub"]:
            body.append(p([run(role["sub"], i=True)], keep=True))
        body += [p([run(b)], style="B") for b in role["bullets"]]
    heading("Education")
    for e in r["education"]:
        body.append(p([run(e["degree"], b=True), run(", "), run(e["school"], i=True), TAB, run(e["dates"], b=True)], tabs=True))
    heading("Technical Skills")
    body += [p([run(s["label"] + ":", b=True), run(" " + s["value"])], style="B") for s in r["skills"]]
    if r["projects"]:
        heading("Projects")
    for n, pr in enumerate(r["projects"]):
        body.append(p([run(pr["title"], b=True), TAB, link(pr["link_text"], pr.get("url"), b=True)], tabs=True, keep=True,
                      before=0 if n == 0 else 60))
        body += [p([run(b)], style="B") for b in pr["bullets"]]

    sect = ('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720" '
            'w:header="360" w:footer="360" w:gutter="0"/></w:sectPr>')
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(body)}{sect}'
           '</w:body></w:document>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}><w:docDefaults><w:rPrDefault><w:rPr>'
              f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{font}" w:cs="{font}"/><w:color w:val="000000"/>'
              '<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
              '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="B"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr>'
              '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr><w:ind w:left="360" w:hanging="360"/></w:pPr></w:style>'
              '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/>'
              '</w:style></w:styles>')
    numbering = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {W}><w:abstractNum w:abstractNumId="0">'
                 '<w:multiLevelType w:val="hybridMultilevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
                 '<w:lvlText w:val="●"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr><w:rPr>'
                 '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/></w:rPr></w:lvl></w:abstractNum><w:num w:numId="1">'
                 '<w:abstractNumId w:val="0"/></w:num></w:numbering>')
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/'
             f'package/2006/relationships"><Relationship Id="rIdS" Type="{rel}/styles" Target="styles.xml"/>'
             f'<Relationship Id="rIdN" Type="{rel}/numbering" Target="numbering.xml"/>'
             + "".join(f'<Relationship Id="rIdL{i + 1}" Type="{rel}/hyperlink" Target="{escape(u)}" TargetMode="External"/>'
                       for i, u in enumerate(rels)) + '</Relationships>')
    ct_main = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          f'<Override PartName="/word/document.xml" ContentType="{ct_main}.document.main+xml"/>'
          f'<Override PartName="/word/styles.xml" ContentType="{ct_main}.styles+xml"/>'
          f'<Override PartName="/word/numbering.xml" ContentType="{ct_main}.numbering+xml"/></Types>')
    rr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/'
          f'package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="word/document.xml"/>'
          '</Relationships>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rr)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", drels)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
    return out


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__); sys.exit(0)
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    a = sys.argv[1:]
    font = a[a.index("--font") + 1] if "--font" in a else "Times New Roman"
    print(build(rd.resolve(a[0]), a[1], font, allow_placeholder="--no-contact" in a))
