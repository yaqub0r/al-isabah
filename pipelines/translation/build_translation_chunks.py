#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    order: int
    char_start: int
    char_end: int
    text: str


def _clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _split_into_chunks(text: str, max_chars: int, min_chars: int) -> list[Chunk]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        return []

    chunks: list[Chunk] = []
    bucket: list[str] = []
    bucket_len = 0
    cursor = 0

    def flush() -> None:
        nonlocal bucket, bucket_len, cursor
        if not bucket:
            return
        joined = "\n\n".join(bucket).strip()
        if not joined:
            bucket = []
            bucket_len = 0
            return
        idx = len(chunks) + 1
        start = cursor
        end = cursor + len(joined)
        chunks.append(
            Chunk(
                chunk_id=f"chunk_{idx:05d}",
                order=idx,
                char_start=start,
                char_end=end,
                text=joined,
            )
        )
        cursor = end + 2
        bucket = []
        bucket_len = 0

    for para in paras:
        plen = len(para)

        # If a single paragraph is extremely large, hard-wrap by chars.
        if plen > max_chars * 1.35:
            flush()
            pcur = 0
            while pcur < plen:
                part = para[pcur : pcur + max_chars]
                pcur += len(part)
                idx = len(chunks) + 1
                start = cursor
                end = cursor + len(part)
                chunks.append(
                    Chunk(
                        chunk_id=f"chunk_{idx:05d}",
                        order=idx,
                        char_start=start,
                        char_end=end,
                        text=part,
                    )
                )
                cursor = end + 2
            continue

        add_len = plen if not bucket else (2 + plen)
        if bucket and bucket_len + add_len > max_chars and bucket_len >= min_chars:
            flush()

        bucket.append(para)
        bucket_len += add_len

        if bucket_len >= max_chars:
            flush()

    flush()
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description="Build chunk manifest for translation batches.")
    ap.add_argument("--input", required=True, help="Input source text file.")
    ap.add_argument("--out-dir", required=True, help="Output directory for chunk artifacts.")
    ap.add_argument("--book-key", required=True, help="Stable book key (e.g. al_isabah_v1).")
    ap.add_argument("--source-lang", default="ar")
    ap.add_argument("--target-lang", default="en")
    ap.add_argument("--min-chars", type=int, default=3500)
    ap.add_argument("--max-chars", type=int, default=6500)
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"input not found: {src}")

    text = _clean_text(src.read_text(encoding="utf-8", errors="ignore"))
    chunks = _split_into_chunks(text, max_chars=args.max_chars, min_chars=args.min_chars)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "chunks.jsonl"
    meta_path = out_dir / "chunks.meta.json"

    total_chars = 0
    with manifest_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            total_chars += len(c.text)
            rec = {
                "chunk_id": c.chunk_id,
                "order": c.order,
                "book_key": args.book_key,
                "source_lang": args.source_lang,
                "target_lang": args.target_lang,
                "source_file": str(src),
                "char_start": c.char_start,
                "char_end": c.char_end,
                "char_len": len(c.text),
                "word_count_est": len(c.text.split()),
                "source_text": c.text,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    meta = {
        "book_key": args.book_key,
        "source_file": str(src),
        "source_lang": args.source_lang,
        "target_lang": args.target_lang,
        "chunk_count": len(chunks),
        "total_chars": total_chars,
        "avg_chars_per_chunk": int(total_chars / len(chunks)) if chunks else 0,
        "manifest": str(manifest_path),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(chunks)} chunks -> {manifest_path}")
    print(f"meta: {meta_path}")


if __name__ == "__main__":
    main()
