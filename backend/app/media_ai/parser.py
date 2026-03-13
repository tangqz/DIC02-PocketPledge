from __future__ import annotations

import re


EXPRESSION_PATTERN = re.compile(r"\[([a-zA-Z][a-zA-Z0-9_-]{0,31})\]")
SENTENCE_ENDINGS = {"。", "！", "？", ".", "!", "?", "\n"}
TRAILING_CLOSERS = {'"', "'", "”", "’", ")", "]", "}", "】", "）"}


def extract_expression_and_clean(
    text: str, default_expression: str = "neutral"
) -> tuple[str, str]:
    """Extract one expression tag and remove all tags from text."""
    matches = EXPRESSION_PATTERN.findall(text)
    expression = matches[-1].strip().lower() if matches else default_expression
    clean_text = EXPRESSION_PATTERN.sub("", text)
    clean_text = clean_text.replace("\r", " ").replace("\n", " ")
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return expression, clean_text


def split_complete_sentences(text: str) -> tuple[list[str], str]:
    """Split buffered text into complete sentences and a trailing remainder."""
    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in SENTENCE_ENDINGS:
            end = index + 1
            while end < len(text) and text[end] in TRAILING_CLOSERS:
                end += 1
            sentence = text[start:end].strip()
            if sentence:
                sentences.append(sentence)
            start = end
            while start < len(text) and text[start].isspace():
                start += 1
            index = start
            continue
        index += 1

    remainder = text[start:].strip()
    return sentences, remainder


class SentenceBuffer:
    """Incrementally accumulate streamed text and emit complete sentences."""

    def __init__(self) -> None:
        self._buffer = ""

    def push(self, chunk: str) -> list[str]:
        self._buffer += chunk
        sentences, self._buffer = split_complete_sentences(self._buffer)
        return sentences

    def flush(self) -> str:
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder
