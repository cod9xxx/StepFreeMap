import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import requests
import time
import random
import json
import re
import os
import base64
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import openrouteservice
import sqlite3

DB_NAME = "places.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL,
            lon REAL,
            type TEXT,
            source TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()


def add_place(lat, lon, place_type, source):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO places (lat, lon, type, source)
        VALUES (?, ?, ?, ?)
    """, (lat, lon, place_type, source))

    conn.commit()
    conn.close()


def get_places(place_type=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if place_type:
        cursor.execute("""
            SELECT id, lat, lon, type, source
            FROM places
            WHERE type=?
        """, (place_type,))
    else:
        cursor.execute("""
            SELECT id, lat, lon, type, source
            FROM places
        """)

    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_place(place_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM places
        WHERE id=? AND source='user'
    """, (place_id,))

    conn.commit()
    conn.close()


def osm_loaded():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM places WHERE source='osm'")
    count = cursor.fetchone()[0]

    conn.close()
    return count > 0


geolocator = Nominatim(user_agent="rostov_accessibility_app")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
client = openrouteservice.Client(key="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImU4YjRlMDQ5MmM4NjQ3ZWI5ODcxMDYxZDkyZjhmNGM0IiwiaCI6Im11cm11cjY0In0=")

# --- КОНФИГУРАЦИЯ ---
# ВАЖНО: Вместо прямого указания ключа здесь, лучше использовать st.secrets!
# ORS_API_KEY = st.secrets["ORS_API_KEY"]
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImU4YjRlMDQ5MmM4NjQ3ZWI5ODcxMDYxZDkyZjhmNGM0IiwiaCI6Im11cm11cjY0In0="

# Endpoint для Overpass API
OVERPASS_API_URL = "https://overpass.kumi.systems/api/interpreter"

# Границы Ростова-на-Дону (Bounding Box) для запроса в Overpass API (min_lat, min_lon, max_lat, max_lon)
# Этот BBOX используется для Overpass API.
ROSTOV_BBOX = "47.15,39.58,47.38,39.95"

# Строгий Bounding Box для города Ростова-на-Дону
# В формате (min_lon, min_lat, max_lon, max_lat) для Openrouteservice Boundary.rect
ORS_ROSTOV_BOUNDARY = [39.58, 47.15, 39.95, 47.38]  # min_lon, min_lat, max_lon, max_lat

ROSTOV_CENTER_INITIAL = [47.2357, 39.7125]  # Начальные широта, долгота для центрирования карты Folium
ROSTOV_ZOOM_INITIAL = 12  # Начальный масштаб карты

# User-Agent для всех HTTP-запросов (важно для Overpass API)
HEADERS = {
    'User-Agent': 'StreamlitRampApp/1.0 (https://github.com/yourusername/yourrepo)'
    # Пожалуйста, замените на ваш контакт
}
# --- Streamlit Session State для хранения данных ---
if 'map_center' not in st.session_state:
    st.session_state.map_center = ROSTOV_CENTER_INITIAL
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = ROSTOV_ZOOM_INITIAL

# Состояние для маршрута
if 'last_added_click' not in st.session_state:
    st.session_state.last_added_click = None
if 'point_a_text' not in st.session_state:
    st.session_state.point_a_text = ""
if 'point_b_text' not in st.session_state:
    st.session_state.point_b_text = ""
if 'point_a_coords' not in st.session_state:  # [lat, lon]
    st.session_state.point_a_coords = None
if 'point_b_coords' not in st.session_state:  # [lat, lon]
    st.session_state.point_b_coords = None
if 'route_geojson' not in st.session_state:
    st.session_state.route_geojson = None

# Состояние для маркеров POI
if 'osm_ramp_locations' not in st.session_state:
    st.session_state.osm_ramp_locations = []
if 'osm_wc_locations' not in st.session_state:
    st.session_state.osm_wc_locations = []
