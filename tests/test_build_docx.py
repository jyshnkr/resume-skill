"""Seam 8 (tracer part): build_docx.py turns a version into a .docx whose text, margins and font read back from the file."""
import os, re, unittest, zipfile
from helpers import TmpCase, run, EXAMPLE


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


if __name__ == "__main__":
    unittest.main()
