import random
import sqlite3

def add_test_data(current_user):
    conn = sqlite3.connect('reviews.db.db')
    c = conn.cursor()

    # 1. Создаем несколько меток для текущего пользователя, если их еще нет
    test_markers = [
        (55.75, 37.61, 'Пандус', 'Удобный пологий спуск у аптеки'),
        (55.76, 37.62, 'Подъемник', 'Электрический подъемник в переходе'),
        (55.74, 37.60, 'Тактильная плитка', 'Направляет к главному входу')
    ]

    for lat, lon, cat, desc in test_markers:
        c.execute("SELECT id FROM markers WHERE lat=? AND lon=? AND user=?", (lat, lon, current_user))
        if not c.fetchone():
            c.execute("INSERT INTO markers (lat, lon, category, description, user) VALUES (?, ?, ?, ?, ?)",
                      (lat, lon, cat, desc, current_user))

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
                c.execute("INSERT INTO reviews (marker_id, reviewer, vote, comment) VALUES (?, ?, ?, ?)",
                          (m_id, rev_user, vote, comment))

    conn.commit()
    conn.close()
    print("Тестовые данные успешно добавлены!")

add_test_data('cdexxx')