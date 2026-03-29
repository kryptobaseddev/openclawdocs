"""Clean Mintlify MDX components and code fence metadata from markdown content.

Converts non-standard Mintlify components to clean markdown:
- <Tip>, <Warning>, <Note>, <Info>, <Check> → blockquotes with prefix
- <Steps>/<Step> → numbered list with titles
- <Tabs>/<Tab> → headed subsections
- <Accordion>/<AccordionGroup> → headed subsections
- <Card>/<CardGroup> → bullet links
- <CodeGroup> → pass through (already standard code fences inside)

Strips code fence theme metadata:
- ```json5 theme={"theme":{"light":"min-light","dark":"min-dark"}} → ```json5
"""

from __future__ import annotations

import re

# Code fence theme metadata: ```lang theme={...}
_THEME_RE = re.compile(r"^(```\w*)\s+theme=\{.*$", re.MULTILINE)

# Mintlify callout components
_CALLOUT_OPEN = re.compile(r"<(Tip|Warning|Note|Info|Check)>", re.IGNORECASE)
_CALLOUT_CLOSE = re.compile(r"</(Tip|Warning|Note|Info|Check)>", re.IGNORECASE)

# Steps
_STEPS_OPEN = re.compile(r"<Steps>", re.IGNORECASE)
_STEPS_CLOSE = re.compile(r"</Steps>", re.IGNORECASE)
_STEP_OPEN = re.compile(r'<Step\s+title="([^"]+)"[^>]*>', re.IGNORECASE)
_STEP_CLOSE = re.compile(r"</Step>", re.IGNORECASE)

# Tabs
_TABS_OPEN = re.compile(r"<Tabs>", re.IGNORECASE)
_TABS_CLOSE = re.compile(r"</Tabs>", re.IGNORECASE)
_TAB_OPEN = re.compile(r'<Tab\s+title="([^"]+)"[^>]*>', re.IGNORECASE)
_TAB_CLOSE = re.compile(r"</Tab>", re.IGNORECASE)

# Accordions
_ACCORDION_GROUP_OPEN = re.compile(r"<AccordionGroup>", re.IGNORECASE)
_ACCORDION_GROUP_CLOSE = re.compile(r"</AccordionGroup>", re.IGNORECASE)
_ACCORDION_OPEN = re.compile(r'<Accordion\s+title="([^"]+)"[^>]*>', re.IGNORECASE)
_ACCORDION_CLOSE = re.compile(r"</Accordion>", re.IGNORECASE)

# Cards
_CARD_GROUP_OPEN = re.compile(r"<CardGroup[^>]*>", re.IGNORECASE)
_CARD_GROUP_CLOSE = re.compile(r"</CardGroup>", re.IGNORECASE)
_CARD_WITH_HREF = re.compile(
    r'<Card\s+[^>]*title="([^"]+)"[^>]*href="([^"]+)"[^>]*/?>',
    re.IGNORECASE,
)
_CARD_OPEN = re.compile(r'<Card\s+[^>]*title="([^"]+)"[^>]*/?>',re.IGNORECASE)
_CARD_CLOSE = re.compile(r"</Card>", re.IGNORECASE)

# Generic self-closing/empty components to strip
_GENERIC_SELF_CLOSING = re.compile(r"<(Columns|Frame|Snippet|ParamField|ResponseField|Expandable)[^>]*/?>", re.IGNORECASE)
_GENERIC_CLOSE = re.compile(r"</(Columns|Frame|Snippet|ParamField|ResponseField|Expandable)>", re.IGNORECASE)

# All-caps placeholders from llms-full.txt (e.g., <PROVIDER>, <REMOTE>, <ENV>)
_PLACEHOLDER_TAG = re.compile(r"</?[A-Z_]{2,}>")

# CodeGroup just wraps code blocks — strip the wrapper
_CODE_GROUP = re.compile(r"</?CodeGroup>", re.IGNORECASE)


def clean_content(content: str) -> str:
    """Clean Mintlify MDX components and code fence metadata from markdown.

    Returns standard markdown that any LLM can parse without custom tag knowledge.
    """
    # 1. Strip code fence theme metadata
    content = _THEME_RE.sub(r"\1", content)

    # 2. Callouts → blockquotes
    content = _CALLOUT_OPEN.sub(lambda m: f"\n> **{m.group(1)}:**", content)
    content = _CALLOUT_CLOSE.sub("", content)

    # 3. Steps → numbered headers
    # Process each <Steps>...</Steps> block to number steps sequentially
    content = _STEPS_OPEN.sub("", content)
    content = _STEPS_CLOSE.sub("", content)
    counter = [0]
    def _number_step(m: re.Match) -> str:
        counter[0] += 1
        return f"\n**Step {counter[0]}: {m.group(1)}**\n"
    content = _STEP_OPEN.sub(_number_step, content)
    content = _STEP_CLOSE.sub("", content)

    # 4. Tabs → subsections
    content = _TABS_OPEN.sub("", content)
    content = _TABS_CLOSE.sub("", content)
    content = _TAB_OPEN.sub(lambda m: f"\n**{m.group(1)}**\n", content)
    content = _TAB_CLOSE.sub("", content)

    # 5. Accordions → subsections
    content = _ACCORDION_GROUP_OPEN.sub("", content)
    content = _ACCORDION_GROUP_CLOSE.sub("", content)
    content = _ACCORDION_OPEN.sub(lambda m: f"\n**{m.group(1)}**\n", content)
    content = _ACCORDION_CLOSE.sub("", content)

    # 6. Cards → bullet links
    content = _CARD_GROUP_OPEN.sub("", content)
    content = _CARD_GROUP_CLOSE.sub("", content)
    content = _CARD_WITH_HREF.sub(lambda m: f"- [{m.group(1)}]({m.group(2)})", content)
    content = _CARD_OPEN.sub(lambda m: f"- **{m.group(1)}**", content)
    content = _CARD_CLOSE.sub("", content)

    # 7. CodeGroup wrapper — strip
    content = _CODE_GROUP.sub("", content)

    # 8. Generic components — strip
    content = _GENERIC_SELF_CLOSING.sub("", content)
    content = _GENERIC_CLOSE.sub("", content)

    # 9. Preserve all-caps placeholders as-is (they're meaningful, e.g., <PROVIDER>_API_KEY)
    # Don't strip those — they're config placeholders, not MDX components

    # 10. Clean up excessive blank lines from removed tags
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def extract_code_blocks(content: str) -> list[dict]:
    """Extract all fenced code blocks from markdown content.

    Returns list of {language: str, content: str} dicts.
    Theme metadata is stripped before extraction.
    """
    # Strip theme metadata first
    cleaned = _THEME_RE.sub(r"\1", content)

    blocks = []
    pattern = re.compile(r"^```(\w*)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(cleaned):
        lang = match.group(1) or "text"
        code = match.group(2).strip()
        if code:
            blocks.append({"language": lang, "content": code})
    return blocks
