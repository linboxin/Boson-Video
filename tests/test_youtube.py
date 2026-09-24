import json

import pytest

from boson_video.youtube import (
    YouTubeError,
    parse_storyboard,
    parse_video_id,
    parse_watch_page,
    pick_level,
)

VID = "dQw4w9WgXcQ"
SPEC = (
    "https://i.ytimg.com/sb/dQw4w9WgXcQ/storyboard3_L$L/$N.jpg?sqp=abc"
    "|48#27#100#10#10#0#default#rs$AAA"
    "|80#45#108#10#10#2000#M$M#rs$BBB"
    "|160#90#108#5#5#2000#M$M#rs$CCC"
    "|320#180#108#3#3#2000#M$M#rs$DDD"
)


@pytest.mark.parametrize(
    "ref",
    [
        VID,
        f"https://www.youtube.com/watch?v={VID}",
        f"https://www.youtube.com/watch?feature=share&v={VID}&t=42s",
        f"youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}&list=RD",
        f"https://youtu.be/{VID}?si=xyz",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/live/{VID}?feature=share",
        f"https://www.youtube-nocookie.com/embed/{VID}",
    ],
)
def test_parse_video_id_accepts_common_forms(ref):
    assert parse_video_id(ref) == VID


@pytest.mark.parametrize(
    "ref",
    ["", "hello", "https://vimeo.com/123", f"https://notyoutube.com/watch?v={VID}", "https://youtu.be/short"],
)
def test_parse_video_id_rejects_others(ref):
    with pytest.raises(YouTubeError):
        parse_video_id(ref)


def test_parse_storyboard_levels_and_urls():
    levels = parse_storyboard(SPEC)
    assert [lv.level for lv in levels] == [0, 1, 2, 3]
    top = levels[3]
    assert (top.width, top.height, top.count, top.cols, top.rows, top.interval_ms) == (320, 180, 108, 3, 3, 2000)
    assert top.per_sheet == 9 and top.sheet_count == 12
    assert top.sheet_url(5) == "https://i.ytimg.com/sb/dQw4w9WgXcQ/storyboard3_L3/M5.jpg?sqp=abc&sigh=rs$DDD"
    assert levels[0].sheet_url(0) == "https://i.ytimg.com/sb/dQw4w9WgXcQ/storyboard3_L0/default.jpg?sqp=abc&sigh=rs$AAA"


def test_frame_time_uses_interval_or_spreads_evenly_and_clamps():
    levels = parse_storyboard(SPEC)
    assert levels[3].frame_time(10, 213) == 20.0
    assert levels[3].frame_time(107, 213) == 212.5  # past the end: clamped
    assert levels[0].frame_time(50, 200) == 100.0  # interval 0: spread over the video


def test_parse_storyboard_skips_malformed_levels():
    levels = parse_storyboard("https://i.ytimg.com/x/$L/$N.jpg?a|garbage|0#0#0#0#0#0#M$M#s|160#90#10#5#5#1000#M$M#s")
    assert [lv.level for lv in levels] == [2]


def test_pick_level():
    levels = parse_storyboard(SPEC)
    assert pick_level(levels).level == 3
    assert pick_level(levels, 1).level == 1
    with pytest.raises(YouTubeError):
        pick_level(levels, 9)
    with pytest.raises(YouTubeError):
        pick_level([])


def _page(player: dict, data: dict | None = None) -> str:
    html = f"<html><script>var ytInitialPlayerResponse = {json.dumps(player)};var meta = 1;</script>"
    if data is not None:
        html += f'<script>var ytInitialData = {json.dumps(data)};</script>'
    return html + "</html>"


PLAYER = {
    "playabilityStatus": {"status": "OK"},
    "videoDetails": {"title": "A <talk>", "author": "Someone", "lengthSeconds": "213"},
    "storyboards": {"playerStoryboardSpecRenderer": {"spec": SPEC}},
    "captions": {
        "playerCaptionsTracklistRenderer": {
            "captionTracks": [
                {"languageCode": "en", "kind": "asr", "name": {"simpleText": "English (auto)"}},
                {"languageCode": "zh-Hans", "name": {"runs": [{"text": "Chinese"}]}},
            ]
        }
    },
}
DATA = {
    "playerOverlays": {
        "markersMap": [
            {
                "key": "AUTO_CHAPTERS",
                "value": {"chapters": [{"chapterRenderer": {"title": {"simpleText": "auto"}, "timeRangeStartMillis": 0}}]},
            },
            {
                "key": "DESCRIPTION_CHAPTERS",
                "value": {
                    "chapters": [
                        {"chapterRenderer": {"title": {"simpleText": "Outro"}, "timeRangeStartMillis": 180000}},
                        {"chapterRenderer": {"title": {"simpleText": "Intro"}, "timeRangeStartMillis": 0}},
                    ]
                },
            },
        ]
    },
    "frameworkUpdates": {
        "mutations": [
            {
                "markersList": {
                    "markers": [
                        {"startMillis": "0", "durationMillis": "2130", "intensityScoreNormalized": 1},
                        {"startMillis": "2130", "durationMillis": "2130", "intensityScoreNormalized": 0.25},
                    ]
                }
            }
        ]
    },
}


def test_parse_watch_page_extracts_everything():
    page = parse_watch_page(_page(PLAYER, DATA), VID)
    assert page.video.title == "A <talk>" and page.video.channel == "Someone"
    assert page.video.duration == 213 and page.video.id == VID
    assert page.video.link(61.9) == f"https://www.youtube.com/watch?v={VID}&t=61s"
    assert len(page.levels) == 4
    assert [(c.start, c.title) for c in page.chapters] == [(0, "Intro"), (180, "Outro")]  # creator chapters win
    assert [(h.start, h.intensity) for h in page.heat] == [(0, 1.0), (2.13, 0.25)]
    assert [(c.lang, c.kind, c.name) for c in page.captions] == [
        ("en", "asr", "English (auto)"),
        ("zh-Hans", "manual", "Chinese"),
    ]


def test_parse_watch_page_without_initial_data():
    page = parse_watch_page(_page(PLAYER), VID)
    assert page.chapters == [] and page.heat == []


def test_parse_watch_page_errors():
    with pytest.raises(YouTubeError, match="no player data"):
        parse_watch_page("<html>nothing here</html>", VID)
    blocked = dict(PLAYER, playabilityStatus={"status": "LOGIN_REQUIRED", "reason": "Sign in to confirm your age"})
    with pytest.raises(YouTubeError, match="confirm your age"):
        parse_watch_page(_page(blocked), VID)
    live = dict(PLAYER, storyboards={"playerLiveStoryboardSpecRenderer": {"spec": "x"}})
    with pytest.raises(YouTubeError, match="live"):
        parse_watch_page(_page(live), VID)
    bare = {k: v for k, v in PLAYER.items() if k != "storyboards"}
    with pytest.raises(YouTubeError, match="no storyboard"):
        parse_watch_page(_page(bare), VID)