if 'last_clicked_coords' not in st.session_state:
    st.session_state.last_clicked_coords = None
if 'clicked_poi_info_html_text' not in st.session_state:
    st.session_state.clicked_poi_info_html_text = None
if 'overpass_error_message' not in st.session_state:
    st.session_state.overpass_error_message = None
if 'single_clicked_poi_element' not in st.session_state:
    st.session_state.single_clicked_poi_element = None


# --- ФУНКЦИИ ДЛЯ OVERPASS API ---

@st.cache_data(ttl=3600)  # Кэширование данных на 1 час для запросов пандусов (основной поиск)
def get_osm_data_from_overpass(query, cache_message="", is_click_query=False):
    """
    Отправляет запрос к Overpass API и возвращает JSON данные.
    is_click_query: если True, то задержка меньше, т.к. пользователь ждет мгновенно.
    """
    min_delay = 1
    max_delay = 15
    delay = random.uniform(min_delay, max_delay)
    # st.info(f"{cache_message} Пауза на {delay:.2f} сек перед запросом к Overpass API...") # Можно раскомментировать для отладки
    time.sleep(delay)

    response = None  # Инициализируем response для использования в блоке except
    try:
        response = requests.post(OVERPASS_API_URL, data=query.encode('utf-8'), headers=HEADERS, timeout=60)
        response.raise_for_status()

        # Очищаем ошибки, если запрос успешен
        st.session_state.overpass_error_message = None
        return response.json()
    except requests.exceptions.RequestException as e:
        error_text = f"Ошибка при запросе к Overpass API: {e}"
        if e.response is not None:
            error_text += f"\nОтвет API: {e.response.text}"
        st.session_state.overpass_error_message = error_text
        st.error(error_text)
        return None
    except json.JSONDecodeError as e:
        error_text = f"Ошибка при декодировании JSON от Overpass API: {e}"
        if response is not None:  # Теперь response определен
            error_text += f"\nОтвет API (часть): {response.text[:500]}..."
        st.session_state.overpass_error_message = error_text
        st.error(error_text)
        return None


def build_overpass_ramp_query(bbox):
    """
    Строит Overpass QL запрос для поиска объектов с пандусами в заданном BBOX.
    """
    query = f"""
[out:json][timeout:90];
(
  node["wheelchair"="yes"]({bbox});
  way["wheelchair"="yes"]({bbox});
  relation["wheelchair"="yes"]({bbox});

  node["ramp"="yes"]({bbox});
  way["ramp"="yes"]({bbox});
  relation["ramp"="yes"]({bbox});

  node["entrance"="main"]["ramp"="yes"]({bbox});
  way["entrance"="main"]["ramp"="yes"]({bbox});
  relation["entrance"="main"]["ramp"="yes"]({bbox});

  node["ramp:wheelchair"="yes"]({bbox});
  way["ramp:wheelchair"="yes"]({bbox});
  relation["ramp:wheelchair"="yes"]({bbox});
);
out center;
"""
    return query


def build_overpass_wc_query(bbox):
    """
    Поиск туалетов, доступных для инвалидов
    """
    query = f"""
[out:json][timeout:90];
(
  node["amenity"="toilets"]["wheelchair"="yes"]({bbox});
  way["amenity"="toilets"]["wheelchair"="yes"]({bbox});
  relation["amenity"="toilets"]["wheelchair"="yes"]({bbox});
);
out center;
"""
    return query


def autocomplete_address(query):
    if not query or len(query) < 3:
        return []

    try:
        locations = geolocator.geocode(
            query,
            exactly_one=False,
            limit=5,
            addressdetails=True
        )

        if not locations:
            return []

        suggestions = []
        for loc in locations:
            suggestions.append(loc.address)

        return suggestions

    except Exception as e:
        st.error(f"Ошибка автозаполнения: {e}")
        return []


