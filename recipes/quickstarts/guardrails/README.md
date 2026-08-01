# guardrails — block, redact, and record before the model call

**The pain.** A prompt-injection string or a leaked API key shouldn't reach the model at all —
and when you stop one, you want *proof* you did, not a log line you can edit later.

**What this shows.** `instrument()` wraps a fake OpenAI-shaped client; `install()` attaches two
deterministic guardrails on the interceptor seam. A prompt-injection attempt is **blocked before
the request is sent** (`$0.00` spent — the model never sees it); a leaked `sk-…` key is **redacted**
so the *provider* receives `"[redacted]"` instead of the secret. Both decisions land in an
`AuditLog` hash chain as `guardrail_decision` entries that `verify()` confirms — offline, no key.

## Run it

```bash
uv run python recipes/quickstarts/guardrails/main.py
```

## Expected output

```text
BLOCKED by keyword_deny (input): denied keyword: 'ignore previous instructions'
  provider calls so far: 0  =>  $0.00 spent on it

REDACTED before send: provider received 'my key is [redacted]'

guardrail_decision entries in the audit chain:
  block  input  keyword_deny
  redact input  regex_rule

chain verifies: True  (the blocked prompt spent $0.00 - the model never saw it)
```

The checks are deterministic (regex/keyword) — microseconds, offline, `$0`. They catch what you
configure, **not** a novel jailbreak; pair them with a bring-your-own model judge
(`rules.llm_judge`) for open-ended risk, and use `acttrace`'s `guard(Policy…)` for PII/secret
detection. Nothing here is an invented number: the blocked prompt makes **zero** provider calls.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/guardrails/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `guardrails`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
