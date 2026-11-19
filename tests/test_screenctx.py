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
