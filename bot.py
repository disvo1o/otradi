import os
import asyncio
import json
import random

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


# ============================================================
# SETTINGS
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

SQUAD_LIMIT = 20
TOTAL_SQUADS = 10
TOTAL_PARTICIPANTS = SQUAD_LIMIT * TOTAL_SQUADS

PARTICIPANTS_SHEET = "Участники"
STATS_SHEET = "Статистика"


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not ADMIN_TELEGRAM_ID:
    raise RuntimeError("ADMIN_TELEGRAM_ID is not set")

if not GOOGLE_SHEET_ID:
    raise RuntimeError("GOOGLE_SHEET_ID is not set")

if not GOOGLE_SERVICE_ACCOUNT_JSON:
    raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")


# ============================================================
# SQUAD LINKS
# ============================================================

SQUADS = [
    {"name": "Squad 1", "link": os.getenv("SQUAD_1_LINK", "")},
    {"name": "Squad 2", "link": os.getenv("SQUAD_2_LINK", "")},
    {"name": "Squad 3", "link": os.getenv("SQUAD_3_LINK", "")},
    {"name": "Squad 4", "link": os.getenv("SQUAD_4_LINK", "")},
    {"name": "Squad 5", "link": os.getenv("SQUAD_5_LINK", "")},
    {"name": "Squad 6", "link": os.getenv("SQUAD_6_LINK", "")},
    {"name": "Squad 7", "link": os.getenv("SQUAD_7_LINK", "")},
    {"name": "Squad 8", "link": os.getenv("SQUAD_8_LINK", "")},
    {"name": "Squad 9", "link": os.getenv("SQUAD_9_LINK", "")},
    {"name": "Squad 10", "link": os.getenv("SQUAD_10_LINK", "")},
]


# ============================================================
# TELEGRAM
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# GOOGLE SHEETS
# ============================================================

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]


def get_google_service():
    """
    Creates Google Sheets API client.
    """

    credentials_data = json.loads(
        GOOGLE_SERVICE_ACCOUNT_JSON
    )

    credentials = Credentials.from_service_account_info(
        credentials_data,
        scopes=GOOGLE_SCOPES,
    )

    return build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )


def get_spreadsheet():
    service = get_google_service()

    return service.spreadsheets().get(
        spreadsheetId=GOOGLE_SHEET_ID
    ).execute()


def ensure_sheet_exists(sheet_name):
    """
    Creates a Google Sheets tab if it doesn't exist.

    If the tab was created by another simultaneous request,
    the "already exists" error is safely ignored.
    """

    service = get_google_service()

    spreadsheet = service.spreadsheets().get(
        spreadsheetId=GOOGLE_SHEET_ID
    ).execute()

    existing_sheets = [
        sheet["properties"]["title"]
        for sheet in spreadsheet.get("sheets", [])
    ]

    if sheet_name in existing_sheets:
        return

    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": sheet_name
                    }
                }
            }
        ]
    }

    try:

        service.spreadsheets().batchUpdate(
            spreadsheetId=GOOGLE_SHEET_ID,
            body=body,
        ).execute()

    except Exception as error:

        error_text = str(error)

        if "already exists" in error_text:
            return

        raise


def setup_google_sheets():
    """
    Creates required tabs and headers.
    """

    ensure_sheet_exists(
        PARTICIPANTS_SHEET
    )

    ensure_sheet_exists(
        STATS_SHEET
    )

    service = get_google_service()

    # --------------------------------------------------------
    # Participants headers
    # --------------------------------------------------------

    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{PARTICIPANTS_SHEET}!A1:E1",
        valueInputOption="RAW",
        body={
            "values": [
                [
                    "Команда",
                    "Имя",
                    "Фамилия",
                    "Username",
                    "Telegram ID",
                ]
            ]
        },
    ).execute()

    # --------------------------------------------------------
    # Statistics headers
    # --------------------------------------------------------

    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{STATS_SHEET}!A1:C1",
        valueInputOption="RAW",
        body={
            "values": [
                [
                    "Команда",
                    "Участников",
                    "Свободных мест",
                ]
            ]
        },
    ).execute()


