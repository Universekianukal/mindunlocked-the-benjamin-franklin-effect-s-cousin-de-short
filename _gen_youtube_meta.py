"""Generate youtube.json (title/description/tags) from this video's actual
script (vo.txt), so upload metadata is unique per video instead of hand-written.
"""
import json
import os
import re

from anthropic import Anthropic

MODEL = "claude-sonnet-5"

SYS = """You write YouTube metadata for a psychology/self-improvement channel called
MindUnlocked. Given a video's narration script, produce:
- title: under 100 chars, curiosity-driven but accurate to the content, no clickbait lies
- description: 2-4 short paragraphs summarizing the actual content, end with a
  subscribe call-to-action line "Subscribe now \U0001F447 https://www.youtube.com/@MindUnlocked"
- hashtags: end the description with a FINAL line of 5-7 lowercase discovery
  hashtags -- always "#shorts #psychology #psychologyfacts" plus 2-4 specific to
  this video's topic, space-separated, on their own line after the subscribe line
- tags: 5-10 relevant lowercase keyword tags, no hashtags (the hashtags belong in
  the description line described above, not in this list)

Return JSON: {"title": "", "description": "", "tags": ["", ...]}
Respond with ONLY the JSON object — no markdown code fences, no other text."""


def extract_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return json.loads(t)


def main():
    # Mirrors the vo.txt-skip pattern in _gen_video_content.py: a
    # pre-committed youtube.json (hand-authored or pregen-supplied) is
    # never overwritten by a fresh metadata generation call.
    if os.path.exists("youtube.json"):
        print("youtube.json already present, skipping generation")
        return

    script = open("vo.txt").read()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYS,
        messages=[{"role": "user", "content": script}],
    )
    meta = extract_json(next(b.text for b in resp.content if b.type == "text"))

    out = {
        "title": meta["title"],
        "description": meta["description"],
        "tags": meta["tags"],
        "categoryId": "27",
        "privacyStatus": "private",
    }
    json.dump(out, open("youtube.json", "w"), indent=2)
    print(f"Generated youtube.json: {out['title']}")


if __name__ == "__main__":
    main()
