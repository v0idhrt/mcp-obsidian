import json
import os
from collections.abc import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from .tools import ToolHandler
from .fetcher import fetch_url, FetchResult
from .pdf_extractor import extract_pdf_text
from . import obsidian
from .vault_utils import (
    build_vault_tree,
    aggregate_search_results,
)

api_key = os.getenv("OBSIDIAN_API_KEY", "")
obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")


def _get_api() -> obsidian.Obsidian:
    return obsidian.Obsidian(api_key=api_key, host=obsidian_host)


class FetchUrlToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_fetch_url")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Fetch a web page by URL, clean it from ads/navigation, and return "
                "clean markdown text with metadata (title, author, date). "
                "After fetching, use kb_get_taxonomy and kb_get_vault_structure to "
                "determine where to place notes, then kb_find_related_notes to "
                "discover connections."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the web page to fetch",
                    }
                },
                "required": ["url"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "url" not in args:
            raise RuntimeError("url argument missing")

        result = fetch_url(args["url"])

        output = {
            "content": result.content,
            "title": result.title,
            "author": result.author,
            "date": result.date,
            "source_url": result.source_url,
            "is_pdf": result.is_pdf,
        }
        if result.warning:
            output["warning"] = result.warning

        return [TextContent(type="text", text=json.dumps(output, ensure_ascii=False, indent=2))]


class ExtractPdfToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_extract_pdf")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Extract text from a PDF file already present in the vault. "
                "Returns plain text extracted from all pages."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the PDF file in vault (relative to vault root)",
                        "format": "path",
                    }
                },
                "required": ["filepath"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument missing")

        api = _get_api()
        raw_bytes = api.get_file_contents_raw(args["filepath"])
        text = extract_pdf_text(raw_bytes)

        return [TextContent(type="text", text=text)]


class GetVaultStructureToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_get_vault_structure")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Get the folder tree structure of the vault with file counts per folder. "
                "Use this to understand existing organization before placing new notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = _get_api()
        files = api.list_files_in_vault()
        tree = build_vault_tree(files)

        return [TextContent(type="text", text=json.dumps(tree, ensure_ascii=False, indent=2))]


class GetTaxonomyToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_get_taxonomy")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Read the _taxonomy.md control note from the vault root. "
                "This file contains folder organization rules and naming conventions. "
                "Use together with kb_get_vault_structure to decide where to place new notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = _get_api()
        try:
            content = api.get_file_contents("_taxonomy.md")
        except Exception:
            content = "Taxonomy not configured. No _taxonomy.md found in vault root."

        return [TextContent(type="text", text=content)]


class FindRelatedNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_find_related_notes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Search for notes related by keywords. Returns ranked results with snippets. "
                "Use this after analyzing content to discover existing notes that should be linked."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Search terms to find related notes",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["keywords"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "keywords" not in args:
            raise RuntimeError("keywords argument missing")

        api = _get_api()
        limit = args.get("limit", 20)

        results_per_keyword = []
        for keyword in args["keywords"]:
            try:
                results = api.search(keyword, context_length=150)
                results_per_keyword.append(results)
            except Exception:
                continue

        aggregated = aggregate_search_results(results_per_keyword, limit=limit)

        return [TextContent(type="text", text=json.dumps(aggregated, ensure_ascii=False, indent=2))]
