# HDFC mutual fund FAQ assistant

A facts-only FAQ prototype for five HDFC mutual-fund pages. The Vercel deployment uses a FastAPI API, a static browser UI, Groq `openai/gpt-oss-20b` for answer generation, OpenAI embeddings, and Neon Postgres with pgvector. It does not provide investment advice or save questions and answers.

## Deploy on Vercel

1. Create a [Neon](https://neon.tech/) project and database. In the **Connect** panel, copy the pooled connection string and keep it private. The ingestion script enables the `vector` extension and creates the table and cosine HNSW index.
2. In Vercel, import `diyachokshi25-dot/Growfolio` from GitHub. Use the repository root and keep the detected Python runtime/default build settings. The root `app.py` exports the FastAPI `app`; `public/index.html` is the browser UI.
3. In **Project Settings → Environment Variables**, add these as **Secret** values for Production (and Preview if you use preview deployments):

   | Name | Value |
   | --- | --- |
   | `GROQ_API_KEY` | Groq API key. Required for `openai/gpt-oss-20b` answer generation. |
   | `OPENAI_API_KEY` | OpenAI API key. Required for ingestion and query-time embeddings; this may have a separate API cost. |
   | `DATABASE_URL` | Neon pooled PostgreSQL connection string for the same database used by ingestion. |

   Do not add a `NEXT_PUBLIC_` prefix, paste keys into source files, or commit `.env`.
   Create a key in the [Groq Console](https://console.groq.com/team/default/api-keys). Groq's Free plan is for building and testing and has account-specific rate limits; check the [rate limits](https://console.groq.com/docs/rate-limits) for your organization. Never submit personal information.
4. Deploy. Vercel's Python runtime detects the FastAPI `app` in `app.py`; static files are served from `public/`.
5. Before asking questions, populate the Neon database once from a trusted local machine. Use the same `DATABASE_URL` and `OPENAI_API_KEY` values configured in Vercel:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   # Fill the required keys in .env, then run:
   python ingest_neon.py
   ```

   Ingestion fetches only the five allowlisted Groww pages, embeds them with the same configured OpenAI model used at query time, and atomically refreshes the pgvector table. It also writes inspectable stage artifacts under ignored `data/`.
6. Visit the Vercel deployment URL and ask a factual question. Groq `openai/gpt-oss-20b` is the only answer model. When Groq reports the daily request quota is exhausted, the API responds: “Limit for the day reached. Please try again after the daily quota resets.” Short-term rate limits receive a retry-soon message.

The API health check is `/api/health`. If Vercel environment variables change, redeploy so the new values are available to the deployment.

## Local options

- Run the Vercel-compatible API locally with `uvicorn app:app --reload`; it serves the API. Open `public/index.html` separately or use `vercel dev` to test the Vercel routing and static UI together.
- The previous Streamlit prototype remains in `streamlit_app.py`. To run it locally, install `requirements-streamlit.txt`, set its configured local embedding model and `GROQ_API_KEY`, then run `streamlit run streamlit_app.py`. Its local ChromaDB index is separate from the Vercel Neon database.

## Scope and limits

- Only the five URLs in `config.yaml` are scraped; links found on those pages are not followed.
- OpenAI `text-embedding-3-small` and cosine distance are used for both ingestion and query retrieval. Changing the embedding model or dimension requires a fresh ingestion.
- Groq `openai/gpt-oss-20b` is the sole answer model. Groq Free plan model availability and limits are account-specific; OpenAI embeddings and Neon usage have separate quotas or costs.
- Neon Postgres with pgvector is the durable vector store for Vercel; the serverless function does not depend on local files for retrieval.
- The source corpus does not explain statement downloads; the assistant declines to invent steps.
- This is a demo, not a production financial-support service. Review source freshness, security, cost, rate limits, privacy, and provider terms before public use.
- Configure Vercel Firewall rate limits before sharing the public URL; otherwise visitors can incur embedding and LLM API costs.

**Disclaimer:** Facts only. This assistant does not provide investment, legal, or tax advice, make recommendations, or compare performance. Do not enter PAN, Aadhaar, account numbers, OTPs, phone numbers, or email addresses.
