#!/usr/bin/env python3
"""Regression: navigation links remain readable after selection, focus, and hover.

Uses an existing Chrome debugging session, never launches another profile:
  uv run --with playwright python tests/navigation_contrast.py \
    --base-url http://127.0.0.1:8769 --output /tmp/navigation-contrast.json
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STYLE = "#nav-menu-container *, #mobile-nav * {transition: none !important;}"
READ = """a => {
  const s = getComputedStyle(a);
  let e = a, background = 'rgb(255, 255, 255)';
  while (e) {
    const b = getComputedStyle(e).backgroundColor;
    if (b !== 'rgba(0, 0, 0, 0)' && b !== 'transparent') {background = b; break;}
    e = e.parentElement;
  }
  return {text:a.textContent.trim(), href:a.getAttribute('href'),
    color:s.color, background, active:a.parentElement.classList.contains('menu-active')};
}"""


def channels(css):
    numbers = [float(x) for x in re.findall(r'[\d.]+', css)]
    if len(numbers) < 3:
        raise ValueError(f'Unexpected computed color: {css}')
    return numbers[:3], numbers[3] if len(numbers) == 4 else 1.0


def luminance(rgb):
    normalized = [v / 255 for v in rgb]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
              for v in normalized]
    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))


def contrast(data):
    foreground, alpha = channels(data['color'])
    background, _ = channels(data['background'])
    foreground = [alpha * f + (1 - alpha) * b for f, b in zip(foreground, background)]
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + .05) / (dark + .05)


def record(results, page_name, layout, state, link):
    data = link.evaluate(READ)
    ratio = contrast(data)
    results.append(dict(page=page_name, layout=layout, state=state,
                        **data, contrast=round(ratio, 3), passed=ratio >= 4.5))


def audit(browser, base, name, results):
    page = browser.contexts[0].new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.set_viewport_size({'width': 1440, 'height': 1000})
        response = page.goto(urljoin(base.rstrip('/') + '/', name), wait_until='load')
        if not response or response.status != 200:
            raise RuntimeError(f'HTTP {response.status if response else "none"}')
        page.add_style_tag(content=STYLE)
        page.wait_for_function("typeof jQuery !== 'undefined' && !!jQuery.fn.superfish")
        page.wait_for_timeout(100)
        nav = page.locator('#nav-menu-container')
        instructors = nav.locator('a[href="#speakers"]')
        if instructors.count() != 1:
            raise AssertionError(f'{name}: expected exactly one desktop Instructors link')
        parent = instructors.evaluate("a=>[...document.querySelectorAll('#nav-menu-container .nav-menu>li')].indexOf(a.closest('.nav-menu>li'))")
        top = nav.locator('.nav-menu > li > a').nth(parent)
        top.hover()
        instructors.click()
        page.evaluate("jQuery('html, body').finish()")
        page.wait_for_timeout(150)
        top.hover()
        record(results, name, 'desktop', 'after-real-instructors-click', instructors)
        for layout, selector in [('desktop', '#nav-menu-container'), ('mobile', '#mobile-nav')]:
            if layout == 'mobile':
                page.set_viewport_size({'width': 390, 'height': 844})
                toggle = page.locator('#mobile-nav-toggle')
                if toggle.count():
                    toggle.click()
                    page.wait_for_timeout(450)
            links = page.locator(selector + ' a:not([hidden] *)')
            if not links.count():
                raise AssertionError(f'{name}: no {layout} navigation links found')
            for i in range(links.count()):
                link = links.nth(i)
                for state in ['normal', 'selected', 'parent-selected', 'focus']:
                    page.mouse.move(1439 if layout == 'desktop' else 389, 900 if layout == 'desktop' else 843)
                    page.evaluate("document.activeElement?.blur()")
                    link.evaluate("""(a,state)=>{
                      const root=a.closest('#nav-menu-container, #mobile-nav');
                      root.querySelectorAll('.menu-active').forEach(e=>e.classList.remove('menu-active'));
                      if(state==='selected')a.closest('li').classList.add('menu-active');
                      if(state==='parent-selected') {
                        const ancestors=[];let e=a.closest('li');
                        while(e&&root.contains(e)){ancestors.push(e);e=e.parentElement?.closest('li');}
                        ancestors[ancestors.length-1]?.classList.add('menu-active');
                      }
                    }""", state)
                    if state == 'focus':
                        if layout == 'desktop':
                            parent = link.evaluate("a=>[...document.querySelectorAll('#nav-menu-container .nav-menu>li')].indexOf(a.closest('.nav-menu>li'))")
                            nav.locator('.nav-menu > li > a').nth(parent).hover()
                        else:
                            # Expand the mobile fixture so hidden submenus can receive focus.
                            page.locator('#mobile-nav ul ul').evaluate_all("lists=>lists.forEach(ul=>ul.style.display='block')")
                        link.focus()
                        if not link.evaluate("a=>a.matches(':focus')"):
                            raise AssertionError(f'{name}: {layout} link did not receive focus')
                    record(results, name, layout, state, link)
                if layout == 'desktop':
                    link.evaluate("""a=>{
                      const root=a.closest('#nav-menu-container');
                      root.querySelectorAll('.menu-active').forEach(e=>e.classList.remove('menu-active'));
                    }""")
                    parent = link.evaluate("a=>[...document.querySelectorAll('#nav-menu-container .nav-menu>li')].indexOf(a.closest('.nav-menu>li'))")
                    nav.locator('.nav-menu > li > a').nth(parent).hover()
                    link.hover(timeout=5000)
                    record(results, name, layout, 'hover', link)
        return errors
    finally:
        page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8769/')
    parser.add_argument('--cdp-url', default='http://127.0.0.1:9222')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pages', nargs='+')
    parser.add_argument('--append', action='store_true')
    args = parser.parse_args()
    names = args.pages or sorted(p.name for p in ROOT.glob('*.html')
                                if p.name.startswith(('spring', 'fall')) or p.name == 'index.html')
    if not names:
        raise AssertionError('No pages found to audit')
    report = json.loads(args.output.read_text()) if args.append and args.output.exists() else {'checks': [], 'page_errors': {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        for name in names:
            before = len(report['checks'])
            errors = audit(browser, args.base_url, name, report['checks'])
            report['page_errors'][name] = errors
            args.output.write_text(json.dumps(report, indent=2))
            added = report['checks'][before:]
            failures = [r for r in added if not r['passed']]
            print(json.dumps({'page': name, 'checks': len(added), 'failures': len(failures),
                              'failure_examples': failures[:2], 'page_errors': errors}), flush=True)
    failures = [r for r in report['checks'] if not r['passed']]
    print(json.dumps({'pages': len(report['page_errors']), 'checks': len(report['checks']),
                      'failures': len(failures), 'report': str(args.output)}))
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
