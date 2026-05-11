import re
import unicodedata
from urllib.parse import urlparse, urlunparse


def normalize_linkedin_url(raw: str | None) -> str | None:
    if not raw:
        return None

    if not isinstance(raw, str):
        raw = str(raw)

    url = raw.strip().lower()

    # Add scheme if missing so urlparse works correctly
    if not url.startswith("http"):
        url = "https://" + url

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    # Handle language-prefixed paths like /fr/in/slug or /pub/slug
    path = re.sub(r"^/[a-z]{2}/", "/", path)
    path = re.sub(r"^/pub/", "/in/", path)

    # Extract slug after /in/
    match = re.search(r"/in/([^/?#]+)", path)
    if not match:
        return None

    slug = match.group(1).rstrip("/")
    if not slug:
        return None

    return f"https://www.linkedin.com/in/{slug}"


def normalize_name(name: str) -> str:
    # NFD decompose to separate base chars from combining marks (accents)
    decomposed = unicodedata.normalize("NFD", name)
    # Strip combining characters (accents)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Lowercase, strip punctuation, collapse spaces
    cleaned = re.sub(r"[^\w\s]", " ", ascii_only)
    return re.sub(r"\s+", " ", cleaned).strip().lower()
