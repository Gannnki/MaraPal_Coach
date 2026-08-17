"""Streamlit chat frontend with user feedback."""

from __future__ import annotations

import os
from uuid import uuid4

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("MARAPAL_API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="MaraPal Coach", page_icon="🏃", layout="centered")
st.title("🏃 MaraPal Coach")
st.caption("An evidence-aware running assistant by MaraPal")

if "visitor_id" not in st.session_state:
    st.session_state.visitor_id = str(uuid4())

st.sidebar.info("Knowledge retrieval: Vector Search")
st.sidebar.caption("Race queries always use exact SQLite filters.")
st.sidebar.subheader("OpenAI API key")
st.sidebar.caption(
    "Used for this browser session only. It is sent to MaraPal over the API, "
    "but the key itself is not stored in the database or sent to LangSmith."
)


def save_openai_key() -> None:
    candidate = st.session_state.get("openai_api_key_input", "").strip()
    if not candidate:
        st.session_state.api_key_notice = "missing"
        return
    try:
        response = requests.post(
            f"{API_URL}/api/v1/validate-key",
            headers={"X-OpenAI-API-Key": candidate},
            timeout=20,
        )
    except requests.RequestException:
        st.session_state.api_key_notice = "unavailable"
        return
    if response.ok:
        st.session_state.openai_api_key = candidate
        st.session_state.api_key_notice = "saved"
    elif response.status_code == 401:
        st.session_state.pop("openai_api_key", None)
        st.session_state.api_key_notice = "invalid"
    elif response.status_code == 403:
        st.session_state.pop("openai_api_key", None)
        st.session_state.api_key_notice = "permission"
    else:
        st.session_state.api_key_notice = "unavailable"


def forget_openai_key() -> None:
    st.session_state.pop("openai_api_key", None)
    st.session_state.pop("openai_api_key_input", None)
    st.session_state.api_key_notice = "forgotten"


st.sidebar.text_input(
    "API key", type="password", key="openai_api_key_input",
    placeholder="sk-...", label_visibility="collapsed",
)
save_key, forget_key = st.sidebar.columns(2)
save_key.button(
    "Save", use_container_width=True, on_click=save_openai_key
)
forget_key.button(
    "Forget", use_container_width=True, on_click=forget_openai_key
)

if st.session_state.get("api_key_notice") == "saved":
    st.sidebar.success("Saved for this session.")
elif st.session_state.get("api_key_notice") == "missing":
    st.sidebar.error("Enter an API key first.")
elif st.session_state.get("api_key_notice") == "invalid":
    st.sidebar.error("Invalid or revoked OpenAI API key.")
elif st.session_state.get("api_key_notice") == "permission":
    st.sidebar.error("This OpenAI API key does not have the required permission.")
elif st.session_state.get("api_key_notice") == "unavailable":
    st.sidebar.error("Could not validate the key. Please try again.")
elif st.session_state.get("api_key_notice") == "forgotten":
    st.sidebar.info("API key forgotten.")

if st.session_state.get("openai_api_key"):
    st.sidebar.caption("Key configured ✓")


def api_error(response: requests.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


if "messages" not in st.session_state:
    st.session_state.messages = []
if "submitted_feedback" not in st.session_state:
    st.session_state.submitted_feedback = {}


def show_sources(sources: list[dict]) -> None:
    for source in sources:
        if source.get("url"):
            st.caption(
                f"[{source.get('title') or 'running.wiki'}]({source['url']}) · "
                f"evidence: {source.get('evidence') or 'not graded'}"
            )


def show_feedback(message: dict) -> None:
    interaction_id = message.get("interaction_id")
    if not interaction_id:
        return
    choice = st.feedback("thumbs", key=f"feedback_{interaction_id}")
    if choice is None:
        return
    rating = 1 if choice == 1 else -1
    if st.session_state.submitted_feedback.get(interaction_id) == rating:
        return
    try:
        response = requests.post(
            f"{API_URL}/api/v1/feedback",
            json={"interaction_id": interaction_id, "rating": rating}, timeout=10,
        )
        if response.ok:
            st.session_state.submitted_feedback[interaction_id] = rating
            st.toast("Thanks — your feedback was saved.")
        else:
            st.error(f"Feedback failed ({response.status_code}): {api_error(response)}")
    except requests.RequestException as exc:
        st.error(f"Feedback request failed: {exc}")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            metadata = message.get("metadata")
            if metadata:
                st.caption(metadata)
            show_sources(message.get("sources", []))
            show_feedback(message)


api_key = st.session_state.get("openai_api_key")
if question := st.chat_input(
    "Ask about running or German races…",
    disabled=not bool(api_key),
):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Searching evidence…"):
            try:
                response = requests.post(
                    f"{API_URL}/api/v1/ask",
                    json={"question": question},
                    headers={
                        "X-OpenAI-API-Key": api_key,
                        "X-MaraPal-Visitor-ID": st.session_state.visitor_id,
                    },
                    timeout=120,
                )
                if not response.ok:
                    st.error(f"MaraPal request failed ({response.status_code}): {api_error(response)}")
                    st.stop()
                result = response.json()
                metadata = (
                    f"Route: {result['route']} · retrieval: {result['retrieval_mode']} · "
                    f"style: {result['answer_style']} · detail: {result['answer_detail']}"
                )
                st.session_state.messages.append(
                    {
                        "role": "assistant", "content": result["answer"],
                        "sources": result.get("sources", []), "metadata": metadata,
                        "interaction_id": result["interaction_id"],
                    }
                )
                st.rerun()
            except requests.ConnectionError as exc:
                st.error(f"FastAPI backend is unavailable at {API_URL}: {exc}")
            except requests.RequestException as exc:
                st.error(f"Request to FastAPI failed: {exc}")
