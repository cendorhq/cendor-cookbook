"""acttrace-custom-detector — teach the redactor about YOUR identifiers.

The built-in detectors cover what everyone has: emails, cards, IBANs, API keys. They cannot know
that in your system a `PAT-` prefix followed by 24 characters is a partner access token, or that
`case/2026/00842` is a case reference that must never reach a log.

Two opt-ins close that gap, and both are process-global — you turn them on once at startup:

  register_detector(Detector(...))   your own pattern, with an optional validator so a format-shaped
                                     string that fails its checksum is not a false positive
  enable_locale_pack("uk", "in")     bundled government-ID detectors, off by default because a
                                     nine-digit-plus-letter pattern would misfire in a locale that
                                     does not use one

Registered detectors are picked up by `scan()`, `redact()`, and — via the active policy — by
`AuditLog`'s auto-flagging. `reset_detectors()` puts the registry back to the built-ins, which is
what you want between tests.

All the identifiers below are synthetic, format-valid examples. Offline: no model call, no key.

  uv run python recipes/libs/acttrace-custom-detector/main.py
"""

import re

from cendor.acttrace import (
    Detector,
    Policy,
    enable_locale_pack,
    redact,
    register_detector,
    reset_detectors,
    scan,
)

# A partner access token: shaped like a key, but nothing built in knows the prefix.
PARTNER_TOKEN = re.compile(r"\bPAT-[A-Za-z0-9]{24}\b")

# A case reference with a check digit: the LAST digit is the sum of the others mod 10. Without the
# validator, any five digits would match and every invoice number in the corpus becomes a finding.
CASE_REF = re.compile(r"\bcase/20\d{2}/\d{5}\b")


def case_ref_valid(match: str) -> bool:
    digits = [int(c) for c in match.rsplit("/", 1)[1]]
    return sum(digits[:-1]) % 10 == digits[-1]


PAYLOAD = {
    "note": "escalated by dana.smith@contoso.com under case/2026/00842",
    "auth": "PAT-9f2b7c41ea0d5836ab1c4e70",
    "nino": "AB123456C",
    "uid": "234567890009",
    "invoice": "case/2026/12345",  # right shape, wrong check digit — must NOT be a finding
}


def categories(obj) -> list[str]:
    return [f.category for f in scan(obj)]


def main() -> None:
    reset_detectors()
    print(f"built-ins only    : {categories(PAYLOAD)}")
    print("                    (the token, the case ref and both gov IDs are invisible)")

    register_detector(Detector("partner_token", "secret", "critical", PARTNER_TOKEN))
    register_detector(Detector("case_ref", "pii", "warning", CASE_REF, case_ref_valid))
    added = enable_locale_pack("uk", "in")

    print(f"locale packs      : enabled {added}")
    print(f"after registering : {categories(PAYLOAD)}")

    findings = {f.category: f for f in scan(PAYLOAD)}
    print(
        f"validator working : 'case/2026/12345' has the right shape but a bad check digit -> "
        f"case_ref count is {findings['case_ref'].count}, not 2"
    )

    # Policy resolves per category, falling back to the group. A custom detector in the "secret"
    # group inherits whatever the policy says about secrets — no policy edit needed.
    cleaned, resolved = redact(PAYLOAD, Policy.strict())
    print("redact(Policy.strict()):")
    for f in resolved:
        print(f"  {f.category:<14} group={f.group:<8} severity={f.severity:<8} action={f.action}")
    print(f"  scrubbed payload : {cleaned['auth']} / {cleaned['nino']} / {cleaned['uid']}")

    reset_detectors()
    print(f"reset_detectors() : back to {categories(PAYLOAD)} - use this between tests")

    assert "partner_token" not in str(cleaned), "the custom secret survived redaction"
    assert findings["case_ref"].count == 1, "the validator did not reject the bad check digit"
    assert {"uk_nino", "in_aadhaar"} <= set(findings), "the locale packs did not register"
    assert "partner_token" not in categories(PAYLOAD), "reset_detectors() left the registry dirty"


if __name__ == "__main__":
    main()
