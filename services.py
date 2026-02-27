import requests
from gigachat import GigaChat

YANDEX_API_KEY = "718eaa71-f80b-4ecf-ac89-ae7e7367bdce"
GIGACHAT_CREDENTIALS = "MDE5YWVkODctZTkxYS03YWRlLThiZDQtNDdkOTIxY2E3OWM4Ojc3MTkwYTJlLTJkMDMtNGJhMi04NTgwLWVjN2M3ZTY0OThlNA=="


def get_weather(lat=47.2248606, lon=39.7022858):
    url = f"https://api.weather.yandex.ru/v2/forecast?lat={lat}&lon={lon}"
    headers = {"X-Yandex-Weather-Key": YANDEX_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        data = response.json()

        temp = data['fact']['temp']
        condition = data['fact']['condition']

        conditions_ru = {
            "clear": "Ясно", "partly-cloudy": "Малооблачно", "cloudy": "Облачно",
            "overcast": "Пасмурно", "drizzle": "Морось", "light-rain": "Небольшой дождь",
            "rain": "Дождь", "moderate-rain": "Умеренно сильный дождь", "heavy-rain": "Сильный дождь",
            "continuous-heavy-rain": "Длительный сильный дождь", "showers": "Ливень",
            "wet-snow": "Дождь со снегом", "light-snow": "Небольшой снег", "snow": "Снег",
            "snow-showers": "Снегопад", "hail": "Град", "thunderstorm": "Гроза",
            "thunderstorm-with-rain": "Дождь с грозой", "thunderstorm-with-hail": "Гроза с градом"
        }

        return {
            "temp": temp,
            "condition": conditions_ru.get(condition, condition)
        }
    except Exception:
        return None


def get_gigachat_advice(temp, condition):
    prompt = f"Погода сейчас: {temp} градусов, {condition}. Дай короткий (1-2 предложения) совет человеку на инвалидной коляске для прогулки по городу."
    try:
        with GigaChat(credentials=GIGACHAT_CREDENTIALS, verify_ssl_certs=False) as giga:
            response = giga.chat(prompt)
            print(1)
            return response.choices[0].message.content
    except Exception:
        return "Будьте осторожны и планируйте маршрут заранее!"