def read_participants():
    """
    Reads all participants from Google Sheets.

    Returns list of dictionaries.
    """

    service = get_google_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{PARTICIPANTS_SHEET}!A2:E",
    ).execute()

    values = result.get(
        "values",
        []
    )

    participants = []

    for row in values:

        row = row + [""] * (
            5 - len(row)
        )

        participants.append({
            "squad": row[0],
            "first_name": row[1],
            "last_name": row[2],
            "username": row[3],
            "telegram_id": str(row[4]),
        })

    return participants


def clear_participants_sheet():
    """
    Clears participant data, leaving the header.
    """

    service = get_google_service()

    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{PARTICIPANTS_SHEET}!A2:E",
        body={},
    ).execute()


def write_participants(participants):
    """
    Completely rewrites participant table.
    """

    service = get_google_service()

    values = []

    for participant in participants:

        values.append([
            participant["squad"],
            participant["first_name"],
            participant["last_name"],
            participant["username"],
            participant["telegram_id"],
        ])

    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{PARTICIPANTS_SHEET}!A2:E",
        body={},
    ).execute()

    if not values:
        return

    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{PARTICIPANTS_SHEET}!A2",
        valueInputOption="RAW",
        body={
            "values": values
        },
    ).execute()


def write_statistics(participants):
    """
    Rebuilds statistics sheet.
    """

    service = get_google_service()

    counts = {
        squad["name"]: 0
        for squad in SQUADS
    }

    for participant in participants:

        squad_name = participant["squad"]

        if squad_name in counts:
            counts[squad_name] += 1

    values = []

    for squad in SQUADS:

        name = squad["name"]
        count = counts[name]
        free = SQUAD_LIMIT - count

        values.append([
            name,
            count,
            free,
        ])

    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{STATS_SHEET}!A2:C",
        body={},
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{STATS_SHEET}!A2",
        valueInputOption="RAW",
        body={
            "values": values
        },
    ).execute()


def sync_statistics(participants):
    write_statistics(participants)


# ============================================================
# ASYNC GOOGLE SHEETS HELPERS
# ============================================================

async def async_read_participants():

    return await asyncio.to_thread(
        read_participants
    )


async def async_write_participants(
    participants
):

    await asyncio.to_thread(
        write_participants,
        participants,
    )


async def async_write_statistics(
    participants
):

    await asyncio.to_thread(
        write_statistics,
        participants,
    )


async def async_setup_sheets():

    await asyncio.to_thread(
        setup_google_sheets
    )


# ============================================================
# ASSIGNMENT LOCK
# ============================================================

assignment_lock = asyncio.Lock()


# ============================================================
# FIND USER
# ============================================================

def find_user(
    participants,
    telegram_id
):

    telegram_id = str(
        telegram_id
    )

    for participant in participants:

        if str(
            participant["telegram_id"]
        ) == telegram_id:

            return participant

    return None


# ============================================================
# ASSIGN SQUAD
# ============================================================

