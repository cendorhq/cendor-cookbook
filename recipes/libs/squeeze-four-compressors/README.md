# squeeze-four-compressors — "compress this" means four different things

**The pain.** You have a 200 KB payload and a context window. Generic compression either mangles it
or barely helps, because a JSON blob, a log dump, a source file and a page of prose fail in
completely different ways — and the right move for one is the wrong move for another.

**What this shows.** squeeze runs a **different technique per kind**, and `detect()` picks one by
sniffing the content:

| kind | technique | why |
|---|---|---|
| `json` | minify + drop nulls | whitespace and empty fields are pure overhead |
| `logs` | normalize + dedup | blank the volatile fields, then near-identical lines collapse |
| `code` | strip comments and blank lines | structure is the signal, not the formatting |
| `prose` | extractive | keep the sentences carrying the most new information |

`fidelity` chooses how hard to push — `lossless`, `balanced`, `aggressive` — and every result stays
reversible regardless, because the original lives in the content-addressed store.

## Run it

```bash
uv run python recipes/libs/squeeze-four-compressors/main.py
```

## Expected output

```text
kind    detect() fidelity   tokens             ratio   technique
json    json     lossless    5,282 ->  3,123  59.1%   minify
json    json     balanced    5,282 ->  2,643  50.0%   minify+dropnulls
json    json     aggressive  5,282 ->  2,643  50.0%   minify+dropnulls
logs    logs     lossless   14,399 ->     35   0.2%   normalize+dedup
logs    logs     balanced   14,399 ->     35   0.2%   normalize+dedup
logs    logs     aggressive 14,399 ->     35   0.2%   normalize+dedup
code    code     lossless    1,428 ->  1,428  100.0%   code:lossless
code    code     balanced    1,428 ->    852  59.7%   code:balanced
code    code     aggressive  1,428 ->    852  59.7%   code:aggressive
prose   prose    lossless    1,501 ->  1,501  100.0%   extractive
prose   prose    balanced    1,501 ->    944  62.9%   extractive
prose   prose    aggressive  1,501 ->    683  45.5%   extractive

auto    detected logs, target 400 -> 35 tokens (normalize+dedup)
every row above is reversible: handle.expand() returned the original byte-for-byte
```

Three things worth reading off that table, all measured on this recipe's own inputs (swap the
samples and you get the numbers for *your* content):

- **Logs compress ~500×.** Repetitive machine output is where squeeze is spectacular, because after
  normalization there are only a handful of distinct line patterns.
- **`lossless` is a real setting, not a slower `balanced`.** On code and prose it returns the input
  unchanged — nothing can be removed without losing a byte. On JSON it still wins 41%, because
  minification *is* lossless.
- **`aggressive` only differs where there is judgement to exercise.** JSON and logs are identical to
  `balanced`; prose drops another 17 points, because choosing which sentences to keep is the only
  place a "how hard should I push" dial means anything.

Libraries: `core`, `squeeze` · Offline ✓ · [← all recipes](../../../README.md)
