import re


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks, preferring sentence/line breaks."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window_start = start + int(size * 0.6)
            cut = max(text.rfind(". ", window_start, end), text.rfind("\n", window_start, end))
            if cut == -1:
                cut = text.rfind(" ", window_start, end)
            if cut != -1:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)  # always moves forward
    return chunks
