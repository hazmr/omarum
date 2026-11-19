from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import run_test

from omarum.screenctx import ScreenContext


async def test_code_on_screen_goes_with_what_you_said():
    ctx = LLMContext(messages=[{"role": "system", "content": "persona"},
                               {"role": "user", "content": "what does this do?"}])
    proc = ScreenContext(note=lambda: "[On screen: CompanyService.java]\n1 class CompanyService {}")
    down, _ = await run_test(proc, frames_to_send=[LLMContextFrame(context=ctx)], expected_down_frames=[LLMContextFrame])
    last = down[0].context.get_messages()[-1]
    assert last["role"] == "user"
    assert last["content"].startswith("[On screen: CompanyService.java]")
    assert last["content"].endswith("what does this do?")


async def test_nothing_on_screen_changes_nothing():
    ctx = LLMContext(messages=[{"role": "user", "content": "hi"}])
    down, _ = await run_test(ScreenContext(note=lambda: ""), frames_to_send=[LLMContextFrame(context=ctx)],
                             expected_down_frames=[LLMContextFrame])
    assert down[0].context.get_messages()[-1]["content"] == "hi"


async def test_asking_to_look_attaches_one_screenshot_and_older_ones_are_dropped():
    old = {"role": "user", "content": [{"type": "text", "text": "look at my screen"},
                                       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,OLD"}}]}
    ctx = LLMContext(messages=[{"role": "system", "content": "persona"}, old,
                               {"role": "assistant", "content": "nice"},
                               {"role": "user", "content": "what do you see now?"}])
    proc = ScreenContext(note=lambda: "", screenshot=lambda: b"JPEG")
    down, _ = await run_test(proc, frames_to_send=[LLMContextFrame(context=ctx)], expected_down_frames=[LLMContextFrame])
    msgs = down[0].context.get_messages()
    last = msgs[-1]["content"]
    assert isinstance(last, list)
    assert last[0]["type"] == "text" and "what do you see now?" in last[0]["text"]
    assert last[1]["image_url"]["url"] == "data:image/jpeg;base64,SlBFRw=="
    assert msgs[1]["content"][-1] == {"type": "text", "text": "[a screenshot was shown here]"}  # not sent again


async def test_no_screenshot_unless_asked():
    taken = []
    ctx = LLMContext(messages=[{"role": "user", "content": "how was your day"}])
    proc = ScreenContext(note=lambda: "", screenshot=lambda: taken.append(1) or b"x")
    down, _ = await run_test(proc, frames_to_send=[LLMContextFrame(context=ctx)], expected_down_frames=[LLMContextFrame])
    assert taken == [] and down[0].context.get_messages()[-1]["content"] == "how was your day"
