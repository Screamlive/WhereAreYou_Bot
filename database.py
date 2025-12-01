import sqlite3

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            fullname TEXT,
            is_approved INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0
        )
    ''')

    # Таблица отсутствий
    cur.execute('''
        CREATE TABLE IF NOT EXISTS absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            start_date TEXT,
            end_date TEXT,
            comment TEXT,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    ''')

    # Таблица логов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_time TEXT,
            user_id INTEGER,
            action TEXT
        )
    ''')

    # NEW: Таблица запросов на редактирование
    cur.execute('''
        CREATE TABLE IF NOT EXISTS edit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            abs_id INTEGER,
            new_cat TEXT,
            new_sd TEXT,
            new_ed TEXT,
            new_comment TEXT,
            user_id INTEGER
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("База данных и таблицы созданы/обновлены.")