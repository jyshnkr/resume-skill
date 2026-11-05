"""Seam 8: export.py writes the .docx (name, label, copy folder, idempotence) and reports pages through render_check.py.

LibreOffice is not needed for most tests: a stand-in `soffice` on PATH writes a PDF with a chosen number of pages, so the
exit codes and the PAGES lines are tested everywhere. Tests that need the real LibreOffice are skipped when it is missing.
"""
import json, os, re, shutil, stat, sys, unittest, zipfile
from helpers import TmpCase, run, write, EXAMPLE

HAVE_LO = bool(shutil.which("soffice") or shutil.which("libreoffice"))

FAKE_SOFFICE = """#!{python}
import os, sys
a = sys.argv[1:]
out = a[a.index("--outdir") + 1]
src = a[-1]
if os.environ.get("FAKE_SOFFICE_FAIL"):
    sys.exit(1)
pdf = os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".pdf")
with open(pdf, "wb") as f:
    f.write(b"%PDF-1.4\\n<< /Type /Pages /Count 9 >>\\n" + b"<< /Type /Page >>\\n" * int(os.environ["FAKE_SOFFICE_PAGES"]))
"""


class ExportBase(TmpCase):
    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.tmp, "out")
        self.tmpdir = os.path.join(self.tmp, "tmpdir")  # TMPDIR for the child: must be empty again afterwards
        os.mkdir(self.tmpdir)

    def fake_path(self, pages=None, fail=False):
        """PATH holding only a stand-in soffice (or nothing: LibreOffice missing)."""
        d = os.path.join(self.tmp, "fakebin")
        os.makedirs(d, exist_ok=True)
        if pages is not None or fail:
            f = os.path.join(d, "soffice")
            write(f, FAKE_SOFFICE.format(python=sys.executable))
            os.chmod(f, os.stat(f).st_mode | stat.S_IXUSR)
        env = {"PATH": d, "TMPDIR": self.tmpdir}
        if pages is not None:
            env["FAKE_SOFFICE_PAGES"] = str(pages)
        if fail:
            env["FAKE_SOFFICE_FAIL"] = "1"
        return env

    def export(self, *args, data=None, pages=None, fail=False, no_lo=True):
        env = self.env_for(data or EXAMPLE)
        if no_lo:
            env.update(self.fake_path(pages, fail))
        return run("export.py", *args, env=env)

    def docx_name(self, label, name="Jordan_Ellis"):
        return os.path.join(self.out, f"{name}_{label}.docx")


class ExportFileTests(ExportBase):
    def test_version_file_name_uses_the_version_name_and_the_path_is_printed(self):
        r = self.export("full-time", self.out)
        self.assertEqual(r.stdout.splitlines()[0], self.docx_name("full-time"), r.stderr)
        self.assertTrue(zipfile.is_zipfile(self.docx_name("full-time")))

    def test_tailoring_label_is_the_capitalised_slug(self):
        r = self.export("tailoring:acme-backend", self.out)
        self.assertEqual(r.stdout.splitlines()[0], self.docx_name("Acme-backend"), r.stderr)

    def test_label_flag_replaces_the_default(self):
        r = self.export("contract", self.out, "--label", "Acme")
        self.assertEqual(r.stdout.splitlines()[0], self.docx_name("Acme"), r.stderr)

    def test_label_cannot_leave_the_output_folder(self):
        r = self.export("contract", self.out, "--label", "../../x/y")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(os.listdir(self.out), ["Jordan_Ellis_.._.._x_y.docx"])
        self.assertEqual(os.listdir(self.tmp).count("x"), 0)

    def test_draft_file_target_is_labelled_from_its_file_name(self):
        data = self.example_copy()
        draft = os.path.join(self.tmp, "draft-one.json")
        shutil.copy(os.path.join(data, "jobs", "acme-backend", "tailoring.json"), draft)
        r = self.export("file:" + draft, self.out, data=data)
        self.assertEqual(r.stdout.splitlines()[0], self.docx_name("Draft-one"), r.stderr)

    def test_rerun_overwrites_with_identical_bytes_and_leaves_nothing_else(self):
        self.export("full-time", self.out)
        with open(self.docx_name("full-time"), "rb") as f:
            first = f.read()
        r = self.export("full-time", self.out)
        with open(self.docx_name("full-time"), "rb") as f:
            self.assertEqual(f.read(), first)
        self.assertEqual(os.listdir(self.out), ["Jordan_Ellis_full-time.docx"])
        self.assertEqual(r.stdout.count("Jordan_Ellis_full-time.docx"), 1)

    def test_no_contact_file_stops_before_anything_is_written(self):
        data = self.example_copy()
        os.remove(os.path.join(data, "private", "contact.json"))
        r = self.export("full-time", self.out, data=data)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--no-contact", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(os.path.exists(self.out))
        r = self.export("full-time", self.out, "--no-contact", data=data)
        self.assertTrue(os.path.exists(os.path.join(self.out, "your_name_full-time.docx")), r.stderr)

    def test_user_mistakes_are_one_line_errors(self):
        for args, word in ((("no-such-version", self.out), "no-such-version"),
                           (("file:" + os.path.join(self.tmp, "missing.json"), self.out), "missing.json"),
                           (("full-time",), "OUTDIR"),
                           (("full-time", self.out, "--label"), "--label")):
            with self.subTest(args=args):
                r = self.export(*args)
                self.assertEqual(r.returncode, 1)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn(word, r.stderr)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_help_prints_the_docstring(self):
        r = run("export.py", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("PAGES", r.stdout)


class ExportPagesTests(ExportBase):
    def test_libreoffice_missing_says_not_checked_and_exits_2_with_the_file_written(self):
        r = self.export("full-time", self.out)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(r.stdout.splitlines()[1], "PAGES not checked: LibreOffice not installed")
        self.assertTrue(os.path.exists(self.docx_name("full-time")))

    def test_libreoffice_failure_is_also_not_checked(self):
        r = self.export("full-time", self.out, fail=True)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertRegex(r.stdout.splitlines()[1], r"^PAGES not checked: LibreOffice failed")
        self.assertTrue(os.path.exists(self.docx_name("full-time")))

    def test_within_the_cap_exits_0(self):
        r = self.export("contract", self.out, pages=3)  # the contract version has a 3-page cap
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[1], "PAGES OK: 3 (cap 3)")

    def test_over_the_cap_exits_1_and_still_writes_the_file(self):
        r = self.export("contract", self.out, pages=4)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(r.stdout.splitlines()[1], "PAGES FAIL: 4 (cap 3)")
        self.assertTrue(os.path.exists(self.docx_name("contract")))

    def test_a_tailoring_uses_the_cap_of_its_base_version(self):
        r = self.export("tailoring:acme-backend", self.out, pages=3)  # base full-time: cap 2
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.splitlines()[1], "PAGES FAIL: 3 (cap 2)")

    def test_no_cap_in_the_version_is_ok_at_any_count(self):
        data = self.example_copy()
        v = self.jload(data, "versions", "contract.json")
        v["page_cap"] = None
        write(os.path.join(data, "versions", "contract.json"), json.dumps(v))
        r = self.export("contract", self.out, data=data, pages=5)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[1], "PAGES OK: 5 (no cap)")

    def test_json_output_for_each_outcome(self):
        r = self.export("contract", self.out, "--json", pages=4)
        self.assertEqual(r.returncode, 1)
        j = json.loads(r.stdout)
        self.assertEqual((j["docx"], j["pages"], j["page_cap"], j["pages_status"], j["copy"]),
                         (self.docx_name("contract"), 4, 3, "fail", None))
        r = self.export("contract", self.out, "--json")
        self.assertEqual(r.returncode, 2)
        j = json.loads(r.stdout)
        self.assertEqual((j["pages"], j["pages_status"], j["reason"]), (None, "not_checked", "LibreOffice not installed"))

    def test_only_the_output_folder_is_written_and_temp_files_are_removed(self):
        cwd = os.path.join(self.tmp, "cwd")
        os.mkdir(cwd)
        env = {**self.env_for(EXAMPLE), **self.fake_path(2)}
        r = run("export.py", "contract", self.out, env=env, cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.listdir(cwd), [])
        self.assertEqual(os.listdir(self.tmpdir), [])
        self.assertEqual(os.listdir(self.out), ["Jordan_Ellis_contract.docx"])
        self.assertFalse(any(f.endswith(".pdf") for f in os.listdir(self.out)))  # v0.1 builds .docx only


