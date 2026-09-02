from datetime import date

from linerfy_ingest.guardian import build_context, parse_content, strip_html

_CONTENT = {
    "webTitle": "Lana Del Rey: Norman Fucking Rockwell! review",
    "webUrl": "https://www.theguardian.com/music/2019/aug/30/lana-del-rey-norman-fucking-rockwell-review",
    "webPublicationDate": "2019-08-30T06:00:22Z",
    "fields": {
        "body": (
            "<p>We live in a world of terrifying flux. <a href='x'>An artist</a> "
            "you can depend on.</p><p>Second paragraph.</p>"
        ),
        "byline": "Alexis Petridis",
        "starRating": "3",
        "trailText": "An artist you can depend on.",
        "headline": "Lana Del Rey: Norman Fucking Rockwell! review",
        "publication": "The Guardian",
    },
}


def test_strip_html_keeps_paragraphs_and_drops_inline_tags() -> None:
    assert (
        strip_html("<p>A <em>bold</em> claim &amp; more.</p><p>Second para.</p>")
        == "A bold claim & more.\nSecond para."
    )


def test_parse_content_extracts_metadata_and_plain_text() -> None:
    review = parse_content(_CONTENT)

    assert review.title == "Lana Del Rey: Norman Fucking Rockwell! review"
    assert review.author == "Alexis Petridis"
    assert review.score == 3
    assert review.score_scale == 5
    assert review.published_at == date(2019, 8, 30)
    assert review.url.endswith("/lana-del-rey-norman-fucking-rockwell-review")
    assert review.trail_text == "An artist you can depend on."
    assert "We live in a world" in review.body_text
    assert "<" not in review.body_text


def test_build_context_is_summary_less_and_keeps_content_private() -> None:
    review = parse_content(_CONTENT)
    context = build_context(review)

    assert context.summary is None
    assert context.release.id == "norman-fucking-rockwell"

    document = context.review_documents[0]
    assert document.source_id == "guardian"
    assert document.content == review.body_text
    assert len(document.public_excerpt) <= document.policy.excerpt_max_chars