def process_osm_elements(elements):
    """
    Обрабатывает элементы OSM, извлекая нужную и более общую информацию для маркеров.
    """
    locations = []
    processed_osm_ids = set()

    for element in elements:
        osm_id = element.get('id')
        element_type = element.get('type')

        unique_id = f"{element_type}-{osm_id}"
        if unique_id in processed_osm_ids:
            continue
        processed_osm_ids.add(unique_id)

        latitude = element.get('lat')
        longitude = element.get('lon')

        if not (latitude and longitude) and 'center' in element:
            latitude = element['center'].get('lat')
            longitude = element['center'].get('lon')

        if not (latitude and longitude):
            continue

        tags = element.get('tags', {})
        name = tags.get('name', f"Объект OSM (ID: {osm_id})")

        # --- Информация о доступности ---
        description_parts = []
        if tags.get('wheelchair') == 'yes': description_parts.append("Доступно для инвалидных колясок.")
        if tags.get('ramp') == 'yes': description_parts.append("Имеется пандус.")
        if tags.get('entrance') == 'main' and tags.get('ramp') == 'yes': description_parts.append(
            "Главный вход с пандусом.")
        if tags.get('ramp:wheelchair') == 'yes': description_parts.append("Имеется пандус для инвалидных колясок.")
        if tags.get('amenity') == 'toilets' and tags.get('wheelchair') == 'yes': description_parts.append(
            "Туалет доступен для инвалидных колясок.")

        # --- Общая информация о точке (POI) ---
        general_info_parts = []
        if tags.get('amenity'): general_info_parts.append(
            f"Тип объекта: **{tags['amenity'].replace('_', ' ').capitalize()}**.")
        if tags.get('shop'): general_info_parts.append(
            f"Тип магазина: **{tags['shop'].replace('_', ' ').capitalize()}**.")
        if tags.get('leisure'): general_info_parts.append(
            f"Место досуга: **{tags['leisure'].replace('_', ' ').capitalize()}**.")
        if tags.get('building'): general_info_parts.append(
            f"Тип здания: **{tags['building'].replace('_', ' ').capitalize()}**.")

        # Адресная информация
        address_parts = []
        street = tags.get('addr:street')
        housenumber = tags.get('addr:housenumber')
        postcode = tags.get('addr:postcode')
        if street and housenumber:
            address_parts.append(f"{street}, {housenumber}")
        elif street:
            address_parts.append(street)
        if postcode: address_parts.append(f"Индекс: {postcode}")
        if address_parts: general_info_parts.append(f"Адрес: {' '.join(address_parts)}.")

        # Контактная информация
        if tags.get('phone'): general_info_parts.append(f"Телефон: {tags['phone']}.")
        if tags.get('website'): general_info_parts.append(
            f"Сайт: <a href='{tags['website']}' target='_blank'>{tags['website']}</a>.")
        if tags.get('email'): general_info_parts.append(f"Email: {tags['email']}.")
        if tags.get('opening_hours'): general_info_parts.append(f"Часы работы: {tags['opening_hours']}.")

        # Объединяем все части описания для Popup
        full_description_html = []
        if description_parts:
            full_description_html.append("<b>Информация о доступности:</b>")
            full_description_html.extend([f"&bull; {d}" for d in description_parts])

        if general_info_parts:
            if full_description_html: full_description_html.append("<br>")  # Разделитель
            full_description_html.append("<b>Общая информация:</b>")
            full_description_html.extend([f"&bull; {g}" for g in general_info_parts])

        final_description = "<br>".join(
            full_description_html) if full_description_html else "Детальная информация отсутствует."

        locations.append({
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "description": final_description
        })
    return locations


