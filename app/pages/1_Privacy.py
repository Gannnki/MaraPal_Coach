"""Privacy information for MaraPal Coach."""

import streamlit as st

st.set_page_config(
    page_title="MaraPal Coach Privacy",
    page_icon="🔒",
    layout="centered",
)

st.title("🔒 Privacy")
st.caption("How MaraPal Coach handles your API key and conversation data.")

st.subheader("Your OpenAI API key")

st.markdown(
    """
- Your API key is stored only in the current Streamlit session.
- It is sent over HTTPS to the MaraPal FastAPI backend.
- The backend uses it to call OpenAI for embeddings and answer generation.
- The key is not written to SQLite, Chroma, application logs, or LangSmith.
- Selecting **Forget** removes the saved key from the current session.
- Closing or restarting the session also removes the saved key.
"""
)

st.subheader("Questions and answers")

st.markdown(
    """
To monitor and improve answer quality, MaraPal may record:

- Your question
- Retrieved knowledge-base context
- The generated answer
- Routing and retrieval information
- Latency and error category
- Anonymous trace and interaction identifiers
"""
)

st.subheader("LangSmith monitoring")

st.markdown(
    """
Questions, retrieved documents, prompts, answers, model information, latency,
and feedback may be sent to LangSmith for tracing and evaluation.

Your OpenAI API key and MaraPal visitor ID are not included in LangSmith
inputs or metadata.
"""
)

st.subheader("Local monitoring and feedback")

st.markdown(
    """
Questions, execution status, latency, route, and thumbs-up or thumbs-down
feedback are stored in MaraPal's local monitoring database.

These records remain stored until the MaraPal operator deletes them.
"""
)

st.subheader("Third-party services")

st.markdown(
    """
MaraPal currently uses:

- **OpenAI** for embeddings and answer generation
- **LangSmith** for tracing, evaluation, and feedback
- **ngrok** to provide the public HTTPS connection
"""
)

st.subheader("Usage limits")

st.markdown(
    """
Each browser session may submit up to **10 questions per 60 seconds**.
Requests above this limit receive a `429 Too Many Requests` response.
"""
)

st.subheader("Important limitations")

st.markdown(
    """
- Do not submit passwords, financial information, medical records, or other
  highly sensitive personal information.
- Running and health-related answers are informational and are not medical advice.
- MaraPal cannot verify your OpenAI account balance, billing configuration,
  or access to every model before each request.
"""
)

st.info(
    "By using MaraPal, you acknowledge that your questions and generated "
    "answers may be processed by OpenAI and monitored through LangSmith."
)
