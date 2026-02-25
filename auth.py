import streamlit as st
import sqlite3
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.hasher import Hasher

DB_USERS = "users.db"


def init_users_db():
    conn = sqlite3.connect(DB_USERS)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (
                     username
                     TEXT
                     PRIMARY
                     KEY,
                     name
                     TEXT,
                     password_hash
                     TEXT
                 )''')
    conn.commit()
    conn.close()


def get_all_users_config():
    conn = sqlite3.connect(DB_USERS)
    c = conn.cursor()
    c.execute("SELECT username, name, password_hash FROM users")
    rows = c.fetchall()
    conn.close()

    config = {'credentials': {'usernames': {}}}
    for row in rows:
        config['credentials']['usernames'][row[0]] = {
            'name': row[1],
            'password': row[2]
        }
    return config


def register_new_user(username, name, password):
    if not username or not password:
        return False, "Логин и пароль не могут быть пустыми"

    hashed_pw = Hasher([password]).generate()[0]

    conn = sqlite3.connect(DB_USERS)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (username, name, hashed_pw))
        conn.commit()
        return True, "Регистрация успешна!"
    except sqlite3.IntegrityError:
        return False, "Пользователь с таким логином уже существует"
    finally:
        conn.close()


def show_auth_page():
    init_users_db()
    config = get_all_users_config()

    authenticator = stauth.Authenticate(
        config['credentials'],
        'stepfree_session',
        'signature_key_123',
        cookie_expiry_days=1
    )

    tab1, tab2 = st.tabs(["Вход", "Регистрация"])

    with tab1:
        name, authentication_status, username = authenticator.login('main')

        if authentication_status:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["name"] = name
            st.rerun()
        elif authentication_status is False:
            st.error("Неверный логин или пароль")

    with tab2:
        st.subheader("Создать новый аккаунт")
        with st.form("reg_form", clear_on_submit=True):
            new_user = st.text_input("Логин (email или ник)")
            new_name = st.text_input("Имя")
            new_pw = st.text_input("Пароль", type="password")
            submit = st.form_submit_button("Зарегистрироваться")

            if submit:
                success, message = register_new_user(new_user, new_name, new_pw)
                if success:
                    st.success(message)
                    st.info("Теперь вы можете войти во вкладке 'Вход'")
                else:
                    st.error(message)