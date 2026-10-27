import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORM = 'https://docs.google.com/forms/d/e/1FAIpQLSfAITZkiQE--t7hHN9d2XzLwZrGyDJy0zrLsUDTYHz-ZHQ_1A/viewform'

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = []
        self.hrefs = []
        self.words = []
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a: self.ids.append(a['id'])
        if tag == 'a': self.hrefs.append(a.get('href', ''))
    def handle_data(self, data): self.words.append(data)

class Spring27Tests(unittest.TestCase):
    def test_semester_menus_link_to_upcoming_spring_without_replacing_current_fall(self):
        for name in ('index.html', 'fall26.html', 'spring26.html', 'fall25.html',
                     'spring25.html', 'fall24.html', 'spring24.html', 'fall23.html', 'spring23.html'):
            source = (ROOT / name).read_text()
            nav = re.search(r'<nav id="nav-menu-container">[\s\S]*?</nav>', source)
            self.assertIsNotNone(nav, name)
            self.assertEqual(Page(nav.group()).hrefs.count('spring27.html'), 1, name)
            self.assertIn('Spring 2027 (upcoming)', nav.group(), name)
        index = (ROOT / 'index.html').read_text()
        self.assertIn('Explore Fall 2026', index)
        self.assertIn('Fall 2026 applications are closed', index)

    def test_unconfirmed_spring_arrangements_are_provisional(self):
        source = (ROOT / 'spring27.html').read_text()
        self.assertIn('Spring 2027 course team will be announced', source)
        self.assertIn('Planned course format', source)
        self.assertNotIn('Teams receive mentor feedback', source)
        self.assertIn('Previous Course Team (Fall 2026)', source)
        self.assertIn('does not confirm Spring participation', source)
        for section_id in ('schedule',):
            match = re.search(r'<section id="' + section_id + r'".*?</section>', source, re.S)
            assert match is not None
            section = match.group()
            self.assertNotRegex(section, r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:&nbsp;)?\d')
            self.assertNotRegex(section, r'\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b')
        index = (ROOT / 'index.html').read_text()
        self.assertIn('Explore Fall 2026', index)

    def test_upcoming_term_has_its_own_application_and_no_old_term_resources(self):
        path = ROOT / 'spring27.html'
        self.assertTrue(path.exists(), 'Spring 2027 needs a dedicated page')
        source = path.read_text()
        page = Page(source)
        text = ' '.join(page.words)
        self.assertIn('AI Studio | Spring 2027', source)
        self.assertIn('Step 1', text)
        self.assertEqual([href for href in page.hrefs if 'docs.google.com/forms/' in href], [FORM])
        self.assertIn('Step 1 is open', text)
        self.assertNotIn('Applications are not open yet', text)
        self.assertNotIn('1FAIpQLSda4gTkdJINbIhc_TLhQaGgtHSQwxC6pqAB6o55_FvcUc74dQ', source)
        self.assertIn('Step 1 alone does not complete', text)
        self.assertIn('Step 2', text)
        self.assertIn('to be announced', text.lower())
        self.assertIn('new application', text.lower())
        for old in ['qD21EGUYxMnqYsN39', '1jFbnDjcxVRTKdza8', 'qecxvq7s', '/courses/40577', '1SyC6Yrxqn9DHvM7BHzRvkugPSR8811S6dczXJ754pf0']:
            self.assertNotIn(old, source)
        for date in ['September', 'August', 'November 19', 'December 3', 'December 10']:
            self.assertNotIn(date, text)
        self.assertNotIn('drive.google.com/drive/folders/', source)
        self.assertNotIn('docs.google.com/spreadsheets/', source)
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for href in page.hrefs:
            if href.startswith('#') and len(href) > 1:
                self.assertIn(href[1:], page.ids)
        self.assertNotIn('\u2014', source)

if __name__ == '__main__': unittest.main()