def format_osm_element_info(element, clicked_lat=None, clicked_lon=None, include_raw_tags=False):
    """
    Форматирует информацию о конкретном OSM элементе для всплывающего окна маркера
    или для детального текстового вывода.
    """
    tags = element.get('tags', {})
    name = tags.get('name', f"Объект OSM (ID: {element.get('id')})")

    html_parts = []
    html_parts.append(f"<h4>{name}</h4>")
    html_parts.append(f"<p>Тип OSM: {element.get('type').capitalize()}, ID: {element.get('id')}</p>")

    # Координаты объекта (если они есть и отличаются от точки клика, или если это маркер объекта)
    obj_lat = element.get('lat', element.get('center', {}).get('lat'))
    obj_lon = element.get('lon', element.get('center', {}).get('lon'))
    if obj_lat is not None and obj_lon is not None:
        html_parts.append(f"<p>Координаты объекта: {obj_lat:.4f}, {obj_lon:.4f}</p>")

    # Основные теги для отображения
    if tags.get('amenity'): html_parts.append(
        f"&bull; Тип объекта: <b>{tags['amenity'].replace('_', ' ').capitalize()}</b>")
    if tags.get('shop'): html_parts.append(f"&bull; Тип магазина: <b>{tags['shop'].replace('_', ' ').capitalize()}</b>")
    if tags.get('cuisine'): html_parts.append(f"&bull; Кухня: <b>{tags['cuisine'].replace('_', ' ').capitalize()}</b>")

    # Адрес
    address_str = ""
    street = tags.get('addr:street')
    housenumber = tags.get('addr:housenumber')
    if street and housenumber:
        address_str = f"{street}, {housenumber}"
    elif street:
        address_str = street
    if address_str: html_parts.append(f"&bull; Адрес: {address_str}")

    if tags.get('opening_hours'): html_parts.append(f"&bull; Часы работы: {tags['opening_hours']}")
    if tags.get('phone'): html_parts.append(f"&bull; Телефон: {tags['phone']}")
    if tags.get('website'): html_parts.append(
        f"&bull; Сайт: <a href='{tags['website']}' target='_blank'>{tags['website']}</a>.")
    if tags.get('email'): html_parts.append(f"&bull; Email: {tags['email']}.")

    # Информация о доступности (если есть)
    accessibility_info = []
    if tags.get('wheelchair') == 'yes': accessibility_info.append("Доступно для инвалидных колясок")
    if tags.get('ramp') == 'yes': accessibility_info.append("Имеется пандус")
    if accessibility_info:
        html_parts.append(f"<p><b>Доступность:</b> {', '.join(accessibility_info)}</p>")

    # Дополнительные теги в отдельный блок (для текстового вывода, если включено)
    if include_raw_tags:
        other_tags = {k: v for k, v in tags.items() if
                      k not in ['name', 'amenity', 'shop', 'leisure', 'building', 'addr:street', 'addr:housenumber',
                                'addr:postcode', 'phone', 'website', 'email', 'opening_hours', 'wheelchair', 'ramp',
                                'description', 'cuisine']}
        if other_tags:
            html_parts.append("<p><b>Другие теги:</b></p>")
            html_parts.extend([f"&bull; {k}: {v}" for k, v in other_tags.items()])

    return "<br>".join(html_parts)


def get_osm_poi_info_for_coords(lat, lon, radius_m=50):
    """
    Получает детальную информацию о POI в радиусе от кликнутых координат с помощью Overpass API.
    radius_m: Радиус поиска в метрах вокруг кликнутой точки.
    """
    query = f"""
[out:json][timeout:30];
(
  node(around:{radius_m},{lat},{lon});
  way(around:{radius_m},{lat},{lon});
  relation(around:{radius_m},{lat},{lon});
);
out center;
"""
    return get_osm_data_from_overpass(query, cache_message="[Overpass-Click]", is_click_query=True)


