from datetime import date


def build_vault_tree(file_list: list[str]) -> dict:
    """Build a folder tree with file counts from a flat list of file paths."""
    if not file_list:
        return {}

    tree: dict = {}

    for filepath in file_list:
        parts = filepath.split("/")
        if len(parts) == 1:
            tree["_count"] = tree.get("_count", 0) + 1
        else:
            current = tree
            for folder in parts[:-1]:
                if folder not in current:
                    current[folder] = {"_count": 0}
                current = current[folder]
            current["_count"] = current.get("_count", 0) + 1

    return tree


def build_frontmatter(
    title: str,
    tags: list[str],
    aliases: list[str] | None = None,
    source: str | None = None,
    source_type: str | None = None,
    related: list[str] | None = None,
    moc: str | None = None,
) -> str:
    """Build YAML frontmatter string for an atomic note."""
    lines = ["---"]
    lines.append(f'title: "{title}"')
    lines.append(f"tags: [{', '.join(tags)}]")

    if aliases:
        aliases_str = ", ".join(f'"{a}"' for a in aliases)
        lines.append(f"aliases: [{aliases_str}]")

    if source:
        lines.append(f'source: "{source}"')

    if source_type:
        lines.append(f'source_type: "{source_type}"')

    lines.append(f'created: "{date.today().isoformat()}"')

    if related:
        related_str = ", ".join(f'"[[{r}]]"' for r in related)
        lines.append(f"related: [{related_str}]")

    if moc:
        lines.append(f'moc: "[[{moc}]]"')

    lines.append("---")
    return "\n".join(lines) + "\n"


def build_atomic_note(
    title: str,
    content: str,
    tags: list[str],
    aliases: list[str] | None = None,
    source: str | None = None,
    source_type: str | None = None,
    related: list[str] | None = None,
    moc: str | None = None,
) -> str:
    """Build a complete atomic note with frontmatter and content."""
    frontmatter = build_frontmatter(
        title=title, tags=tags, aliases=aliases,
        source=source, source_type=source_type,
        related=related, moc=moc,
    )

    parts = [frontmatter, "", content]

    if related:
        parts.append("")
        parts.append("## Related")
        for r in related:
            parts.append(f"- [[{r}]]")

    return "\n".join(parts) + "\n"


def build_moc_entry(title: str, path: str, description: str) -> str:
    """Build a single MOC entry line."""
    return f"- [[{path}|{title}]] \u2014 {description}"


def build_new_moc(title: str, entries: list[dict]) -> str:
    """Build a complete new MOC note."""
    frontmatter = build_frontmatter(title=title, tags=["moc"])

    lines = [frontmatter, f"# {title.removeprefix('MOC ')}", ""]

    for entry in entries:
        lines.append(build_moc_entry(entry["title"], entry["path"], entry["description"]))

    return "\n".join(lines) + "\n"


def append_to_moc(existing_content: str, entries: list[dict]) -> str:
    """Append new entries to an existing MOC, deduplicating by path."""
    new_entries = []
    for entry in entries:
        if entry["path"] not in existing_content:
            new_entries.append(
                build_moc_entry(entry["title"], entry["path"], entry["description"])
            )

    if not new_entries:
        return existing_content

    result = existing_content.rstrip("\n")
    result += "\n" + "\n".join(new_entries) + "\n"
    return result


def build_binary_wrapper(
    title: str,
    attachment_path: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Build a wrapper note for a binary file."""
    all_tags = ["attachment"] + (tags or [])
    frontmatter = build_frontmatter(title=title, tags=all_tags, source_type="binary")
    # Insert file field before closing ---
    frontmatter_lines = frontmatter.split("\n")
    insert_idx = len(frontmatter_lines) - 2
    frontmatter_lines.insert(insert_idx, f'file: "[[{attachment_path}]]"')
    frontmatter = "\n".join(frontmatter_lines)

    parts = [frontmatter, f"# {title}", "", f"![[{attachment_path}]]"]
    if description:
        parts.append("")
        parts.append(description)

    return "\n".join(parts) + "\n"


def aggregate_search_results(
    results_per_keyword: list[list[dict]], limit: int = 20
) -> list[dict]:
    """Aggregate and rank search results from multiple keyword searches."""
    scores: dict[str, float] = {}
    snippets: dict[str, str] = {}

    for results in results_per_keyword:
        for item in results:
            path = item["filename"]
            score = item.get("score", 0)
            scores[path] = scores.get(path, 0) + score

            if path not in snippets:
                matches = item.get("matches", [])
                if matches:
                    ctx = matches[0].get("context", "") if isinstance(matches[0], dict) else ""
                    snippets[path] = ctx

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

    return [
        {
            "path": path,
            "title": path.rsplit("/", 1)[-1].removesuffix(".md"),
            "score": score,
            "snippet": snippets.get(path, ""),
        }
        for path, score in ranked
    ]
