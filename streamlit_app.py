
import hashlib
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import chromadb
import requests
import streamlit as st
import yaml
from bs4 import BeautifulSoup
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv


ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.yaml"
DATA_PATH = ROOT / "data"
load_dotenv(ROOT / ".env")


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


CONFIG = load_config()
SOURCES = CONFIG["sources"]
st.set_page_config(page_title="Groww MF FAQ assistant", page_icon="🌱", layout="wide")
SOURCE_ALLOWLIST = {
    "hdfc_amc": "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
    "hdfc_large_cap": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "hdfc_flexi_cap": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "hdfc_elss": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "hdfc_mid_cap": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
}


@st.cache_resource
def create_embedding_function(provider: str, model: str):
    if provider != "sentence-transformers":
        raise ValueError(f"Unsupported embedding provider: {provider}.")
    if not model:
        raise ValueError("An embedding model must be configured.")
    return SentenceTransformerEmbeddingFunction(model_name=model)


def embedding_fingerprint(provider: str, model: str) -> str:
    return hashlib.sha256(f"{provider}:{model}".encode("utf-8")).hexdigest()


def embed_documents(
    texts: list[str], embedding_function: Any
) -> tuple[list[list[float]], int]:
    if not texts:
        raise ValueError("No chunks are available to embed.")

    raw_embeddings = embedding_function(texts)
    if len(raw_embeddings) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: {len(raw_embeddings)} vectors for "
            f"{len(texts)} chunks."
        )

    embeddings = []
    dimension = None
    for index, raw_vector in enumerate(raw_embeddings):
        try:
            vector = [float(value) for value in raw_vector]
        except (TypeError, ValueError) as error:
            raise ValueError(f"Embedding {index} contains a non-numeric value.") from error
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ValueError(f"Embedding {index} is empty or contains a non-finite value.")
        if dimension is None:
            dimension = len(vector)
        elif len(vector) != dimension:
            raise ValueError("Embedding vectors have inconsistent dimensions.")
        embeddings.append(vector)
    if dimension is None:
        raise RuntimeError("Embedding provider returned no vectors.")
    return embeddings, dimension


def source_is_allowed(url: str) -> bool:
    return url in SOURCE_ALLOWLIST.values() and url in {
        item["url"] for item in SOURCES
    }


def validate_source_config() -> None:
    configured = {item["id"]: item["url"] for item in SOURCES}
    if len(SOURCES) != len(SOURCE_ALLOWLIST) or configured != SOURCE_ALLOWLIST:
        raise ValueError(
            "Scraping is restricted to the five URLs specified for this prototype."
        )


def scrape_pages() -> list[dict[str, Any]]:
    validate_source_config()
    pages = []
    for source in SOURCES:
        response = None
        try:
            response = requests.get(
                source["url"],
                headers={"User-Agent": CONFIG["scraping"]["user_agent"]},
                timeout=CONFIG["scraping"]["timeout_seconds"],
                allow_redirects=False,
                stream=True,
            )
            if 300 <= response.status_code < 400:
                raise ValueError(
                    f"Redirect blocked for {source['url']}: "
                    f"{response.headers.get('Location', 'no location provided')}"
                )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                raise ValueError(
                    f"Expected an HTML page at {source['url']}, got "
                    f"{content_type or 'unknown content type'}."
                )

            body = bytearray()
            max_bytes = CONFIG["scraping"]["max_response_bytes"]
            for block in response.iter_content(chunk_size=64 * 1024):
                if block:
                    body.extend(block)
                    if len(body) > max_bytes:
                        raise ValueError(
                            f"Response exceeded the configured size limit for "
                            f"{source['url']}."
                        )
            raw_html = bytes(body)
            html = raw_html.decode(response.encoding or "utf-8", errors="replace")
        except requests.RequestException as error:
            raise RuntimeError(
                f"Failed to scrape {source['id']} ({source['url']}): {error}"
            ) from error
        finally:
            if response is not None:
                response.close()

        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()
        for heading in soup.find_all(re.compile(r"^h[1-6]$")):
            heading.replace_with(f"\n## {heading.get_text(' ', strip=True)}\n")
        text = "\n".join(
            line.strip()
            for line in soup.get_text(separator="\n").splitlines()
            if line.strip()
        )
        pages.append(
            {
                "source_id": source["id"],
                "title": source["title"],
                "url": source["url"],
                "fetched_at": date.today().isoformat(),
                "status_code": response.status_code,
                "content_type": content_type,
                "content_hash": hashlib.sha256(raw_html).hexdigest(),
                "text": text,
            }
        )
    return pages


