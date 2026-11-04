"""Article text extraction."""

from __future__ import annotations

from custom_components.briefly.extract import extract_article_text

from .helpers import HOMES_PARAS, article_html

LONG = "This paragraph is comfortably longer than the forty character minimum."


def test_extracts_article_paragraphs_only() -> None:
    text = extract_article_text(article_html(HOMES_PARAS))
    assert text.split("\n\n") == HOMES_PARAS
    assert "Copyright" not in text
    assert "iPlayer" not in text


def test_falls_back_to_all_paragraphs_without_article() -> None:
    html = (
        f"<html><body><div><p>{LONG}</p><p>Too short.</p><p>{LONG} Again.</p></div></body></html>"
    )
    assert extract_article_text(html) == f"{LONG}\n\n{LONG} Again."


def test_skips_scripts_figures_and_void_tags() -> None:
    html = (
        "<article><figure><p>A caption that is long enough to be counted here.</p></figure>"
        f"<p>{LONG}<br><img src='x'> <script>bad()</script>End.</p>"
        f"<p>{LONG}</p><p>{LONG}</p><p>{LONG}</p></article>"
    )
    text = extract_article_text(html)
    assert "caption" not in text
    assert "bad()" not in text
    assert text.startswith(f"{LONG} End.")
    assert text.count(LONG) == 2  # duplicates dropped


def test_limit_and_unclosed_paragraph() -> None:
    html = "<article>" + "".join(f"<p>{LONG} {i}</p>" for i in range(10)) + "<p>" + LONG
    text = extract_article_text(html, limit=160)
    assert len(text.split("\n\n")) == 2
    single = extract_article_text("<p>" + "x" * 500, limit=100)
    assert single == "x" * 100


def test_stray_closing_tags() -> None:
    html = f"</nav></article><p>{LONG}</p>"
    assert extract_article_text(html) == LONG
