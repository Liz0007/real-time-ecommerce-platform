import os

import requests
import streamlit as st

AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://ai-agent-service:8000")

st.set_page_config(page_title="Order Assistant", page_icon="🤖")
st.title("🤖 Order Assistant")

# Fetch available tools from the agent service to populate the dropdown
@st.cache_data(ttl=60)
def get_available_tools():
    resp = requests.get(f"{AGENT_SERVICE_URL}/agent/tools")
    resp.raise_for_status()
    return resp.json()["available_tools"]

available_tools = get_available_tools()

enabled_tools = st.multiselect(
    "Active tools",
    options=available_tools,
    default=available_tools,  # all on by default
    help="Choose which tools the agent is allowed to use for this question.",
)

# Streamlit reruns the whole script on every interaction, so anything not
# kept in session_state is lost between runs. history holds every past
# exchange so it can be re-rendered on each rerun, not just the latest one.
if "history" not in st.session_state:
    st.session_state.history = []

question = st.text_input("Ask a question", placeholder="What's the status of order ...?")

ask_col, _, clear_col = st.columns([1, 6, 2], gap="small")
with ask_col:
    ask_clicked = st.button("Ask")
with clear_col:
    if st.button("Clear history", disabled=not st.session_state.history, use_container_width=True):
        st.session_state.history = []
        
if ask_clicked and question:
    with st.spinner("Thinking..."):
        resp = requests.post(
            f"{AGENT_SERVICE_URL}/agent/ask",
            json={"question": question, "enabled_tools": enabled_tools},
        )
        resp.raise_for_status()
        data = resp.json()

    st.session_state.history.append(
        {
            "question": question,
            "answer": data["answer"],
            "enabled_tools": enabled_tools,
            "tools_used": data["tools_used"],
        }
    )
    st.rerun()  # redraw immediately so Clear history's disabled state updates without a second click

# Render most recent first
for exchange in reversed(st.session_state.history):
    st.markdown(f"**Q: {exchange['question']}**")
    st.write(exchange["answer"])

    col1, col2 = st.columns(2)
    with col1:
        with st.expander("Tools enabled (allowed)"):
            st.markdown(", ".join(exchange["enabled_tools"]) if exchange["enabled_tools"] else "all")
    with col2:
        with st.expander("Tools actually used"):
            st.markdown(
                ", ".join(exchange["tools_used"])
                if exchange["tools_used"]
                else "*none — answered without a tool call*"
            )
    st.divider()