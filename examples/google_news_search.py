"""Search Google News through Layla's host-owned WebView and print results.

Run this script inside Layla's embedded Python runtime. It uses the
Playwright-like ``lython.page`` API; it does not make direct HTTP requests.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from typing import Any, TypeVar
from urllib.parse import urlencode

import lython
from lython import (
    LythonError,
    LythonHostError,
    LythonNativeUnavailableError,
    LythonTimeoutError,
    Page,
)


GOOGLE_SEARCH = "https://www.google.com/search"
NEWS_TARGET_ATTRIBUTE = "data-lython-google-news-target"
NEWS_TARGET_VALUE = "selected"
NEWS_TARGET_SELECTOR = f'[{NEWS_TARGET_ATTRIBUTE}="{NEWS_TARGET_VALUE}"]'
RESULT_HEADING_SELECTOR = 'a h3, a [role="heading"], a .n0jPhd, a .MBeuO'
TIMEOUT_MS = 30_000

T = TypeVar("T")

_ACCEPT_GOOGLE_CONSENT = r"""
() => {
  const acceptedLabels = new Set(['accept all', 'i agree']);
  const candidates = document.querySelectorAll(
    'button, input[type="button"], input[type="submit"]'
  );

  for (const candidate of candidates) {
    const label = (candidate.innerText || candidate.value || '')
      .trim()
      .toLowerCase();
    if (acceptedLabels.has(label)) {
      candidate.click();
      return true;
    }
  }
  return false;
}
"""

_FIND_AND_MARK_NEWS_TAB = r"""
({ attribute, marker }) => {
  const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const bodyText = normalize(document.body?.innerText).toLowerCase();
  if (location.hostname === 'sorry.google.com' ||
      bodyText.includes('unusual traffic from your computer network')) {
    return { blocked: true, url: location.href };
  }
  const candidates = [];

  for (const link of document.querySelectorAll('a[href]')) {
    const label = normalize(
      link.innerText || link.textContent || link.getAttribute('aria-label') || link.title
    );
    const normalizedLabel = label.toLowerCase();
    let parsedUrl;
    try {
      parsedUrl = new URL(link.href, location.href);
    } catch {
      continue;
    }

    const isNewsUrl = parsedUrl.searchParams.get('tbm') === 'nws' ||
      parsedUrl.searchParams.get('udm') === '5';
    const isNewsLabel = normalizedLabel === 'news' ||
      /(^|\s)news($|\s)/.test(normalizedLabel);
    if (!isNewsUrl && !isNewsLabel) continue;

    const style = window.getComputedStyle(link);
    const rect = link.getBoundingClientRect();
    const visible = style.display !== 'none' && style.visibility !== 'hidden' &&
      rect.width > 0 && rect.height > 0;
    const score = (isNewsUrl ? 100 : 0) +
      (normalizedLabel === 'news' ? 80 : isNewsLabel ? 40 : 0) +
      (visible ? 20 : 0);
    candidates.push({ link, label, parsedUrl, visible, score });
  }

  candidates.sort((left, right) => right.score - left.score);
  const best = candidates[0];
  if (!best) return false;

  for (const link of document.querySelectorAll(`[${attribute}]`)) {
    link.removeAttribute(attribute);
  }
  best.link.setAttribute(attribute, marker);
  return {
    text: best.label,
    href: best.parsedUrl.href,
    visible: best.visible,
    score: best.score,
    html: best.link.outerHTML.slice(0, 800),
    candidateCount: candidates.length,
  };
}
"""

_RESULTS_ARE_READY = r"""
selector => location.pathname.includes('/search') &&
  document.querySelectorAll(selector).length > 0
