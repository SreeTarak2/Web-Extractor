"""Export generated content as Markdown with frontmatter."""
import os
from datetime import datetime, UTC
from app.config import OUTPUT_DIR


def export(result: dict, filename: str | None = None) -> str:
    """Save generated_content as a .md file. Returns the file path."""
    content = result.get("generated_content", "")
    if not content:
        return ""

    if not filename:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"content_{ts}.md"

    meta = result.get("metadata", {})
    frontmatter = (
        f"---\n"
        f"source_url: {meta.get('url', '')}\n"
        f"query: {meta.get('query', '')}\n"
        f"generated_at: {datetime.now(UTC).isoformat()}\n"
        f"---\n\n"
    )

    path = os.path.join(OUTPUT_DIR, "content", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return path
