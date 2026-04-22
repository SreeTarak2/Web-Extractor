"""Unit tests for image extractor — no API calls needed."""
from app.preprocessing.image_extractor import extract_images


def test_extracts_basic_src():
    html = '<img src="https://example.com/photo.jpg" alt="test">'
    result = extract_images(html)
    assert "https://example.com/photo.jpg" in result


def test_extracts_srcset_largest():
    html = '<img srcset="img-400.jpg 400w, img-800.jpg 800w, img-200.jpg 200w" src="img-200.jpg">'
    result = extract_images(html)
    assert result[0] == "img-800.jpg"  # Largest srcset wins


def test_extracts_data_src():
    html = '<img data-src="https://example.com/lazy.jpg" src="placeholder.gif">'
    result = extract_images(html)
    assert "https://example.com/lazy.jpg" in result


def test_extracts_og_image():
    html = '<meta property="og:image" content="https://example.com/og.jpg">'
    result = extract_images(html)
    assert "https://example.com/og.jpg" in result


def test_skips_base64():
    html = '<img src="data:image/png;base64,abc123==">'
    result = extract_images(html)
    assert not result


def test_skips_tracking_pixels():
    html = '<img src="https://track.example.com/pixel.gif" width="1" height="1">'
    result = extract_images(html)
    assert not any("pixel.gif" in u for u in result)


def test_decodes_nextjs_image():
    html = '<img src="/_next/image?url=https%3A%2F%2Fcdn.example.com%2Fimg.jpg&w=800&q=75">'
    result = extract_images(html)
    assert "https://cdn.example.com/img.jpg" in result


def test_deduplicates():
    html = '<img src="https://example.com/a.jpg"><img src="https://example.com/a.jpg">'
    result = extract_images(html)
    assert result.count("https://example.com/a.jpg") == 1


def test_extracts_jsonld_image():
    html = '''
    <script type="application/ld+json">
    {"@type": "Product", "image": "https://example.com/product.jpg"}
    </script>
    '''
    result = extract_images(html)
    assert "https://example.com/product.jpg" in result
