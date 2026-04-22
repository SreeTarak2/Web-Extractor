"""Convert plain English queries into a list of field names."""
import re

# Mapping of common phrases → canonical field names
_PHRASE_TO_FIELD = {
    # Name
    r"\bname\b": "name",
    r"\btitle\b": "name",
    r"\bproduct name\b": "name",

    # Price
    r"\bprice\b": "price",
    r"\bcost\b": "price",
    r"\bpricing\b": "price",

    # Currency
    r"\bcurrency\b": "currency",

    # Description
    r"\bdescription\b": "description",
    r"\babout\b": "description",
    r"\bdetails?\b": "description",
    r"\bspec(?:ification)?s?\b": "specifications",

    # Images
    r"\bimage\b": "image_urls",
    r"\bimages\b": "image_urls",
    r"\bphoto\b": "image_urls",
    r"\bpicture\b": "image_urls",
    r"\bthumbnail\b": "image_urls",

    # Rating / reviews
    r"\brating\b": "rating",
    r"\bstar\b": "rating",
    r"\breview(?:s)?\b": "review_count",
    r"\breview count\b": "review_count",

    # Stock / availability
    r"\bavailability\b": "availability",
    r"\bstock\b": "availability",
    r"\bin stock\b": "availability",

    # Brand
    r"\bbrand\b": "brand",
    r"\bmanufacturer\b": "brand",
    r"\bmake\b": "brand",

    # Category
    r"\bcategor(?:y|ies)\b": "category",

    # SKU / ID
    r"\bsku\b": "sku",
    r"\bproduct id\b": "sku",
    r"\bmodel number\b": "sku",

    # URL
    r"\burl\b": "source_url",
    r"\blink\b": "source_url",

    # Author (for articles/blogs)
    r"\bauthor\b": "author",

    # Date
    r"\bdate\b": "date",
    r"\bpublished\b": "date",

    # Contest-specific
    r"\bdeadline\b": "deadline",
    r"\bsubmission\b": "deadline",
    r"\bprize\b": "prize",
    r"\baward\b": "prize",
    r"\beligibilit\b": "eligibility",
    r"\bwho can apply\b": "eligibility",
    r"\bcompetition\b": "title",
    r"\bcontest\b": "title",
    r"\bhackathon\b": "title",

    # Conference-specific
    r"\bvenue\b": "venue",
    r"\blocation\b": "location",
    r"\bconference\b": "title",
    r"\bspeaker\b": "speakers",
    r"\bschedule\b": "schedule",
    r"\bregistration\b": "registration_deadline",
    r"\btrack\b": "tracks",
}

_DEFAULT_FIELDS = ["name", "price", "description", "image_urls"]

# Schema-specific field sets used when query is empty or doesn't match
_SCHEMA_FIELDS: dict[str, list[str]] = {
    "contest": [
        "title", "organizer", "deadline", "prize", "eligibility",
        "description", "category", "source_url", "image_urls",
    ],
    "conference": [
        "title", "location", "venue", "start_date", "end_date",
        "description", "registration_deadline", "speakers",
        "tracks", "source_url", "image_urls",
    ],
}


def parse_query(query: str, schema: str | None = None) -> list[str]:
    """
    Extract a deduplicated list of field names from a plain English query.

    If *schema* is provided and no fields are found in the query, falls back
    to schema-specific defaults (e.g. contest fields) rather than the generic
    product defaults. This dramatically improves analyzer accuracy.
    """
    query_lower = query.lower()
    found: list[str] = []
    seen: set[str] = set()

    for pattern, field in _PHRASE_TO_FIELD.items():
        if re.search(pattern, query_lower) and field not in seen:
            found.append(field)
            seen.add(field)

    if not found:
        if schema and schema in _SCHEMA_FIELDS:
            return list(_SCHEMA_FIELDS[schema])
        return list(_DEFAULT_FIELDS)

    return found
