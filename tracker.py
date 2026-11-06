import asyncio
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "telegram_activity.db"
SESSION_PATH = APP_DIR / "telegram_tracker_session"
POLL_SECONDS = 20

def now_utc():
    return datetime.now(timezone.utc)

def stamp(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")

def parse_stamp(value):
    return datetime.fromisoformat(value)

def db_init():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_seconds INTEGER
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            event TEXT NOT NULL,
            at TEXT NOT NULL,
            raw_status TEXT
        )""")

def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    print("=== Telegram Activity Tracker 2.0 ===")
    print("API ID и API HASH получаются на https://my.telegram.org")
    api_id = int(input("API ID: ").strip())
    api_hash = input("API HASH: ").strip()
    phone = input("Телефон своего Telegram-аккаунта (например +79990000000): ").strip()
    target = input("Username отслеживаемого аккаунта (без @): ").strip().lstrip("@")
    data = {"api_id": api_id, "api_hash": api_hash, "phone": phone, "target": target}
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def status_kind(status):
    if isinstance(status, UserStatusOnline):
        return "online", "online"
    if isinstance(status, UserStatusOffline):
        return "offline", "offline"
    if isinstance(status, UserStatusRecently):
        return "unknown", "recently"
    if isinstance(status, UserStatusLastWeek):
        return "unknown", "last_week"
    if isinstance(status, UserStatusLastMonth):
        return "unknown", "last_month"
    if status is None:
        return "unknown", "hidden_or_unavailable"
    return "unknown", type(status).__name__

def record_event(target, event, raw):
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO events(target,event,at,raw_status) VALUES(?,?,?,?)",
                   (target, event, stamp(now_utc()), raw))

def start_session(target):
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("INSERT INTO sessions(target,started_at) VALUES(?,?)",
                         (target, stamp(now_utc())))
        return cur.lastrowid

def end_session(session_id):
    end = now_utc()
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("SELECT started_at FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            seconds = max(0, int((end - parse_stamp(row[0])).total_seconds()))
            db.execute("UPDATE sessions SET ended_at=?,duration_seconds=? WHERE id=?",
                       (stamp(end), seconds, session_id))
            return seconds
    return 0

def fmt_duration(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h} ч {m} мин {s} сек"

def show_reports(target):
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""SELECT started_at,ended_at,duration_seconds FROM sessions
                             WHERE target=? ORDER BY id DESC LIMIT 100""", (target,)).fetchall()
        total7 = db.execute("""SELECT COALESCE(SUM(duration_seconds),0) FROM sessions
                               WHERE target=? AND started_at>=? AND ended_at IS NOT NULL""",
                            (target, stamp(now_utc()-timedelta(days=7)))).fetchone()[0]
        total30 = db.execute("""SELECT COALESCE(SUM(duration_seconds),0) FROM sessions
                                WHERE target=? AND started_at>=? AND ended_at IS NOT NULL""",
                             (target, stamp(now_utc()-timedelta(days=30)))).fetchone()[0]
    print("\n=== СТАТИСТИКА ===")
    print("За 7 дней:", fmt_duration(total7))
    print("За 30 дней:", fmt_duration(total30))
    print("\nПоследние сессии:")
    for r in rows:
        start = parse_stamp(r["started_at"]).astimezone().strftime("%d.%m.%Y %H:%M:%S")
        end = parse_stamp(r["ended_at"]).astimezone().strftime("%d.%m.%Y %H:%M:%S") if r["ended_at"] else "ещё онлайн"
        dur = fmt_duration(r["duration_seconds"]) if r["duration_seconds"] is not None else "в процессе"
        print(f"{start} — {end} | {dur}")
    print()

def export_csv(target):
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("""SELECT started_at,ended_at,duration_seconds FROM sessions
                             WHERE target=? ORDER BY id""", (target,)).fetchall()
    out = APP_DIR / "sessions_export.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Начало UTC", "Конец UTC", "Длительность, секунд"])
        writer.writerows(rows)
    print("CSV сохранён:", out)

async def main():
    db_init()
    cfg = load_config()
    target = cfg["target"].lstrip("@")
    client = TelegramClient(str(SESSION_PATH), int(cfg["api_id"]), cfg["api_hash"])
    await client.start(phone=cfg["phone"])
    try:
        entity = await client.get_entity(target)
    except Exception as e:
        print("Не удалось найти пользователя:", e)
        await client.disconnect()
        return

    display = getattr(entity, "username", None) or str(getattr(entity, "id", target))
    print(f"\nОтслеживание @{display}. Интервал: {POLL_SECONDS} секунд.")
    print("Команды: [R] отчёт, [E] экспорт CSV, [Q] выход.")
    print("Статус зависит от настроек приватности Telegram; скрытый статус не угадывается.\n")

    state = None
    session_id = None
    last_report = 0

    async def commands():
        nonlocal last_report
        while True:
            try:
                cmd = await asyncio.to_thread(input, "")
            except (EOFError, KeyboardInterrupt):
                cmd = "q"
            cmd = cmd.strip().lower()
            if cmd == "r":
                show_reports(target)
            elif cmd == "e":
                export_csv(target)
            elif cmd == "q":
                return
            await asyncio.sleep(0)

    command_task = asyncio.create_task(commands())
    try:
        while not command_task.done():
            try:
                fresh = await client.get_entity(target)
                current, raw = status_kind(getattr(fresh, "status", None))
                if current != state and current in ("online", "offline"):
                    local_time = now_utc().astimezone().strftime("%d.%m.%Y %H:%M:%S")
                    if current == "online":
                        session_id = start_session(target)
                        record_event(target, "online", raw)
                        print(f"[{local_time}] @{display} В СЕТИ")
                    else:
                        record_event(target, "offline", raw)
                        if session_id is not None:
                            seconds = end_session(session_id)
                            print(f"[{local_time}] @{display} ВЫШЕЛ ИЗ СЕТИ | Был онлайн: {fmt_duration(seconds)}")
                            session_id = None
                        else:
                            print(f"[{local_time}] @{display} НЕ В СЕТИ (начало сессии неизвестно)")
                    state = current
                elif current == "unknown" and state != "unknown":
                    print(f"[{now_utc().astimezone().strftime('%H:%M:%S')}] Статус скрыт/недоступен ({raw}); точное время определить нельзя.")
                    state = "unknown"
                await asyncio.sleep(POLL_SECONDS)
            except Exception as e:
                print("Ошибка проверки:", repr(e))
                await asyncio.sleep(POLL_SECONDS)
    finally:
        if session_id is not None:
            end_session(session_id)
        command_task.cancel()
        await client.disconnect()
        print("Мониторинг остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено.")