async def assign_squad(
    telegram_id,
    first_name,
    last_name,
    username,
):

    async with assignment_lock:

        participants = (
            await async_read_participants()
        )

        # ----------------------------------------------------
        # Check if user already has a squad
        # ----------------------------------------------------

        existing = find_user(
            participants,
            telegram_id,
        )

        if existing:

            for squad in SQUADS:

                if squad["name"] == existing["squad"]:

                    return squad, False

            return None, False

        # ----------------------------------------------------
        # Count participants in each squad
        # ----------------------------------------------------

        counts = {
            squad["name"]: 0
            for squad in SQUADS
        }

        for participant in participants:

            squad_name = participant["squad"]

            if squad_name in counts:
                counts[squad_name] += 1

        # ----------------------------------------------------
        # Check total capacity
        # ----------------------------------------------------

        if len(participants) >= TOTAL_PARTICIPANTS:

            return None, False

        # ----------------------------------------------------
        # Weighted random selection
        #
        # Every free place is one ticket.
        #
        # Example:
        #
        # Squad 1 has 20 free places
        # Squad 2 has 10 free places
        #
        # Squad 1 gets twice the probability.
        #
        # This keeps assignment random while guaranteeing
        # that no squad can exceed 20 participants.
        # ----------------------------------------------------

        free_slots = []

        for squad in SQUADS:

            count = counts[
                squad["name"]
            ]

            free_places = (
                SQUAD_LIMIT - count
            )

            for _ in range(free_places):

                free_slots.append(
                    squad["name"]
                )

        if not free_slots:

            return None, False

        selected_name = random.choice(
            free_slots
        )

        selected_squad = None

        for squad in SQUADS:

            if squad["name"] == selected_name:

                selected_squad = squad
                break

        if selected_squad is None:

            return None, False

        # ----------------------------------------------------
        # Save participant
        # ----------------------------------------------------

        participant = {
            "squad": selected_squad["name"],
            "first_name": first_name or "",
            "last_name": last_name or "",
            "username": (
                f"@{username}"
                if username
                else ""
            ),
            "telegram_id": str(
                telegram_id
            ),
        }

        participants.append(
            participant
        )

        await async_write_participants(
            participants
        )

        await async_write_statistics(
            participants
        )

        return selected_squad, True


# ============================================================
# MAIN KEYBOARD
# ============================================================

def main_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎲 Получить свою команду",
                    callback_data="get_squad",
                )
            ]
        ]
    )


# ============================================================
# SEND TEAM
# ============================================================

