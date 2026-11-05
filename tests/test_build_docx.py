"""Seam 8 (tracer part): build_docx.py turns a version into a .docx whose text, margins and font read back from the file."""
import json, os, re, unittest, zipfile
from xml.sax.saxutils import unescape
from helpers import TmpCase, run, write, EXAMPLE


def parts(path):
    z = zipfile.ZipFile(path)
    return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def paragraphs(xml):
    out = []
    for p in re.findall(r"<w:p>(.*?)</w:p>", xml, flags=re.S):
        out.append("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, flags=re.S)))
    return out


class TracerDocxTests(TmpCase):
    def build(self, target="full-time", *extra):
        out = os.path.join(self.tmp, "out.docx")
        r = run("build_docx.py", target, out, *extra, env=self.env_for(EXAMPLE))
        return r, out

    def test_version_builds_a_docx_with_the_resume_text(self):
        r, out = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        xml = parts(out)["word/document.xml"]
        paras = paragraphs(xml)
        self.assertEqual(paras[0], "Jordan Ellis")
        self.assertIn("(555) 010-0142", paras[1])
        self.assertIn("SUMMARY", paras)
        self.assertIn("PROFESSIONAL EXPERIENCE", paras)
        self.assertTrue(any(p.startswith("Cut nightly shipment-report runtime") for p in paras))
        self.assertTrue(any(p.startswith("Senior Backend Engineer with 8+ years") for p in paras))

    def test_letter_page_half_inch_margins_and_default_font(self):
        r, out = self.build()
        p = parts(out)
        self.assertIn('w:pgSz w:w="12240" w:h="15840"', p["word/document.xml"])
        self.assertIn('w:top="720" w:right="720" w:bottom="720" w:left="720"', p["word/document.xml"])
        self.assertIn('w:ascii="Times New Roman"', p["word/styles.xml"])
        self.assertIn('<w:sz w:val="22"/>', p["word/styles.xml"])

    def test_no_contact_file_stops_the_build_unless_asked(self):
        data = self.example_copy()
        os.remove(os.path.join(data, "private", "contact.json"))
        out = os.path.join(self.tmp, "x.docx")
        r = run("build_docx.py", "full-time", out, env=self.env_for(data))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--no-contact", r.stderr)
        self.assertFalse(os.path.exists(out))
        r = run("build_docx.py", "full-time", out, "--no-contact", env=self.env_for(data))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("&lt;phone&gt;", parts(out)["word/document.xml"])

    def test_unknown_version_is_a_clear_error(self):
        r, _ = self.build("no-such-version")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("no-such-version", r.stderr)
        self.assertIn("full-time", r.stderr)  # names the versions that do exist


def docx_paragraphs(xml):
    """(text, paragraph xml) per paragraph; a run tab reads as 8 spaces, as in resume_data.render_text."""
    out = []
    for p in re.findall(r"<w:p>(.*?)</w:p>", xml, flags=re.S):
        bits = re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>|(<w:tab/>)", p, flags=re.S)
        out.append(("".join(unescape(t) if t or not tab else "        " for t, tab in bits), p))
    return out


class ReadBackTests(TmpCase):
    """Slice 8: the written file, read back, matches the resume text, page setup, links and styles."""

    def build_to(self, target, data=None, *extra):
        out = os.path.join(self.tmp, "out.docx")
        r = run("build_docx.py", target, out, *extra, env=self.env_for(data or EXAMPLE))
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def text_lines(self, target, data=None):
        r = run("resume_data.py", target, "--with-contact", env=self.env_for(data or EXAMPLE))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.rstrip("\n").split("\n")

    def test_every_paragraph_matches_the_text_view_for_each_target(self):
        for target in ("full-time", "contract", "tailoring:acme-backend"):
            with self.subTest(target=target):
                want = [l[2:] if l.startswith("* ") else l for l in self.text_lines(target)]
                got = [t for t, _ in docx_paragraphs(parts(self.build_to(target))["word/document.xml"])]
                self.assertEqual(got, want)

    def test_page_size_and_margins_and_font_size(self):
        p = parts(self.build_to("contract"))
        doc = p["word/document.xml"]
        self.assertEqual(re.findall(r'<w:pgSz w:w="(\d+)" w:h="(\d+)"', doc), [("12240", "15840")])
        self.assertEqual(re.findall(r'<w:pgMar w:top="(\d+)" w:right="(\d+)" w:bottom="(\d+)" w:left="(\d+)"', doc),
                         [("720", "720", "720", "720")])
        self.assertIn("<w:sz w:val=\"22\"/>", re.search(r"<w:rPrDefault>.*?</w:rPrDefault>", p["word/styles.xml"], re.S).group(0))

    def test_contact_and_project_links_are_hyperlinks_with_targets(self):
        p = parts(self.build_to("full-time"))
        self.assertEqual(p["word/document.xml"].count("<w:hyperlink "), 4)
        targets = re.findall(r'Target="([^"]+)" TargetMode="External"', p["word/_rels/document.xml.rels"])
        self.assertEqual(targets, ["mailto:jordan.ellis@example.com", "https://www.linkedin.com/in/jordan-ellis-example",
                                   "https://github.com/jordan-ellis-example", "https://github.com/jordan-ellis-example/specgen"])

    def test_bullets_use_style_b_and_role_title_lines_keep_with_next(self):
        doc = parts(self.build_to("full-time"))["word/document.xml"]
        paras = docx_paragraphs(doc)
        n_bullets = sum(1 for l in self.text_lines("full-time") if l.startswith("* "))
        self.assertEqual(sum('<w:pStyle w:val="B"/>' in x for _, x in paras), n_bullets)
        titles = [x for t, x in paras if t.startswith(("Senior Backend Engineer, Harbor Logistics \u2013", "Software Engineer, Brightwave Payments \u2013"))]
        self.assertEqual(len(titles), 2)
        self.assertTrue(all("<w:keepNext/>" in x for x in titles))

    def test_font_comes_from_settings_and_the_flag_wins(self):
        data = self.example_copy()
        s = self.jload(data, "settings.json")
        s["output"]["font"] = "Georgia"
        write(os.path.join(data, "settings.json"), json.dumps(s))
        self.assertIn('w:ascii="Georgia"', parts(self.build_to("full-time", data))["word/styles.xml"])
        self.assertIn('w:ascii="Arial"', parts(self.build_to("full-time", data, "--font", "Arial"))["word/styles.xml"])

    def test_two_builds_are_byte_identical(self):
        a = self.build_to("full-time")
        with open(a, "rb") as f:
            first = f.read()
        with zipfile.ZipFile(a) as z:  # the zip clock ticks every 2 s, so also pin the stored dates
            self.assertEqual({i.date_time for i in z.infolist()}, {(1980, 1, 1, 0, 0, 0)})
        os.remove(a)
        b = self.build_to("full-time")
        with open(b, "rb") as f:
            self.assertEqual(f.read(), first)

    def test_certifications_section_follows_projects_and_accepts_strings_and_records(self):
        data = self.example_copy()
        v = self.jload(data, "versions", "full-time.json")
        v["certifications"] = ["Cloud Practitioner (example)", {"name": "Solutions Architect", "issuer": "Example Cloud", "dates": "2023"}]
        write(os.path.join(data, "versions", "full-time.json"), json.dumps(v))
        paras = [t for t, _ in docx_paragraphs(parts(self.build_to("full-time", data))["word/document.xml"])]
        i = paras.index("CERTIFICATIONS")
        self.assertGreater(i, paras.index("PROJECTS"))
        self.assertEqual(paras[i + 1:], ["Cloud Practitioner (example)", "Solutions Architect Example Cloud 2023"])
        self.assertEqual(paras, [l[2:] if l.startswith("* ") else l for l in self.text_lines("full-time", data)])

    def test_empty_certifications_leave_no_heading(self):
        paras = [t for t, _ in docx_paragraphs(parts(self.build_to("full-time"))["word/document.xml"])]
        self.assertNotIn("CERTIFICATIONS", paras)


if __name__ == "__main__":
    unittest.main()
