---
name: study-guide
description: >-
  Maintains STUDY_GUIDE.md at the project root for interview prep and onboarding-style
  explanations. Use when creating or finalizing implementation plans, making architecture
  or technology decisions, completing major features or components, or after fixes that
  reveal how the system works. Also use when the user asks to update the study guide or
  explain the project for a junior developer.
---

# Study Guide

Whenever you create an implementation plan, make architectural decisions, or complete significant implementation work in this project, you MUST update the `STUDY_GUIDE.md` file at the project root.

## When to update

- After creating or finalizing any implementation plan
- After making a technology or architecture decision (e.g., choosing a database, framework, algorithm)
- After completing a major feature or component
- After resolving a significant bug where the fix reveals how something works

## What to write

Write as if explaining to a junior developer who has never seen this project. The reader should be able to study this file and confidently answer interview questions about the project.

### Required sections (update as applicable)

1. **What We're Building** — A plain-English summary of the project, what problem it solves, and who it's for.

2. **How It Works (High Level)** — The end-to-end flow from user input to output. Use a simple numbered list, not jargon-heavy paragraphs.

3. **Key Decisions & Why** — For every major technical choice, explain:
   - What was chosen
   - What the alternatives were
   - Why this choice was made (pros)
   - What the tradeoffs are (cons)
   - A one-sentence analogy or example a junior dev would understand

4. **How Each Piece Works** — For each major component/module, write:
   - What it does in one sentence
   - How it works in 2-3 sentences using simple language
   - A concrete example of input → output

5. **Things That Don't Work Well** — Honest list of known weaknesses, edge cases, and failure modes. Interviewers love hearing these.

6. **Key Metrics & Results** — Performance numbers, eval results, and what they mean.

## Writing style rules

- Use short sentences. Avoid jargon — if you must use a technical term, define it in parentheses.
- Use concrete examples, not abstract descriptions.
- Use analogies (e.g., "Pinecone is like a search index, but instead of matching keywords, it finds code that *means* similar things").
- Use bullet points and headers liberally. No walls of text.
- Write in present tense ("The chunker splits files..." not "The chunker will split files...").

## File rules

- `STUDY_GUIDE.md` is gitignored — it's a personal study reference, not project documentation.
- Do NOT duplicate the README or architecture docs. This file is specifically for interview prep and quick understanding.
- Append new decisions and components as they happen. Don't rewrite the whole file each time — just update the relevant section.
