"""Unit tests for HTML cleaner — no API calls needed."""
from app.preprocessing.html_cleaner import clean_html


def test_removes_scripts():
    html = "<body><script>alert('x')</script><p>Hello</p></body>"
    result = clean_html(html)
    assert "<script>" not in result
    assert "Hello" in result


def test_removes_style_tags():
    html = "<body><style>.foo { color: red; }</style><p>World</p></body>"
    result = clean_html(html)
    assert "<style>" not in result
    assert "World" in result


def test_strips_tailwind_classes():
    html = '<body><div class="flex items-center p-4 text-sm product-card">Item</div></body>'
    result = clean_html(html)
    assert "flex" not in result
    assert "items-center" not in result
    assert "p-4" not in result
    assert "product-card" in result  # semantic class kept


def test_removes_data_attributes():
    html = '<body><div data-testid="abc" data-nimg="1">Content</div></body>'
    result = clean_html(html)
    assert 'data-testid' not in result
    assert "Content" in result


def test_removes_inline_styles():
    html = '<body><p style="color: red; font-size: 14px;">Text</p></body>'
    result = clean_html(html)
    assert 'style=' not in result
    assert "Text" in result


def test_truncates_to_max_chars():
    html = "<body>" + "A" * 100_000 + "</body>"
    result = clean_html(html, max_chars=1000)
    assert len(result) <= 1000


def test_extracts_body_only():
    html = "<html><head><title>Test</title></head><body><p>Body content</p></body></html>"
    result = clean_html(html)
    assert "<head>" not in result
    assert "Body content" in result


def test_removes_aria_attributes():
    html = '<body><button aria-label="Close" aria-expanded="false">X</button></body>'
    result = clean_html(html)
    assert "aria-label" not in result
    assert "aria-expanded" not in result
