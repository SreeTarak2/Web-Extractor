"""Unit tests for result merger."""
from app.pipeline.result_merger import merge, merge_all


def test_merge_adds_images():
    item = {"name": "Widget", "price": 9.99}
    images = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    result = merge(item, images)
    assert result["image_urls"] == images
    assert result["primary_image"] == images[0]
    assert result["name"] == "Widget"


def test_merge_empty_images():
    item = {"name": "Widget"}
    result = merge(item, [])
    assert result["image_urls"] == []
    assert result["primary_image"] is None


def test_merge_overrides_llm_images():
    item = {"name": "Widget", "image_urls": ["https://llm-hallucinated.jpg"]}
    images = ["https://real-image.jpg"]
    result = merge(item, images)
    assert result["image_urls"] == ["https://real-image.jpg"]


def test_merge_all():
    items = [{"name": "A"}, {"name": "B"}]
    images = [["img1.jpg"], ["img2.jpg"]]
    results = merge_all(items, images)
    assert results[0]["primary_image"] == "img1.jpg"
    assert results[1]["primary_image"] == "img2.jpg"
