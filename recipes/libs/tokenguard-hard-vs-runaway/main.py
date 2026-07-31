"""tokenguard-hard-vs-runaway — `clamp` and `break` guard two different failures. Pick by intent.

They are easy to confuse because both "cap the output", and the docs list them side by side. They
are not interchangeable:

  clamp  — a HARD CAP, enforced by the PROVIDER. Before the call goes out, tokenguard injects the
           provider's own output-limit kwarg (`max_completion_tokens`, or the nested equivalent on
           Bedrock/Gemini/Ollama). The response physically cannot exceed it. The call still happens.
  break  — a RUNAWAY GUARD, enforced by YOU, mid-flight. It only bites on a *stream*: a per-chunk
           observer closes the provider stream once the running output estimate crosses the cap.
           On a non-streamed call there is no mid-flight, so it can only notice afterwards.

Rule of thumb: **clamp** when you know the answer should be short. **break** when you don't know how
long it will be and want a stop button. **block** (not shown here) when the call must not happen at
all — see `recipes/quickstarts/tokenguard`.

Offline: fake OpenAI-shaped clients, no key.

  uv run python recipes/libs/tokenguard-hard-vs-runaway/main.py
"""

from types import SimpleNamespace

from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, clamps, reset

MODEL = "gpt-4o"
PROMPT = [{"role": "user", "content": "explain the refund policy"}]


def blocking_client(seen: dict):
    """A normal (non-streaming) fake provider that records the kwargs it was handed."""

    class Completions:
        def create(self, **kw):
            seen.clear()
            seen.update(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="short answer"))],
                usage=SimpleNamespace(prompt_tokens=40, completion_tokens=900),
                model=MODEL,
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def streaming_client(chunks: int = 80):
    closed = {"v": False}

    class Stream:
        def __init__(self) -> None:
            self._left = chunks

        def __iter__(self):
            return self

        def __next__(self):
            if self._left == 0:
                raise StopIteration
            self._left -= 1
            return SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="on and on "))]
            )

        def close(self) -> None:
            closed["v"] = True

    class Completions:
        def create(self, **kw):
            return Stream()

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions()))), closed


def main() -> None:
    # ---- clamp: the provider is told the ceiling, so the answer cannot be long ------------------
    reset()
    seen: dict = {}
    with budget(tokens=200, on_exceed="clamp"):
        blocking_client(seen).chat.completions.create(model=MODEL, messages=PROMPT)
    ceiling = seen.get("max_completion_tokens")
    print(
        f"clamp  (non-stream) : injected max_completion_tokens={ceiling} -> "
        f"{len(clamps())} clamp, no exception, the call ran"
    )

    # ---- break: the stream is cut mid-flight, and the socket is closed --------------------------
    reset()
    client, closed = streaming_client()
    got, cut = 0, None
    with budget(tokens=25, on_exceed="break"):
        try:
            for _ in client.chat.completions.create(model=MODEL, messages=PROMPT, stream=True):
                got += 1
        except BudgetExceeded as exc:
            cut = exc
    print(f"break  (stream)     : cut after {got}/80 chunks, provider stream closed={closed['v']}")

    # ---- break on a NON-stream: nothing to cut, so it can only notice afterwards ----------------
    reset()
    after = None
    try:
        with budget(tokens=25, on_exceed="break"):
            blocking_client({}).chat.completions.create(model=MODEL, messages=PROMPT)
    except BudgetExceeded as exc:
        after = str(exc)
    print(
        f"break  (non-stream) : {'raised POST-flight' if after else 'no effect'} - "
        f"the money is already spent"
    )
    print(f"                      {after.splitlines()[0][:96] if after else ''}")
    print(
        "choose              : clamp when the answer should be short (provider enforces it); "
        "break when length is unknown and you want a stop button"
    )

    assert ceiling is not None, "clamp did not inject a server-side ceiling"
    assert cut is not None and 0 < got < 80, "break did not cut the stream mid-flight"
    assert closed["v"] is True, "break left the provider stream open"
    assert after is not None, "break on a non-streamed call should still surface a breach"


if __name__ == "__main__":
    main()
