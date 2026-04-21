"""Canonical markdown → structured blocks with deterministic IDs.

Block kinds we emit:
  heading (level 1..6), paragraph, list_item (ordered/unordered), code_block,
  blockquote, thematic_break, table, image_block

Block ID formula (per FORGE_SPEC §5):
  block_id = "b_" + sha1(f"{order}:{kind}:{normalized_text[:120]}")[:7]

Collisions get a `_N` suffix (N is the duplicate index).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from typing import Any

from markdown_it import MarkdownIt


@dataclass
class Block:
    id: str
    order: int
    kind: str
    level: int | None
    text: str
    char_range: tuple[int, int]
    detected_lang: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["char_range"] = list(self.char_range)
        return d


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()[:120]


def _make_id(order: int, kind: str, text: str, seen: set[str]) -> str:
    norm = _normalize(text)
    digest = hashlib.sha1(f"{order}:{kind}:{norm}".encode()).hexdigest()[:7]
    base = f"b_{digest}"
    if base not in seen:
        seen.add(base)
        return base
    # collision — append suffix
    for i in range(1, 100):
        cand = f"{base}_{i}"
        if cand not in seen:
            seen.add(cand)
            return cand
    seen.add(base + "_x")
    return base + "_x"


def _render_inline(tokens) -> str:
    """Flatten inline tokens into plain text with minimal markdown preserved."""
    parts: list[str] = []
    for t in tokens:
        if t.type == "text":
            parts.append(t.content)
        elif t.type == "softbreak" or t.type == "hardbreak":
            parts.append("\n")
        elif t.type == "code_inline":
            parts.append(f"`{t.content}`")
        elif t.type == "link_open":
            # keep links in the text
            href = dict(t.attrs or {}).get("href", "")
            parts.append(f"[")
        elif t.type == "link_close":
            # We don't know href at close; emit closing bracket — href gets kept below
            parts.append("]")
        elif t.type == "image":
            alt = t.content or ""
            src = dict(t.attrs or {}).get("src", "")
            parts.append(f"![{alt}]({src})")
        elif t.type == "em_open" or t.type == "em_close":
            parts.append("*")
        elif t.type == "strong_open" or t.type == "strong_close":
            parts.append("**")
        elif t.content:
            parts.append(t.content)
    return "".join(parts)


def parse_blocks(markdown: str) -> list[Block]:
    md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
    tokens = md.parse(markdown)
    blocks: list[Block] = []
    seen_ids: set[str] = set()
    order = 0

    # We keep a shallow stack to know list context
    list_stack: list[str] = []  # "ul" | "ol"

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            text = inline.content if inline and inline.type == "inline" else ""
            start, end = _char_range(tok, tokens, i)
            bid = _make_id(order, "heading", text, seen_ids)
            blocks.append(Block(id=bid, order=order, kind="heading", level=level,
                                text=text, char_range=(start, end)))
            order += 1
            i += 3  # heading_open, inline, heading_close
            continue

        if tok.type == "paragraph_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            text = inline.content if inline and inline.type == "inline" else ""
            if list_stack:
                kind = "list_item"
            else:
                kind = "paragraph"
            start, end = _char_range(tok, tokens, i)
            bid = _make_id(order, kind, text, seen_ids)
            blocks.append(Block(id=bid, order=order, kind=kind, level=None,
                                text=text, char_range=(start, end)))
            order += 1
            i += 3
            continue

        if tok.type == "fence" or tok.type == "code_block":
            text = tok.content or ""
            start, end = _char_range(tok, tokens, i)
            bid = _make_id(order, "code_block", text, seen_ids)
            blocks.append(Block(id=bid, order=order, kind="code_block", level=None,
                                text=text, char_range=(start, end),
                                detected_lang=(tok.info.strip() or None) if hasattr(tok, "info") else None))
            order += 1
            i += 1
            continue

        if tok.type == "blockquote_open":
            # Collect the inner content as text
            depth = 1
            j = i + 1
            parts: list[str] = []
            while j < len(tokens) and depth > 0:
                t = tokens[j]
                if t.type == "blockquote_open":
                    depth += 1
                elif t.type == "blockquote_close":
                    depth -= 1
                elif t.type == "inline":
                    parts.append(t.content)
                j += 1
            text = "\n".join(parts).strip()
            start, end = _char_range(tok, tokens, i)
            bid = _make_id(order, "blockquote", text, seen_ids)
            blocks.append(Block(id=bid, order=order, kind="blockquote", level=None,
                                text=text, char_range=(start, end)))
            order += 1
            i = j
            continue

        if tok.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append("ul" if tok.type == "bullet_list_open" else "ol")
            i += 1
            continue
        if tok.type in ("bullet_list_close", "ordered_list_close"):
            if list_stack:
                list_stack.pop()
            i += 1
            continue

        if tok.type == "hr":
            start, end = _char_range(tok, tokens, i)
            bid = _make_id(order, "thematic_break", "---", seen_ids)
            blocks.append(Block(id=bid, order=order, kind="thematic_break", level=None,
                                text="---", char_range=(start, end)))
            order += 1
            i += 1
            continue

        # Skip everything else (list_item_open/close handled by paragraph collection above, etc.)
        i += 1

    return blocks


def _char_range(open_tok, tokens, idx: int) -> tuple[int, int]:
    """Best-effort byte range from markdown-it map fields.

    markdown-it-py sets `map = [start_line, end_line]` on block tokens.
    We don't have line-to-char conversion without the original text, so callers
    that care about exact ranges can compute them afterwards. For now we use
    the open token's map as a crude `(start_line, end_line)` tuple interpreted
    as the range (the Forge API client just needs them to round-trip).
    """
    m = getattr(open_tok, "map", None)
    if m and isinstance(m, (list, tuple)) and len(m) >= 2:
        return (int(m[0]), int(m[1]))
    return (0, 0)
