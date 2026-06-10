"""Day 2: HTML parsing and data extraction."""

from bs4 import BeautifulSoup

from src.parsing.html_parser import HTMLParser

SAMPLE_HTML = """
<html lang="en">
<head>
    <title>Sample page</title>
    <meta name="description" content="A sample description">
    <meta name="keywords" content="test, crawler">
    <meta property="og:title" content="OG Sample">
    <link rel="canonical" href="https://example.com/canonical">
    <script>var ignored = "SCRIPT_NOISE";</script>
    <style>.ignored { color: red; }</style>
</head>
<body>
    <h1>Main heading</h1>
    <h2>Section one</h2>
    <h2>Section two</h2>
    <h3>Subsection</h3>
    <p>Some body text here.</p>
    <a href="https://example.com/page1">Absolute</a>
    <a href="/page2">Relative</a>
    <a href="page3#section">With fragment</a>
    <a href="mailto:user@example.com">Mail</a>
    <a href="javascript:void(0)">JS</a>
    <a href="https://example.com/page1">Duplicate</a>
    <img src="/logo.png" alt="Logo">
    <img src="data:image/png;base64,xyz" alt="Inline">
    <table>
        <tr><th>Name</th><th>Value</th></tr>
        <tr><td>a</td><td>1</td></tr>
    </table>
    <ul><li>first</li><li>second</li></ul>
    <ol><li>one</li></ol>
    <div id="target">selected text</div>
</body>
</html>
"""

BASE_URL = "https://example.com/dir/index.html"


def make_soup(html: str = SAMPLE_HTML) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


async def test_parse_valid_html():
    parser = HTMLParser()
    page = await parser.parse_html(SAMPLE_HTML, BASE_URL)

    assert page["url"] == BASE_URL
    assert page["title"] == "Sample page"
    assert "Some body text here." in page["text"]
    assert "error" not in page


async def test_parse_broken_html_does_not_raise():
    parser = HTMLParser()
    page = await parser.parse_html("<div><p>unclosed <b>tags<table><tr>", "https://x.test/")

    assert page["url"] == "https://x.test/"
    assert isinstance(page["links"], list)


async def test_parse_empty_html_returns_partial():
    page = await HTMLParser().parse_html("", "https://x.test/")

    assert page["url"] == "https://x.test/"
    assert page["title"] == ""
    assert page["links"] == []


def test_extract_links_absolute_and_filtered():
    links = HTMLParser().extract_links(make_soup(), BASE_URL)

    assert "https://example.com/page1" in links
    assert "https://example.com/page2" in links  # relative resolved against host root
    assert "https://example.com/dir/page3" in links  # fragment dropped
    assert not any(link.startswith(("mailto:", "javascript:")) for link in links)
    assert links.count("https://example.com/page1") == 1  # deduplicated


def test_extract_text_with_selector():
    text = HTMLParser().extract_text(make_soup(), selector="#target")

    assert text == "selected text"


def test_extract_text_skips_script_and_style():
    page_text = HTMLParser()._parse(SAMPLE_HTML, BASE_URL).text

    assert "SCRIPT_NOISE" not in page_text
    assert "ignored" not in page_text


def test_extract_metadata():
    metadata = HTMLParser().extract_metadata(make_soup())

    assert metadata["title"] == "Sample page"
    assert metadata["description"] == "A sample description"
    assert metadata["keywords"] == "test, crawler"
    assert metadata["og:title"] == "OG Sample"
    assert metadata["lang"] == "en"
    assert metadata["canonical"] == "https://example.com/canonical"


def test_extract_images_absolute_src_and_skip_data_uri():
    images = HTMLParser().extract_images(make_soup(), BASE_URL)

    assert images == [{"src": "https://example.com/logo.png", "alt": "Logo"}]


def test_extract_headings():
    headings = HTMLParser().extract_headings(make_soup())

    assert headings["h1"] == ["Main heading"]
    assert headings["h2"] == ["Section one", "Section two"]
    assert headings["h3"] == ["Subsection"]


def test_extract_tables_and_lists():
    parser = HTMLParser()
    soup = make_soup()

    assert parser.extract_tables(soup) == [[["Name", "Value"], ["a", "1"]]]
    lists = parser.extract_lists(soup)
    assert {"type": "ul", "items": ["first", "second"]} in lists
    assert {"type": "ol", "items": ["one"]} in lists


async def test_fetch_and_parse_integration(server, crawler):
    page = await crawler.fetch_and_parse(str(server.make_url("/html")))

    assert page["title"] == "Test page"
    assert page["metadata"]["description"] == "demo page"
    # Relative links resolved against the test server origin.
    assert str(server.make_url("/ok")) in page["links"]
    assert str(server.make_url("/relative/path")) in page["links"]


async def test_fetch_and_parse_returns_none_on_fetch_error(server, crawler):
    assert await crawler.fetch_and_parse(str(server.make_url("/no-such"))) is None
