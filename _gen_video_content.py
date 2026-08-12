"""Generate vo.txt, beats.json, highlight_words.json, cta.json, canvas.json,
and meta.json from a single TOPIC string, via one LLM call. Short-form variant:
~150-180 word narration, portrait canvas, single chunk.

Only runs when vo.txt isn't already committed (mirrors the TTS-skip pattern),
so a hand-authored video in this repo is never overwritten.
"""
import json
import os
import re
import datetime

from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"

SYS = """You are the writer for MindUnlocked Shorts, a YouTube channel that
explains psychology phenomena in a hook-driven, conversational, second-person
style, condensed into a 45-65 second vertical short.

Write the narration through these beats, IN ORDER. Do NOT include literal
section labels in the output — this is pacing guidance only; the vo must read
as one continuous piece of narration with a blank-line paragraph break
between beats:

1. Hook (one line, ideally with a deliberate short pause built into the
   phrasing — e.g. "Two identical cookies."): drop straight into a concrete,
   visual scenario, no throat-clearing intro.
2. Relatable setup (2-3 sentences): describe ONE real, specific, named study —
   real researcher name(s), approximate year, concrete numbers or detail (e.g.
   "same bakery, same recipe — the only difference was one jar had ten
   cookies, the other had two"). No phenomenon name yet.
3. The twist / core fact: state the counterintuitive result of that study
   plainly, then name the specific psychological phenomenon.
4. Bridge to life: one line connecting the study to something the viewer has
   personally felt (an ex, a sold-out item, a forbidden thing) — concrete, not
   abstract.
5. Identity close: a short, actionable takeaway framed as a question the
   viewer can ask themselves in the moment (not generic advice).
6. CTA line: "Comment \"WORD\" if [this changed how you think about X /
   your brain has done this to you]." — WORD is one striking word from the
   topic.

Style rules:
- Second person, short punchy sentences, paragraph breaks between beats.
- Concrete numbers and named people beat vague generalities.
- Target length: 150-180 words total.

Also produce:
- beats: a list of ~18-22 short visual search phrases (3-6 words each, like
  stock-footage search queries) that sequentially match the narration's
  emotional/narrative beats in order, each with "count": 2.
- highlight_words: 10-20 lowercase single words worth visually emphasizing
  in captions.
- cta_q: unused for shorts, return "".
- cta_chip: the exact comment-prompt word used in the script's final line,
  formatted like "Comment WORD \U0001F447".
- thumbnail_headline: ONE punchy phrase or short clause for a YouTube
  thumbnail, mixed case (not ALL CAPS), editorial/documentary tone (think Vox
  or The Atlantic explainer covers) — e.g. "The One Missing Piece Your Brain
  Won't Let Go Of". This is a SEPARATE hook from the video title, generated
  later by a different process — pull a specific, vivid detail straight from
  the script you just wrote (a stat, a phrase from the study, the mechanism,
  a direct question) rather than a generic summary, since it needs to stand
  alone as its own reason to click. Vary structure per topic (question,
  statement, a number, etc.) — don't reuse the same template every time.
- thumbnail_subline: ONE short supporting sentence underneath the headline,
  plain/lighter tone, adding one more concrete detail from the script.
- thumbnail_category: a topic-specific tag, 1-3 words, ALL CAPS (e.g.
  "COGNITIVE BIAS", "MEMORY", "SOCIAL PSYCHOLOGY") — new information for the
  viewer, never the channel name.
- thumbnail_image_prompt: a photorealistic image for a FULL-BLEED 1280x720
  background — either a symbolic/conceptual object or scene directly related
  to the topic (preferred when it captures the idea well — e.g. a single
  missing puzzle piece for an "unfinished tasks" topic) OR a portrait if the
  topic is more personal/emotional, composed with darker, emptier negative
  space toward the BOTTOM of the frame for a text scrim. Cinematic, moody,
  documentary-photography lighting. If a portrait: prefer face/shoulders-up
  framing; AVOID prompts requiring detailed close-up hands or hands
  interacting with objects — free image models reliably render hands wrong
  (extra/missing fingers). Do NOT mention any text, words, letters, numbers,
  logos, or UI elements — describe only the photo itself. Also AVOID any
  object that inherently implies visible writing even if you never ask for
  text explicitly — newspapers, books, signs, screens/monitors, letters,
  documents, horoscope columns, handwritten notes — free image models always
  render fake garbled text on these, which fails QA. Pick a symbolic object
  or scene with no legible surfaces at all.

Return JSON: {"vo": "...", "beats": [{"query":"","count":2}, ...],
"highlight_words": ["", ...], "cta_q": "", "cta_chip": "",
"thumbnail_headline": "", "thumbnail_subline": "", "thumbnail_category": "",
"thumbnail_image_prompt": ""}
Respond with ONLY the JSON object — no markdown code fences, no other text."""

