# acttrace-custom-detector — teach the redactor about *your* identifiers

**The pain.** The built-in detectors cover what everyone has: emails, cards, IBANs, API keys. They
cannot know that in your system a `PAT-` prefix followed by 24 characters is a partner access token,
or that `case/2026/00842` is a case reference that must never reach a log. So the one identifier that
is actually specific to you is the one that leaks.

**What this shows.** Two opt-ins, both process-global (you turn them on once at startup):

- `register_detector(Detector(category, group, severity, pattern, validator))` — your own pattern,
  with an optional **validator** so a format-shaped string that fails its checksum is not a false
  positive.
- `enable_locale_pack("uk", "in")` — bundled government-ID detectors, off by default because a
  nine-digit-plus-letter pattern would misfire badly in a locale that does not use one.

Registered detectors are picked up by `scan()`, `redact()`, and — via the active policy — by
`AuditLog`'s auto-flagging. `reset_detectors()` restores the built-ins, which is what you want
between tests.

Closes `register_detector` and `enable_locale_pack`, which no other recipe exercises.

## Run it

```bash
uv run python recipes/libs/acttrace-custom-detector/main.py
```

## Expected output

```text
built-ins only    : ['email']
                    (the token, the case ref and both gov IDs are invisible)
locale packs      : enabled ['uk_nino', 'in_aadhaar']
after registering : ['case_ref', 'email', 'in_aadhaar', 'partner_token', 'uk_nino']
validator working : 'case/2026/12345' has the right shape but a bad check digit -> case_ref count is 1, not 2
redact(Policy.strict()):
  case_ref       group=pii      severity=warning  action=redact
  email          group=pii      severity=warning  action=redact
  in_aadhaar     group=gov_id   severity=critical action=block
  partner_token  group=secret   severity=critical action=block
  uk_nino        group=gov_id   severity=critical action=block
  scrubbed payload : <redacted> / <redacted> / <redacted>
reset_detectors() : back to ['email'] - use this between tests
```

The first line is the honest baseline: out of five sensitive values in the payload, the built-ins
found **one**. Four registrations later, all five are found.

**The `validator` is the part people skip.** The payload contains two strings matching
`case/20\d{2}/\d{5}`; only one has a valid check digit, and only one becomes a finding. Without the
validator, every invoice number in your corpus is a false positive — and a detector that cries wolf
gets switched off, which is worse than not having it.

**You do not edit the policy.** A custom detector declares a `group` (`secret`, `pii`, `gov_id`, …),
and the policy resolves on category-then-group, so `partner_token` inherits whatever
`Policy.strict()` says about secrets. Category-specific rules still win when you want one.

Every identifier here is synthetic and format-valid — nothing real is committed.

Libraries: `core`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
