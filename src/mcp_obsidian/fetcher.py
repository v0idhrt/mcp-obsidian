from dataclasses import dataclass
import requests
import trafilatura
import markdownify

MAX_PAGE_SIZE = 5 * 1024 * 1024  # 5 MB
FETCH_TIMEOUT = 30


@dataclass
class FetchResult:
    content: str = ""
    title: str | None = None
    author: str | None = None
    date: str | None = None
    source_url: str = ""
    is_pdf: bool = False
    warning: str | None = None


def fetch_url(url: str) -> FetchResult:
    """Fetch a web page, clean it, and return markdown content with metadata."""
    response = requests.get(
        url,
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (compatible; mcp-obsidian-kb/1.0)"},
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    content_length = response.headers.get("Content-Length")

    if content_length and int(content_length) > MAX_PAGE_SIZE:
        raise Exception(f"Page size {content_length} exceeds maximum {MAX_PAGE_SIZE} bytes")

    # PDF detection
    if "application/pdf" in content_type:
        return FetchResult(
            source_url=response.url,
            is_pdf=True,
        )

    # HTML extraction
    html = response.content

    if len(html) > MAX_PAGE_SIZE:
        raise Exception(f"Page size {len(html)} exceeds maximum {MAX_PAGE_SIZE} bytes")

    # Try trafilatura first
    extracted = trafilatura.extract(
        html,
        output_format="txt",
        include_comments=False,
        include_tables=True,
    )

    # Parse metadata from trafilatura
    meta = trafilatura.metadata.extract_metadata(html)
    title = meta.title if meta else None
    author = meta.author if meta else None
    date = meta.date if meta else None

    content = extracted or ""
    warning = None

    # Fallback to markdownify if trafilatura returns nothing
    if not content:
        content = markdownify.markdownify(
            html.decode("utf-8", errors="replace"),
            heading_style="ATX",
            strip=["script", "style", "nav", "footer", "header"],
        )
        warning = "Content extracted via fallback method, may contain noise"

    return FetchResult(
        content=content,
        title=title,
        author=author,
        date=date,
        source_url=response.url,
        warning=warning,
    )