async def send_team(
    message: Message,
    squad,
):

    if squad["link"]:

        text = (
            f"🎉 <b>Твоя команда — "
            f"{squad['name']}!</b>\n\n"
            f"Переходи в свою команду:\n"
            f"{squad['link']}"
        )

    else:

        text = (
            f"🎉 <b>Твоя команда — "
            f"{squad['name']}!</b>\n\n"
            "⚠️ Ссылка на эту команду "
            "пока не настроена."
        )

    await message.answer(
        text,
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# /START
# ============================================================

@dp.message(Command("start"))
async def start_handler(
    message: Message
):

    await message.answer(
        "Привет! 👋\n\n"
        "Нажми кнопку ниже, чтобы получить "
        "свою случайную команду.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# GET SQUAD BUTTON
# ============================================================

@dp.callback_query(
    F.data == "get_squad"
)
async def get_squad_callback(
    callback: CallbackQuery,
):

    user = callback.from_user

    try:

        squad, newly_assigned = (
            await assign_squad(
                telegram_id=user.id,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                username=user.username or "",
            )
        )

    except Exception as error:

        print(
            "Assignment error:",
            repr(error),
        )

        await callback.message.answer(
            "❌ Произошла ошибка. "
            "Попробуй ещё раз через несколько секунд."
        )

        await callback.answer()

        return

    if squad is None:

        await callback.message.answer(
            "❌ Все команды уже заполнены.\n\n"
            "Всего мест: 200."
        )

        await callback.answer()

        return

    await send_team(
        callback.message,
        squad,
    )

    await callback.answer()


# ============================================================
# /TEAM
# ============================================================

@dp.message(Command("team"))
async def team_handler(
    message: Message
):

    user = message.from_user

    try:

        participants = (
            await async_read_participants()
        )

    except Exception as error:

        print(
            "Read participants error:",
            repr(error),
        )

        await message.answer(
            "❌ Не удалось получить данные. "
            "Попробуй ещё раз."
        )

        return

    participant = find_user(
        participants,
        user.id,
    )

    if not participant:

        await message.answer(
            "У тебя пока нет команды.\n\n"
            "Нажми кнопку ниже.",
            reply_markup=main_keyboard(),
        )

        return

    squad = None

    for item in SQUADS:

        if item["name"] == participant["squad"]:

            squad = item
            break

    if squad is None:

        await message.answer(
            "❌ Не удалось найти твою команду."
        )

        return

    await send_team(
        message,
        squad,
    )


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(
    message: Message
):

    return str(
        message.from_user.id
    ) == str(
        ADMIN_TELEGRAM_ID
    )


# ============================================================
# /ADMIN
# ============================================================

@dp.message(Command("admin"))
async def admin_handler(
    message: Message
):

    if not is_admin(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return

    try:

        participants = (
            await async_read_participants()
        )

    except Exception as error:

        print(
            "Admin read error:",
            repr(error),
        )

        await message.answer(
            "❌ Не удалось прочитать "
            "Google Таблицу."
        )

        return

    counts = {
        squad["name"]: 0
        for squad in SQUADS
    }

    for participant in participants:

        if participant["squad"] in counts:

            counts[
                participant["squad"]
            ] += 1

    lines = [
        "📊 <b>Статистика команд</b>",
        "",
    ]

    for squad in SQUADS:

        name = squad["name"]
        count = counts[name]
        free = SQUAD_LIMIT - count

        lines.append(
            f"<b>{name}</b>: "
            f"{count}/{SQUAD_LIMIT} "
            f"(свободно: {free})"
        )

    lines.extend([
        "",
        f"👥 Всего: "
        f"{len(participants)}/"
        f"{TOTAL_PARTICIPANTS}",
    ])

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# /SYNC
# ============================================================

@dp.message(Command("sync"))
async def sync_handler(
    message: Message
):

    if not is_admin(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return

    try:

        participants = (
            await async_read_participants()
        )

        await async_write_statistics(
            participants
        )

        await message.answer(
            "✅ Статистика Google Таблицы "
            "обновлена."
        )

    except Exception as error:

        print(
            "Sync error:",
            repr(error),
        )

        await message.answer(
            "❌ Ошибка синхронизации "
            "Google Таблицы."
        )


# ============================================================
# /RESET
# ============================================================

@dp.message(Command("reset"))
async def reset_handler(
    message: Message
):

    if not is_admin(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return

    async with assignment_lock:

        try:

            participants = []

            await async_write_participants(
                participants
            )

            await async_write_statistics(
                participants
            )

        except Exception as error:

            print(
                "Reset error:",
                repr(error),
            )

            await message.answer(
                "❌ Не удалось выполнить сброс."
            )

            return

    await message.answer(
        "♻️ Распределение полностью сброшено.\n\n"
        "Все 10 команд снова пустые.\n"
        "Доступно 200 мест."
    )


# ============================================================
# /HELP
# ============================================================

@dp.message(Command("help"))
async def help_handler(
    message: Message
):

    text = (
        "ℹ️ <b>Команды</b>\n\n"
        "/start — начать\n"
        "/team — показать свою команду\n"
        "/help — помощь\n\n"
    )

    if is_admin(message):

        text += (
            "<b>Администратор:</b>\n"
            "/admin — статистика\n"
            "/sync — обновить статистику\n"
            "/reset — сбросить распределение"
        )

    await message.answer(
        text,
        parse_mode="HTML",
    )


# ============================================================
# FALLBACK
# ============================================================

@dp.message()
async def fallback_handler(
    message: Message
):

    await message.answer(
        "Нажми кнопку ниже, чтобы получить "
        "свою команду 👇",
        reply_markup=main_keyboard(),
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    print("Starting bot...")

    try:

        await async_setup_sheets()

        print("Google Sheets ready.")

    except Exception as error:

        print(
            "Google Sheets setup error:",
            repr(error),
        )

        raise

    print("Bot started.")

    await dp.start_polling(bot)


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    asyncio.run(main())
