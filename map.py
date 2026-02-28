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
import traceback
from gtts import gTTS
import tempfile
import streamlit as st
import random

from services import get_weather, get_gigachat_advice


def speak_route(route_json, max_steps=20):
    steps = route_json["routes"][0]["segments"][0]["steps"]

    if not steps:
        return

    steps = steps[:max_steps]

    text_parts = ["Маршрут построен."]

    for step in steps:

        distance = int(step.get("distance", 0))
        street = step.get("name", "")
        maneuver_type = step.get("type", 0)

        if not street or street.strip() in ["-", "none"]:
            street = ""

        # types of dir change
        maneuver_map = {
            0: "Начните движение",
            1: "Продолжайте движение",
            2: "Поверните налево",
            3: "Поверните направо",
            4: "Резкий поворот налево",
            5: "Резкий поворот направо",
            6: "Двигайтесь на север",
            7: "Двигайтесь на северо-восток",
            8: "Двигайтесь на восток",
            9: "Двигайтесь на юго-восток",
            10: "Вы прибыли в пункт назначения",
            11: "На кольце поверните на первый съезд",
            12: "На кольце поверните на второй съезд",
            13: "На кольце поверните на третий съезд",
            14: "На кольце поверните на четвертый съезд"
        }

        phrase = maneuver_map.get(maneuver_type, "Следуйте далее")

        if street and maneuver_type != 10:
            phrase += f" на {street}"

        if distance > 0 and maneuver_type != 10:
            phrase = f"Через {distance} метров {phrase.lower()}."

        text_parts.append(phrase)

    final_text = " ".join(text_parts)

    # audio
    tts = gTTS(text=final_text, lang="ru", slow=False)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tts.save(tmp.name)
        with open(tmp.name, "rb") as audio_file:
            audio_bytes = audio_file.read()

    st.session_state.route_audio = audio_bytes


geolocator = Nominatim(user_agent="rostov_accessibility_app")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)
st.set_page_config(layout="wide")

# CSS
st.markdown("""
<style>
button[kind="primary"] {
    background-color: #0B5ED7 !important;
}
</style>
""", unsafe_allow_html=True)
st.title("OpenWay")
st.markdown(
    "<p style='color:#0B5ED7; font-size:18px;'>Веб-приложение для помощи людям с ОВЗ</p>",
    unsafe_allow_html=True
)

