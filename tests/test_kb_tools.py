import pytest
import json
from unittest.mock import patch, MagicMock
from mcp_obsidian.kb_tools import (
    FetchUrlToolHandler,
    ExtractPdfToolHandler,
    GetVaultStructureToolHandler,
    GetTaxonomyToolHandler,
    FindRelatedNotesToolHandler,
    SaveAtomicNoteToolHandler,
    UpdateMocToolHandler,
    SaveBinaryToolHandler,
    ListMocsToolHandler,
)


class TestFetchUrlToolHandler:
    def setup_method(self):
        self.handler = FetchUrlToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_fetch_url"

    def test_tool_description_exists(self):
        desc = self.handler.get_tool_description()
        assert desc.name == "kb_fetch_url"
        assert "url" in desc.inputSchema["properties"]

    def test_missing_url_raises(self):
        with pytest.raises(RuntimeError, match="url"):
            self.handler.run_tool({})

    @patch("mcp_obsidian.kb_tools.fetch_url")
    def test_returns_content(self, mock_fetch):
        from mcp_obsidian.fetcher import FetchResult
        mock_fetch.return_value = FetchResult(
            content="# Article\n\nSome text",
            title="Article",
            author="Author",
            date="2026-01-01",
            source_url="https://example.com",
        )
        result = self.handler.run_tool({"url": "https://example.com"})
        data = json.loads(result[0].text)
        assert data["title"] == "Article"
        assert data["content"] == "# Article\n\nSome text"
        assert data["source_url"] == "https://example.com"

    @patch("mcp_obsidian.kb_tools.fetch_url")
    def test_pdf_detected(self, mock_fetch):
        from mcp_obsidian.fetcher import FetchResult
        mock_fetch.return_value = FetchResult(
            source_url="https://example.com/paper.pdf",
            is_pdf=True,
        )
        result = self.handler.run_tool({"url": "https://example.com/paper.pdf"})
        data = json.loads(result[0].text)
        assert data["is_pdf"] is True


class TestExtractPdfToolHandler:
    def setup_method(self):
        self.handler = ExtractPdfToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_extract_pdf"

    def test_missing_filepath_raises(self):
        with pytest.raises(RuntimeError, match="filepath"):
            self.handler.run_tool({})

    @patch("mcp_obsidian.kb_tools._get_api")
    @patch("mcp_obsidian.kb_tools.extract_pdf_text")
    def test_extracts_text(self, mock_extract, mock_get_api):
        mock_api = MagicMock()
        mock_api.get_file_contents_raw.return_value = b"fake pdf bytes"
        mock_get_api.return_value = mock_api
        mock_extract.return_value = "Extracted PDF text"

        result = self.handler.run_tool({"filepath": "docs/paper.pdf"})
        assert "Extracted PDF text" in result[0].text


