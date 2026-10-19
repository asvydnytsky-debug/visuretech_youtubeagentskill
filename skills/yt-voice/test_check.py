#!/usr/bin/env python3
"""test_check.py - what --check says, with the network stubbed out.

    python3 test_check.py

No key, no requests, no spend. The transport is replaced, so every branch is reachable without
an account in a particular state of brokenness.

This file exists because --check got the same answer wrong twice. First it printed "ok" over a
402 and exited 0, blessing a run that could not happen. Then it probed with a hardcoded voice the
account did not hold, which answers 402 on a free plan, and reported a working key as a billing
problem. Both were one-line reads of a two-case world. The cases are pinned here now.
"""
import importlib.util, io, json, os, sys, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("narrate", os.path.join(HERE, "narrate.py"))
narrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(narrate)

VOICES = json.dumps({"voices": [{"voice_id": "CwhRBWXzGAHq8TQ4Fs17", "name": "Roger - Laid-Back"},
                                {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George - Warm"}]}).encode()


def http(code, status):
    body = json.dumps({"detail": {"status": status, "message": f"simulated {status}"}}).encode()
    return urllib.error.HTTPError("https://x", code, status, {}, io.BytesIO(body))


def stub(failures):
    """A transport that fails for paths containing a given fragment and succeeds otherwise."""
    calls = []

    def send(path, method="GET", body=None, query=""):
        calls.append(path)
        for fragment, outcome in failures.items():
            if fragment in path:
                raise outcome()
        return (VOICES if path == "/voices" else b"{}"), {}
    send.calls = calls
    return send


def run(failures, voice=None, as_json=False):
    narrate.send = stub(failures)
    buf = io.StringIO()
    stdout, sys.stdout = sys.stdout, buf
    try:
        code = narrate.check(voice, as_json)
    finally:
        sys.stdout = stdout
    return code, buf.getvalue(), narrate.send.calls


CASES = [
    # name, failures, expected exit, substrings the output must contain
    ("a clean key probes a voice the account holds", {}, 0,
     ["CwhRBWXzGAHq8TQ4Fs17", "this account's own, Roger", "will serve it"]),
    ("a real 402, on the account's own voice, is a real 402",
     {"text-to-speech": lambda: http(402, "payment_required")}, 1,
     ["BLOCKED", "credit balance", "Narration is blocked"]),
    ("no voices_read: the stock fallback carries the 402 caveat",
     {"/voices": lambda: http(401, "missing_permissions"),
      "text-to-speech": lambda: http(402, "payment_required")}, 1,
     ["a stock fallback", "Read this one twice", "--voice <an id from --voices>"]),
    ("a spent quota blocks narration too",
     {"text-to-speech": lambda: http(401, "quota_exceeded")}, 1,
     ["BLOCKED", "characters are spent"]),
    ("a missing text_to_speech scope points at the key page",
     {"text-to-speech": lambda: http(401, "missing_permissions")}, 1,
     ["MISSING", "scopes it was created without"]),
    ("missing voices_read alone does not block narration",
     {"/voices": lambda: http(401, "missing_permissions")}, 0,
     ["MISSING", "Narration itself works"]),
    ("voice_not_found proves the scope and is not the account's fault",
     {"text-to-speech": lambda: http(400, "voice_not_found")}, 0, ["voice_not_found"]),
]

fail = 0
for name, failures, want_code, want_text in CASES:
    code, out, _ = run(failures)
    absent = [t for t in want_text if t not in out]
    ok = code == want_code and not absent
    fail += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        print(f"         exit {code}, wanted {want_code}" if code != want_code else "")
        print(f"         absent from output: {absent}" if absent else "")
        print("".join(f"         | {line}\n" for line in out.splitlines()))

# One /voices call answers both the voices_read row and which voice to probe with.
for label, voice in (("without --voice", None), ("with --voice", "MYVOICEID")):
    _, out, calls = run({}, voice=voice)
    n = calls.count("/voices")
    ok = n == 1 and (voice in out if voice else True)
    fail += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: /voices called {n}x, wanted 1")

code, out, _ = run({"text-to-speech": lambda: http(402, "payment_required")}, as_json=True)
doc = json.loads(out)
ok = code == 1 and doc["can_narrate"] is False and doc["blocked"] == ["text_to_speech"]
fail += not ok
print(f"  [{'PASS' if ok else 'FAIL'}] --json reports the block in can_narrate and blocked")

print(f"\n  {'all passed' if not fail else f'{fail} FAILED'}\n")
sys.exit(1 if fail else 0)