DB_NAME = "places.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS places
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       lat
                       REAL,
                       lon
                       REAL,
                       type
                       TEXT,
                       source
                       TEXT
                   )
                   """)

    conn.commit()
    conn.close()


init_db()


def init_reviews_db():
    conn = sqlite3.connect('reviews.db')
    c = conn.cursor()

    c.execute("""
              CREATE TABLE IF NOT EXISTS markers
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  lat
                  REAL,
                  lon
                  REAL,
                  category
                  TEXT,
                  description
                  TEXT,
                  user
                  TEXT
              )
              """)

    c.execute("""
              CREATE TABLE IF NOT EXISTS reviews
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  marker_id
                  INTEGER,
                  reviewer
                  TEXT,
                  vote
                  INTEGER,
                  comment
                  TEXT
              )
              """)

    conn.commit()
    conn.close()


def add_test_data(current_user):
    init_reviews_db()
    conn = sqlite3.connect('reviews.db')
    c = conn.cursor()

    test_markers = [
        (55.75, 37.61, 'Пандус', 'Удобный пологий спуск у аптеки'),
        (55.76, 37.62, 'Подъемник', 'Электрический подъемник в переходе'),
        (55.74, 37.60, 'Тактильная плитка', 'Направляет к главному входу')
    ]

    for lat, lon, cat, desc in test_markers:
        c.execute(
            "SELECT id FROM markers WHERE lat=? AND lon=? AND user=?",
            (lat, lon, current_user)
        )
        if not c.fetchone():
            c.execute(
                "INSERT INTO markers (lat, lon, category, description, user) VALUES (?, ?, ?, ?, ?)",
                (lat, lon, cat, desc, current_user)
            )

    conn.commit()

    c.execute("SELECT id FROM markers WHERE user=?", (current_user,))
    user_marker_ids = [row[0] for row in c.fetchall()]

    fake_reviewers = ["Ivan_92", "Elena_Pro", "City_Watcher", "User_101"]
    fake_comments = [
        ("Спасибо, очень помогло!", 1),
        ("Пандус отличный, подтверждаю.", 1),
        ("Подъемник заблокирован, пришлось просить ключ.", -1),
        ("Плитка уложена криво, опасно.", -1),
        ("Все работает штатно.", 1)
    ]

    for m_id in user_marker_ids:
        c.execute("SELECT id FROM reviews WHERE marker_id=?", (m_id,))
        if not c.fetchone():
            for _ in range(random.randint(1, 2)):
                rev_user = random.choice(fake_reviewers)
                comment, vote = random.choice(fake_comments)
                c.execute(
                    "INSERT INTO reviews (marker_id, reviewer, vote, comment) VALUES (?, ?, ?, ?)",
                    (m_id, rev_user, vote, comment)
                )

    conn.commit()
    conn.close()


def get_reviews_for_place(place_id):
    conn = sqlite3.connect('reviews.db')
    c = conn.cursor()

    c.execute("""
              SELECT reviewer, vote, comment
              FROM reviews
              WHERE marker_id = ?
              """, (place_id,))

    rows = c.fetchall()
    conn.close()
    return rows


if "test_data_added" not in st.session_state:
    add_test_data("demo_user")
    st.session_state.test_data_added = True


def add_fake_reviews_for_places():
    conn = sqlite3.connect('reviews.db')
    c = conn.cursor()

    conn_places = sqlite3.connect(DB_NAME)
    c_places = conn_places.cursor()
    c_places.execute("SELECT id FROM places")
    place_ids = c_places.fetchall()
    conn_places.close()

    fake_reviewers = ["Иван", "Мария", "Алексей"]
    fake_comments = [
        ("Очень удобно!", 1),
        ("Можно улучшить уклон.", -1),
        ("Проверено, всё работает.", 1)
    ]

    for (place_id,) in place_ids:
        c.execute("SELECT id FROM reviews WHERE marker_id=?", (place_id,))
        if not c.fetchone():
            reviewer = random.choice(fake_reviewers)
            comment, vote = random.choice(fake_comments)
            c.execute("""
                      INSERT INTO reviews (marker_id, reviewer, vote, comment)
                      VALUES (?, ?, ?, ?)
                      """, (place_id, reviewer, vote, comment))

    conn.commit()
    conn.close()


add_fake_reviews_for_places()


# speech parsing
def parse_route_from_speech(text):
    if not text:
        return None, None

    text = text.lower()

    match = re.search(r"от (.+?) до (.+)", text)

    if match:
        point_a = match.group(1).strip()
        point_b = match.group(2).strip()
        return point_a, point_b

    return None, None


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
                       WHERE type = ?
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
                   DELETE
                   FROM places
                   WHERE id = ?
                     AND source = 'user'
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


def clean_voice_text(text):
    text = text.lower()
    print(text)
    if "инвалид" in text or "коляск" in text:
        st.session_state.wheelchair_mode = True

    words_to_remove = ["инвалид", "инвалидов", "инвалида", "коляски", "колясок", "стоп"]

    for word in words_to_remove:
        text = re.sub(rf"\b{word}\b", "", text)

    return text


def normalize_street_type(text):
    replacements = {
        "улицы": "улица",
        "улицу": "улица",
        "проспекта": "проспект",
        "проспекту": "проспект",
        "проспекте": "проспект"
    }

    words = text.split()
    normalized = []

    for w in words:
        w_lower = w.lower()
        if w_lower in replacements:
            normalized.append(replacements[w_lower])
        else:
            normalized.append(w)

    return " ".join(normalized)


# openroute api
client = openrouteservice.Client(
    key="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImU4YjRlMDQ5MmM4NjQ3ZWI5ODcxMDYxZDkyZjhmNGM0IiwiaCI6Im11cm11cjY0In0=")

# overpass api
OVERPASS_API_URL = "https://overpass.kumi.systems/api/interpreter"

# RnD lat lon
ROSTOV_BBOX = "47.15,39.58,47.38,39.95"

ORS_ROSTOV_BOUNDARY = [39.58, 47.15, 39.95, 47.38]  # min_lon, min_lat, max_lon, max_lat

ROSTOV_CENTER_INITIAL = [47.2357, 39.7125]
ROSTOV_ZOOM_INITIAL = 12

HEADERS = {
    'User-Agent': 'StreamlitRampApp/1.0 (https://github.com/cod9xxx/StepFreeMap)'
}
if 'map_center' not in st.session_state:
    st.session_state.map_center = ROSTOV_CENTER_INITIAL
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = ROSTOV_ZOOM_INITIAL

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

if "spoken_text" not in st.session_state:
    st.session_state.spoken_text = ""
if "last_audio_bytes" not in st.session_state:
    st.session_state.last_audio_bytes = None
if "voice_processed" not in st.session_state:
    st.session_state.voice_processed = False
if "auto_build_route" not in st.session_state:
    st.session_state.auto_build_route = False
if "wheelchair_mode" not in st.session_state:
    st.session_state.wheelchair_mode = False
if "voice_mode" not in st.session_state:
    st.session_state.voice_mode = False
if "route_spoken" not in st.session_state:
    st.session_state.route_spoken = False
if 'route_json' not in st.session_state:
    st.session_state.route_json = None

if "intro_ready" not in st.session_state:
    st.session_state.intro_ready = True

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


# overpass api funcs

@st.cache_data(ttl=3600)  # streamlit caching (!)
def get_osm_data_from_overpass(query, cache_message="", is_click_query=False):
    min_delay = 1
    max_delay = 15
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

    response = None
    try:
        response = requests.post(OVERPASS_API_URL, data=query.encode('utf-8'), headers=HEADERS, timeout=60)
        response.raise_for_status()

        st.session_state.overpass_error_message = None
        return response.json()
    except requests.exceptions.RequestException as e:
        error_text = f"request overpass api: {e}"
        if e.response is not None:
            error_text += f"\nanswer: {e.response.text}"
        st.session_state.overpass_error_message = error_text
        st.error(error_text)
        return None
    except json.JSONDecodeError as e:
        error_text = f"json overpass api error: {e}"
        if response is not None:
            error_text += f"\napi answer: {response.text[:500]}..."
        st.session_state.overpass_error_message = error_text
        st.error(error_text)
        return None


def build_overpass_ramp_query(bbox):
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


@st.cache_data(ttl=600)
def autocomplete_address(query):
    if not query or len(query.strip()) < 4:
        return []

    try:
        locations = geocode(
            query,
            exactly_one=False,
            limit=5,
            addressdetails=True
        )

        if not locations:
            return []

        return [loc.address for loc in locations]

    except Exception:
        print('overpass error')
        return []


def process_osm_elements(elements):
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

        # overpass info
        description_parts = []
        if tags.get('wheelchair') == 'yes': description_parts.append("Доступно для инвалидных колясок.")
        if tags.get('ramp') == 'yes': description_parts.append("Имеется пандус.")
        if tags.get('entrance') == 'main' and tags.get('ramp') == 'yes': description_parts.append(
            "Главный вход с пандусом.")
        if tags.get('ramp:wheelchair') == 'yes': description_parts.append("Имеется пандус для инвалидных колясок.")
        if tags.get('amenity') == 'toilets' and tags.get('wheelchair') == 'yes': description_parts.append(
            "Туалет доступен для инвалидных колясок.")

        general_info_parts = []
        if tags.get('amenity'): general_info_parts.append(
            f"Тип объекта: **{tags['amenity'].replace('_', ' ').capitalize()}**.")
        if tags.get('shop'): general_info_parts.append(
            f"Тип магазина: **{tags['shop'].replace('_', ' ').capitalize()}**.")
        if tags.get('leisure'): general_info_parts.append(
            f"Место досуга: **{tags['leisure'].replace('_', ' ').capitalize()}**.")
        if tags.get('building'): general_info_parts.append(
            f"Тип здания: **{tags['building'].replace('_', ' ').capitalize()}**.")

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

        if tags.get('phone'): general_info_parts.append(f"Телефон: {tags['phone']}.")
        if tags.get('website'): general_info_parts.append(
            f"Сайт: <a href='{tags['website']}' target='_blank'>{tags['website']}</a>.")
        if tags.get('email'): general_info_parts.append(f"Email: {tags['email']}.")
        if tags.get('opening_hours'): general_info_parts.append(f"Часы работы: {tags['opening_hours']}.")

        full_description_html = []
        if description_parts:
            full_description_html.append("<b>Информация о доступности:</b>")
            full_description_html.extend([f"&bull; {d}" for d in description_parts])

        if general_info_parts:
            if full_description_html: full_description_html.append("<br>")
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
    tags = element.get('tags', {})
    name = tags.get('name', f"Объект OSM (ID: {element.get('id')})")

    html_parts = []
    html_parts.append(f"<h4>{name}</h4>")
    html_parts.append(f"<p>Тип OSM: {element.get('type').capitalize()}, ID: {element.get('id')}</p>")

    obj_lat = element.get('lat', element.get('center', {}).get('lat'))
    obj_lon = element.get('lon', element.get('center', {}).get('lon'))
    if obj_lat is not None and obj_lon is not None:
        html_parts.append(f"<p>Координаты объекта: {obj_lat:.4f}, {obj_lon:.4f}</p>")

    # tags
    if tags.get('amenity'): html_parts.append(
        f"&bull; Тип объекта: <b>{tags['amenity'].replace('_', ' ').capitalize()}</b>")
    if tags.get('shop'): html_parts.append(f"&bull; Тип магазина: <b>{tags['shop'].replace('_', ' ').capitalize()}</b>")
    if tags.get('cuisine'): html_parts.append(f"&bull; Кухня: <b>{tags['cuisine'].replace('_', ' ').capitalize()}</b>")

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

    accessibility_info = []
    if tags.get('wheelchair') == 'yes': accessibility_info.append("Доступно для инвалидных колясок")
    if tags.get('ramp') == 'yes': accessibility_info.append("Имеется пандус")
    if accessibility_info:
        html_parts.append(f"<p><b>Доступность:</b> {', '.join(accessibility_info)}</p>")

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
    choose one most relevant osm element
    """
    if not osm_elements:
        return None

    most_relevant = None
    min_dist_sq = float('inf')

    for element in osm_elements:
        lat = element.get('lat')
        lon = element.get('lon')
        if not (lat and lon) and 'center' in element:
            lat = element['center'].get('lat')
            lon = element['center'].get('lon')

        if lat is None or lon is None: continue

        dist_sq = (lat - clicked_lat) ** 2 + (lon - clicked_lon) ** 2

        has_name = element.get('tags', {}).get('name') is not None

        if most_relevant is None:
            most_relevant = element
            min_dist_sq = dist_sq
        else:
            most_relevant_has_name = most_relevant.get('tags', {}).get('name') is not None
            if has_name and not most_relevant_has_name:
                most_relevant = element
                min_dist_sq = dist_sq
            elif has_name and most_relevant_has_name and dist_sq < min_dist_sq:
                most_relevant = element
                min_dist_sq = dist_sq
            elif not has_name and not most_relevant_has_name and dist_sq < min_dist_sq:
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
        st.error(f"geo errror: {e}")
        return None