def load_documents(
    raw_path: Path = DATA_PATH / "01_raw" / "pages.json",
) -> list[dict[str, str]]:
    validate_source_config()
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Scraped documents not found at {raw_path}. Run the scrape phase first."
        )
    try:
        raw_pages = json.loads(raw_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in scraped document file: {raw_path}") from error
    except OSError as error:
        raise RuntimeError(f"Could not read scraped document file: {raw_path}") from error

    if not isinstance(raw_pages, list):
        raise ValueError("Scraped document file must contain a list of page records.")

    sources_by_id = {source["id"]: source for source in SOURCES}
    loaded_ids = set()
    loaded_urls = set()
    documents = []
    manifest_documents = []
    required_fields = {
        "source_id",
        "title",
        "url",
        "fetched_at",
        "status_code",
        "content_type",
        "content_hash",
        "text",
    }

    for index, page in enumerate(raw_pages):
        if not isinstance(page, dict):
            raise ValueError(f"Scraped page record {index} must be an object.")
        missing_fields = required_fields.difference(page)
        if missing_fields:
            raise ValueError(
                f"Scraped page record {index} is missing: "
                f"{', '.join(sorted(missing_fields))}."
            )

        source_id = page["source_id"]
        if not isinstance(source_id, str) or not isinstance(page["url"], str):
            raise ValueError(f"Scraped page record {index} has an invalid source ID or URL.")
        source = sources_by_id.get(source_id)
        if source is None or page["url"] != source["url"] or not source_is_allowed(
            page["url"]
        ):
            raise ValueError(
                f"Scraped page record {index} is not one of the approved sources."
            )
        if source_id in loaded_ids or page["url"] in loaded_urls:
            raise ValueError(f"Duplicate scraped source record: {source_id}.")
        if page["title"] != source["title"]:
            raise ValueError(f"Unexpected title for approved source {source_id}.")
        if (
            type(page["status_code"]) is not int
            or not 200 <= page["status_code"] < 300
        ):
            raise ValueError(f"Source {source_id} has an unsuccessful fetch status.")
        if not isinstance(page["content_type"], str) or "text/html" not in page[
            "content_type"
        ].lower():
            raise ValueError(f"Source {source_id} does not contain HTML.")
        if not isinstance(page["text"], str) or not page["text"].strip():
            raise ValueError(f"Source {source_id} contains no extracted text.")
        if not isinstance(page["fetched_at"], str):
            raise ValueError(f"Source {source_id} has an invalid fetch date.")
        try:
            date.fromisoformat(page["fetched_at"])
        except ValueError as error:
            raise ValueError(
                f"Source {source_id} has an invalid fetch date."
            ) from error
        if not isinstance(page["content_hash"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", page["content_hash"]
        ):
            raise ValueError(f"Source {source_id} has an invalid content hash.")

        loaded_ids.add(source_id)
        loaded_urls.add(page["url"])
        documents.append(
            {
                "source_id": source_id,
                "title": page["title"],
                "url": page["url"],
                "fetched_at": page["fetched_at"],
                "content_hash": page["content_hash"],
                "text": page["text"].strip(),
            }
        )
        manifest_documents.append(
            {
                "source_id": source_id,
                "url": page["url"],
                "fetched_at": page["fetched_at"],
                "content_hash": page["content_hash"],
            }
        )

    missing_sources = set(sources_by_id).difference(loaded_ids)
    if missing_sources:
        raise ValueError(
            f"Scraped document file is missing required sources: "
            f"{', '.join(sorted(missing_sources))}."
        )

    write_json(raw_path.parent / "loaded_documents.json", documents)
    write_json(
        raw_path.parent / "load_manifest.json",
        {
            "validation_status": "passed",
            "loaded_at": date.today().isoformat(),
            "document_count": len(documents),
            "documents": manifest_documents,
        },
    )
    return documents


def chunk_pages(pages: list[dict[str, str]]) -> list[dict[str, Any]]:
    chunks = []
    max_chars = CONFIG["chunking"]["max_chars"]
    if not isinstance(max_chars, int) or max_chars < 100:
        raise ValueError("chunking.max_chars must be an integer of at least 100.")

    excluded_heading = re.compile(
        r"return calculator|returns and rankings|holdings|compare similar funds|"
        r"fund management|how to invest|list of hdfc mutual fund in india",
        re.IGNORECASE,
    )
    performance_line = re.compile(
        r"\b(performance|annuali[sz]ed|historic returns|fund returns|"
        r"category average|rankings?)\b",
        re.IGNORECASE,
    )
    standalone_percentage = re.compile(
        r"[+-]?\d+(?:\.\d+)?%(\s+\d+D)?",
        re.IGNORECASE,
    )
    fact_label = re.compile(
        r"^(expense ratio|min\. for sip|min\. for 1st investment|"
        r"min\. for 2nd investment|minimum investment amount|"
        r"minimum sip investment|minimum lumpsum investment|"
        r"fund benchmark|benchmark|exit load)\s*:?\s*$",
        re.IGNORECASE,
    )

    for page in pages:
        current_heading = "Overview"
        current_lines = []
        chunk_number = 0
        current_length = 0
        skip_section = False

        def flush_chunk() -> None:
            nonlocal current_lines, current_length, chunk_number
            text = " ".join(current_lines).strip()
            if text:
                chunks.append(_make_chunk(page, current_heading, chunk_number, text))
                chunk_number += 1
            current_lines = []
            current_length = 0

        for raw_line in page["text"].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                flush_chunk()
                current_heading = line.lstrip("# ").strip() or "Overview"
                skip_section = bool(excluded_heading.search(current_heading))
                continue
            if skip_section or performance_line.search(line) or standalone_percentage.fullmatch(
                line
            ):
                continue

            next_length = current_length + len(line) + (1 if current_lines else 0)
            label_precedes_value = bool(
                current_lines and fact_label.fullmatch(current_lines[-1])
            )
            if current_lines and next_length > max_chars and not label_precedes_value:
                flush_chunk()
            current_lines.append(line)
            current_length += len(line) + (1 if len(current_lines) > 1 else 0)

        flush_chunk()
    return chunks


def _make_chunk(
    page: dict[str, str], heading: str, number: int, text: str
) -> dict[str, Any]:
    return {
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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary_path, path)


def store_in_chroma(
    chunks: list[dict[str, Any]],
    embedding_data: dict[str, Any],
    page_count: int,
) -> dict[str, Any]:
    if CONFIG["vector_db"]["provider"] != "chromadb":
        raise ValueError("This prototype supports ChromaDB as its vector database.")

    embedding_provider = CONFIG["embedding"]["provider"]
    embedding_model = CONFIG["embedding"]["model"]
    fingerprint = embedding_fingerprint(embedding_provider, embedding_model)
    if (
        embedding_data.get("provider") != embedding_provider
        or embedding_data.get("model") != embedding_model
        or embedding_data.get("model_fingerprint") != fingerprint
    ):
        raise ValueError(
            "The embedding artifact does not match the configured provider/model."
        )

    items = embedding_data.get("items")
    chunk_ids = [chunk["id"] for chunk in chunks]
    if (
        not isinstance(items, list)
        or len(items) != len(chunks)
        or embedding_data.get("count") != len(chunks)
        or not chunks
    ):
        raise ValueError("Chunk and embedding artifact counts do not match.")
    if [item.get("id") for item in items if isinstance(item, dict)] != chunk_ids:
        raise ValueError("Embedding IDs do not match the ordered chunk IDs.")

    vectors = []
    dimension = embedding_data.get("dimension")
    for index, item in enumerate(items):
        vector = item.get("embedding")
        if not isinstance(vector, list) or len(vector) != dimension:
            raise ValueError(f"Embedding {index} has an invalid dimension.")
        if any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError(f"Embedding {index} contains an invalid vector value.")
        vectors.append([float(value) for value in vector])

    base_name = CONFIG["vector_db"]["collection_name"]
    if (
        not isinstance(base_name, str)
        or len(base_name) < 3
        or len(base_name) > 50
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*[A-Za-z0-9]", base_name)
    ):
        raise ValueError("The configured ChromaDB collection name is invalid.")

    generation_id = uuid4().hex[:12]
    collection_name = f"{base_name}_{generation_id}"
    embedding_function = create_embedding_function(
        embedding_provider, embedding_model
    )
    client = chromadb.PersistentClient(
        path=str(ROOT / CONFIG["vector_db"]["persist_directory"])
    )
    collection = client.create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={
            "hnsw:space": "cosine",
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "embedding_dimension": dimension,
            "model_fingerprint": fingerprint,
            "generation_id": generation_id,
        },
    )
    collection.add(
        ids=chunk_ids,
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
        embeddings=vectors,
    )

    stored_count = collection.count()
    if stored_count != len(chunks):
        raise RuntimeError(
            f"ChromaDB stored {stored_count} records; expected {len(chunks)}."
        )
    sample_result = collection.query(
        query_embeddings=[vectors[0]],
        n_results=1,
        include=["documents", "metadatas", "distances"],
        where={"source_id": chunks[0]["metadata"]["source_id"]},
    )
    sample_ids = sample_result["ids"][0]
    if not sample_ids:
        raise RuntimeError("ChromaDB sample retrieval returned no stored chunks.")
    sample_metadata = sample_result["metadatas"][0][0]
    if sample_metadata.get("source_url") != chunks[0]["metadata"]["source_url"]:
        raise RuntimeError("ChromaDB sample retrieval returned incorrect source metadata.")

    manifest = {
        "status": "complete",
        "generation_id": generation_id,
        "pages": page_count,
        "chunks": len(chunks),
        "embeddings": len(vectors),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dimension": dimension,
        "model_fingerprint": fingerprint,
        "vector_db": "ChromaDB",
        "configured_collection": base_name,
        "active_collection": collection_name,
        "collection": collection_name,
        "storage_validation": {
            "stored_count": stored_count,
            "sample_chunk_id": sample_ids[0],
            "sample_source_url": sample_metadata["source_url"],
        },
        "fetched_at": date.today().isoformat(),
    }
    write_json_atomic(DATA_PATH / "04_vector_db" / "manifest.json", manifest)
    return manifest


def ingest() -> dict[str, Any]:
    scraped_pages = scrape_pages()
    raw_path = DATA_PATH / "01_raw" / "pages.json"
    write_json(raw_path, scraped_pages)
    pages = load_documents(raw_path)

    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("Chunking produced no documents to embed.")
    write_json(DATA_PATH / "02_chunks" / "chunks.json", chunks)

    embedding_provider = CONFIG["embedding"]["provider"]
    embedding_model = CONFIG["embedding"]["model"]
    fingerprint = embedding_fingerprint(embedding_provider, embedding_model)
    embedding_function = create_embedding_function(
        embedding_provider, embedding_model
    )
    texts = [chunk["text"] for chunk in chunks]
    embeddings, embedding_dimension = embed_documents(texts, embedding_function)
    embedding_data = {
        "provider": embedding_provider,
        "model": embedding_model,
        "model_fingerprint": fingerprint,
        "dimension": embedding_dimension,
        "count": len(embeddings),
        "items": [
            {"id": chunk["id"], "embedding": embedding}
            for chunk, embedding in zip(chunks, embeddings)
        ],
    }
    write_json(DATA_PATH / "03_embeddings" / "embeddings.json", embedding_data)
    return store_in_chroma(chunks, embedding_data, page_count=len(pages))


def collection_for_search():
    if CONFIG["vector_db"]["provider"] != "chromadb":
        raise ValueError("This prototype supports ChromaDB as its vector database.")
    embedding_provider = CONFIG["embedding"]["provider"]
    embedding_model = CONFIG["embedding"]["model"]
    fingerprint = embedding_fingerprint(embedding_provider, embedding_model)
    embedding_function = create_embedding_function(
        embedding_provider, embedding_model
    )
    manifest_path = DATA_PATH / "04_vector_db" / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("No ChromaDB index is active. Run ingestion first.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("The ChromaDB manifest is invalid; rerun ingestion.") from error
    if manifest.get("status") != "complete":
        raise RuntimeError("The ChromaDB index is incomplete; rerun ingestion.")
    if manifest.get("model_fingerprint") != fingerprint:
        raise RuntimeError(
            "The indexed embedding model does not match configuration. "
            "Run ingestion again before retrieval."
        )
    collection_name = manifest.get("active_collection")
    if not isinstance(collection_name, str) or not collection_name:
        raise RuntimeError("The ChromaDB manifest has no active collection.")
    client = chromadb.PersistentClient(
        path=str(ROOT / CONFIG["vector_db"]["persist_directory"])
    )
    collection = client.get_collection(
        name=collection_name,
        embedding_function=embedding_function,
    )
    metadata = collection.metadata or {}
    if metadata.get("model_fingerprint") != fingerprint:
        raise RuntimeError(
            "The indexed embedding model does not match configuration. "
            "Run ingestion again before retrieval."
        )
    if collection.count() != manifest.get("chunks"):
        raise RuntimeError(
            "The active ChromaDB collection does not match its manifest. "
            "Run ingestion again."
        )
    return collection


def retrieve(question: str) -> list[dict[str, Any]]:
    target_source = None
    for source_id, aliases in {
        "hdfc_large_cap": ("large cap",),
        "hdfc_flexi_cap": ("flexi cap",),
        "hdfc_elss": ("elss", "tax saver"),
        "hdfc_mid_cap": ("mid cap",),
        "hdfc_amc": ("hdfc mutual fund overview", "amc overview"),
    }.items():
        if any(alias in question.lower() for alias in aliases):
            target_source = source_id
            break
    top_k = CONFIG["retrieval"]["top_k"]
    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("retrieval.top_k must be a positive integer.")
    filters = {"where": {"source_id": target_source}} if target_source else {}
    result = collection_for_search().query(
        query_texts=[question],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
        **filters,
    )
    documents = result.get("documents")
    metadatas = result.get("metadatas")
    distances = result.get("distances")
    if not documents or not documents[0]:
        return []
    if (
        not metadatas
        or not metadatas[0]
        or not distances
        or len(documents[0]) != len(metadatas[0])
        or len(documents[0]) != len(distances[0])
    ):
        raise RuntimeError("ChromaDB returned incomplete retrieval results.")

    matches = []
    for text, metadata, distance in zip(
        documents[0], metadatas[0], distances[0]
    ):
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("ChromaDB returned an empty document.")
        if not isinstance(metadata, dict):
            raise RuntimeError("ChromaDB returned invalid source metadata.")
        source_url = metadata.get("source_url")
        if not isinstance(source_url, str) or not source_is_allowed(source_url):
            raise RuntimeError("ChromaDB returned a source outside the allowlist.")
        if not isinstance(distance, (int, float)) or not math.isfinite(distance):
            raise RuntimeError("ChromaDB returned an invalid retrieval distance.")
        fetched_at = metadata.get("fetched_at")
        try:
            date.fromisoformat(fetched_at)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Retrieved source metadata has an invalid fetch date."
            ) from error
        matches.append(
            {
                "text": text,
                "metadata": metadata,
                "distance": float(distance),
            }
        )
    return matches


def call_llm(question: str, matches: list[dict[str, Any]]) -> str:
    provider_config = CONFIG["llm"]["providers"]["gemini"]
    api_key = os.getenv(provider_config["api_key_env"])
    if not api_key:
        raise RuntimeError(
            f"Set {provider_config['api_key_env']} to use Gemini."
        )

    context = "\n\n".join(
        f"Source: {match['metadata']['source_url']}\n"
        f"Section: {match['metadata']['section']}\n"
        f"Excerpt: {match['text']}"
        for match in matches
    )
    system = (
        "You answer factual questions about the HDFC mutual fund pages in the "
        "provided context. Use only facts explicitly stated there. Never give "
        "investment, tax, or legal advice. Never state or compare investment "
        "performance. If unsupported, say the provided pages do not contain the "
        "answer. Answer in at most two short sentences, and do not invent URLs. "
        "Do not repeat or request personal or account information."
    )
    prompt = f"Question: {question}\n\nApproved source excerpts:\n{context}"
    endpoint = provider_config["endpoint"].format(model=provider_config["model"])
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 220, "temperature": 0},
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except requests.RequestException as error:
        raise RuntimeError("Gemini request failed.") from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise RuntimeError("Gemini returned an invalid response.") from error
    if not isinstance(answer, str):
        raise RuntimeError("Gemini returned a non-text response.")
    return answer.strip()


