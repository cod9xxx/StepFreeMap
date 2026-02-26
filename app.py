import streamlit as st
from auth import show_auth_page
from profile import show_profile_page

st.set_page_config(page_title="StepFree Map", layout='centered')

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    show_auth_page()
else:
    show_profile_page()