def build_overpass_extra_query(bbox):
    query = f"""
[out:json][timeout:90];
(
  node["amenity"="parking"]["capacity:disabled"]({bbox});
  node["highway"="elevator"]({bbox});
  node["tactile_paving"="yes"]({bbox});
  node["highway"="bus_stop"]["wheelchair"="yes"]({bbox});
  node["kerb"="lowered"]({bbox});
);
out center;
"""
    return query


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

    extra_query = build_overpass_extra_query(ROSTOV_BBOX)
    extra_data = get_osm_data_from_overpass(extra_query)

    if extra_data and 'elements' in extra_data:
        for el in extra_data['elements']:
            lat = el.get('lat') or el.get('center', {}).get('lat')
            lon = el.get('lon') or el.get('center', {}).get('lon')
            tags = el.get('tags', {})

            if not lat or not lon:
                continue

            if tags.get("amenity") == "parking":
                add_place(lat, lon, "disabled_parking", "osm")
            elif tags.get("highway") == "elevator":
                add_place(lat, lon, "elevator", "osm")
            elif tags.get("tactile_paving") == "yes":
                add_place(lat, lon, "tactile", "osm")
            elif tags.get("highway") == "bus_stop":
                add_place(lat, lon, "bus_stop", "osm")
            elif tags.get("kerb") == "lowered":
                add_place(lat, lon, "lowered_kerb", "osm")

    st.success("OSM данные загружены в базу.")
    st.rerun()

