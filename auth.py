import streamlit as st
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.hasher import Hasher
import sqlite3

st.set_page_config(page_title="StepFree - Вход", layout="centered")

def get_all_users():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT username, name, password_hash FROM users")
    data = c.fetchall()
    conn.close()
    config = {'credentials': {'usernames': {}}}
    for row in data:
        config['credentials']['usernames'][row[0]] = {'name': row[1], 'password': row[2]}
    return config

config = get_all_users()
authenticator = stauth.Authenticate(config['credentials'], 'stepfree_cookie', 'auth_key')

name, authentication_status, username = authenticator.login('main')

if authentication_status:
    st.session_state["authenticated"] = True
    st.success(f"Добро пожаловать, {name}!")
    st.info("Перейдите на вкладку 'Карта' в боковом меню ←")
    authenticator.logout('Выйти', 'sidebar')

elif not authentication_status:
    st.error('Неверный логин/пароль')
elif authentication_status is None:
    st.warning('Пожалуйста, введите данные или зарегистрируйтесь ниже')
    with st.expander("Регистрация нового пользователя"):
        new_user = st.text_input("Choose username")
        new_password = st.text_input("Choose password", type='password')
        if st.button("Create account"):
            if register_user(new_user, new_password):
                st.success("Аккаунт создан! Теперь войдите.")
            else:
                st.error("Такой логин уже занят")

def register_user(username, password, name):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed_pw = Hasher([password]).generate()[0]

    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (username, name, hashed_pw))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()