class TestGetVaultStructureToolHandler:
    def setup_method(self):
        self.handler = GetVaultStructureToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_get_vault_structure"

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_returns_tree(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.list_files_in_vault.return_value = [
            "Программирование/Python/intro.md",
            "Финансы/budget.md",
        ]
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({})
        data = json.loads(result[0].text)
        assert "Программирование" in data
        assert data["Финансы"]["_count"] == 1


class TestGetTaxonomyToolHandler:
    def setup_method(self):
        self.handler = GetTaxonomyToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_get_taxonomy"

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_returns_content(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.get_file_contents.return_value = "# Таксономия\n\n## Папки\n- Тест/"
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({})
        assert "Таксономия" in result[0].text

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_missing_taxonomy_returns_message(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.get_file_contents.side_effect = Exception("Not found")
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({})
        assert "not configured" in result[0].text.lower() or "не настроена" in result[0].text.lower()


class TestFindRelatedNotesToolHandler:
    def setup_method(self):
        self.handler = FindRelatedNotesToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_find_related_notes"

    def test_missing_keywords_raises(self):
        with pytest.raises(RuntimeError, match="keywords"):
            self.handler.run_tool({})

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_returns_aggregated_results(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.search.return_value = [
            {"filename": "note1.md", "score": 10, "matches": [{"context": "some context"}]},
        ]
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({"keywords": ["python"]})
        data = json.loads(result[0].text)
        assert len(data) == 1
        assert data[0]["path"] == "note1.md"


class TestSaveAtomicNoteToolHandler:
    def setup_method(self):
        self.handler = SaveAtomicNoteToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_save_atomic_note"

    def test_missing_required_raises(self):
        with pytest.raises(RuntimeError):
            self.handler.run_tool({"filepath": "test.md"})

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_creates_note(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.get_file_contents.side_effect = Exception("Not found")
        mock_api.put_content.return_value = None
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({
            "filepath": "Тест/заметка.md",
            "title": "Тестовая заметка",
            "content": "Содержимое заметки",
            "tags": ["тест", "пример"],
            "related": ["Другая заметка"],
            "source": "https://example.com",
            "source_type": "url",
        })

        mock_api.put_content.assert_called_once()
        call_args = mock_api.put_content.call_args
        written_content = call_args[0][1]
        assert "Тестовая заметка" in written_content
        assert "[[Другая заметка]]" in written_content
        assert "Successfully" in result[0].text

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_existing_file_raises(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.get_file_contents.return_value = "existing content"
        mock_get_api.return_value = mock_api

        with pytest.raises(RuntimeError, match="already exists"):
            self.handler.run_tool({
                "filepath": "existing.md",
                "title": "T",
                "content": "C",
                "tags": ["t"],
            })


class TestUpdateMocToolHandler:
    def setup_method(self):
        self.handler = UpdateMocToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_update_moc"

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_creates_new_moc(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.get_file_contents.side_effect = Exception("Not found")
        mock_api.put_content.return_value = None
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({
            "moc_path": "MOC Test.md",
            "entries": [{"title": "Note 1", "path": "n1.md", "description": "desc"}],
        })

        mock_api.put_content.assert_called_once()
        written = mock_api.put_content.call_args[0][1]
        assert "MOC Test" in written
        assert "[[n1.md|Note 1]]" in written

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_appends_to_existing_moc(self, mock_get_api):
        existing_moc = "---\ntitle: \"MOC Test\"\ntags: [moc]\n---\n# Test\n\n- [[old.md|Old]] \u2014 old\n"
        mock_api = MagicMock()
        mock_api.get_file_contents.return_value = existing_moc
        mock_api.put_content.return_value = None
        mock_get_api.return_value = mock_api

        self.handler.run_tool({
            "moc_path": "MOC Test.md",
            "entries": [{"title": "New", "path": "new.md", "description": "new desc"}],
        })

        written = mock_api.put_content.call_args[0][1]
        assert "[[new.md|New]]" in written
        assert "[[old.md|Old]]" in written


class TestSaveBinaryToolHandler:
    def setup_method(self):
        self.handler = SaveBinaryToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_save_binary"

    def test_missing_required_raises(self):
        with pytest.raises(RuntimeError):
            self.handler.run_tool({"source_path": "/tmp/file.png"})

    @patch("mcp_obsidian.kb_tools._get_api")
    @patch("builtins.open", create=True)
    def test_saves_file_and_wrapper(self, mock_open, mock_get_api):
        mock_file = MagicMock()
        mock_file.read.return_value = b"binary data"
        mock_open.return_value.__enter__ = lambda s: mock_file
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        mock_api = MagicMock()
        mock_api.put_content.return_value = None
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({
            "source_path": "/tmp/screenshot.png",
            "vault_dir": "Тест",
            "description": "UI mockup",
            "tags": ["скриншот"],
        })

        data = json.loads(result[0].text)
        assert "file_path" in data
        assert "wrapper_path" in data
        assert "_attachments" in data["file_path"]


class TestListMocsToolHandler:
    def setup_method(self):
        self.handler = ListMocsToolHandler()

    def test_tool_name(self):
        assert self.handler.name == "kb_list_mocs"

    @patch("mcp_obsidian.kb_tools._get_api")
    def test_returns_moc_list(self, mock_get_api):
        mock_api = MagicMock()
        mock_api.search.return_value = [
            {"filename": "MOC Programming.md", "score": 10, "matches": [{"context": "tags: [moc]"}]},
            {"filename": "MOC Finance.md", "score": 8, "matches": [{"context": "tags: [moc]"}]},
        ]
        mock_get_api.return_value = mock_api

        result = self.handler.run_tool({})
        data = json.loads(result[0].text)
        assert len(data) == 2
        assert data[0]["path"] == "MOC Programming.md"
