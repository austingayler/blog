Product Brief: Frictionless Markdown Blogging System
Overview

Build a personal blogging system optimized for reducing the time and effort required to capture ideas and publish them as blog posts.

The system should allow creation of blog content directly from a phone using text messages, voice notes, and photos. Markdown files are the canonical storage format. The user should not need to open a CMS, editor, or blogging application during content capture.

The guiding principle is:

"Capture now, organize automatically, publish later."

Goals
Minimize friction between having an idea and recording it.
Use markdown files as the source of truth.
Store images alongside markdown in a filesystem-friendly structure.
Support text, voice, and photo-first workflows.
Automatically generate draft blog posts from captured content.
Keep the architecture simple and durable.
Ensure all content remains accessible without proprietary systems.
Non-Goals
Multi-user collaboration.
Rich WYSIWYG editing.
Social media features.
Complex content management workflows.
Real-time collaborative editing.
Primary User

A technically proficient individual who:

Writes personal blog posts.
Frequently captures ideas while away from a computer.
Often records thoughts during outdoor activities, travel, climbing, hiking, etc.
Wants long-term ownership of content.
Prefers markdown-based workflows.
Core User Stories
Voice Capture

As a user, I want to send a voice message from my phone and have it automatically become a draft markdown post.

Photo Capture

As a user, I want to send one or more photos and have them automatically attached to a draft post.

Mixed Capture

As a user, I want to send text, photos, and voice messages together and have the system combine them into a single draft.

Deferred Publishing

As a user, I want to capture content immediately and decide later whether it should be published.

Git-Based Storage

As a user, I want all content stored in a git repository as markdown and image files.

Proposed Architecture
Capture Layer

Telegram bot acts as the primary inbox.

Supported inputs:

Text messages
Voice notes
Photos
Photo groups
Processing Layer

Voice messages:

Transcribe using Whisper or equivalent.

Photos:

Download and store.
Optionally generate image descriptions.

Text:

Preserve original text.

AI processing:

Combine text, transcript, and image descriptions.
Generate a draft markdown document.
Generate a suggested title.
Generate metadata.
Storage Layer

Git repository structure:

content/
drafts/
2026/
2026-06-09-post-slug/
post.md
image-01.jpg
image-02.jpg

Published content may later be moved to:

content/
posts/

Markdown is the canonical format.

No content should exist exclusively in a database.

Publishing Layer

Static site generator.

Candidate options:

Hugo
Astro
Next.js static export

Initial recommendation:

Hugo

Hosting options:

Cloudflare Pages
GitHub Pages
Netlify
Draft Generation Requirements

Generated markdown should:

Preserve the user's original words whenever possible.
Avoid excessive rewriting.
Insert image references automatically.
Support frontmatter.

Example:

Today we climbed the ridge.




More notes here.

Review Workflow
User sends content to Telegram.
System creates draft.
Draft is committed to git.
User reviews later on desktop.
User edits markdown if desired.
User marks as published.
Site rebuilds automatically.
Future Enhancements
AI-Assisted Post Assembly

Given:

Multiple voice notes
Multiple photos
Multiple messages

Automatically construct a coherent blog draft.

Automatic Tagging

Generate:

Tags
Categories
Location metadata
Travel and Activity Journals

Aggregate multiple captures into a single trip report.

Weekly Digest

Automatically combine captured content into a weekly summary post.

Technical Constraints
Markdown must remain the source of truth.
Images must be stored as files, not blobs in a database.
Git repository must contain all published and draft content.
System should remain functional if AI components are removed.
AI should enhance workflows, not own the data model.
Success Metrics
Time from idea to capture under 10 seconds.
Ability to create a draft using only a phone.
Zero manual file handling for photos.
Draft generation success rate above 95%.
User rarely needs to touch infrastructure after initial setup.
