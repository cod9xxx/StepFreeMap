import streamlit as st
from database import get_user_stats

if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
    st.error("Сначала авторизуйтесь на главной странице")
    st.stop()

username = st.session_state.get("username")
name = st.session_state.get("name", username)
gender = st.session_state.get("gender", "Не указан")

st.title(f"Профиль: {name}")

rating, reviews_list = get_user_stats(username)

col1, col2 = st.columns(2)
with col1:
    st.metric(label="Ваш рейтинг доверия", value=f"{rating}")
with col2:
    st.metric(label="Всего отзывов", value=len(reviews_list))

st.markdown("---")
left_col, right_col = st.columns([1, 2])

with left_col:
    st.subheader("О пользователе")
    st.write(f"**Логин:** {username}")
    st.write(f"**Пол:** {gender}")
    st.write(f"**Статус:** {'Эксперт' if rating > 10 else 'Новичок'}")

    if st.button("Выйти из аккаунта", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

with right_col:
    st.subheader("Последние отзывы на ваши метки")
    if not reviews_list:
        st.info("Ваши метки пока никто не оценил.")
    else:
        for rev_user, rev_text, m_type, m_vote in reviews_list:
            with st.chat_message(rev_user):
                sign = "+1" if m_vote > 0 else "-1"
                st.write(f"**{rev_user}** оценил вашу метку ({m_type}) {sign}")
                st.write(f"*{rev_text}*")