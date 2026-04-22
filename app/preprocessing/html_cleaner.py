"""HTML cleaner — strips Tailwind classes, scripts, noise; returns lean HTML."""
import re
import logging

logger = logging.getLogger(__name__)

# Tailwind utility prefixes to strip
_TAILWIND_PREFIXES = (
    # Layout
    "flex", "grid", "block", "inline", "hidden", "items-", "justify-", "content-",
    "self-", "place-", "order-", "col-", "row-", "float-", "clear-",
    # Spacing
    "p-", "px-", "py-", "pt-", "pr-", "pb-", "pl-",
    "m-", "mx-", "my-", "mt-", "mr-", "mb-", "ml-",
    "gap-", "space-x-", "space-y-",
    # Sizing
    "w-", "h-", "max-w-", "max-h-", "min-w-", "min-h-", "size-",
    # Typography
    "text-xs", "text-sm", "text-base", "text-lg", "text-xl", "text-2xl",
    "text-3xl", "text-4xl", "text-5xl", "font-", "leading-", "tracking-",
    "whitespace-", "break-", "truncate", "line-clamp-", "list-", "antialiased",
    # Colors (text-gray-500, bg-blue-100, etc.)
    "text-gray-", "text-red-", "text-blue-", "text-green-", "text-yellow-",
    "text-purple-", "text-pink-", "text-indigo-", "text-orange-", "text-teal-",
    "text-slate-", "text-zinc-", "text-neutral-", "text-stone-", "text-sky-",
    "text-cyan-", "text-emerald-", "text-lime-", "text-amber-", "text-violet-",
    "text-fuchsia-", "text-rose-", "text-white", "text-black",
    "bg-", "border-", "ring-", "divide-", "placeholder-",
    # Borders & effects
    "rounded-", "border", "outline-", "ring-", "shadow-", "opacity-",
    "transition-", "duration-", "ease-", "delay-", "animate-",
    # States & responsive
    "hover:", "focus:", "active:", "disabled:", "checked:", "dark:", "group-",
    "sm:", "md:", "lg:", "xl:", "2xl:",
    # Position
    "relative", "absolute", "fixed", "sticky", "static",
    "z-", "top-", "right-", "bottom-", "left-", "inset-",
    # Overflow & display
    "overflow-", "overscroll-", "scroll-", "snap-",
    # Cursor & pointer
    "cursor-", "pointer-events-", "select-",
    # Aspect & container
    "aspect-", "container", "columns-",
)

# Semantic classes worth keeping (contain data-relevant terms)
_KEEP_CLASS_KEYWORDS = (
    "product", "price", "description", "rating", "review", "cart",
    "availability", "stock", "category", "breadcrumb", "pagination",
    "nav-main", "header-main", "footer-main", "search", "filter",
    "title", "name", "sku", "brand", "image", "gallery",
)

# Tags to remove entirely (with their content)
_REMOVE_TAGS = re.compile(
    r"<(script|style|noscript|svg|iframe|canvas|template)"
    r"(\s[^>]*)?>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)

# Self-closing script/style tags
_REMOVE_SELF_CLOSING = re.compile(
    r"<(script|style|link)(\s[^>]*)?>",
    re.IGNORECASE,
)

# HTML comments
_REMOVE_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)

# data-* attributes
_REMOVE_DATA_ATTRS = re.compile(r'\s+data-[a-z][a-z0-9-]*="[^"]*"', re.IGNORECASE)

# inline style attributes
_REMOVE_STYLE_ATTR = re.compile(r'\s+style="[^"]*"', re.IGNORECASE)

# aria-* and role attributes
_REMOVE_ARIA = re.compile(r'\s+aria-[a-z-]+="[^"]*"', re.IGNORECASE)
_REMOVE_ROLE = re.compile(r'\s+role="[^"]*"', re.IGNORECASE)

# Next.js / React noise attributes
_REMOVE_FRAMEWORK_ATTRS = re.compile(
    r'\s+(data-nimg|fetchpriority|decoding|loading|crossorigin|referrerpolicy)'
    r'="[^"]*"',
    re.IGNORECASE,
)

# Collapse whitespace
_MULTI_SPACE = re.compile(r"\s{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def _filter_class(class_value: str) -> str:
    """Keep only non-Tailwind or semantically meaningful classes."""
    classes = class_value.split()
    kept = []
    for cls in classes:
        # Always keep if it contains a semantic keyword
        if any(kw in cls.lower() for kw in _KEEP_CLASS_KEYWORDS):
            kept.append(cls)
            continue
        # Strip if it starts with a Tailwind prefix
        if any(cls.startswith(prefix) or cls == prefix.rstrip("-")
               for prefix in _TAILWIND_PREFIXES):
            continue
        # Keep everything else (custom classes, IDs encoded as classes, etc.)
        kept.append(cls)
    return " ".join(kept)


def _strip_classes(html: str) -> str:
    """Process class="..." attributes and filter Tailwind utilities."""
    def replacer(m):
        filtered = _filter_class(m.group(1))
        if not filtered:
            return ""
        return f' class="{filtered}"'

    return re.sub(r'\s+class="([^"]*)"', replacer, html)


def clean_html(raw_html: str, max_chars: int = 50_000) -> str:
    """
    Full cleaning pipeline.
    Returns lean HTML suitable for LLM consumption.
    """
    html = raw_html

    # 1. Extract body content only
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if body_match:
        html = body_match.group(1)

    # 2. Remove noisy tags and their content
    html = _REMOVE_TAGS.sub("", html)
    html = _REMOVE_SELF_CLOSING.sub("", html)
    html = _REMOVE_COMMENTS.sub("", html)

    # 3. Remove noisy attributes
    html = _REMOVE_DATA_ATTRS.sub("", html)
    html = _REMOVE_STYLE_ATTR.sub("", html)
    html = _REMOVE_ARIA.sub("", html)
    html = _REMOVE_ROLE.sub("", html)
    html = _REMOVE_FRAMEWORK_ATTRS.sub("", html)

    # 4. Strip Tailwind classes
    html = _strip_classes(html)

    # 5. Remove empty wrapper divs/spans (simple pass — not recursive)
    html = re.sub(r"<(div|span)(\s[^>]*)?>\s*</(div|span)>", "", html)

    # 6. Collapse whitespace
    html = _MULTI_SPACE.sub(" ", html)
    html = _MULTI_NEWLINE.sub("\n\n", html)
    html = html.strip()

    # 7. Truncate to budget
    if len(html) > max_chars:
        html = html[:max_chars]
        logger.warning(f"HTML truncated from original to {max_chars} chars")

    return html