MIN_WORDS, MAX_WORDS = 130, 220  # target 150-180; LLMs don't reliably hit
# prose length instructions on the first try (observed as low as 80 words in
# testing with gpt-4o-mini), so this is enforced with a retry loop rather
# than trusted, regardless of model.


def extract_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return json.loads(t, strict=False)


def generate(client, topic, hook_feedback=""):
    user = f"Topic: {topic}"
    if hook_feedback:
        user += (
            "\n\nPERFORMANCE FEEDBACK from this channel's recent videos (use it to "
            "write a stronger HOOK/opening line -- this is guidance, not content to "
            f"restate):\n{hook_feedback}"
        )
    messages = [{"role": "user", "content": user}]
    d = None
    for attempt in range(4):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYS,
            messages=messages,
        )
        raw = next(b.text for b in resp.content if b.type == "text")
        try:
            d = extract_json(raw)
        except json.JSONDecodeError as e:
            print(f"attempt {attempt + 1}: malformed JSON ({e}), retrying")
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": (
                    "That response was not valid JSON (" + str(e) + "). "
                    "A likely cause is an unescaped quote or control character inside a "
                    "string value. Return the SAME content as strict, valid JSON — "
                    "escape every double-quote and newline inside string values properly."
                ),
            })
            continue
        words = len(d["vo"].split())
        if MIN_WORDS <= words <= MAX_WORDS:
            return d
        print(f"attempt {attempt + 1}: {words} words, outside [{MIN_WORDS},{MAX_WORDS}], retrying")
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": (
                f"Your script's \"vo\" field was {words} words. It MUST be between "
                f"{MIN_WORDS} and {MAX_WORDS} words. "
                + ("Expand it with more concrete detail/example, same story." if words < MIN_WORDS
                   else "Tighten it, same story.")
                + " Return the full corrected JSON."
            ),
        })
    if d is None:
        raise RuntimeError("Model never returned valid JSON after 4 attempts")
    return d  # last attempt, even if still out of range


def main():
    if os.path.exists("vo.txt"):
        print("vo.txt already present, skipping content generation")
        return

    topic = os.environ["TOPIC"]
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    d = generate(client, topic, os.environ.get("HOOK_FEEDBACK", "").strip())

    open("vo.txt", "w", encoding="utf-8").write(d["vo"].strip() + "\n")
    json.dump(d["beats"], open("beats.json", "w"), indent=1)
    json.dump(d["highlight_words"], open("highlight_words.json", "w"))

    cta = {
        "q": d["cta_q"],
        "chip": d["cta_chip"],
        "follow": "Subscribe now \U0001F447",
        "tail_after_vo": 2.0,
        "at_offset_end": 10.5,
    }
    json.dump(cta, open("cta.json", "w"), indent=2)

    json.dump({
        "headline": d["thumbnail_headline"],
        "subline": d["thumbnail_subline"],
        "category": d["thumbnail_category"],
        "image_prompt": d["thumbnail_image_prompt"],
    }, open("thumbnail_spec.json", "w"), indent=2)

    json.dump({"width": 1080, "height": 1920, "chunks": 4}, open("canvas.json", "w"))

    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:50]
    json.dump(
        {"id": slug, "name": slug, "createdAt": datetime.datetime.utcnow().isoformat() + "Z"},
        open("meta.json", "w"), indent=2,
    )

    words = len(d["vo"].split())
    print(f"Generated: {words} words, {len(d['beats'])} beats")


if __name__ == "__main__":
    main()
