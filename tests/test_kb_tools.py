import pytest
import json
from unittest.mock import patch, MagicMock
from mcp_obsidian.kb_tools import FetchUrlToolHandler, ExtractPdfToolHandler


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