def get_most_relevant_osm_element(osm_elements, clicked_lat, clicked_lon):
    """
    Выбирает ОДИН наиболее релевантный OSM элемент из списка.
    Приоритет:
    1. Имеет тег 'name'.
    2. Ближайший к точке клика.
    """
    if not osm_elements:
        return None

    most_relevant = None
    min_dist_sq = float('inf')  # Квадрат расстояния для сравнения

    for element in osm_elements:
        lat = element.get('lat')
        lon = element.get('lon')
        if not (lat and lon) and 'center' in element:  # Для путей/отношений берем центр
            lat = element['center'].get('lat')
            lon = element['center'].get('lon')

        if lat is None or lon is None: continue  # Пропускаем, если нет координат

        dist_sq = (lat - clicked_lat) ** 2 + (lon - clicked_lon) ** 2  # Квадрат расстояния

        # Приоритет: есть имя + ближе, ИЛИ нет имени, но это первый найденный, ИЛИ текущий ближе, чем предыдущий без имени
        has_name = element.get('tags', {}).get('name') is not None

        if most_relevant is None:
            most_relevant = element
            min_dist_sq = dist_sq
        else:
            most_relevant_has_name = most_relevant.get('tags', {}).get('name') is not None
            if has_name and not most_relevant_has_name:  # Текущий имеет имя, а предыдущий нет
                most_relevant = element
                min_dist_sq = dist_sq
            elif has_name and most_relevant_has_name and dist_sq < min_dist_sq:  # Оба с именем, но текущий ближе
                most_relevant = element
                min_dist_sq = dist_sq
            elif not has_name and not most_relevant_has_name and dist_sq < min_dist_sq:  # Оба без имени, но текущий ближе
                most_relevant = element
                min_dist_sq = dist_sq

    return most_relevant


@st.cache_data(ttl=3600)
def geocode_address(address):
    if not address:
        return None

    try:
        location = geocode(address)

        if not location:
            return None

        return [location.latitude, location.longitude]

    except Exception as e:
        st.error(f"Ошибка геокодирования: {e}")
        return None




# --- ПЕРВИЧНАЯ ЗАГРУЗКА OSM В БАЗУ ---
if not osm_loaded():
    st.write("Первичная загрузка данных Ростова...")

    ramp_query = build_overpass_ramp_query(ROSTOV_BBOX)
    wc_query = build_overpass_wc_query(ROSTOV_BBOX)

    ramp_data = get_osm_data_from_overpass(ramp_query)
    wc_data = get_osm_data_from_overpass(wc_query)

    if ramp_data and 'elements' in ramp_data:
        ramps = process_osm_elements(ramp_data['elements'])
        for r in ramps:
            add_place(r['latitude'], r['longitude'], "ramp", "osm")

    if wc_data and 'elements' in wc_data:
        toilets = process_osm_elements(wc_data['elements'])
        for t in toilets:
            add_place(t['latitude'], t['longitude'], "toilet", "osm")

    st.success("OSM данные загружены в базу.")

st.set_page_config(layout="wide")

st.title("Карта Ростова-на-Дону (OpenStreetMap)")
st.markdown(
    "Данные получены из [OpenStreetMap](https://www.openstreetmap.org/) через [Overpass API](http://overpass-api.de/). "
    "Маршруты строятся с использованием [Openrouteservice](https://openrouteservice.org/).")

st.sidebar.header("Настройки")

# --- Секция "Маршрут" ---
st.sidebar.subheader("Построение маршрута")

point_a_query = st.sidebar.text_input(
    "Пункт А (Начало)",
    value=st.session_state.point_a_text,
    key="point_a_input"
)
st.sidebar.markdown("---")
st.sidebar.subheader("Добавить объект")

add_mode = st.sidebar.checkbox("Режим добавления")

new_place_type = None
if add_mode:
    new_place_type = st.sidebar.selectbox(
        "Что добавить?",
        ["Пандус", "Туалет"]
    )
point_a_suggestions = autocomplete_address(point_a_query)

if point_a_suggestions:
    st.session_state.point_a_text = st.sidebar.selectbox(
        "Выберите адрес А:",
        point_a_suggestions,
        key="point_a_select"
    )
