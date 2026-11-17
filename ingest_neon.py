import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pgvector import Vector

from local_embeddings import embed_passages
from neon_store import VECTOR_TABLE, connect_neon


ROOT = Path(__file__).parent
ARTIFACT_ROOT = ROOT / "data" / "neon"
load_dotenv(ROOT / ".env")
with (ROOT / "config.yaml").open(encoding="utf-8") as file:
    CONFIG = yaml.safe_load(file)
SOURCES = CONFIG["sources"]
SOURCE_ALLOWLIST = {
    "hdfc_amc": "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
    "hdfc_large_cap": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "hdfc_flexi_cap": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "hdfc_elss": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "hdfc_mid_cap": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_sources() -> None:
    configured = {item["id"]: item["url"] for item in SOURCES}
    if len(SOURCES) != len(SOURCE_ALLOWLIST) or configured != SOURCE_ALLOWLIST:
        raise ValueError("Ingestion is restricted to the five approved Groww URLs.")


def scrape_pages() -> list[dict[str, Any]]:
    validate_sources()
    pages = []
    for source in SOURCES:
        response = requests.get(
            source["url"],
            headers={"User-Agent": CONFIG["scraping"]["user_agent"]},
            timeout=CONFIG["scraping"]["timeout_seconds"],
            allow_redirects=False,
            stream=True,
        )
        try:
            if 300 <= response.status_code < 400:
                raise ValueError(f"Redirect blocked for {source['url']}.")
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                raise ValueError(f"Expected HTML at {source['url']}.")
            body = bytearray()
            for block in response.iter_content(chunk_size=64 * 1024):
                if block:
                    body.extend(block)
                    if len(body) > CONFIG["scraping"]["max_response_bytes"]:
                        raise ValueError(f"Response exceeded size limit for {source['url']}.")
            raw_html = bytes(body)
            status_code = response.status_code
            encoding = response.encoding or "utf-8"
        finally:
            response.close()

        soup = BeautifulSoup(
            raw_html.decode(encoding, errors="replace"), "html.parser"
        )
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()
        for heading in soup.find_all(re.compile(r"^h[1-6]$")):
            heading.replace_with(f"\n## {heading.get_text(' ', strip=True)}\n")
        text = "\n".join(
            line.strip()
            for line in soup.get_text(separator="\n").splitlines()
            if line.strip()
        )
        if not text:
            raise ValueError(f"No text was extracted from {source['url']}.")
        pages.append(
            {
                "source_id": source["id"],
                "title": source["title"],
                "url": source["url"],
                "fetched_at": date.today().isoformat(),
                "status_code": status_code,
                "content_type": content_type,
                "content_hash": hashlib.sha256(raw_html).hexdigest(),
                "text": text,
            }
        )
    return pages


def load_documents(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    validate_sources()
    sources_by_id = {source["id"]: source for source in SOURCES}
    loaded = []
    seen = set()
    for page in pages:
        source_id = page.get("source_id")
        source = sources_by_id.get(source_id)
        if source is None or page.get("url") != source["url"]:
            raise ValueError("A scraped page is outside the approved source list.")
        if source_id in seen:
            raise ValueError(f"Duplicate scraped source: {source_id}.")
        if (
            page.get("title") != source["title"]
            or type(page.get("status_code")) is not int
            or not 200 <= page["status_code"] < 300
            or "text/html" not in str(page.get("content_type", "")).lower()
            or not isinstance(page.get("text"), str)
            or not page["text"].strip()
        ):
            raise ValueError(f"Scraped source {source_id} failed validation.")
        try:
            date.fromisoformat(page["fetched_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Scraped source {source_id} has an invalid fetch date.") from error
        if not re.fullmatch(r"[0-9a-f]{64}", str(page.get("content_hash", ""))):
            raise ValueError(f"Scraped source {source_id} has an invalid content hash.")
        seen.add(source_id)
        loaded.append(
            {
                "source_id": source_id,
                "title": page["title"],
                "url": page["url"],
                "fetched_at": page["fetched_at"],
                "content_hash": page["content_hash"],
                "text": page["text"].strip(),
            }
        )
    missing = set(sources_by_id).difference(seen)
    if missing:
        raise ValueError(
            f"Scrape is missing required sources: {', '.join(sorted(missing))}."
        )
    return loaded


def chunk_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = []
    max_chars = CONFIG["chunking"]["max_chars"]
    if type(max_chars) is not int or max_chars < 100:
        raise ValueError("chunking.max_chars must be an integer of at least 100.")
    excluded_heading = re.compile(
        r"return calculator|returns and rankings|holdings|compare similar funds|"
        r"fund management|how to invest|list of hdfc mutual fund in india",
        re.I,
    )
    performance_line = re.compile(
        r"\b(performance|annuali[sz]ed|historic returns|fund returns|"
        r"category average|rankings?)\b",
        re.I,
    )
    standalone_percentage = re.compile(r"[+-]?\d+(?:\.\d+)?%(\s+\d+D)?", re.I)
    fact_label = re.compile(
        r"^(expense ratio|min\. for sip|min\. for 1st investment|"
        r"min\. for 2nd investment|minimum investment amount|"
        r"minimum sip investment|minimum lumpsum investment|"
        r"fund benchmark|benchmark|exit load)\s*:?\s*$",
        re.I,
    )

    for page in pages:
        heading = "Overview"
        lines: list[str] = []
        length = 0
        number = 0
        skip_section = False

        def flush() -> None:
            nonlocal lines, length, number
            text = " ".join(lines).strip()
            if text:
                chunks.append(
                    {
                        "id": f"{page['source_id']}-{number:04d}",
                        "text": text,
                        "metadata": {
                            "source_id": page["source_id"],
                            "source_title": page["title"],
                            "source_url": page["url"],
                            "fetched_at": page["fetched_at"],
                            "section": heading,
                        },
                    }
                )
                number += 1
            lines = []
            length = 0

        for raw_line in page["text"].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                flush()
                heading = line.lstrip("# ").strip() or "Overview"
                skip_section = bool(excluded_heading.search(heading))
                continue
            if skip_section or performance_line.search(line) or standalone_percentage.fullmatch(line):
                continue
            next_length = length + len(line) + (1 if lines else 0)
            label_precedes_value = bool(lines and fact_label.fullmatch(lines[-1]))
            if lines and next_length > max_chars and not label_precedes_value:
                flush()
            lines.append(line)
            length += len(line) + (1 if len(lines) > 1 else 0)
        flush()
    return chunks


def embed_chunks(chunks: list[dict[str, Any]]) -> tuple[list[list[float]], int]:
    if CONFIG["deployment"]["embedding_provider"] != "fastembed":
        raise RuntimeError("The configured deployment embedding provider is not supported.")
    model = CONFIG["deployment"]["embedding_model"]
    vectors = embed_passages(model, [chunk["text"] for chunk in chunks])
    dimension = len(vectors[0]) if vectors else 0
    if (
        len(vectors) != len(chunks)
        or not dimension
        or any(
            len(vector) != dimension
            or any(not math.isfinite(value) for value in vector)
            for vector in vectors
        )
    ):
        raise RuntimeError("Embedding vectors are empty or have inconsistent dimensions.")
    return vectors, dimension


def main() -> None:
    if CONFIG["deployment"]["vector_db"] != "neon_pgvector":
        raise RuntimeError("The configured deployment vector database is not supported.")
    pages = scrape_pages()
    write_json(ARTIFACT_ROOT / "01_raw" / "pages.json", pages)
    documents = load_documents(pages)
    write_json(ARTIFACT_ROOT / "01_raw" / "loaded_documents.json", documents)
    write_json(
        ARTIFACT_ROOT / "01_raw" / "load_manifest.json",
        {
            "validation_status": "passed",
            "loaded_at": date.today().isoformat(),
            "document_count": len(documents),
            "documents": [
                {
                    "source_id": page["source_id"],
                    "url": page["url"],
                    "fetched_at": page["fetched_at"],
                    "content_hash": page["content_hash"],
                }
                for page in documents
            ],
        },
    )
    chunks = chunk_pages(documents)
    if not chunks:
        raise RuntimeError("Chunking produced no records.")
    write_json(ARTIFACT_ROOT / "02_chunks" / "chunks.json", chunks)
    vectors, dimension = embed_chunks(chunks)
    expected_dimension = CONFIG["deployment"]["embedding_dimensions"]
    if dimension != expected_dimension:
        raise RuntimeError(
            f"Embedding dimension {dimension} does not match configured "
            f"dimension {expected_dimension}."
        )
    write_json(
        ARTIFACT_ROOT / "03_embeddings" / "embeddings.json",
        {
            "provider": CONFIG["deployment"]["embedding_provider"],
            "model": CONFIG["deployment"]["embedding_model"],
            "dimension": dimension,
            "count": len(vectors),
            "items": [
                {"id": chunk["id"], "embedding": vector}
                for chunk, vector in zip(chunks, vectors)
            ],
        },
    )

    embedding_model = CONFIG["deployment"]["embedding_model"]
    try:
        with connect_neon(initialize_extension=True) as connection:
            connection.execute(f"DROP TABLE IF EXISTS {VECTOR_TABLE}")
            connection.execute(
                f"""
                CREATE TABLE {VECTOR_TABLE} (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    fetched_at DATE NOT NULL,
                    section TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding vector({expected_dimension}) NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {VECTOR_TABLE}_embedding_hnsw_idx
                ON {VECTOR_TABLE} USING hnsw (embedding vector_cosine_ops)
                """
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    f"""
                    INSERT INTO {VECTOR_TABLE} (
                        id, source_id, source_title, source_url, fetched_at,
                        section, text, embedding_model, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            chunk["id"],
                            chunk["metadata"]["source_id"],
                            chunk["metadata"]["source_title"],
                            chunk["metadata"]["source_url"],
                            date.fromisoformat(chunk["metadata"]["fetched_at"]),
                            chunk["metadata"]["section"],
                            chunk["text"],
                            embedding_model,
                            Vector(vector),
                        )
                        for chunk, vector in zip(chunks, vectors)
                    ],
                )
                cursor.execute(f"SELECT COUNT(*) FROM {VECTOR_TABLE}")
                stored_count = cursor.fetchone()[0]
                if stored_count != len(chunks):
                    raise RuntimeError(
                        f"Neon has {stored_count} records; expected {len(chunks)}."
                    )
                cursor.execute(
                    f"""
                    SELECT source_url
                    FROM {VECTOR_TABLE}
                    WHERE source_id = %s
                    ORDER BY embedding <=> %s
                    LIMIT 1
                    """,
                    (
                        chunks[0]["metadata"]["source_id"],
                        Vector(vectors[0]),
                    ),
                )
                sample = cursor.fetchone()
                if not sample:
                    raise RuntimeError("Neon sample retrieval returned no records.")
                if sample[0] != chunks[0]["metadata"]["source_url"]:
                    raise RuntimeError(
                        "Neon sample retrieval returned incorrect source metadata."
                    )
    except psycopg.Error as error:
        raise RuntimeError("Neon pgvector indexing failed.") from error

    manifest = {
        "status": "complete",
        "pages": len(pages),
        "chunks": len(chunks),
        "embeddings": len(vectors),
        "embedding_model": CONFIG["deployment"]["embedding_model"],
        "embedding_dimension": dimension,
        "vector_db": CONFIG["deployment"]["vector_db"],
        "table": VECTOR_TABLE,
        "stored_count": stored_count,
        "fetched_at": date.today().isoformat(),
    }
    write_json(ARTIFACT_ROOT / "04_vector_db" / "manifest.json", manifest)
    print(
        f"Ingestion complete: {len(pages)} pages, {len(chunks)} chunks "
        f"stored in Neon table '{VECTOR_TABLE}'."
    )


if __name__ == "__main__":
    main()
