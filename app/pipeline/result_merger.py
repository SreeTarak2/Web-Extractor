"""Merge LLM-extracted text data with code-extracted image data."""


def merge(llm_item: dict, image_meta: dict) -> dict:
    """
    Merge LLM-extracted item with structured image metadata.

    image_meta should have:
        banner: str  — best banner/hero image URL
        logo:   str  — best logo URL (fallback)
        alt:    str  — alt text for the banner (or logo)
        all:    list — all discovered image URLs
    """
    result = dict(llm_item)

    banner = image_meta.get("banner", "")
    logo = image_meta.get("logo", "")
    alt = image_meta.get("alt", "")
    all_urls = image_meta.get("all", [])

    # Store pre-extracted data as private fields for the normalizer to consume
    result["_banner_url"] = banner
    result["_logo_url"] = logo
    result["_image_alt"] = alt

    # Keep a flat list for backwards compat / display
    result["image_urls"] = all_urls
    result["primary_image"] = banner or logo or (all_urls[0] if all_urls else None)

    return result


def merge_all(llm_items: list[dict], image_metas: list[dict]) -> list[dict]:
    """Merge a list of LLM items with their corresponding image metadata dicts."""
    return [
        merge(item, meta)
        for item, meta in zip(llm_items, image_metas)
    ]
