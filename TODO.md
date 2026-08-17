# MaraPal Coach roadmap

## Done

- [x] Build the RAG workflow with LangChain and LangGraph.
- [x] Compare BM25, vector, and hybrid search, then choose vector search.
- [x] Compare two prompts with DeepEval and Gemini.
- [x] Build the FastAPI backend and Streamlit frontend.
- [x] Let users use and validate their own OpenAI API key.
- [x] Add LangSmith tracing, user feedback, and a separate monitoring page.
- [x] Use Kestra for the ingestion workflow.
- [x] Put the full project in Docker Compose.
- [x] Share the local app with ngrok.

## Next

- [ ] Add GitHub Actions CI for tests and Docker builds.
- [ ] Stop loading all documents and rebuilding the retriever for every request.
- [ ] Add more questions to the retrieval evaluation dataset.
- [ ] Improve queries that mix German and English.
- [ ] Improve the race registration status data.

## Later

- [ ] Test document reranking.
- [ ] Test query rewriting.
- [ ] Use Redis if the API needs multiple workers later.
- [ ] Pin Kestra to a specific Docker image version.
- [ ] Run the containers as non-root users.
- [ ] Decide how long monitoring data should be kept.

## Deployment

MaraPal Coach currently runs on my computer with Docker Compose. I use ngrok
to give it a public HTTPS URL, so the demo only works when my computer is online.

I am not doing cloud deployment now because of the cost. I can reconsider AWS
or another hosting option later if MaraPal becomes a bigger product.
