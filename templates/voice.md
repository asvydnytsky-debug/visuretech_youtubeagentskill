# voice.md

Copy this to `~/.claude/youtube/voice.md` and fill it in. Every skill in this pack reads it. Ten
minutes here is worth more than any prompt you will ever write, because on YouTube you have to say
the words out loud and a script in the wrong voice is unreadable on camera.

## Who I am talking to

One person. Name them properly - not "creators", but "someone with under a thousand subs who has
made nine videos and cannot work out why none of them break 400 views".

## How I actually talk

Paste the transcript of your best-performing video here, or three of them. Not what you wish you
sounded like.

## Words I never use

The ones that are not mine. Be specific: "unlock", "game-changer", "dive in", "let's get into it".

## Words I do use

Your tics. The phrases that are yours. Keep them.

## What I will not claim

Numbers I cannot show, results that are not mine, tools I have not used. Write them down so the
skills refuse them for you instead of you catching it in the edit.

## My format

Length, how a video opens, whether there is an intro, whether you swear, whether you appear on
camera, what the desk looks like.

## The voice that reads it, when it is not me

Only `/yt-voice` reads this section, and only when you are not reading the script yourself. Name
the voice once and you stop being asked every run:

    voice_id: <an id from narrate.py --voices>
    model: eleven_multilingual_v2

Leave it empty if you read your own scripts. On a face-to-camera channel your own voice is the
product, and an empty section here is the right answer rather than a gap to fill.
