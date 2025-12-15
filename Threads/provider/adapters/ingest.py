from __future__ import annotations

import json
import glob
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class StandardRecord:
    datetime: str
    post_link: str
    content: str
    likes: Optional[int]
    comments: Optional[int]
    author: Optional[str]
    response_to: Optional[str]
    attachment: Optional[str]
    source_file: str
    line_no: int


def iter_files(data_dir: str) -> List[str]:
    patterns = [
        f"{data_dir}/**/*.jsonl",
        f"{data_dir}/**/*.json",
    ]
    files: List[str] = []
    for p in patterns:
        files.extend(glob.glob(p, recursive=True))
    return sorted(set(files))


def parse_line(obj: dict, source_file: str, line_no: int) -> Optional[StandardRecord]:
    # threads 爬蟲欄位：datetime, post_link, content, likes, comments, author, response_to, attachment
    dt = obj.get("datetime")
    link = obj.get("post_link")
    content = obj.get("content")
    if not dt or not link or content is None:
        return None
    return StandardRecord(
        datetime=str(dt),
        post_link=str(link),
        content=str(content),
        likes=(obj.get("likes") if isinstance(obj.get("likes"), int) else None),
        comments=(obj.get("comments") if isinstance(obj.get("comments"), int) else None),
        author=(str(obj.get("author")) if obj.get("author") is not None else None),
        response_to=(str(obj.get("response_to")) if obj.get("response_to") is not None else None),
        attachment=(str(obj.get("attachment")) if obj.get("attachment") is not None else None),
        source_file=source_file,
        line_no=line_no,
    )


def read_jsonl(path: str) -> Iterable[StandardRecord]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            rec = parse_line(obj, path, i)
            if rec:
                yield rec


def read_json(path: str) -> Iterable[StandardRecord]:
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            return
        if isinstance(data, list):
            for i, obj in enumerate(data, start=1):
                if not isinstance(obj, dict):
                    continue
                rec = parse_line(obj, path, i)
                if rec:
                    yield rec
        elif isinstance(data, dict):
            rec = parse_line(data, path, 1)
            if rec:
                yield rec


def ingest(data_dir: str) -> List[StandardRecord]:
    out: List[StandardRecord] = []
    for fp in iter_files(data_dir):
        if fp.endswith(".jsonl"):
            out.extend(list(read_jsonl(fp)))
        elif fp.endswith(".json"):
            out.extend(list(read_json(fp)))
    return out
