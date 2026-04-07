import pytest
from unittest.mock import patch, MagicMock
from mcp_obsidian.fetcher import fetch_url, FetchResult

class TestFetchUrl:
    def test_fetch_returns_result_object(self):
        html = """
        <html><head><title>Test Article</title></head>
        <body>
        <article>
        <h1>Test Article</h1>
        <p>This is the main content of the test article with enough text to be extracted properly by trafilatura.</p>
        <p>It needs multiple paragraphs to work reliably with content extraction libraries.</p>
        <p>Adding more content here to ensure the extraction threshold is met for trafilatura processing.</p>
        </article>
        </body></html>
        """
        with patch("mcp_obsidian.fetcher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            mock_resp.content = html.encode("utf-8")
            mock_resp.url = "https://example.com/article"
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = fetch_url("https://example.com/article")

            assert isinstance(result, FetchResult)
            assert result.source_url == "https://example.com/article"
            assert result.title is not None
            assert len(result.content) > 0

    def test_fetch_pdf_content_type_returns_hint(self):
        with patch("mcp_obsidian.fetcher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.headers = {"Content-Type": "application/pdf"}
            mock_resp.content = b"%PDF-1.4 fake content"
            mock_resp.url = "https://example.com/paper.pdf"
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = fetch_url("https://example.com/paper.pdf")

            assert result.is_pdf is True
            assert result.content == ""

    def test_fetch_timeout_raises(self):
        with patch("mcp_obsidian.fetcher.requests.get") as mock_get:
            mock_get.side_effect = Exception("Connection timed out")

            with pytest.raises(Exception, match="Connection timed out"):
                fetch_url("https://example.com/slow")

    def test_fetch_too_large_raises(self):
        with patch("mcp_obsidian.fetcher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.headers = {"Content-Type": "text/html", "Content-Length": "10000000"}
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            with pytest.raises(Exception, match="exceeds maximum"):
                fetch_url("https://example.com/huge")