else:
    st.session_state.point_a_text = point_a_query
point_b_query = st.sidebar.text_input(
    "Пункт Б (Конец)",
    value=st.session_state.point_b_text,
    key="point_b_input"
)

point_b_suggestions = autocomplete_address(point_b_query)

if point_b_suggestions:
    st.session_state.point_b_text = st.sidebar.selectbox(
        "Выберите адрес Б:",
        point_b_suggestions,
        key="point_b_select"
    )
else:
    st.session_state.point_b_text = point_b_query

col1, col2 = st.sidebar.columns(2)
build_route_button = col1.button("Построить маршрут")
clear_route_button = col2.button("Очистить маршрут")

# Галочка для профиля маршрута
profile_option = st.sidebar.checkbox("♿ Маршрут для инвалидных колясок (через пандусы)", value=False)
route_profile = 'wheelchair' if profile_option else 'foot-walking'

if build_route_button:
    st.session_state.route_geojson = None  # Очищаем старый маршрут
    st.session_state.point_a_coords = None
    st.session_state.point_b_coords = None

    if not st.session_state.point_a_text or not st.session_state.point_b_text:
        st.sidebar.warning("Пожалуйста, введите оба пункта (А и Б) для построения маршрута.")
    else:
        with st.spinner("Геокодирование адресов и построение маршрута..."):
            point_a_geocoded = geocode_address(st.session_state.point_a_text)
            point_b_geocoded = geocode_address(st.session_state.point_b_text)

            if point_a_geocoded and point_b_geocoded:
                st.session_state.point_a_coords = point_a_geocoded
                st.session_state.point_b_coords = point_b_geocoded

                # openrouteservice.Client.directions ожидает [[lon1, lat1], [lon2, lat2]]
                ors_coords = [
                    [st.session_state.point_a_coords[1], st.session_state.point_a_coords[0]],
                    [st.session_state.point_b_coords[1], st.session_state.point_b_coords[0]]
                ]
                try:
                    route = client.directions(
                        coordinates=ors_coords,
                        profile=route_profile,
                        format='geojson'
                    )
                    st.session_state.route_geojson = route
                    st.sidebar.success("Маршрут успешно построен!")
                except Exception as e:
                    st.sidebar.error(
                        f"Ошибка при построении маршрута: {e}. Проверьте введенные адреса или попробуйте другой профиль.")
            else:
                st.sidebar.error("Не удалось геокодировать один или оба адреса **в пределах города Ростов-на-Дону**. "
                                 "Пожалуйста, проверьте их (например, 'улица, дом').")

if clear_route_button:
    st.session_state.point_a_text = ""
    st.session_state.point_b_text = ""
    st.session_state.point_a_coords = None
    st.session_state.point_b_coords = None
    st.session_state.route_geojson = None
    st.sidebar.info("Маршрут очищен.")

st.sidebar.markdown("---")
st.sidebar.subheader("Поиск объектов")
# Галочки вместо кнопки
show_ramps = st.sidebar.checkbox("♿ Показывать объекты с пандусами", value=False)
show_wc = st.sidebar.checkbox("🚻 Туалеты для инвалидов", value=False)
st.sidebar.markdown("---")
st.sidebar.subheader("Удаление (dev режим)")

delete_id = st.sidebar.number_input("ID для удаления", step=1)

if st.sidebar.button("Удалить объект"):
    delete_place(delete_id)
    st.success("Объект удален.")
    st.rerun()
# Логика загрузки данных для пандусов


# --- Отображение карты ---
st.markdown("---")
st.subheader("Карта")
all_places = get_places()

total_ramps = sum(1 for p in all_places if p[3] == "ramp")
total_toilets = sum(1 for p in all_places if p[3] == "toilet")

st.write(
    f"На карте отмечены {total_ramps} объектов с пандусами "
    f"и {total_toilets} туалетов для людей с ограниченными возможностями."
)
# Создаем карту, используя сохраненное состояние
m = folium.Map(
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    control_scale=True,
    tiles=None
)

