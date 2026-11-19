from omarum.config import Config
from omarum.persona import render


def test_persona_fills_names():
    text = render(Config(user_name="Sam"))
    assert "You are Rum." in text
    assert "Sam" in text
    assert "{name}" not in text and "{user}" not in text


def test_persona_is_a_conversation_partner_not_an_interviewer():
    from omarum.persona import DEFAULT_PERSONA

    p = DEFAULT_PERSONA.lower()
    assert "ask follow-up questions" not in p and "let them talk more than you" not in p
    assert "speech recognition" in p          # misheard words: go with the likely meaning, don't doubt them
    assert "your own" in p                     # shares its own thoughts, stories, opinions
    assert "not every" in p                    # questions only sometimes


def test_untouched_old_persona_file_is_upgraded_but_an_edited_one_is_kept(tmp_path):
    from omarum import persona
    from omarum.config import Config

    class S:
        persona_path = tmp_path / "persona.md"

    S.persona_path.write_text(persona.PREVIOUS_DEFAULTS[0])
    out = persona.load(Config(companion_name="Rum", user_name="Hazem"), S)
    assert "speech recognition" in out and S.persona_path.read_text() == persona.DEFAULT_PERSONA

    S.persona_path.write_text(persona.PREVIOUS_DEFAULTS[0] + "\nAlways call me captain.\n")
    out = persona.load(Config(companion_name="Rum", user_name="Hazem"), S)
    assert "captain" in out and "speech recognition" not in out  # the user's own version wins
