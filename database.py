import sqlite3

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    def column_exists(table: str, column: str) -> bool:
        cur.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cur.fetchall())

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
    if not column_exists("users", "last_group_id"):
        cur.execute("ALTER TABLE users ADD COLUMN last_group_id INTEGER")

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

    # NEW: Таблица групп
    cur.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT,
            created_by INTEGER
        )
    ''')

    # NEW: Участники групп (many-to-many)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS group_memberships (
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TEXT,
            created_by INTEGER,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY(user_id) REFERENCES users(telegram_id),
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')

    # NEW: Запросы на вступление/выход из группы
    cur.execute('''
        CREATE TABLE IF NOT EXISTS group_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT,
            reviewed_at TEXT,
            requested_by INTEGER,
            reviewed_by INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id),
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')

    # NEW: Запросы на роль в группе (например, role='viewer')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS group_role_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            target_role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT,
            reviewed_at TEXT,
            requested_by INTEGER,
            reviewed_by INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id),
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')

    # NEW: Настройки уведомлений суперадминов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS superadmin_notification_prefs (
            user_id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL DEFAULT 'global',
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS superadmin_notification_groups (
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY(user_id) REFERENCES users(telegram_id),
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("База данных и таблицы созданы/обновлены.")
