"""Seam 8: export.py writes the .docx (name, label, copy folder, idempotence) and reports pages through render_check.py.

LibreOffice is not needed for most tests: a stand-in `soffice` on PATH writes a PDF with a chosen number of pages, so the
exit codes and the PAGES lines are tested everywhere. Tests that need the real LibreOffice are skipped when it is missing.
"""
import hashlib, json, os, re, shutil, stat, sys, unittest, zipfile
from helpers import TmpCase, run, write, EXAMPLE, SKILL

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
        if os.path.exists(os.path.join(d, "soffice")):
            os.remove(os.path.join(d, "soffice"))
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


def tree_hash(folder):
    h = hashlib.sha256()
    for dirpath, dirs, files in sorted(os.walk(folder)):
        dirs.sort()
        h.update(dirpath[len(folder):].encode() + b"/")
        for f in sorted(files):
            h.update(f.encode())
            with open(os.path.join(dirpath, f), "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


class SkillFolderGuardTests(ExportBase):
    """User data must never land in the skill folder: a skill update would erase it."""

    def setUp(self):
        super().setUp()
        self.skill = os.path.join(self.tmp, "skillcopy")
        shutil.copytree(SKILL, self.skill, ignore=shutil.ignore_patterns("__pycache__"))
        self.before = tree_hash(self.skill)

    def run_copy(self, script, *args, cwd=None, data=None):
        env = {**self.env_for(data or EXAMPLE), **self.fake_path(2)}
        return run(os.path.join(self.skill, "scripts", script), *args, env=env, cwd=cwd or self.skill)

    def assert_refused(self, r):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertIn("skill folder", r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(tree_hash(self.skill), self.before)

    def test_relative_outdir_run_from_inside_the_skill_folder(self):
        self.assert_refused(self.run_copy("export.py", "full-time", "out/"))
        self.assert_refused(self.run_copy("export.py", "full-time", "."))

    def test_absolute_dotdot_and_symlinked_outdirs_are_refused(self):
        link = os.path.join(self.tmp, "link-to-skill")
        os.symlink(self.skill, link)
        for outdir in (os.path.join(self.skill, "out"), os.path.join(self.tmp, "elsewhere", "..", "skillcopy", "out"),
                       os.path.join(link, "out"), os.path.join(self.skill, "scripts")):
            with self.subTest(outdir=outdir):
                self.assert_refused(self.run_copy("export.py", "full-time", outdir, cwd=self.tmp))

    def test_an_outdir_beside_the_skill_folder_is_fine(self):
        r = self.run_copy("export.py", "full-time", os.path.join(self.tmp, "skillcopy-out"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_copy_resumes_to_inside_the_skill_folder_is_refused_and_nothing_is_written(self):
        data = self.example_copy()
        s = self.jload(data, "settings.json")
        s["output"]["copy_resumes_to"] = os.path.join(self.skill, "assets")
        write(os.path.join(data, "settings.json"), json.dumps(s))
        r = self.run_copy("export.py", "full-time", self.out, data=data, cwd=self.tmp)
        self.assert_refused(r)
        self.assertFalse(os.path.exists(self.out))

    def test_render_check_out_inside_the_skill_folder_is_refused(self):
        self.assert_refused(self.run_copy("render_check.py", "full-time", "--out", "kept.docx"))
        self.assert_refused(self.run_copy("render_check.py", "full-time", "--out", os.path.join(self.skill, "x", "kept.docx"), cwd=self.tmp))


class RenderCheckBase(ExportBase):
    def check(self, *args, pages=None, fail=False, no_lo=True, cwd=None):
        env = self.env_for(EXAMPLE)
        if no_lo:
            env.update(self.fake_path(pages, fail))
        return run("render_check.py", *args, env=env, cwd=cwd)

    def text_file(self, target="full-time", edit=None):
        r = run("resume_data.py", target, "--with-contact", env=self.env_for(EXAMPLE))
        text = r.stdout if edit is None else edit(r.stdout)
        path = os.path.join(self.tmp, "want.txt")
        write(path, text)
        return path


class RenderCheckTests(RenderCheckBase):
    def test_libreoffice_missing_is_not_checked_and_exits_2(self):
        r = self.check("full-time")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(r.stdout.strip(), "PAGES not checked full-time: LibreOffice not installed")
        self.assertEqual(os.listdir(self.tmpdir), [])

    def test_page_count_against_the_cap(self):
        r = self.check("full-time", pages=2)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "PAGES OK full-time: 2 pages (cap 2)"), r.stderr)
        r = self.check("full-time", pages=3)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "PAGES FAIL full-time: 3 pages (cap 2)"))
        self.assertEqual(os.listdir(self.tmpdir), [])  # temp build and PDF folders removed

    def test_expect_pages_replaces_the_cap(self):
        r = self.check("contract", "--expect-pages", "2", pages=2)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "PAGES OK contract: 2 pages (expected 2)"), r.stderr)
        r = self.check("contract", "--expect-pages", "2", pages=3)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "PAGES FAIL contract: 3 pages (expected 2)"))

    def test_against_reports_identical_text_and_differences(self):
        r = self.check("full-time", "--against", self.text_file(), pages=2)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertRegex(r.stdout, r"(?m)^TEXT OK full-time: \d+ lines identical$")
        want = self.text_file(edit=lambda t: t.replace("Cut nightly shipment-report", "Trimmed nightly shipment-report"))
        r = self.check("full-time", "--against", want, pages=2)
        self.assertEqual(r.returncode, 1)
        self.assertRegex(r.stdout, r"(?m)^TEXT FAIL full-time: \d+ lines vs \d+ expected, 1 differ$")
        self.assertIn("want: * Trimmed nightly", r.stdout)
        r = self.check("full-time", "--against", want)  # TEXT is compared even when pages cannot be
        self.assertEqual(r.returncode, 1)
        self.assertIn("TEXT FAIL", r.stdout)

    def test_out_keeps_the_built_file_and_default_leaves_nothing(self):
        cwd = os.path.join(self.tmp, "cwd")
        os.mkdir(cwd)
        self.check("full-time", pages=1, cwd=cwd)
        self.assertEqual(os.listdir(cwd), [])
        keep = os.path.join(self.tmp, "kept.docx")
        r = self.check("full-time", "--out", keep, pages=1)
        self.assertTrue(zipfile.is_zipfile(keep))
        self.assertTrue(r.stdout.strip().endswith("-> " + keep))

    def test_spare_reports_bullet_lines_that_fit(self):
        r = self.check("full-time", "--spare", pages=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"(?m)^SPARE full-time: about 64 one-line bullets fit before page 3 \(64 or more\)")

    def test_a_draft_file_is_resolved_without_writing_the_data_folder(self):
        data = self.example_copy()
        draft = os.path.join(self.tmp, "d.json")
        shutil.copy(os.path.join(data, "jobs", "acme-backend", "tailoring.json"), draft)
        before = sorted(os.listdir(data))
        env = {**self.env_for(data), **self.fake_path(2)}
        r = run("render_check.py", "file:" + draft, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing in the data folder was written", r.stdout)
        self.assertEqual(sorted(os.listdir(data)), before)

    def test_user_mistakes_are_one_line_errors(self):
        for args, word in ((("no-such-version",), "no-such-version"),
                           (("full-time", "--against", os.path.join(self.tmp, "nope.txt")), "nope.txt"),
                           (("full-time", "--expect-pages", "two"), "--expect-pages"),
                           (("full-time", "--against"), "--against")):
            with self.subTest(args=args):
                r = self.check(*args, pages=1)
                self.assertEqual(r.returncode, 1)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn(word, r.stderr)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_help_prints_the_docstring(self):
        r = run("render_check.py", "-h")
        self.assertEqual(r.returncode, 0)
        self.assertIn("PAGES not checked", r.stdout)


@unittest.skipUnless(HAVE_LO, "needs LibreOffice (soffice) on PATH")
class RealRenderCheckTests(RenderCheckBase):
    """The same command with the real LibreOffice: page count, --expect-pages and --spare."""

    def test_real_page_count_and_expect_pages(self):
        r = self.check("contract", no_lo=False)
        m = re.search(r"^PAGES OK contract: (\d+) pages \(cap 3\)$", r.stdout, re.M)
        self.assertTrue(m, r.stdout + r.stderr)
        n = int(m.group(1))
        self.assertEqual(self.check("contract", "--expect-pages", str(n), no_lo=False).returncode, 0)
        self.assertEqual(self.check("contract", "--expect-pages", str(n + 1), no_lo=False).returncode, 1)

    def test_real_spare(self):
        r = self.check("contract", "--spare", no_lo=False)
        self.assertRegex(r.stdout, r"(?m)^SPARE contract: about \d+ one-line bullets? fit before page 4")


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
