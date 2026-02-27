import streamlit as st

def local_css(file_name):
    with open(file_name, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

login_page = st.Page("auth.py", title="Вход в систему")
map_page = st.Page("map.py", title="Интерактивная карта")
profile_page = st.Page("profile.py", title="Личный кабинет")

if st.session_state.get("logout"):
    st.session_state["authenticated"] = False
    del st.session_state["logout"]
    st.rerun()

if st.session_state.get("authenticated"):
    pg = st.navigation([map_page, profile_page])
else:
    pg = st.navigation([login_page])

pg.run()