import speech_recognition as sr
import tempfile

if st.session_state.get("intro_ready"):
    st.markdown("### 🔊 Инструкция по голосовому вводу")
    st.audio("audio_1.mp3", autoplay=True)

st.markdown("### Голосовой ввод")

audio_file = st.audio_input("Запишите голос")

if audio_file is not None:

    audio_bytes = audio_file.read()

    if st.session_state.last_audio_bytes == audio_bytes:
        pass
    else:
        st.session_state.last_audio_bytes = audio_bytes

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            temp_audio_path = tmp.name

        recognizer = sr.Recognizer()

        with sr.AudioFile(temp_audio_path) as source:
            audio = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio, language="ru-RU")
            st.success("Речь распознана")
            st.session_state.spoken_text = text
            st.session_state.voice_processed = False
            st.session_state.voice_mode = True
        except:
            st.error("Не удалось распознать речь")
    st.session_state.intro_ready = False
if st.session_state.spoken_text and not st.session_state.voice_processed:
    st.markdown("### Вы сказали:")
    st.info(st.session_state.spoken_text)
    # marshrut golosovoy
    text = st.session_state.spoken_text
    if "инвалид" in text.lower() or "коляск" in text.lower():
        st.session_state.wheelchair_mode = True
    st.session_state.voice_processed = True
    text = st.session_state.spoken_text
    text = clean_voice_text(text)
    print(text)
    point_a_voice, point_b_voice = parse_route_from_speech(text)

    if point_a_voice and point_b_voice:

        st.markdown("### Обнаружена команда маршрута")
        st.write(f"Точка А: {point_a_voice}")
        st.write(f"Точка Б: {point_b_voice}")

        point_a_voice = normalize_street_type(point_a_voice + ", Ростов-на-Дону")
        point_b_voice = normalize_street_type(point_b_voice + ", Ростов-на-Дону")

        coords_a = geocode_address(point_a_voice + ", Ростов-на-Дону")
        coords_b = geocode_address(point_b_voice + ", Ростов-на-Дону")
        print(point_a_voice + ", г Ростов-на-Дону")
        print(point_b_voice + ", г Ростов-на-Дону")

        if coords_a and coords_b:
            st.session_state.point_a_text = point_a_voice
            st.session_state.point_b_text = point_b_voice

            st.session_state.point_a_coords = coords_a
            st.session_state.point_b_coords = coords_b
            st.session_state.map_center = coords_a
            st.session_state.auto_build_route = True

            st.rerun()
        else:
            st.error("Не удалось определить координаты одной из точек.")

