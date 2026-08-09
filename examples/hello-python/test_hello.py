from hello import greet


def test_default_style_greeting():
    assert greet("World") == "Hello, World!"


def test_named_greeting():
    assert greet("Claude") == "Hello, Claude!"