class CopyFolderTests(ExportBase):
    def data_with_copy_to(self, folder):
        data = self.example_copy()
        s = self.jload(data, "settings.json")
        s["output"]["copy_resumes_to"] = folder
        write(os.path.join(data, "settings.json"), json.dumps(s))
        return data

    def test_copy_goes_to_an_existing_folder_and_its_path_is_printed(self):
        dest = os.path.join(self.tmp, "mirror")
        os.mkdir(dest)
        r = self.export("contract", self.out, data=self.data_with_copy_to(dest), pages=2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[:2], [self.docx_name("contract"), os.path.join(dest, "Jordan_Ellis_contract.docx")])
        with open(self.docx_name("contract"), "rb") as a, open(os.path.join(dest, "Jordan_Ellis_contract.docx"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(os.listdir(dest), ["Jordan_Ellis_contract.docx"])

    def test_the_folder_is_created_when_its_parent_exists(self):
        dest = os.path.join(self.tmp, "new-mirror")
        r = self.export("contract", self.out, data=self.data_with_copy_to(dest), pages=2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(dest, "Jordan_Ellis_contract.docx")))

    def test_missing_parent_is_a_one_line_error_after_the_main_file_is_written(self):
        dest = os.path.join(self.tmp, "no-parent", "mirror")
        r = self.export("contract", self.out, data=self.data_with_copy_to(dest), pages=2)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertIn(dest, r.stderr)
        self.assertTrue(os.path.exists(self.docx_name("contract")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "no-parent")))

    def test_json_names_the_copy(self):
        dest = os.path.join(self.tmp, "mirror")
        r = self.export("contract", self.out, "--json", data=self.data_with_copy_to(dest), pages=2)
        self.assertEqual(json.loads(r.stdout)["copy"], os.path.join(dest, "Jordan_Ellis_contract.docx"))


@unittest.skipUnless(HAVE_LO, "needs LibreOffice (soffice) on PATH")
class RealLibreOfficeTests(ExportBase):
    def test_sample_versions_fit_their_caps(self):
        for target, cap in (("full-time", 2), ("contract", 3)):
            with self.subTest(target=target):
                r = self.export(target, self.out, no_lo=False)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                m = re.search(r"^PAGES OK: (\d+) \(cap %d\)$" % cap, r.stdout, re.M)
                self.assertTrue(m, r.stdout)
                self.assertGreaterEqual(int(m.group(1)), 1)

    def test_a_resume_longer_than_its_cap_fails(self):
        data = self.example_copy()
        v = self.jload(data, "versions", "contract.json")
        v["page_cap"] = 1
        for role in v["roles"]:
            role["bullet_ids"] = role["bullet_ids"] * 6  # several pages of bullets
        write(os.path.join(data, "versions", "contract.json"), json.dumps(v))
        r = self.export("contract", self.out, data=data, no_lo=False)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(?m)^PAGES FAIL: [2-9]\d* \(cap 1\)$")


if __name__ == "__main__":
    unittest.main()