folium.TileLayer(
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr="© OSM",  # <--- НЕ пусто!
    control=False
).add_to(m)

# скрываем блок после
m.get_root().html.add_child(folium.Element("""
<style>
.leaflet-control-attribution {
    display: none !important;
}
</style>
"""))
marker_cluster = MarkerCluster().add_to(m)
for place in all_places:
    place_id, lat, lon, place_type, source = place

    # Фильтр по галочкам
    if place_type == "ramp" and not show_ramps:
        continue
    if place_type == "toilet" and not show_wc:
        continue

    color = "green" if place_type == "ramp" else "blue"
    icon_name = "wheelchair" if place_type == "ramp" else "info-sign"

    popup_html = f"""
    <b>ID:</b> {place_id}<br>
    <b>Тип:</b> {"Пандус" if place_type == "ramp" else "Туалет"}
    """

    folium.Marker(
        location=[lat, lon],
        popup=popup_html,
        icon=folium.Icon(color=color, icon=icon_name)
    ).add_to(marker_cluster)


# Добавляем маркеры найденных пандусов (зеленые)
# Загружаем изображение и кодируем его в Base64 (для иконок)
# Убедитесь, что 'ramp_icon.webp' находится в папке 'static'
ramp_icon_base64 = None
try:
    with open("static/ramp_icon.webp", "rb") as f:
        encoded_image = base64.b64encode(f.read()).decode()
    ramp_icon_base64 = f"data:image/webp;base64,{encoded_image}"
except FileNotFoundError:
    st.warning("Файл 'static/ramp_icon.webp' не найден. Используется стандартная иконка.")
    # Используем стандартную иконку Font Awesome как запасной вариант
    # ramp_icon_base64 = None # Оставляем None, чтобы использовать FontAwesome



# Добавляем маркер для Пункта А (если геокодирован)
if st.session_state.point_a_coords:
    folium.Marker(
        location=st.session_state.point_a_coords,
        tooltip="Пункт А (Начало маршрута)",
        icon=folium.Icon(color='green', icon='play', prefix='fa')
    ).add_to(m)

# Добавляем маркер для Пункта Б (если геокодирован)
if st.session_state.point_b_coords:
    folium.Marker(
        location=st.session_state.point_b_coords,
        tooltip="Пункт Б (Конец маршрута)",
        icon=folium.Icon(color='red', icon='stop', prefix='fa')
    ).add_to(m)

# Добавляем ОДИН маркер объекта, найденного по клику (темно-фиолетовый)
if st.session_state.single_clicked_poi_element:
    element = st.session_state.single_clicked_poi_element
    lat = element.get('lat')
    lon = element.get('lon')
    if not (lat and lon) and 'center' in element:
        lat = element['center'].get('lat')
        lon = element['center'].get('lon')
    if lat and lon and st.session_state.last_clicked_coords:
        popup_html = format_osm_element_info(element, clicked_lat=st.session_state.last_clicked_coords[0],
                                             clicked_lon=st.session_state.last_clicked_coords[1])
        iframe = folium.IFrame(popup_html, width=300, height=250)
        popup = folium.Popup(iframe, max_width=300)

        folium.Marker(
            location=[lat, lon],
            popup=popup,
            icon=folium.Icon(color='darkpurple', icon='tag', prefix='fa')
        ).add_to(m)
# Если есть информация о последнем клике, добавляем временный маркер для точки клика (оранжевый)
if st.session_state.last_clicked_coords:
    lat_c, lon_c = st.session_state.last_clicked_coords
    folium.Marker(
        location=[lat_c, lon_c],
        tooltip="Точка клика",
        popup=f"Вы кликнули сюда: {lat_c:.4f}, {lon_c:.4f}",
        icon=folium.Icon(color='orange', icon='crosshairs', prefix='fa')
    ).add_to(m)