def blocked_reason(question: str) -> str | None:
    if re.search(
        r"\b(returns?|performance|alpha|cagr|best performing)\b", question, re.I
    ):
        return "I can’t provide or compare performance claims. Please consult HDFC AMC’s official scheme disclosures."
    if re.search(r"\b(should i|recommend|advice|buy|sell|which is better|best fund)\b", question, re.I):
        return "I can provide scheme facts, but not investment recommendations or advice."
    if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", question, re.I):
        return "Please remove personal identifiers; this assistant does not process or store them."
    if re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", question):
        return "Please remove personal identifiers; this assistant does not process or store them."
    if re.search(r"(?<!\d)(?:\d[\s-]?){12}(?!\d)", question):
        return "Please remove personal identifiers; this assistant does not process or store them."
    if re.search(r"(?<!\d)(?:\d[\s-]?){10}(?!\d)", question):
        return "Please remove personal identifiers; this assistant does not process or store them."
    if re.search(r"\b(otp|aadhaar|pan number|account number)\b", question, re.I):
        return "Please do not share PAN, Aadhaar, account numbers, OTPs, phone numbers, or emails."
    return None


def source_link(matches: list[dict[str, Any]]) -> str:
    if matches:
        return matches[0]["metadata"]["source_url"]
    return SOURCES[0]["url"]