"""

_EXTRACT_RESULTS = r"""
({ limit, selector }) => {
  const results = [];
  const seen = new Set();

  for (const heading of document.querySelectorAll(selector)) {
    const link = heading.closest('a');
    const title = (heading.innerText || heading.textContent || '').trim();
    if (!link || !title || !link.href || seen.has(link.href)) continue;
    if (link.href.startsWith('https://www.google.com/search?')) continue;

    let card = link.parentElement;
    for (let depth = 0; card && depth < 4; depth += 1) {
      const text = (card.innerText || '').trim();
      if (text.length > title.length + 20) break;
      card = card.parentElement;
    }

    const lines = card
      ? (card.innerText || '').split('\n').map((line) => line.trim()).filter(Boolean)
      : [];
    const details = lines.filter((line) => line !== title).slice(0, 4);

    seen.add(link.href);
    results.push({
      title,
      url: link.href,
      details: details.join(' — '),
    });
    if (results.length >= limit) break;
  }

  return results;
}
"""

_PAGE_DIAGNOSTICS = r"""
({ resultSelector }) => {
  const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const newsCandidates = [];
  for (const link of document.querySelectorAll('a[href]')) {
    const text = normalize(
      link.innerText || link.textContent || link.getAttribute('aria-label') || link.title
    );
    const href = link.href || '';
    if (/news/i.test(text) || /(?:[?&](?:tbm=nws|udm=5)(?:&|$))/i.test(href)) {
      newsCandidates.push({
        text,
        href,
        html: link.outerHTML.slice(0, 500),
      });
    }
    if (newsCandidates.length >= 10) break;
  }

  return {
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    selectorCounts: {
      requestedResultSelector: document.querySelectorAll(resultSelector).length,
      anchorH3: document.querySelectorAll('a h3').length,
      anchorRoleHeading: document.querySelectorAll('a [role="heading"]').length,
      allHeadings: document.querySelectorAll('h1, h2, h3, [role="heading"]').length,
      anchors: document.querySelectorAll('a[href]').length,
    },
    resultHeadingSamples: Array.from(document.querySelectorAll(resultSelector))
      .slice(0, 5)
      .map((element) => ({
        text: normalize(element.innerText || element.textContent),
        html: element.outerHTML.slice(0, 500),
      })),
    newsCandidates,
    bodyTextPreview: normalize(document.body?.innerText).slice(0, 1_500),
  };
}
"""

_DETECT_GOOGLE_BLOCK = r"""
() => {
  const text = (document.body?.innerText || '').toLowerCase();
  return location.hostname === 'sorry.google.com' ||
    text.includes('unusual traffic from your computer network');
}
"""


def _notify(message: str) -> None:
    """Send non-result progress and diagnostics to Layla."""

    lython.notify(message)


def _print_page_diagnostics(page: Page) -> None:
    try:
        diagnostics = page.evaluate(
            _PAGE_DIAGNOSTICS,
            {"resultSelector": RESULT_HEADING_SELECTOR},
            timeout=5_000,
        )
        _notify(
            "[google-news] Page diagnostics:\n"
            + json.dumps(diagnostics, indent=2, ensure_ascii=False, default=str)
        )
    except Exception as diagnostic_error:
        _notify(
            "[google-news] Could not collect page diagnostics: "
            f"{type(diagnostic_error).__name__}: {diagnostic_error}"
        )


def _run_step(
    page: Page,
    name: str,
    operation: Callable[[], T],
    *,
    selector: str | None = None,
    function: str | None = None,
) -> T:
    started = time.monotonic()
    context = []
    if selector:
        context.append(f"selector={selector!r}")
    if function:
        context.append(f"function={function}")
    suffix = f" ({', '.join(context)})" if context else ""
    _notify(f"[google-news] START {name}{suffix}")

    try:
        result = operation()
    except Exception as error:
        elapsed_ms = (time.monotonic() - started) * 1_000
        _notify(
            f"[google-news] FAILED {name} after {elapsed_ms:.0f} ms{suffix}: "
            f"{type(error).__name__}: {error}"
        )
        if isinstance(error, LythonHostError):
            _notify(
                "[google-news] Host error: "
                f"code={error.code!r}, retryable={error.retryable!r}, "
                f"details={error.details!r}"
            )
        _print_page_diagnostics(page)
        raise

    elapsed_ms = (time.monotonic() - started) * 1_000
    _notify(f"[google-news] OK {name} ({elapsed_ms:.0f} ms)")
    return result


def search_google_news(query: str, limit: int = 10) -> list[dict[str, str]]:
    """Perform an interactive Google search and return visible news results."""

    if not query.strip():
        raise ValueError("query must not be empty")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    page = lython.page
    search_url = f"{GOOGLE_SEARCH}?{urlencode({'hl': 'en', 'q': query})}"
    _run_step(
        page,
        "navigate directly to Google search results",
        lambda: page.goto(search_url, timeout=TIMEOUT_MS),
        function="page.goto",
    )

    _run_step(
        page,
        "check for Google consent",
        lambda: page.evaluate(_ACCEPT_GOOGLE_CONSENT, timeout=5_000),
        function="_ACCEPT_GOOGLE_CONSENT",
    )
    _run_step(
        page,
        "confirm the Google search URL",
        lambda: page.wait_for_url("**/search**", timeout=TIMEOUT_MS),
        function="page.wait_for_url",
    )

    news_target = _run_step(
        page,
        "inspect page HTML and find the News tab",
        lambda: page.wait_for_function(
            _FIND_AND_MARK_NEWS_TAB,
            {"attribute": NEWS_TARGET_ATTRIBUTE, "marker": NEWS_TARGET_VALUE},
            timeout=TIMEOUT_MS,
        ),
        selector="a[href] whose label contains 'News' or URL has tbm=nws/udm=5",
        function="_FIND_AND_MARK_NEWS_TAB",
    )
    if not isinstance(news_target, dict):
        raise RuntimeError(
            "News-tab discovery returned an unexpected value: "
            f"{news_target!r}"
        )
    if news_target.get("blocked") is True:
        raise RuntimeError(
            "Google displayed its automated-traffic challenge; complete it in "
            "the WebView and run the search again."
        )
    _notify(
        "[google-news] Selected News candidate:\n"
        + json.dumps(news_target, indent=2, ensure_ascii=False, default=str)
    )

    _run_step(
        page,
        "click the discovered News tab",
        lambda: page.locator(NEWS_TARGET_SELECTOR).click(timeout=TIMEOUT_MS),
        selector=NEWS_TARGET_SELECTOR,
        function="Locator.click",
    )
    _run_step(
        page,
        "wait for Google News result headings",
        lambda: page.wait_for_function(
            _RESULTS_ARE_READY,
            RESULT_HEADING_SELECTOR,
            timeout=TIMEOUT_MS,
        ),
        selector=RESULT_HEADING_SELECTOR,
        function="_RESULTS_ARE_READY",
    )

    if _run_step(
        page,
        "check the News page for a Google traffic block",
        lambda: page.evaluate(_DETECT_GOOGLE_BLOCK, timeout=5_000),
        function="_DETECT_GOOGLE_BLOCK",
    ):
        raise RuntimeError(
            "Google displayed its automated-traffic challenge; complete it in "
            "the WebView and run the search again."
        )

    raw_results: Any = _run_step(
        page,
        "extract Google News results",
        lambda: page.evaluate(
            _EXTRACT_RESULTS,
            {"limit": limit, "selector": RESULT_HEADING_SELECTOR},
            timeout=TIMEOUT_MS,
        ),
        selector=RESULT_HEADING_SELECTOR,
        function="_EXTRACT_RESULTS",
    )
    if not isinstance(raw_results, list):
        raise RuntimeError("Google result extraction returned an unexpected value")

    results: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        details = item.get("details", "")
        if isinstance(title, str) and isinstance(url, str):
            results.append(
                {
                    "title": title,
                    "url": url,
                    "details": details if isinstance(details, str) else "",
                }
            )
    return results


def print_results(query: str, results: list[dict[str, str]]) -> None:
    """Print search results in a compact, readable form."""

    print(f'Google News results for "{query}":')
    if not results:
        print("No results found.")
        return

    for index, result in enumerate(results, start=1):
        print(f"\n{index}. {result['title']}")
        if result["details"]:
            print(f"   {result['details']}")
        print(f"   {result['url']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search Google News using Layla's WebView automation API."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="latest news",
        help='search query (default: "latest news")',
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="maximum number of results to print (default: 10)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        results = search_google_news(args.query, args.limit)
    except LythonNativeUnavailableError:
        print(
            "This script must run inside Layla's embedded Python runtime.",
            file=sys.stderr,
            flush=True,
        )
    except LythonTimeoutError as error:
        print(
            f"Google did not finish loading before the timeout: {error}",
            file=sys.stderr,
            flush=True,
        )
    except (LythonError, RuntimeError, ValueError) as error:
        print(f"Search failed: {error}", file=sys.stderr, flush=True)
    else:
        print_results(args.query, results)


if __name__ == "__main__":
    main()
