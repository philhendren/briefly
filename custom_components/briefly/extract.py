"""Keep only the readable paragraphs of an article page."""

from __future__ import annotations

from html.parser import HTMLParser
import re

from .const import MAX_ARTICLE_CHARS

MIN_PARAGRAPH_CHARS = 40
_SKIP_TAGS = frozenset(
    {"script", "style", "nav", "header", "footer", "aside", "form", "figure", "noscript", "svg", "button"}
)
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.article_depth = 0
        self.in_paragraph = False
        self.current: list[str] = []
        self.article_paragraphs: list[str] = []
        self.all_paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            return
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
        elif tag == "article":
            self.article_depth += 1
        elif tag == "p" and not self.skip_depth:
            self._finish()
            self.in_paragraph = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag == "article":
            self._finish()
            self.article_depth = max(0, self.article_depth - 1)
        elif tag == "p":
            self._finish()

    def handle_data(self, data: str) -> None:
        if self.in_paragraph and not self.skip_depth:
            self.current.append(data)

    def _finish(self) -> None:
        if self.in_paragraph:
            text = re.sub(r"\s+", " ", "".join(self.current)).strip()
            if len(text) >= MIN_PARAGRAPH_CHARS:
                self.all_paragraphs.append(text)
                if self.article_depth:
                    self.article_paragraphs.append(text)
        self.in_paragraph = False
        self.current = []


def extract_article_text(html: str, limit: int = MAX_ARTICLE_CHARS) -> str:
    """Return the article's readable paragraphs, up to `limit` characters."""
    parser = _ArticleParser()
    parser.feed(html)
    parser.close()
    parser._finish()  # noqa: SLF001 - flush an unclosed final paragraph
    paragraphs = parser.article_paragraphs
    if sum(len(p) for p in paragraphs) < 200:
        paragraphs = parser.all_paragraphs
    kept: list[str] = []
    seen: set[str] = set()
    total = 0
    for paragraph in paragraphs:
        if paragraph in seen:
            continue
        seen.add(paragraph)
        if total + len(paragraph) > limit:
            if not kept:
                kept.append(paragraph[:limit])
            break
        kept.append(paragraph)
        total += len(paragraph) + 2
    return "\n\n".join(kept)