def source_last_updated(matches: list[dict[str, Any]], url: str) -> str:
    if matches:
        return matches[0]["metadata"]["fetched_at"]
    pages_path = DATA_PATH / "01_raw" / "pages.json"
    if pages_path.exists():
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        for page in pages:
            if page["url"] == url:
                return page["fetched_at"]
    return "Not available (source not fetched)"


def answer_question(question: str) -> tuple[str, str, str]:
    reason = blocked_reason(question)
    if reason:
        url = (
            "https://www.hdfcfund.com/"
            if re.search(
                r"\b(returns?|performance|alpha|cagr|best performing)\b",
                question,
                re.I,
            )
            else SOURCES[0]["url"]
        )
        return reason, url, source_last_updated([], url)
    if re.search(r"\b(statement|download)\b", question, re.I):
        url = SOURCES[0]["url"]
        return (
            "The five indexed pages do not explain how to download statements, so I can’t confirm the steps.",
            url,
            source_last_updated([], url),
        )
    matches = retrieve(question)
    url = source_link(matches)
    max_distance = CONFIG["retrieval"]["max_distance"]
    if (
        not isinstance(max_distance, (int, float))
        or not math.isfinite(max_distance)
        or max_distance < 0
    ):
        raise ValueError("retrieval.max_distance must be a non-negative number.")
    if not matches or matches[0]["distance"] > max_distance:
        return (
            "I couldn’t find this fact in the indexed pages. The prototype does not infer missing details.",
            url,
            source_last_updated(matches, url),
        )
    citation_url = matches[0]["metadata"]["source_url"]
    supporting_matches = [
        match
        for match in matches
        if match["metadata"]["source_url"] == citation_url
    ]
    answer = call_llm(question, supporting_matches)
    answer = re.sub(r"https?://\S+", "", answer).strip()
    answer = re.sub(r"\[[^\]]*\]\([^)]*\)", "", answer).strip()
    if re.search(
        r"\b(returns?|performance|alpha|cagr|best performing)\b", answer, re.I
    ):
        return (
            "I couldn’t provide a concise facts-only answer from the retrieved text.",
            citation_url,
            source_last_updated(supporting_matches, citation_url),
        )
    sentences = [item for item in re.split(r"(?<=[.!?])\s+", answer) if item.strip()]
    if len(sentences) > 2:
        return (
            "I couldn’t provide a concise facts-only answer from the retrieved text.",
            citation_url,
            source_last_updated(supporting_matches, citation_url),
        )
    if not answer:
        return (
            "I couldn’t provide a facts-only answer from the retrieved text.",
            citation_url,
            source_last_updated(supporting_matches, citation_url),
        )
    return (
        answer,
        citation_url,
        source_last_updated(supporting_matches, citation_url),
    )


