#!/usr/bin/env python3
"""narrate.py - a script into recorded voiceover, one audio file per beat.

    python3 narrate.py script.md --dry-run          # the plan, no key, no network, no spend
    python3 narrate.py script.md --voice <voice_id> # synthesize
    python3 narrate.py --voices                     # the voices on your account
    python3 narrate.py --quota                      # characters left this month
    python3 narrate.py --check                      # which scopes your key actually carries

Takes the script /yt-script wrote and strips it back to the words you would actually say: the
`[ON SCREEN: ...]` directions, the beat headers, the timestamps and the markdown all come out, because
every one of them is a character you would otherwise pay to have read aloud. What is left is cut at
beat boundaries, never mid-sentence, and sent one beat per request.

One beat per file is the point. A line you dislike is one beat to redo, not the whole script, and
your editor gets cuts that already line up with the beats you wrote.

Continuity across those cuts is handled rather than assumed: each request carries the tail of the
previous beat and the head of the next one as context, plus the previous request ids, so the voice
does not reset its prosody at every file boundary.

Reads the key from ELEVENLABS_API_KEY, XI_API_KEY or KEY, in that order. A restricted key is
accepted by the account and then refuses one scope at a time, which reads as several unrelated
failures; `--check` asks for all of them at once and tells you which single thing to fix.

WHAT IT DOES NOT DO. It does not publish, it does not edit, and it does not stitch. It writes mp3s
and a `concat.txt`, and you run ffmpeg if you want one file. It never invents a voice id - without
--voice it asks and stops. Characters are real money on your account, so --dry-run prints the exact
spend before anything is sent, and nothing is sent until you drop the flag.
"""
import json, os, re, ssl, sys, urllib.error, urllib.request

API = "https://api.elevenlabs.io/v1"
WPM = 150                      # the pack's own convention for runtime estimates
DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_MAX = 2200             # characters per request; small enough that a retake is cheap

# Direction, not speech. Every one of these is stripped before a character is billed.
ON_SCREEN = re.compile(r"\[\s*on\s*screen\s*:[^\]]*\]", re.I)
BRACKETED = re.compile(r"\[[^\]]*\]")
CAPS_PAREN = re.compile(r"\(\s*[A-Z][A-Z\s/'-]{2,}\s*\)")
TIMECODE = re.compile(r"\(?\b\d{1,2}:\d{2}\s*[-–—]\s*\d{1,2}:\d{2}\b\)?")
BOLD_ONLY = re.compile(r"^\s*(\*\*|__)[^*_]+(\*\*|__)\s*:?\s*$")
EMPHASIS = re.compile(r"(\*\*|\*|__|_|`)")
BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
QUOTE = re.compile(r"^\s*>\s?")
RULE = re.compile(r"^\s*([-*_]\s*){3,}$")
HEADER = re.compile(r"^\s*#{1,6}\s*")
PAUSE = re.compile(r"\[\s*(pause|beat)\s*(?::\s*([\d.]+)\s*s?)?\s*\]", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\"'”’])\s+")
BREAK_TAG = re.compile(r"<break[^>]*>")


def spoken(s):
    """True if anything here would be said out loud. A lone pause is not speech."""
    return bool(re.search(r"\w", BREAK_TAG.sub(" ", s)))


def key():
    for name in ("ELEVENLABS_API_KEY", "XI_API_KEY", "KEY"):
        v = (os.environ.get(name) or "").strip()
        if v:
            return v, name
    return None, None


