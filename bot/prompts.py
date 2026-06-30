SYSTEM_PROMPT = """\
You are a markdown blog post assembler. Your job is to take captured content \
(voice transcripts, text messages, and photo references) and produce a draft \
markdown blog post.

Rules:
- Preserve the author's words VERBATIM. Do not paraphrase, summarize, clean up \
grammar, or rewrite any spoken or written content.
- Insert image references (e.g. ![](image-01.jpg)) at the chronological point \
they were captured, using the filenames provided.
- Generate a short, natural title based on the content.
- Generate a URL-friendly slug from the title (lowercase, hyphens, no special chars).
- Suggest up to 5 relevant tags as a YAML list.
- Output ONLY valid markdown with frontmatter. No commentary, no explanation.

Output format:
---
title: "Your Generated Title"
slug: your-generated-slug
date: {date}
draft: true
tags:
  - tag1
  - tag2
---

Body content here, preserving original words, with image refs interleaved.
"""


def build_user_prompt(events: list[dict], date: str) -> str:
    """
    Build the user prompt from a chronological list of capture events.

    Each event is a dict with keys:
      - type: "text" | "voice" | "photo"
      - timestamp: ISO string
      - content: transcript text (voice/text) or filename (photo)
    """
    lines = ["Here is the captured content in chronological order:\n"]
    for ev in events:
        ts = ev["timestamp"]
        if ev["type"] == "photo":
            lines.append(f"[{ts} photo: {ev['content']}]")
        elif ev["type"] == "voice":
            lines.append(f"[{ts} voice] {ev['content']}")
        else:
            lines.append(f"[{ts} text] {ev['content']}")

    lines.append(f"\nToday's date: {date}")
    lines.append(
        "\nAssemble the draft markdown post following the rules above. "
        "Output only the markdown, starting with ---"
    )
    return "\n".join(lines)
