import streamlit as st
import folium
from streamlit_folium import st_folium


def show_map_page():
    # Заголовок и описание
    st.title("♿ Карта доступности города")
    st.markdown("Помогаем находить пандусы и тактильные дорожки в реальном времени.")

    # --- Боковая панель ---
    st.sidebar.header("Управление")

    # Кнопка выхода (чтобы вернуться в auth_view)
    if st.sidebar.button("Выйти из аккаунта"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("Фильтры объектов")
    show_ramps = st.sidebar.checkbox("Пандусы", value=True)
    show_tactile = st.sidebar.checkbox("Тактильные дорожки", value=True)

    # --- Логика создания карты ---
    # Создаем объект карты
    m = folium.Map(location=[55.751244, 37.618423], zoom_start=13, control_scale=True)

    # Пример данных (позже заменим на запрос к locations.db)
    points = [
        {"loc": [55.7558, 37.6173], "type": "Пандус", "status": "Ок"},
        {"loc": [55.7522, 37.6200], "type": "Тактильная дорожка", "status": "Изношена"},
    ]

    for p in points:
        # Фильтрация на лету
        if p["type"] == "Пандус" and not show_ramps: continue
        if p["type"] == "Тактильная дорожка" and not show_tactile: continue

        icon_color = "green" if p["type"] == "Пандус" else "blue"
        folium.Marker(
            location=p["loc"],
            popup=f"{p['type']} (Статус: {p['status']})",
            icon=folium.Icon(color=icon_color, icon="info-sign")
        ).add_to(m)

    # --- Рендеринг интерфейса ---
    col1, col2 = st.columns([3, 1])

    with col1:
        # Отображаем карту и получаем данные о кликах
        # width=None позволяет карте растягиваться по колонке
        map_data = st_folium(m, width="100%", height=600)

    with col2:
        st.subheader("Детали объекта")

        # Проверяем клик по маркеру
        if map_data and map_data.get('last_object_clicked'):
            st.info("Вы выбрали маркер")
            st.json(map_data['last_object_clicked'])

        # Проверяем клик по самой карте (для добавления новой метки)
        elif map_data and map_data.get('last_clicked'):
            st.success("Точка выбрана")
            lat = map_data['last_clicked']['lat']
            lon = map_data['last_clicked']['lng']
            st.write(f"Координаты: {lat:.4f}, {lon:.4f}")

            with st.expander("Добавить метку здесь"):
                with st.form("new_marker"):
                    m_type = st.selectbox("Тип", ["Пандус", "Тактильная дорожка"])
                    m_desc = st.text_input("Описание")
                    if st.form_submit_button("Сохранить"):
                        # Сюда добавим логику сохранения в БД
                        st.write("Сохранено!")
        else:
            st.write("Нажмите на маркер или любое место на карте.")