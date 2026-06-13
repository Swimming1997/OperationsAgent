"""Douyin connector (browser + intercepted-response collection).

Mirrors the XHS connector layout but reuses the platform-agnostic engine core
(``engine.pacing`` for human-like behavior, ``engine.session`` for the session
contract). Collection prefers driving a logged-in browser like a human and
capturing the JSON the page itself fetches (the page signs ``a_bogus`` for us),
with DOM as fallback — we never sign requests ourselves.
"""
