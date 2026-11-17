# HDFC mutual fund FAQ assistant

A facts-only FAQ prototype for five HDFC mutual-fund pages. The Vercel deployment uses a FastAPI API, a static browser UI, Groq `openai/gpt-oss-20b` for answer generation, and a bundled TF-IDF vector index. It does not need a hosted vector database, does not provide investment advice, and does not save questions and answers.

## Deploy on Vercel

1. In Vercel, import `diyachokshi25-dot/Growfolio` from GitHub. Use the repository root and a Python 3.11+ runtime. The root `app.py` exports the FastAPI `app`; `public/index.html` is the browser UI.
2. In **Project Settings → Environment Variables**, add this as a **Secret** value for Production (and Preview if you use preview deployments):

   | Name | Value |
   | --- | --- |
   | `GROQ_API_KEY` | Groq API key. Required for `openai/gpt-oss-20b` answer generation. |

   Do not add a `NEXT_PUBLIC_` prefix, paste keys into source files, or commit `.env`.
   Create a key in the [Groq Console](https://console.groq.com/team/default/api-keys). Groq's Free plan is for building and testing and has account-specific rate limits; check the [rate limits](https://console.groq.com/docs/rate-limits) for your organization. Never submit personal information.
3. Before deploying, generate the bundled index from a trusted local machine:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python ingest.py
   ```

   Ingestion fetches only the five allowlisted Groww pages, creates sparse TF-IDF vectors without an external model or API key, and writes stage artifacts under ignored `data/pipeline/`. It also creates `deployment_index.py`; commit that generated file and push it so Vercel has the corpus.
4. Deploy. Vercel's Python runtime detects the FastAPI `app` in `app.py`; static files are served from `public/`.
5. Visit the Vercel deployment URL and ask a factual question. Groq `openai/gpt-oss-20b` is the only answer model. When Groq reports the daily request quota is exhausted, the API responds: “Limit for the day reached. Please try again after the daily quota resets.” Short-term rate limits receive a retry-soon message.

The API health check is `/api/health`. If Vercel environment variables change, redeploy so the new values are available to the deployment.

## Local options

- Run only the API locally with `uvicorn app:app --reload`; it does not serve the browser UI. For a full local UI-and-API test, run `vercel dev` from the repository root and open its URL. Do not open `public/index.html` directly, because its relative API requests need to use the same origin.
- The previous Streamlit prototype remains in `streamlit_app.py`. To run it locally, install `requirements-streamlit.txt`, set its configured local embedding model and `GROQ_API_KEY`, then run `streamlit run streamlit_app.py`. Its ChromaDB index is separate from the bundled Vercel index.

## Scope and limits

- Only the five URLs in `config.yaml` are scraped; links found on those pages are not followed.
- Scheme-specific answers are limited to HDFC Large Cap, Flexi Cap, ELSS, and Mid Cap. Other HDFC scheme questions are refused even if the AMC overview contains summary text about them.
- Ingestion and retrieval use the same local TF-IDF vocabulary and sparse vectors. This lexical method is lightweight and deterministic, but less semantic than a neural embedding model. Regenerate and deploy `deployment_index.py` whenever the corpus or vectorization changes.
- Groq `openai/gpt-oss-20b` is the sole answer model. Groq Free plan model availability and limits are account-specific.
- Vercel reads the bundled, read-only `deployment_index.py`; there is no hosted database, database credential, model download, or external vector service.
- The source corpus does not explain statement downloads; the assistant declines to invent steps.
- This is a demo, not a production financial-support service. Review source freshness, security, cost, rate limits, privacy, and provider terms before public use.
- Configure Vercel Firewall rate limits before sharing the public URL; visitors consume Vercel compute and Groq usage.

**Disclaimer:** Facts only. This assistant does not provide investment, legal, or tax advice, make recommendations, or compare performance. Do not enter PAN, Aadhaar, account numbers, OTPs, phone numbers, or email addresses.