def render_answer(answer: str, url: str, last_updated: str) -> None:
    st.markdown(
        f"{answer} [Source]({url})\n\n"
        f"Last updated from sources: {last_updated}"
    )


st.title("HDFC Mutual Fund FAQ assistant")
st.caption("Facts from the five selected Groww pages. No investment advice.")
st.info(
    "Facts only — this assistant does not recommend, compare performance, or "
    "provide investment, tax, or legal advice. Never enter PAN, Aadhaar, account "
    "numbers, OTPs, email addresses, or phone numbers."
)

with st.sidebar:
    st.subheader("Pipeline configuration")
    st.write(f"Embedding: `{CONFIG['embedding']['model']}`")
    st.write(f"Vector DB: `ChromaDB` · {CONFIG['vector_db']['collection_name']}")
    st.write("Answer model: `Gemini 3.5 Flash-Lite`")
    st.caption(
        "Gemini free-tier quotas and data-use terms apply. "
        "Questions and keys are not saved by this app."
    )
    if st.button("Run all ingestion phases", type="primary"):
        try:
            with st.spinner(
                "Scraping, loading, chunking, embedding, and indexing five pages…"
            ):
                st.session_state["manifest"] = ingest()
            st.success("All ingestion phases completed.")
        except Exception as error:
            st.error(f"Ingestion failed: {error}")
    manifest_path = DATA_PATH / "04_vector_db" / "manifest.json"
    if manifest_path.exists():
        st.json(json.loads(manifest_path.read_text(encoding="utf-8")))
    load_manifest_path = DATA_PATH / "01_raw" / "load_manifest.json"
    if load_manifest_path.exists():
        with st.expander("Loaded document validation"):
            st.json(json.loads(load_manifest_path.read_text(encoding="utf-8")))

question = st.text_input("Ask a scheme fact", max_chars=500)
if st.button("Ask", disabled=not question.strip()):
    try:
        with st.spinner("Retrieving source passages…"):
            answer, citation, updated = answer_question(question.strip())
        render_answer(answer, citation, updated)
    except Exception as error:
        st.error(f"Could not answer this question: {error}")

with st.expander("Show indexed source scope"):
    for item in SOURCES:
        st.markdown(f"- [{item['title']}]({item['url']})")
