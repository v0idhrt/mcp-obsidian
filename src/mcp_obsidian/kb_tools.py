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
    build_atomic_note,
    build_new_moc,
    append_to_moc,
    build_binary_wrapper,
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


class SaveAtomicNoteToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_save_atomic_note")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Create an atomic Zettelkasten note with full frontmatter (tags, related, source, MOC link). "
                "Returns error if file already exists — decide whether to update or choose a different name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Target path in vault (e.g. 'Программирование/Python/Генераторы.md')",
                        "format": "path",
                    },
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Markdown body of the note"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags in Russian, format тема/подтема",
                    },
                    "related": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of related notes for [[wikilinks]]",
                    },
                    "source": {"type": "string", "description": "Source URL or file path"},
                    "source_type": {
                        "type": "string",
                        "enum": ["url", "pdf", "manual"],
                        "description": "Type of source",
                    },
                    "aliases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alternative names for the note",
                    },
                    "moc": {"type": "string", "description": "MOC this note belongs to"},
                },
                "required": ["filepath", "title", "content", "tags"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        for field in ["filepath", "title", "content", "tags"]:
            if field not in args:
                raise RuntimeError(f"{field} argument missing")

        api = _get_api()

        # Check if file already exists
        try:
            api.get_file_contents(args["filepath"])
            raise RuntimeError(f"File already exists: {args['filepath']}. Choose a different name or update the existing file.")
        except RuntimeError:
            raise
        except Exception:
            pass  # File doesn't exist — good

        note_content = build_atomic_note(
            title=args["title"],
            content=args["content"],
            tags=args["tags"],
            aliases=args.get("aliases"),
            source=args.get("source"),
            source_type=args.get("source_type"),
            related=args.get("related"),
            moc=args.get("moc"),
        )

        api.put_content(args["filepath"], note_content)

        return [TextContent(type="text", text=f"Successfully created note: {args['filepath']}")]


class UpdateMocToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_update_moc")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Add entries to a Map of Content (MOC) note. Creates the MOC if it doesn't exist. "
                "Deduplicates entries by path. Use after creating atomic notes to update relevant MOCs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "moc_path": {
                        "type": "string",
                        "description": "Path to MOC file in vault",
                        "format": "path",
                    },
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "path": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["title", "path", "description"],
                        },
                        "description": "Entries to add to the MOC",
                    },
                },
                "required": ["moc_path", "entries"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        for field in ["moc_path", "entries"]:
            if field not in args:
                raise RuntimeError(f"{field} argument missing")

        api = _get_api()

        try:
            existing = api.get_file_contents(args["moc_path"])
            updated = append_to_moc(existing, args["entries"])
        except Exception:
            moc_title = args["moc_path"].rsplit("/", 1)[-1].removesuffix(".md")
            updated = build_new_moc(title=moc_title, entries=args["entries"])

        api.put_content(args["moc_path"], updated)

        return [TextContent(type="text", text=f"Successfully updated MOC: {args['moc_path']}")]


class SaveBinaryToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_save_binary")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Save a binary file (screenshot, document, image) to the vault and create a wrapper note. "
                "The file is saved to _attachments/ subfolder, and a markdown wrapper is created alongside."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_path": {
                        "type": "string",
                        "description": "Absolute path to the file on disk",
                    },
                    "vault_dir": {
                        "type": "string",
                        "description": "Target folder in vault (e.g. 'Проект/Дизайн')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the file content",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the wrapper note",
                    },
                },
                "required": ["source_path", "vault_dir"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        for field in ["source_path", "vault_dir"]:
            if field not in args:
                raise RuntimeError(f"{field} argument missing")

        source_path = args["source_path"]
        vault_dir = args["vault_dir"]
        filename = os.path.basename(source_path)
        filename_no_ext = os.path.splitext(filename)[0]

        attachment_vault_path = f"{vault_dir}/_attachments/{filename}"
        wrapper_vault_path = f"{vault_dir}/{filename_no_ext}.md"

        with open(source_path, "rb") as f:
            file_bytes = f.read()

        api = _get_api()

        api.put_content(attachment_vault_path, file_bytes.decode("latin-1"))

        wrapper_content = build_binary_wrapper(
            title=filename_no_ext,
            attachment_path=f"_attachments/{filename}",
            description=args.get("description"),
            tags=args.get("tags"),
        )
        api.put_content(wrapper_vault_path, wrapper_content)

        result = {
            "file_path": attachment_vault_path,
            "wrapper_path": wrapper_vault_path,
        }

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


class ListMocsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("kb_list_mocs")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "List all Map of Content (MOC) notes in the vault. "
                "Use this to understand the existing MOC landscape before creating or updating MOCs."
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
            results = api.search("tags: [moc]", context_length=50)
        except Exception:
            results = []

        mocs = []
        for item in results:
            path = item.get("filename", "")
            title = path.rsplit("/", 1)[-1].removesuffix(".md")
            mocs.append({"path": path, "title": title})

        return [TextContent(type="text", text=json.dumps(mocs, ensure_ascii=False, indent=2))]
