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

PRO, PREMADE = "cBTYF7NiJbR8Bvmdeuse", "CwhRBWXzGAHq8TQ4Fs17"
# A professional voice first in the list, as a real account returns it: a free plan answers 402
# on it while premade voices go through, which is the case that reads as a billing problem.
VOICES = json.dumps({"voices": [
    {"voice_id": PRO, "name": "Mike - Animation", "category": "professional"},
    {"voice_id": PREMADE, "name": "Roger - Laid-Back", "category": "premade"},
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George - Warm", "category": "premade"},
]}).encode()


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


def tts_calls(calls):
    return [c.rsplit("/", 1)[-1] for c in calls if c.startswith("/text-to-speech/")]


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
    ("402 on every voice is the account, and says it was re-probed",
     {"text-to-speech": lambda: http(402, "payment_required")}, 1,
     ["BLOCKED", "credit balance", "failed there too, so it is not the voice",
      "Narration is blocked"]),
    ("402 on one voice only: the voice, not the plan - and never Subscription",
     {f"text-to-speech/{PRO}": lambda: http(402, "payment_required")}, 1,
     ["this voice only", "this is the voice, not the plan", "Do not go to",
      "Narration works, but not with"]),
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
    ("no voice list to re-probe with: the 402 is not stated as billing",
     {"/voices": lambda: http(401, "missing_permissions"),
      "text-to-speech": lambda: http(402, "payment_required")}, 1,
     ["a stock fallback", "may still be", "Confirm with --voice <an id from --voices>"]),
]

fail = 0
for name, failures, want_code, want_text in CASES:
    # Only the "one voice only" case is about a voice the user named.
    named = PRO if "402 on one voice only" in name else None
    code, out, _ = run(failures, voice=named)
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

# Auto-pick skips the professional voice entirely: a free plan is allowed premade ones, so the
# common path never has to recover from a 402 it could have avoided.
_, out, calls = run({})
first = tts_calls(calls)[0]
ok = first == PREMADE and "Roger" in out
fail += not ok
print(f"  [{'PASS' if ok else 'FAIL'}] auto-pick prefers premade: probed {first[:12]}..., "
      f"wanted {PREMADE[:12]}...")

# An unusable voice we picked ourselves is a note, not a failed key: another of theirs works.
code, out, _ = run({f"text-to-speech/{PREMADE}": lambda: http(402, "payment_required")})
ok = code == 0 and "Narration works. Narrate with" in out
fail += not ok
print(f"  [{'PASS' if ok else 'FAIL'}] a voice we chose that 402s is a note, not a blocked key "
      f"(exit {code}, wanted 0)")

# The re-probe costs exactly one extra request, and only on a 402.
_, _, calls = run({})
ok = len(tts_calls(calls)) == 1
fail += not ok
print(f"  [{'PASS' if ok else 'FAIL'}] no 402, no re-probe: {len(tts_calls(calls))} tts call(s), "
      "wanted 1")
_, _, calls = run({f"text-to-speech/{PRO}": lambda: http(402, "payment_required")}, voice=PRO)
ok = len(tts_calls(calls)) == 2
fail += not ok
print(f"  [{'PASS' if ok else 'FAIL'}] a 402 costs one re-probe: {len(tts_calls(calls))} tts "
      "call(s), wanted 2")

print(f"\n  {'all passed' if not fail else f'{fail} FAILED'}\n")
sys.exit(1 if fail else 0)
