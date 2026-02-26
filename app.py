import streamlit as st

login_page = st.Page("auth.py", title="Вход в систему")
map_page = st.Page("map.py", title="Интерактивная карта")
profile_page = st.Page("profile.py", title="Личный кабинет")

if st.session_state.get("authenticated"):
    pg = st.navigation([map_page, profile_page])
else:
    pg = st.navigation([login_page])

pg.run()