# --- Отрисовка маршрута ---
if st.session_state.route_geojson:
    folium.GeoJson(
        st.session_state.route_geojson,
        name="route",
        style_function=lambda x: {
            'color': 'red',
            'weight': 5
        }
    ).add_to(m)

output = st_folium(
    m,
    width="100%",
    height=600,
    key="folium_map",
    return_on_hover=False,
    zoom=st.session_state.map_zoom
)

# --- Обработка кликов по карте (только для POI) ---
if output and output.get("last_clicked"):

    lat_clicked = output["last_clicked"]["lat"]
    lon_clicked = output["last_clicked"]["lng"]

    # --- ЕСЛИ режим добавления ---
    if add_mode and new_place_type:

        # Проверяем, не обработан ли уже этот клик
        if st.session_state.last_added_click != (lat_clicked, lon_clicked):
            place_type_value = "ramp" if new_place_type == "Пандус" else "toilet"
            add_place(lat_clicked, lon_clicked, place_type_value, "user")

            st.session_state.last_added_click = (lat_clicked, lon_clicked)

            st.success("Объект добавлен!")
            st.rerun()

    # --- ИНАЧЕ обычный клик ---
    if not add_mode:

        if st.session_state.last_clicked_coords != (lat_clicked, lon_clicked):

            st.session_state.last_clicked_coords = (lat_clicked, lon_clicked)
            st.session_state.overpass_error_message = None
            st.session_state.single_clicked_poi_element = None
            st.session_state.clicked_poi_info_html_text = None

            with st.spinner("Запрос детальной информации (Overpass API)..."):
                poi_data = get_osm_poi_info_for_coords(lat_clicked, lon_clicked, radius_m=50)

                if poi_data and 'elements' in poi_data:
                    single_element = get_most_relevant_osm_element(
                        poi_data['elements'],
                        lat_clicked,
                        lon_clicked
                    )

                    if single_element:
                        st.session_state.single_clicked_poi_element = single_element
                        st.session_state.clicked_poi_info_html_text = format_osm_element_info(
                            single_element,
                            lat_clicked,
                            lon_clicked,
                            include_raw_tags=True
                        )
                    else:
                        st.session_state.clicked_poi_info_html_text = "Не удалось определить релевантный объект."
                else:
                    st.session_state.clicked_poi_info_html_text = f"Нет данных для точки {lat_clicked:.6f}, {lon_clicked:.6f}"
# Блок для вывода информации о кликнутой точке (текстовый, в экспандере)
st.markdown(f"---")
st.subheader("Информация о кликнутой точке")

# Отображаем ошибку Overpass API, если она есть
if st.session_state.overpass_error_message:
    st.error("Произошла ошибка при запросе к Overpass API. Пожалуйста, попробуйте позже.")
    st.markdown(f"Детали ошибки: {st.session_state.overpass_error_message}")
    st.info("Overpass API является публичным сервисом и может быть перегружен или блокировать слишком частые запросы.")
elif st.session_state.last_clicked_coords:
    lat_c, lon_c = st.session_state.last_clicked_coords
    st.write(f"Информация по клику на: **{lat_c:.6f}, {lon_c:.6f}**")

    if st.session_state.single_clicked_poi_element:
        st.write(f"Отображен 1 наиболее релевантный объект.")
        if st.session_state.clicked_poi_info_html_text:
            with st.expander("Показать детальную текстовую информацию"):
                st.markdown(st.session_state.clicked_poi_info_html_text, unsafe_allow_html=True)
    else:
        st.info("Не удалось найти наиболее релевантный объект для этой точки.")
        if st.session_state.clicked_poi_info_html_text:
            with st.expander("Показать детальную текстовую информацию"):
                st.markdown(st.session_state.clicked_poi_info_html_text, unsafe_allow_html=True)
else:
    st.info("Кликните на карту, чтобы выбрать точку и узнать о ней информацию.")