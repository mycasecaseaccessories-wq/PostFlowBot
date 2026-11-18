from app.services.content_transform import transform_text


def test_route_transformations_are_independent_and_literal():
    source = "Hello @sample_user visit https://example.com and PROMO.CODE!"
    assert transform_text(source, remove_usernames=True) == (
        "Hello visit https://example.com and PROMO.CODE!"
    )
    assert transform_text(source, remove_links=True) == (
        "Hello @sample_user visit and PROMO.CODE!"
    )
    assert transform_text(source, remove_keywords="promo.code") == (
        "Hello @sample_user visit https://example.com and !"
    )


def test_transform_handles_multiple_keywords_and_normalizes_spacing():
    assert transform_text(
        "Sale   TODAY\n\n\nVisit https://example.com",
        remove_links=True,
        remove_keywords="sale,today",
    ) == "Visit"


def test_transform_empty_text_and_keyword_list():
    assert transform_text(None) == ""
    assert transform_text("Keep this", remove_keywords=" ,\n ") == "Keep this"
