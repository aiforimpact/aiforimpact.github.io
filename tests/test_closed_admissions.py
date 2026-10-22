"""Fall 2026 admissions messaging regression tests, using only the stdlib.

Run with: python3 -m unittest discover -s tests -p 'test_*.py' -v
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    """Collect visible copy, links, regions, and all fragment IDs.

    Honor hidden attributes and inline display:none/visibility:hidden only;
    external CSS and stylesheet rules are not evaluated.
    """

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}
    BLOCK_TAGS = {"address", "article", "aside", "blockquote", "body", "br",
                  "dd", "details", "div", "dl", "dt", "fieldset", "figcaption",
                  "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5",
                  "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
                  "section", "summary", "table", "tbody", "td", "tfoot", "th",
                  "thead", "tr", "ul"}
    HIDDEN_STYLE = re.compile(
        r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)"
        r"\s*(?:!\s*important\s*)?(?:;|$)", re.IGNORECASE)

    def __init__(self, name=None, *, html=None):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.regions = {}
        self.ids = set()
        self.links = []
        if html is None:
            if name is None:
                raise ValueError("Provide a page name or raw HTML")
            html = (ROOT / name).read_text(encoding="utf-8")
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") is not None:
            self.ids.add(attrs["id"])
        hidden = (bool(self.stack and self.stack[-1]["hidden"])
                  or tag in {"script", "style"} or "hidden" in attrs
                  or bool(self.HIDDEN_STYLE.search(attrs.get("style") or "")))
        entry = {"tag": tag, "attrs": attrs, "parts": [], "hidden": hidden}
        if not hidden:
            if tag in self.BLOCK_TAGS:
                self.handle_data(" ")
            if tag == "a":
                self.links.append(entry)
        if tag not in self.VOID_TAGS:
            self.stack.append(entry)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                if not self.stack[index]["hidden"] and tag in self.BLOCK_TAGS:
                    self.handle_data(" ")
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1]["hidden"]:
            return
        self.parts.append(data)
        for entry in self.stack:
            entry["parts"].append(data)
            region = entry["attrs"].get("id")
            if region:
                self.regions.setdefault(region, []).append(data)

    @staticmethod
    def normalize(parts):
        return " ".join("".join(parts).split())

    @property
    def text(self):
        return self.normalize(self.parts)

    def region(self, name):
        return self.normalize(self.regions.get(name, []))

    def link_pairs(self):
        return [(link["attrs"].get("href", ""), self.normalize(link["parts"]))
                for link in self.links]


class ClosedAdmissionsTests(unittest.TestCase):
    def assert_no_application_urls(self, page):
        for href, label in page.link_pairs():
            with self.subTest(href=href, label=label):
                url = urlsplit(href)
                host = (url.hostname or "").lower().rstrip(".")
                path = url.path.rstrip("/")
                prohibited = (
                    host == "forms.gle"
                    or (host == "docs.google.com"
                        and (path == "/forms" or path.startswith("/forms/")))
                    or (host == "luma.com"
                        and (path == "/qecxvq7s" or path.startswith("/qecxvq7s/")))
                )
                self.assertFalse(prohibited, f"Active application URL: {href}")

    def test_homepage_directs_to_current_course_without_join_invitation(self):
        page = Page("index.html")
        self.assert_no_application_urls(page)
        self.assertNotRegex(page.text, r"(?i)\bapply\b|\bjoin (?:this|the Fall 2026) class\b")
        self.assertIn("Fall 2026 applications are closed", page.text)
        self.assertTrue(any(href.endswith("fall26.html") for href, _ in page.link_pairs()))
        self.assertTrue(any(href.endswith("spring26.html") for href, _ in page.link_pairs()))

    def test_fall26_consistently_closes_admissions_and_routes_students_to_resources(self):
        page = Page("fall26.html")
        self.assert_no_application_urls(page)
        self.assertIn("Fall 2026 applications are closed", page.region("intro"))
        self.assertIn("Fall 2026 applications are closed", page.region("admissions"))
        self.assertIn("Can I still apply for Fall 2026?", page.region("faq"))
        self.assertIn("Applications are closed", page.region("faq"))
        self.assertNotRegex(page.text, re.compile(
            r"how to apply|application steps|application waves|priority wave|second wave|"
            r"final wave|rolling basis|apply early|welcome to apply|who should apply|"
            r"before you submit|view details and register|is scheduled for August|"
            r"reviewed in waves|late applications|in each wave", re.IGNORECASE))
        for href, label in page.link_pairs():
            with self.subTest(href=href, label=label):
                self.assertNotRegex(label, r"(?i)apply|application steps|register")
        # Named hero regions contain both student destinations, irrespective of styling.
        self.assertIn("Course Schedule", page.region("intro"))
        self.assertIn("Canvas", page.region("intro"))
        self.assertIn(("#course", "Course Schedule"), page.link_pairs())
        self.assertIn(("https://canvas.mit.edu/courses/40577", "Canvas"), page.link_pairs())

    def test_fall26_preserves_student_milestones_and_navigation_targets(self):
        page = Page("fall26.html")
        self.assertIn("Thursday, December 3, 2026", page.region("schedule"))
        self.assertIn("Thursday, November 19, 2026", page.region("schedule"))
        self.assertIn("1. Individual Agent", page.region("projects"))
        self.assertIn("2. Multi-Agent Team", page.region("projects"))
        self.assertIn("3. Agentic Organization", page.region("projects"))
        self.assertIn("December 3, 2026", page.region("projects"))
        self.assertIn("Ramesh Raskar", page.region("speakers"))
        self.assertIn("Nikhil Behari", page.region("speakers"))
        for href, _ in page.link_pairs():
            if href.startswith("#") and href != "#":
                with self.subTest(href=href):
                    self.assertIn(href[1:], page.ids)


class ParserFixtureTests(unittest.TestCase):
    @staticmethod
    def page(html):
        return Page(html=html)

    def test_comments_entities_void_inline_and_empty_targets(self):
        page = self.page('''<main id="intro"><!-- not visible -->
            <script>not visible <a href="bad">Apply</a></script>
            <style>.hidden { display: none; }</style>
            <p>Fish &amp; chips<span>!</span><br>Next<img alt="not text">.</p>
            <p>App<span>ly</span> now</p><a href="#empty">Go<span>!</span></a>
            <a id="empty"></a><input id="void-target"><span hidden>secret</span>
            </main>''')
        self.assertEqual(page.text, "Fish & chips! Next. Apply now Go!")
        self.assertEqual(page.region("intro"), page.text)
        self.assertEqual(page.link_pairs(), [("#empty", "Go!"), ("", "")])

    def test_inline_invitation_cannot_bypass_visible_text_check(self):
        page = self.page("<p>App<span>ly</span> now</p>")
        self.assertRegex(page.text, r"(?i)\bapply\b")

    def test_block_boundaries_separate_text_without_splitting_inline_words(self):
        page = self.page('<section id="intro"><p>Fall 2026</p>'
                         '<div>applications are <strong>closed</strong></div>'
                         '<hr><p>Resources</p></section>')
        self.assertEqual(page.text, "Fall 2026 applications are closed Resources")
        self.assertEqual(page.region("intro"), page.text)

    def test_hidden_subtrees_cannot_supply_closure_notice_or_links(self):
        for attrs in ('hidden', 'hidden="false"',
                      'style="display: none"',
                      'style="color:red; DISPLAY : NONE !important;"',
                      'style="visibility: hidden"'):
            with self.subTest(attrs=attrs):
                page = self.page(f'<main id="intro"><div {attrs}>'
                                 '<b>Fall 2026 applications are closed</b>'
                                 '<a href="https://forms.gle/test">Apply</a>'
                                 '</div><p>Visible</p></main>')
                self.assertEqual(page.text, "Visible")
                self.assertEqual(page.region("intro"), "Visible")
                self.assertEqual(page.link_pairs(), [])

    def test_all_ids_include_empty_void_and_hidden_fragment_targets(self):
        page = self.page('<a href="#empty">Jump</a><a id="empty"></a>'
                         '<input id="void-target"><div hidden id="hidden-target"></div>')
        self.assertTrue({"empty", "void-target", "hidden-target"} <= page.ids)
        for href, _ in page.link_pairs():
            if href.startswith("#"):
                self.assertIn(href[1:], page.ids)


class PagePolicyFixtureTests(unittest.TestCase):
    def check_with_link(self, filename, href):
        html = (ROOT / filename).read_text(encoding="utf-8")
        method = ("test_homepage_directs_to_current_course_without_join_invitation"
                  if filename == "index.html" else
                  "test_fall26_consistently_closes_admissions_and_routes_students_to_resources")
        case = ClosedAdmissionsTests(method)
        with patch.object(Path, "read_text", return_value=html + f'<a href="{href}">Resources</a>'):
            getattr(case, method)()

    def test_both_pages_reject_application_urls_with_normalized_hosts(self):
        for filename in ("index.html", "fall26.html"):
            for href in ("https://forms.gle/test", "//FORMS.GLE/test",
                         "https://user@FORMS.GLE.:443/test",
                         "https://DOCS.GOOGLE.COM/forms/d/example/viewform",
                         "//docs.google.com/forms?entry=1",
                         "https://LUMA.COM/qecxvq7s?ref=home"):
                with self.subTest(filename=filename, href=href):
                    with self.assertRaises(AssertionError):
                        self.check_with_link(filename, href)

    def test_url_checks_do_not_confuse_hostnames_with_paths_or_suffixes(self):
        for filename in ("index.html", "fall26.html"):
            for href in ("https://example.com/forms.gle",
                         "https://forms.gle.example.com/info",
                         "https://docs.google.com/document/d/notes",
                         "https://docs.google.com/forms-help",
                         "https://luma.com/qecxvq7s-not-the-event"):
                with self.subTest(filename=filename, href=href):
                    self.check_with_link(filename, href)

    def test_empty_fragment_target_is_valid_in_course_page(self):
        html = (ROOT / "fall26.html").read_text(encoding="utf-8")
        html += '<a href="#empty-fixture">Jump</a><a id="empty-fixture"></a>'
        case = ClosedAdmissionsTests(
            "test_fall26_preserves_student_milestones_and_navigation_targets")
        with patch.object(Path, "read_text", return_value=html):
            case.test_fall26_preserves_student_milestones_and_navigation_targets()


if __name__ == "__main__":
    unittest.main()
