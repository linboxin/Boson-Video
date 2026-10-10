"""The video's page inside an AI app (MCP Apps) offline: video_open carries the page, the page's own
tools stay hidden from the model, the document answers with only its version when nothing changed,
and pictures and sheets come out small and only for what is on disk."""

import asyncio
import io
import json

from PIL import Image

from boson_video import library, mcp_server, viewer

from test_plugin import _tl, home  # noqa: F401  (home is a fixture)

KEY = "abcdefghijk"


def test_the_page_is_one_document_with_the_bridge_before_the_page():
    html = viewer.page()
    assert html.startswith("<!doctype html>") and html.count("</script>") == 2 and html.count("</style>") == 1
    assert html.index("window.BV_SOURCE = {") < html.index("const SRC = window.BV_SOURCE")  # mcp.js runs first
    assert ".embed:not(.full) .watch" in html and ':root[data-theme="dark"]' in html


def test_video_open_shows_the_page_and_the_page_tools_stay_hidden_from_the_model():
    tools = {t.name: (t.meta or {}).get("ui") for t in asyncio.run(mcp_server.server.list_tools())}
    assert tools["video_open"] == {"resourceUri": viewer.URI}
    for name in ("page_document", "page_picture", "page_sheet"):
        assert tools[name] == {"resourceUri": viewer.URI, "visibility": ["app"]}
    assert tools["video_read"] is None  # the reading tools stay plain text
    page = asyncio.run(mcp_server.server.read_resource(viewer.URI))[0]
    assert page.mime_type == "text/html;profile=mcp-app"
    assert page.meta["ui"]["csp"]["frameDomains"] == viewer.FRAMES  # the YouTube player, nothing else framed


def test_the_document_says_only_its_version_when_nothing_changed(home):
    library.save(_tl(), home / KEY)
    doc = json.loads(mcp_server.page_document(KEY))
    assert doc["video"]["title"] == "残差流是什么" and len(doc["transcript"]) == 4 and doc["status"]["stage"]
    assert viewer.document(KEY, doc["version"]) == {"same": True, "version": doc["version"]}
    (home / KEY / "status.json").write_text(json.dumps({"stage": "screens"}), encoding="utf-8")
    again = viewer.document(KEY, doc["version"])
    assert again["version"] != doc["version"] and again["status"]["stage"] == "screens"


def test_a_video_not_started_yet_has_no_document(home):
    doc = viewer.document("zyxwvutsrqp")
    assert "video" not in doc and doc["status"]["stage"] == "missing"


def test_pictures_are_cut_at_whole_seconds_and_sent_small(home):
    library.save(_tl(), home / KEY)
    data = viewer.picture(KEY, 12.7)
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "JPEG" and im.width <= viewer.WIDTH
    assert [p.name for p in (home / KEY / "frames").glob("*-thumb.jpg")] == ["12000-thumb.jpg"]
    assert viewer.picture("zyxwvutsrqp", 3) is None


def test_sheets_come_by_index_and_only_from_the_video_folder(home):
    library.save(_tl(), home / KEY)
    assert viewer.sheet(KEY, 0)[:2] == b"\xff\xd8"
    assert viewer.sheet(KEY, 5) is None and viewer.sheet(KEY, -1) is None
    assert mcp_server.page_sheet(KEY, 5) == "no such sheet"
