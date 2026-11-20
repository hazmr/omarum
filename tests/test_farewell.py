from omarum.farewell import is_farewell


def test_goodbyes_close_rum():
    for said in ("Bye.", "Okay, bye bye!", "Goodbye Rum", "See you tomorrow.", "Good night!", "That's all, thanks.",
                 "Thanks, talk to you later", "Stop listening.", "OK I'm done, bye", "see ya"):
        assert is_farewell(said), said


def test_ordinary_sentences_dont():
    for said in ("I'll fix it later today, it's fine", "what does goodbye mean in Arabic and how do I say it nicely",
                 "That's all the code I wrote this morning, can you check it?", "let me see you handle this one",
                 "I'm done with the controller, now the service", "how was your night"):
        assert not is_farewell(said), said