left_col, right_col = st.columns([1, 2])

with left_col:
    # weather sidebar
    st.sidebar.header("Погода и советы")


    @st.cache_data(ttl=3600)
    def fetch_weather(lat, lon):
        return get_weather(lat, lon)


    @st.cache_data(ttl=3600)
    def fetch_advice(temp, condition):
        return get_gigachat_advice(temp, condition)


    weather = fetch_weather(47.2248606, 39.7022858)

    if weather:
        col1, col2 = st.sidebar.columns(2)
        col1.metric("Темп. в РнД", f"{weather['temp']}°C")
        col2.write(f"**Осадки:** \n{weather['condition']}")

        with st.sidebar.expander("Совет от GigaChat", expanded=True):
            advice = fetch_advice(weather['temp'], weather['condition'])
            st.write(f"{advice}")
    else:
        st.sidebar.warning("Не удалось загрузить данные о погоде")

    st.sidebar.markdown("---")
    st.subheader("Фильтры доступности")
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        show_ramps = st.checkbox("Пандусы", value=True)
        show_wc = st.checkbox("Туалеты", value=True)
        show_parking = st.checkbox("Парковки", value=True)

    with col_f2:
        show_elevator = st.checkbox("Лифты", value=True)
        show_tactile = st.checkbox("Тактильная плитка", value=True)
        show_bus = st.checkbox("Остановки", value=True)
        show_kerb = st.checkbox("Пониженные бордюры", value=True)

    st.markdown("---")
    st.subheader("Маршрут")
    wheelchair_mode = st.checkbox(
        "Маршрут для инвалидных колясок",
        key="wheelchair_mode"
    )

    point_a_query = st.text_input(
        "Точка А",
        key="point_a_text"
    )
    if len(point_a_query) > 3:
        suggestions_a = autocomplete_address(point_a_query)

        if suggestions_a:
            selected_a = st.selectbox(
                "Выберите адрес А",
                suggestions_a,
                key="select_a"
            )

            if selected_a:
                coords = geocode_address(selected_a)
                if coords:
                    st.session_state.point_a_coords = coords
                    st.session_state.map_center = coords

    point_b_query = st.text_input(
        "Точка Б",
        key="point_b_text"
    )
    if len(point_b_query) > 3:
        suggestions_b = autocomplete_address(point_b_query)

        if suggestions_b:
            selected_b = st.selectbox(
                "Выберите адрес B",
                suggestions_b,
                key="select_b"
            )

            if selected_b:
                coords = geocode_address(selected_b)
                if coords:
                    st.session_state.point_b_coords = coords
                    st.session_state.map_center = coords

    build_route_button = st.button("Построить маршрут")

    if build_route_button or st.session_state.auto_build_route:

        if not st.session_state.point_a_coords or not st.session_state.point_b_coords:
            st.error("Укажите обе точки маршрута.")
        else:
            try:
                profile_type = "wheelchair" if wheelchair_mode else "foot-hiking"

                ors_coords = [
                    [st.session_state.point_a_coords[1], st.session_state.point_a_coords[0]],
                    [st.session_state.point_b_coords[1], st.session_state.point_b_coords[0]]
                ]
                # для карты
                route_geo = client.directions(
                    coordinates=ors_coords,
                    profile=profile_type,
                    format="geojson"
                )

                route_json = client.directions(
                    coordinates=ors_coords,
                    profile=profile_type,
                    format="json"
                )

                st.session_state.route_geojson = route_geo
                st.session_state.route_json = route_json


            except Exception as e:

                error_details = traceback.format_exc()

                st.error("Ошибка при построении маршрута")

                with st.expander("Показать детали ошибки"):

                    st.code(error_details)

        st.session_state.auto_build_route = False

    if "add_mode" not in st.session_state:
        st.session_state.add_mode = False
    if st.session_state.add_mode:
        st.warning("Режим добавления включён. Кликните на карту.")

    add_mode = st.session_state.add_mode

    if add_mode:
        new_place_type = st.selectbox(
            "Что добавить?",
            [
                "Пандус",
                "Туалет",
                "Парковка для инвалидов",
                "Лифт",
                "Тактильная плитка",
                "Остановка",
                "Пониженный бордюр"
            ]
        )

