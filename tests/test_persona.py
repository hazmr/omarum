from omarum.config import Config
from omarum.persona import render


def test_persona_fills_names():
    text = render(Config(user_name="Hazem"))
    assert "You are Rum." in text
    assert "Hazem" in text
    assert "{name}" not in text and "{user}" not in text
