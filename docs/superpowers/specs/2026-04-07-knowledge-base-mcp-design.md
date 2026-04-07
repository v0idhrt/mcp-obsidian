# Knowledge Base MCP Design

## Overview

Extend mcp-obsidian from a basic Obsidian REST API wrapper into an intelligent knowledge base management system. The MCP server provides specialized "building block" tools; the calling LLM orchestrates the full pipeline (Thin MCP approach).

**Core workflow:** External content (web article by URL, PDF file) is fetched, cleaned, and then the LLM decomposes it into atomic Zettelkasten-style notes, places them in the correct folders, adds tags and wikilinks, and updates Map of Content (MOC) index notes.

## Scope

### In scope
- Web articles: fetch URL, clean HTML, return markdown
- PDF files: extract text from PDF already in vault
- Binary files (screenshots, docs): save with wrapper note
- Automatic folder placement (hybrid: existing structure + `_taxonomy.md`)
- Wikilinks, tags, MOC creation and updates
- Multi-language input, Russian-only output (notes, tags, folders)

### Out of scope
- OCR for images/screenshots
- Embedded LLM calls inside MCP server (intelligence stays in the calling LLM)
- Option B content type (user's own notes — future phase)
- Semantic/vector search

## Architecture

### Approach: Thin MCP (Building Blocks)

The MCP server provides focused tools. The LLM calling the MCP orchestrates the pipeline: analyzing content, deciding on topics, choosing folders, generating connections.

**Rationale:**
- Follows MCP philosophy: tools, not agents
- No additional API keys needed inside the server
- Maximum flexibility: logic changes via prompt, not code
- Each tool is independently testable

### New files

```
src/mcp_obsidian/
├── obsidian.py          # existing — add get_file_contents_raw()
├── server.py            # existing — register new handlers
├── tools.py             # existing — untouched
├── kb_tools.py          # NEW — 9 KB tool handlers
├── fetcher.py           # NEW — web page fetching and cleaning
├── pdf_extractor.py     # NEW — PDF text extraction
└── vault_utils.py       # NEW — vault structure, taxonomy, MOC operations
```

### New dependencies

| Package | Purpose |
|---|---|
| `trafilatura` | Extract clean text from HTML (superior to readability for articles) |
| `pymupdf` (fitz) | Extract text from PDF — fast, no external dependencies |
| `markdownify` | HTML to Markdown conversion (fallback when trafilatura returns HTML) |

## New Tools (9 total)

### Content Fetching

#### `kb_fetch_url`

Fetches a web page, strips navigation/ads, returns clean markdown with metadata.

**Input:**
- `url: string` (required) — URL to fetch

**Output:** JSON with fields:
- `content: string` — cleaned markdown text
- `title: string` — page title
- `author: string | null`
- `date: string | null` — publication date
- `source_url: string` — original URL

**Behavior:**
- Uses trafilatura for extraction, markdownify as fallback
- If URL points to PDF (by Content-Type), saves file to vault, returns path + hint to use `kb_extract_pdf`
- Timeout: 30 seconds
- Max page size: 5 MB
- On paywall/partial content: returns what was extracted + warning

**Tool description hint for LLM:**
> "After fetching, use kb_get_taxonomy and kb_get_vault_structure to determine where to place notes, then kb_find_related_notes to discover connections."

#### `kb_extract_pdf`

Extracts text from a PDF file already present in the vault.

**Input:**
- `filepath: string` (required) — path to PDF in vault

**Output:** Extracted text as string

**Behavior:**
- Uses pymupdf for extraction
- Max file size: 50 MB
- Returns error with reason if PDF is corrupted/encrypted

### Vault Analysis

#### `kb_get_vault_structure`

Returns the folder tree of the vault with file counts per folder.

**Input:** none

**Output:** JSON tree, e.g.:
```json
{
  "Программирование": {"_count": 15, "Python": {"_count": 8}, "Архитектура": {"_count": 7}},
  "Финансы": {"_count": 5}
}
```

**Behavior:**
- Calls `list_files_in_vault()`, builds tree from flat file list
- `_count` key holds number of files directly in each folder

#### `kb_get_taxonomy`

Reads the `_taxonomy.md` control note from vault root.

**Input:** none

**Output:** File content as string, or empty result with message "taxonomy not configured"

#### `kb_find_related_notes`

Searches for notes related by keywords and/or tags.

**Input:**
- `keywords: string[]` (required) — search terms
- `tags: string[]` (optional) — filter by tags
- `limit: int` (optional, default 20) — max results

**Output:** Array of:
```json
{"path": "...", "title": "...", "score": 0.85, "snippet": "...context..."}
```

**Behavior:**
- Calls `search()` for each keyword
- Aggregates, deduplicates, ranks by cumulative score
- Extracts title from first `# heading` or filename

### Creation and Updates

#### `kb_save_atomic_note`

Creates a note with full frontmatter and content.

**Input:**
- `filepath: string` (required) — target path in vault
- `title: string` (required)
- `content: string` (required) — markdown body
- `tags: string[]` (required)
- `related: string[]` (optional) — wikilink targets, e.g. `["Заметка 1", "Заметка 2"]`
- `source: string` (optional) — source URL or file path
- `source_type: string` (optional) — `"url"`, `"pdf"`, or `"manual"`
- `aliases: string[]` (optional)
- `moc: string` (optional) — MOC this note belongs to

**Output:** Confirmation + created file path

**Behavior:**
- Assembles frontmatter from parameters:
  ```yaml
  ---
  title: "..."
  tags: [...]
  aliases: [...]
  source: "..."
  source_type: "..."
  created: "YYYY-MM-DD"
  related: ["[[...]]", "[[...]]"]
  moc: "[[...]]"
  ---
  ```
- Appends "Related" section at the end with wikilinks if `related` is provided
- Returns error if file already exists (LLM decides: update or rename)
- Uses `put_content()` under the hood

#### `kb_update_moc`

Adds entries to a MOC note. Creates the MOC if it doesn't exist.

**Input:**
- `moc_path: string` (required) — path to MOC file
- `entries: [{title: string, path: string, description: string}]` (required)

**Output:** Confirmation

**Behavior:**
- If MOC doesn't exist: creates from template with `tags: [moc]` frontmatter
- If MOC exists: appends entries at end of content (safe — doesn't parse complex structures)
- Entry format: `- [[{path}|{title}]] — {description}`
- Deduplicates: skips entries whose path already appears in MOC

#### `kb_save_binary`

Saves a binary file to vault and creates a wrapper note.

**Input:**
- `source_path: string` (required) — path to file on disk or in vault
- `vault_dir: string` (required) — target folder in vault
- `description: string` (optional)
- `tags: string[]` (optional)

**Output:** JSON with `file_path` and `wrapper_path`

**Behavior:**
- Saves binary to `{vault_dir}/_attachments/{filename}`
- Creates wrapper note at `{vault_dir}/{filename_without_ext}.md`:
  ```markdown
  ---
  title: "..."
  tags: [attachment, ...]
  source_type: "binary"
  file: "[[_attachments/filename]]"
  created: "YYYY-MM-DD"
  ---
  # {title}
  ![[_attachments/filename]]
  {description}
  ```

### Utilities

#### `kb_list_mocs`

Lists all MOC notes in the vault.

**Input:** none

**Output:** Array of `{"path": "...", "title": "..."}`

**Behavior:**
- Uses `complex_search` with JsonLogic to find files containing `tags: [moc]` or `tags:.*moc` in frontmatter
- Extracts title from frontmatter or first heading

## Data Conventions

### Frontmatter — atomic note

```yaml
---
title: "Название заметки"
tags: [тема/подтема, концепция]
aliases: ["альтернативное название"]
source: "https://original-url.com"
source_type: "url" | "pdf" | "manual"
created: "2026-04-07"
related: ["[[Связанная заметка 1]]", "[[Связанная заметка 2]]"]
moc: "[[MOC Тема]]"
---
```

### MOC format

```markdown
---
title: "MOC Программирование"
tags: [moc]
created: "2026-04-07"
---
# Программирование

## Ключевые концепции
- [[Заметка 1]] — краткое описание
- [[Заметка 2]] — краткое описание

## Связанные MOC
- [[MOC Алгоритмы]]
```

### `_taxonomy.md` format

Located at vault root. Example:

```markdown
# Таксономия

## Папки
- Программирование/ — всё про код, языки, фреймворки
  - Программирование/Python/
  - Программирование/Архитектура/
- Финансы/ — инвестиции, бюджет, крипто
- Здоровье/ — медицина, спорт, питание

## Правила
- Теги пишутся на русском, в формате тема/подтема
- MOC-файлы лежат в корне папки темы (например, Программирование/MOC Программирование.md)
- Бинарные файлы хранятся в _attachments/ внутри тематической папки
- Если тема не подходит ни под одну папку — создать новую и добавить сюда
```

### Binary wrapper note format

```markdown
---
title: "Скриншот интерфейса"
tags: [вложение, скриншот]
source_type: "binary"
file: "[[_attachments/screenshot.png]]"
created: "2026-04-07"
---
# Скриншот интерфейса
![[_attachments/screenshot.png]]
Описание: ...
```

## Orchestration Pipelines

These are not MCP code — they describe how the calling LLM should use the tools. Tool descriptions contain hints guiding the LLM through the correct sequence.

### Pipeline: Web article (URL)

```
1. kb_fetch_url(url)
   → clean markdown + metadata

2. kb_get_taxonomy()
   → organization rules

3. kb_get_vault_structure()
   → current folder tree

4. LLM analysis:
   → extract 2-7 atomic topics/concepts
   → for each: title, tags, target folder
   → determine which MOCs to update/create

5. kb_find_related_notes(keywords per topic)
   → discover existing related notes

6. kb_list_mocs()
   → understand existing MOC landscape

7. For each atomic note:
   kb_save_atomic_note(filepath, title, content, tags, related, source)

8. For each affected MOC:
   kb_update_moc(moc_path, new_entries)
```

### Pipeline: PDF file

```
1. kb_extract_pdf(filepath)
   → extracted text

2-8. Same pipeline as URL (steps 2-8)
     source_type = "pdf"
```

### Pipeline: Binary file

```
1. kb_get_taxonomy()
   → determine target folder

2. kb_save_binary(source_path, vault_dir, description, tags)
   → saves file + creates wrapper note
```

## Error Handling

### Fetch errors
| Situation | Behavior |
|---|---|
| URL unreachable / timeout | `kb_fetch_url` returns error with description |
| URL points to PDF | Saves file, returns path + hint to use `kb_extract_pdf` |
| Paywall / auth required | Returns extracted content + warning "content may be incomplete" |
| PDF corrupted / encrypted | `kb_extract_pdf` returns error with reason |

### Vault conflicts
| Situation | Behavior |
|---|---|
| File with same name exists | `kb_save_atomic_note` returns error, LLM decides: update or rename |
| `_taxonomy.md` not found | `kb_get_taxonomy` returns empty + message, LLM works from vault structure only |
| MOC file corrupted / non-standard | `kb_update_moc` appends entries at end, doesn't break existing content |

### Limits
| Parameter | Value |
|---|---|
| Max page download size | 5 MB |
| Max PDF size | 50 MB |
| URL fetch timeout | 30 seconds |
| Max `kb_find_related_notes` results | default 20, configurable via `limit` |

## Changes to Existing Files

- **`server.py`** — import `kb_tools`, register 9 new handlers via `add_tool_handler()`
- **`obsidian.py`** — add `get_file_contents_raw()` method for binary data (PDF)
- **`pyproject.toml`** — add dependencies: `trafilatura`, `pymupdf`, `markdownify`
- **`tools.py`** — untouched
