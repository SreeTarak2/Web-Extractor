"""Unit tests for query parser."""
from app.pipeline.query_parser import parse_query


def test_parses_price():
    fields = parse_query("Get me all prices and names")
    assert "price" in fields
    assert "name" in fields


def test_parses_images():
    fields = parse_query("Extract product images and descriptions")
    assert "image_urls" in fields
    assert "description" in fields


def test_parses_rating():
    fields = parse_query("I want ratings and review counts")
    assert "rating" in fields
    assert "review_count" in fields


def test_defaults_when_nothing_matched():
    fields = parse_query("scrape everything you can find")
    assert fields == ["name", "price", "description", "image_urls"]


def test_no_duplicates():
    fields = parse_query("get names, titles, and product names")
    assert fields.count("name") == 1