with right_col:
    # MAP VIEW
    st.markdown("---")
    st.subheader("Карта")
    all_places = get_places()

    total_counts = {
        "ramp": 0,
        "toilet": 0,
        "disabled_parking": 0,
        "elevator": 0,
        "tactile": 0,
        "bus_stop": 0,
        "lowered_kerb": 0
    }

    for p in all_places:
        if p[3] in total_counts:
            total_counts[p[3]] += 1

    # MAP CREATING
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        control_scale=True,
        tiles=None,
        prefer_canvas=True
    )
    from folium.plugins import LocateControl

    LocateControl(
        auto_start=False,
        flyTo=True,
        keepCurrentZoomLevel=True
    ).add_to(m)

    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="© OSM",
        control=False
    ).add_to(m)

    # fade
    m.get_root().html.add_child(folium.Element("""
    <style>
    .leaflet-control-attribution {
        display: none !important;
    }
    </style>
    """))
    marker_cluster = MarkerCluster().add_to(m)
    ICON_PATH = "icons"

    icon_cache = {}

    icon_files = {
        "ramp": "ramp.png",
        "toilet": "toilet.png",
        "disabled_parking": "parking.png",
        "elevator": "elevator.png",
        "tactile": "tactile.png",
        "bus_stop": "bus.png",
        "lowered_kerb": "kerb.png",
    }

    for key, filename in icon_files.items():
        path = os.path.join(ICON_PATH, filename)
        if os.path.exists(path):
            icon_cache[key] = folium.CustomIcon(
                icon_image=path,
                icon_size=(28, 28),
                icon_anchor=(14, 28),
            )
        else:
            icon_cache[key] = folium.Icon(color="gray", icon="info-sign")
    for place in all_places:
        place_id, lat, lon, place_type, source = place

        if place_type == "ramp" and not show_ramps:
            continue
        if place_type == "toilet" and not show_wc:
            continue
        if place_type == "disabled_parking" and not show_parking:
            continue
        if place_type == "elevator" and not show_elevator:
            continue
        if place_type == "tactile" and not show_tactile:
            continue
        if place_type == "bus_stop" and not show_bus:
            continue
        if place_type == "lowered_kerb" and not show_kerb:
            continue

        if place_type == "ramp":
            color = "green"
            type_name = "Пандус"
        elif place_type == "toilet":
            color = "blue"
            type_name = "Туалет"
        elif place_type == "disabled_parking":
            color = "purple"
            type_name = "Парковка для инвалидов"
        elif place_type == "elevator":
            color = "orange"
            type_name = "Лифт"
        elif place_type == "tactile":
            color = "cadetblue"
            type_name = "Тактильная плитка"
        elif place_type == "bus_stop":
            color = "darkred"
            type_name = "Доступная остановка"
        elif place_type == "lowered_kerb":
            color = "darkgreen"
            type_name = "Пониженный бордюр"
        else:
            color = "gray"
            type_name = place_type
        icon_name = "wheelchair" if place_type == "ramp" else "info-sign"

        reviews = get_reviews_for_place(place_id)

        popup_html = f"""
        <b>ID:</b> {place_id}<br>
        <b>Тип:</b> {type_name}<br>
        <b>Источник:</b> {source}
        <br><br>
        <b>Отзывы:</b><br>
        """

        if reviews:
            for reviewer, vote, comment in reviews:
                emoji = "👍" if vote == 1 else "👎"
                popup_html += f"{reviewer}: {comment} {emoji}<br>"
        else:
            popup_html += "Пока нет отзывов"

        ICON_PATH = "icons"

        icon_config = {
            "ramp": {"file": "ramp.png", "type_name": "Пандус"},
            "toilet": {"file": "toilet.png", "type_name": "Туалет"},
            "disabled_parking": {"file": "parking.png", "type_name": "Парковка для инвалидов"},
            "elevator": {"file": "elevator.png", "type_name": "Лифт"},
            "tactile": {"file": "tactile.png", "type_name": "Тактильная плитка"},
            "bus_stop": {"file": "bus.png", "type_name": "Остановка"},
            "lowered_kerb": {"file": "kerb.png", "type_name": "Пониженный бордюр"},
        }
        custom_icon = icon_cache.get(place_type, folium.Icon(color="gray"))

        folium.Marker(
            location=[lat, lon],
            popup=popup_html,
            icon=custom_icon
        ).add_to(marker_cluster)

    # MARKERS.IMAGES BASE64

    from branca.element import MacroElement
    from jinja2 import Template

    legend = MacroElement()

    legend._template = Template(f"""
    {{% macro html(this, kwargs) %}}

    <div id="maplegend" 
         style="
         position:absolute;
         z-index:9999;
         bottom:20px;
         left:20px;
         background:#212136;
         padding:12px 15px;
         border-radius:12px;
         box-shadow:0 0 15px rgba(0,0,0,0.3);
         font-size:14px;
         min-width:200px;
    ">

    <div style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;"
         onclick="
            var content = this.nextElementSibling;
            content.style.display = content.style.display === 'none' ? 'block' : 'none';
         ">
        <b style="color:#0B5ED7;">Легенда</b>
        <span style="font-weight:bold;">⯆</span>
    </div>

    <div style="margin-top:8px;">

    <span style="color:green;">●</span> Пандусы: {total_counts['ramp']}<br>
    <span style="color:blue;">●</span> Туалеты: {total_counts['toilet']}<br>
    <span style="color:purple;">●</span> Парковки: {total_counts['disabled_parking']}<br>
    <span style="color:orange;">●</span> Лифты: {total_counts['elevator']}<br>
    <span style="color:cadetblue;">●</span> Тактильная плитка: {total_counts['tactile']}<br>
    <span style="color:darkred;">●</span> Остановки: {total_counts['bus_stop']}<br>
    <span style="color:darkgreen;">●</span> Бордюры: {total_counts['lowered_kerb']}<br>

    </div>

    </div>

    {{% endmacro %}}
    """)

    m.get_root().add_child(legend)

    if st.session_state.point_a_coords:
        folium.Marker(
            location=st.session_state.point_a_coords,
            tooltip="Пункт А (Начало маршрута)",
            icon=folium.Icon(color='green', icon='play', prefix='fa')
        ).add_to(m)

    if st.session_state.point_b_coords:
        folium.Marker(
            location=st.session_state.point_b_coords,
            tooltip="Пункт Б (Конец маршрута)",
            icon=folium.Icon(color='red', icon='stop', prefix='fa')
        ).add_to(m)

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
    if st.session_state.last_clicked_coords:
        lat_c, lon_c = st.session_state.last_clicked_coords
        folium.Marker(
            location=[lat_c, lon_c],
            tooltip="Точка клика",
            popup=f"Вы кликнули сюда: {lat_c:.4f}, {lon_c:.4f}",
            icon=folium.Icon(color='orange', icon='crosshairs', prefix='fa')
        ).add_to(m)

    # draw route
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
        returned_objects=["last_clicked"]
    )

    st.markdown("""
    <style>

    /* Обёртка карты */
    div[data-testid="stVerticalBlock"] iframe {
        border: 4px solid #0B5ED7 !important;
        border-radius: 15px !important;
        box-shadow: 0 0 20px rgba(11, 94, 215, 0.6) !important;
    }

    </style>
    """, unsafe_allow_html=True)