def send(path, method="GET", body=None, query=""):
    """One request, raw and unforgiving. Both callers below want a different failure."""
    k, src = key()
    if not k:
        die("no key in ELEVENLABS_API_KEY, XI_API_KEY or KEY - export one and run again")
    headers = {"xi-api-key": k, "accept": "*/*"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    req = urllib.request.Request(API + path + query, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    with urllib.request.urlopen(req, context=ctx, timeout=180) as r:
        return r.read(), dict(r.headers)


def fault(e):
    """An HTTPError reduced to the (code, status, message) both callers want."""
    detail = e.read().decode("utf-8", "replace")
    try:
        d = json.loads(detail).get("detail", {})
        return e.code, d.get("status", ""), (d.get("message") or d.get("status") or detail)
    except Exception:
        return e.code, "", detail[:300]


def unreachable(e):
    die(f"cannot reach {API}: {e.reason}\n"
        "  if this is a sandbox, api.elevenlabs.io has to be an allowed host")


def call(path, method="GET", body=None, raw=False, query=""):
    try:
        payload, headers = send(path, method, body, query)
        return (payload, headers) if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        code, status, msg = fault(e)
        src = key()[1]
        hint = {
            "invalid_api_key": f"the value in {src} is not a key this account accepts - "
                               "re-copy it from elevenlabs.io -> Profile -> API Keys",
            "missing_permissions": f"the key in {src} is a restricted key and this one scope is "
                                   "not on it - the key itself is fine. Run --check to see every "
                                   "scope at once, then add the missing ones at elevenlabs.io -> "
                                   "Profile -> API Keys -> the key",
            "quota_exceeded": "the monthly character quota is spent - --dry-run costs nothing "
                              "and still shows the plan",
            "voice_not_found": "that voice id is not on this account - run --voices",
            "detected_unusual_activity": "free-tier abuse guard; this needs a paid plan",
        }.get(status, "")
        die(f"{code} {status or 'error'}: {msg}" + (f"\n  {hint}" if hint else ""))
    except urllib.error.URLError as e:
        unreachable(e)


# A restricted key is accepted by the account and still refuses the work one scope at a time, so
# four calls fail for four different-looking reasons and none of them says "fix the key". --check
# asks for all of them in one go, because the useful answer is the whole row, not the first no.
PROBE_VOICE = "21m00Tcm4TlvDq8ikWAM"   # a stock ElevenLabs voice, asked for two characters
READ_PROBES = {"voices_read": "/voices", "models_read": "/models", "user_read": "/user/subscription"}
SCOPES = [
    ("text_to_speech", True, "narration itself - without this nothing else matters"),
    ("voices_read", False, "--voices, and so picking a voice id at all"),
    ("models_read", False, "naming a --model other than the default"),
    ("user_read", False, "--quota, and nothing else"),
]


def probe(scope, voice):
    """Is this scope on the key? Returns (present, note). Bills two characters, once, for TTS."""
    if scope == "text_to_speech":
        args = (f"/text-to-speech/{voice}", "POST", {"text": "ok", "model_id": DEFAULT_MODEL})
    else:
        args = (READ_PROBES[scope], "GET", None)
    try:
        send(*args)
        return True, ""
    except urllib.error.HTTPError as e:
        code, status, _ = fault(e)
        if status == "missing_permissions":
            return False, ""
        if status == "invalid_api_key":
            die(f"the value in {key()[1]} is not a key this account accepts - re-copy it from "
                "elevenlabs.io -> Profile -> API Keys")
        # Anything else got past the scope check, so the scope is there. A voice id that is not
        # on this account, or a quota already spent, both answer the question --check asked.
        return True, status or str(code)
    except urllib.error.URLError as e:
        unreachable(e)


def check(voice, as_json):
    """Every scope this pack uses, in one pass, so a restricted key is one fix and not four."""
    src = key()[1]
    if not src:
        die("no key in ELEVENLABS_API_KEY, XI_API_KEY or KEY - set one and run again")
    voice = voice or PROBE_VOICE
    rows = []
    for scope, required, needed_for in SCOPES:
        present, note = probe(scope, voice)
        rows.append({"scope": scope, "required": required, "needed_for": needed_for,
                     "present": present, "note": note})
    missing = [r["scope"] for r in rows if not r["present"]]
    blocked = [r["scope"] for r in rows if not r["present"] and r["required"]]

    if as_json:
        print(json.dumps({"key_from": src, "probe_voice": voice, "scopes": rows,
                          "missing": missing, "can_narrate": not blocked}, indent=1))
        return 1 if blocked else 0

    print(f"\n  key read from {src}, voice {voice} for the text_to_speech probe\n")
    for r in rows:
        print(f"    {r['scope']:<16} {'ok     ' if r['present'] else 'MISSING'} "
              f"{r['note']:<10} {r['needed_for']}")
    if not missing:
        print("\n  Every scope this pack uses is on the key. Nothing here is in your way.\n")
        return 0
    print(f"\n  {len(missing)} of {len(rows)} missing: {', '.join(missing)}.")
    print("  The key is valid - these are scopes it was created without. Add them at")
    print("  elevenlabs.io -> Profile -> API Keys -> the key -> scopes, or make an")
    print("  unrestricted key and put that in the secret instead.")
    print(f"  {'Narration is blocked until text_to_speech is on the key.' if blocked else 'Narration works; the missing scopes only cost you the flags above.'}\n")
    return 1 if blocked else 0


def die(msg):
    print(f"\n  {msg}\n", file=sys.stderr)
    sys.exit(1)


def speakable(raw):
    """The script reduced to the words said out loud, grouped into beats."""
    beats, cur = [], []
    for line in raw.splitlines():
        # Timecodes come off before the label test, not after: `**Hook** (0:00-0:15)` is a
        # beat label, and left to the end of the pipeline it survives as the spoken word
        # "Hook" - a character billed to hear the script's own scaffolding read out.
        line = TIMECODE.sub(" ", line)
        if RULE.match(line) or HEADER.match(line) or BOLD_ONLY.match(line):
            # A header is a boundary and never speech - the label is for the person holding
            # the script, and read aloud it is just a paid-for mistake.
            if cur:
                beats.append(" ".join(cur))
                cur = []
            continue
        if ON_SCREEN.search(line) and not ON_SCREEN.sub("", line).strip():
            continue
        t = line
        t = PAUSE.sub(lambda m: f'<break time="{m.group(2) or "0.7"}s" />', t)
        t = ON_SCREEN.sub(" ", t)
        t = BRACKETED.sub(" ", t)
        t = CAPS_PAREN.sub(" ", t)
        t = QUOTE.sub("", t)
        t = BULLET.sub("", t)
        t = EMPHASIS.sub("", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            cur.append(t)
        elif cur:
            beats.append(" ".join(cur))
            cur = []
    if cur:
        beats.append(" ".join(cur))
    # A beat that is only a pause is not a request. On its own it bills characters for a file
    # of silence and puts a seam where you wanted a breath, so it folds into the beat it was
    # written under and the pause lands where you put it.
    out = []
    for b in beats:
        if spoken(b):
            out.append(b)
        elif out:
            out[-1] = f"{out[-1]} {b}".strip()
    return out


def chunk(beats, limit):
    """Beats packed into requests under the limit. A sentence is never split."""
    out = []
    for b in beats:
        if len(b) <= limit:
            out.append(b)
            continue
        part = ""
        for s in SENTENCE_END.split(b):
            if not s.strip():
                continue
            if len(part) + len(s) + 1 > limit and part:
                out.append(part.strip())
                part = ""
            # A single sentence over the limit is still one request: cutting mid-clause
            # sounds worse than a long read, and the API takes it.
            part = f"{part} {s}".strip()
        if part:
            out.append(part.strip())
    return out


def words(s):
    return len(re.findall(r"[^\s]+", BREAK_TAG.sub(" ", s)))


def runtime(s):
    return words(s) / WPM * 60


def arg(a, name, default=None, cast=str):
    return cast(a[a.index(name) + 1]) if name in a else default


def main():
    a = sys.argv[1:]
    as_json = "--json" in a
    dry = "--dry-run" in a

    if "--check" in a:
        sys.exit(check(arg(a, "--voice"), as_json))

    if "--voices" in a:
        vs = call("/voices").get("voices", [])
        if as_json:
            print(json.dumps([{k: v.get(k) for k in ("voice_id", "name", "category")} for v in vs], indent=1))
            return
        print(f"\n  {len(vs)} voices on this account\n")
        for v in vs:
            lab = v.get("labels") or {}
            tags = ", ".join(x for x in (lab.get("accent"), lab.get("gender"), lab.get("use_case")) if x)
            print(f"    {v.get('voice_id'):<24} {(v.get('name') or '')[:22]:<24} "
                  f"{(v.get('category') or ''):<12} {tags}")
        print()
        return

    if "--quota" in a:
        s = call("/user/subscription")
        used, cap = s.get("character_count", 0), s.get("character_limit", 0)
        if as_json:
            print(json.dumps(s, indent=1))
            return
        print(f"\n  tier {s.get('tier')}   {used}/{cap} characters used, {cap - used} left\n")
        return

    files = [x for x in a if not x.startswith("--") and not re.match(r"^[\d.]+$", x)
             and x not in {arg(a, "--voice"), arg(a, "--model"), arg(a, "--out"), arg(a, "--max-chars")}]
    text = arg(a, "--text")
    if not text and (not files or not os.path.exists(files[0])):
        print(__doc__)
        sys.exit(1)

    src = "--text" if text else files[0]
    raw = text if text else open(files[0], encoding="utf-8", errors="replace").read()
    beats = speakable(raw)
    if not beats:
        die("nothing speakable in that file - it is all direction, or it is empty")
    limit = arg(a, "--max-chars", DEFAULT_MAX, int)
    chunks = chunk(beats, limit)
    chars = sum(len(c) for c in chunks)
    secs = sum(runtime(c) for c in chunks)
    model = arg(a, "--model", DEFAULT_MODEL)
    voice = arg(a, "--voice")
    out = arg(a, "--out", "voiceover")

    plan = {"source": src, "model": model, "voice": voice, "beats": len(beats),
            "requests": len(chunks), "characters": chars, "words": sum(words(c) for c in chunks),
            "estimated_seconds": round(secs, 1),
            "stripped_characters": len(re.sub(r"\s+", " ", raw)) - chars,
            "chunks": [{"n": i + 1, "characters": len(c), "seconds": round(runtime(c), 1),
                        "opens": c[:72]} for i, c in enumerate(chunks)]}

    if dry or not voice:
        if as_json:
            print(json.dumps(plan, indent=1))
        else:
            print(f"\n  {src}   {len(beats)} beats -> {len(chunks)} requests, "
                  f"{chars} characters, ~{secs / 60:.1f} min at {WPM} wpm")
            print(f"  {plan['stripped_characters']} characters stripped as direction "
                  f"and never billed\n")
            for c in plan["chunks"]:
                print(f"    {c['n']:>3}  {c['characters']:>5} ch  {c['seconds']:>5.1f}s  {c['opens']}")
            print(f"\n  {chars} characters would be billed to your account.")
            if not voice:
                print("  No --voice given, so nothing was sent. Run --voices, pick one, "
                      "then pass --voice <id>.")
            else:
                print("  Dry run. Drop --dry-run to synthesize.")
            print()
        return

    os.makedirs(out, exist_ok=True)
    prev_ids, manifest = [], []
    for i, c in enumerate(chunks):
        body = {"text": c, "model_id": model,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                                   "style": 0.0, "use_speaker_boost": True}}
        if i:
            body["previous_text"] = chunks[i - 1][-400:]
        if i + 1 < len(chunks):
            body["next_text"] = chunks[i + 1][:400]
        if prev_ids:
            body["previous_request_ids"] = prev_ids[-3:]
        audio, headers = call(f"/text-to-speech/{voice}", "POST", body, raw=True,
                              query="?output_format=mp3_44100_128")
        path = os.path.join(out, f"{i + 1:03d}.mp3")
        with open(path, "wb") as f:
            f.write(audio)
        rid = headers.get("request-id") or headers.get("Request-Id")
        if rid:
            prev_ids.append(rid)
        manifest.append({"n": i + 1, "file": path, "characters": len(c),
                         "bytes": len(audio), "request_id": rid, "text": c})
        if not as_json:
            print(f"    {i + 1:>3}/{len(chunks)}  {len(c):>5} ch  {len(audio) / 1024:>7.1f} KB  {path}")

    with open(os.path.join(out, "concat.txt"), "w", encoding="utf-8") as f:
        for m in manifest:
            f.write(f"file '{os.path.basename(m['file'])}'\n")
    plan["files"] = manifest
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)

    if as_json:
        print(json.dumps(plan, indent=1, ensure_ascii=False))
        return
    print(f"\n  {len(manifest)} files in {out}/, {chars} characters billed, "
          f"~{secs / 60:.1f} min of audio")
    print(f"  one file:  ffmpeg -f concat -safe 0 -i {out}/concat.txt -c copy {out}/full.mp3")
    print("  Listen to beat one before you record anything around it.\n")


if __name__ == "__main__":
    main()
