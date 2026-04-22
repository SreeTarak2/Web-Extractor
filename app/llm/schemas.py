"""JSON schemas for structured LLM output."""


def build_extraction_schema(fields: list[str]) -> dict:
    """Build a JSON schema dynamically from the requested field list."""
    properties = {}
    for field in fields:
        if field in ("image_urls",):
            properties[field] = {"type": ["array", "null"], "items": {"type": "string"}}
        elif field in ("price", "rating", "review_count"):
            properties[field] = {"type": ["number", "null"]}
        else:
            properties[field] = {"type": ["string", "null"]}

    # Always include source_url
    properties["source_url"] = {"type": ["string", "null"]}

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "extracted_item",
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties.keys()),
                "additionalProperties": False,
            },
            "strict": True,
        },
    }


ANALYZER_SCHEMA = {
    "type": "json_object",
}

NAVIGATOR_SCHEMA = {
    "type": "json_object",
}