# MAIN STREAMLIT APP

if output and output.get("last_clicked"):

    lat_clicked = round(output["last_clicked"]["lat"], 6)
    lon_clicked = round(output["last_clicked"]["lng"], 6)
    clicked_tuple = (lat_clicked, lon_clicked)

    if st.session_state.last_clicked_coords == clicked_tuple:
        st.stop()

    st.session_state.last_clicked_coords = clicked_tuple

    if add_mode and new_place_type:
        type_mapping = {
            "Пандус": "ramp",
            "Туалет": "toilet",
            "Парковка для инвалидов": "disabled_parking",
            "Лифт": "elevator",
            "Тактильная плитка": "tactile",
            "Остановка": "bus_stop",
            "Пониженный бордюр": "lowered_kerb"
        }

        place_type_value = type_mapping.get(new_place_type)
        add_place(lat_clicked, lon_clicked, place_type_value, "user")

        st.session_state.last_added_click = clicked_tuple
        st.success("Объект добавлен!")
        st.rerun()

    if not add_mode:

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
                st.session_state.clicked_poi_info_html_text = (
                    f"Нет данных для точки {lat_clicked:.6f}, {lon_clicked:.6f}"
                )
st.markdown(f"---")
st.subheader("Информация о кликнутой точке")

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
if (
        st.session_state.route_geojson
        and st.session_state.voice_mode
        and not st.session_state.route_spoken
):
    try:
        route = st.session_state.route_geojson
        steps = route["features"][0]["properties"]["segments"][0]["steps"]

        speak_route(st.session_state.route_json)

        st.session_state.route_spoken = True
        st.session_state.voice_mode = False

    except Exception as e:
        st.error(f"Ошибка озвучки: {e}")

st.markdown("---")
if "route_audio" in st.session_state:
    st.audio(st.session_state.route_audio, format="audio/mp3")
st.markdown('<div class="bottom-bar">', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Добавить объект"):
        st.session_state.add_mode = not st.session_state.get("add_mode", False)
with col2:
    st.button("Режимы", disabled=True)

st.markdown('</div>', unsafe_allow_html=True)
