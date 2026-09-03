import os
import asyncio
import random
import json
from io import StringIO

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from database import Base, Squad, Participant


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if not ADMIN_TELEGRAM_ID:
    raise RuntimeError("ADMIN_TELEGRAM_ID is not set")

if not GOOGLE_SERVICE_ACCOUNT_JSON:
    raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

if not GOOGLE_SHEET_ID:
    raise RuntimeError("GOOGLE_SHEET_ID is not set")


# ============================================================
# DATABASE URL
# ============================================================

DATABASE_URL = DATABASE_URL.strip()

# Railway/PostgreSQL may provide postgres://
# SQLAlchemy async engine needs asyncpg.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+asyncpg://",
        1,
    )

elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )


# ============================================================
# DATABASE
# ============================================================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


# ============================================================
# SQUADS
# ============================================================

SQUAD_LIMIT = 20

SQUADS = [
    {
        "name": "Squad 1",
        "link": os.getenv("SQUAD_1_LINK", ""),
    },
    {
        "name": "Squad 2",
        "link": os.getenv("SQUAD_2_LINK", ""),
    },
    {
        "name": "Squad 3",
        "link": os.getenv("SQUAD_3_LINK", ""),
    },
    {
        "name": "Squad 4",
        "link": os.getenv("SQUAD_4_LINK", ""),
    },
    {
        "name": "Squad 5",
        "link": os.getenv("SQUAD_5_LINK", ""),
    },
    {
        "name": "Squad 6",
        "link": os.getenv("SQUAD_6_LINK", ""),
    },
    {
        "name": "Squad 7",
        "link": os.getenv("SQUAD_7_LINK", ""),
    },
    {
        "name": "Squad 8",
        "link": os.getenv("SQUAD_8_LINK", ""),
    },
    {
        "name": "Squad 9",
        "link": os.getenv("SQUAD_9_LINK", ""),
    },
    {
        "name": "Squad 10",
        "link": os.getenv("SQUAD_10_LINK", ""),
    },
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


def get_google_sheets_service():
    """
    Creates Google Sheets API client from
    GOOGLE_SERVICE_ACCOUNT_JSON.
    """

    credentials_data = json.loads(
        GOOGLE_SERVICE_ACCOUNT_JSON
    )

    credentials = Credentials.from_service_account_info(
        credentials_data,
        scopes=GOOGLE_SCOPES,
    )

    service = build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )

    return service


def update_google_sheet(rows):
    """
    Completely rebuilds the Participants sheet
    from PostgreSQL data.

    This makes Google Sheets a mirror of the database.
    """

    service = get_google_sheets_service()

    values = [
        [
            "Команда",
            "Имя",
            "Фамилия",
            "Username",
            "Telegram ID",
        ]
    ]

    for row in rows:
        values.append([
            row["squad"],
            row["first_name"],
            row["last_name"],
            row["username"],
            row["telegram_id"],
        ])

    body = {
        "values": values
    }

    # Clear existing data
    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Участники!A:E",
        body={},
    ).execute()

    # Write fresh data
    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Участники!A1",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def update_google_stats(stats):
    """
    Updates the Statistics sheet.
    """

    service = get_google_sheets_service()

    values = [
        [
            "Команда",
            "Участников",
            "Свободных мест",
        ]
    ]

    for stat in stats:
        values.append([
            stat["name"],
            stat["count"],
            stat["free"],
        ])

    body = {
        "values": values
    }

    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Статистика!A:C",
        body={},
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Статистика!A1",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


async def sync_google_sheets():
    """
    Loads current PostgreSQL state and synchronizes
    both Google Sheets tabs.
    """

    async with SessionLocal() as session:

        squads_result = await session.execute(
            select(Squad).order_by(Squad.id)
        )

        squads = squads_result.scalars().all()

        participants_result = await session.execute(
            select(Participant, Squad)
            .join(Squad, Participant.squad_id == Squad.id)
            .order_by(Squad.id, Participant.id)
        )

        participant_rows = participants_result.all()

    rows = []

    for participant, squad in participant_rows:

        rows.append({
            "squad": squad.name,
            "first_name": participant.first_name or "",
            "last_name": participant.last_name or "",
            "username": (
                f"@{participant.username}"
                if participant.username
                else ""
            ),
            "telegram_id": str(participant.telegram_id),
        })

    stats = []

    for squad in squads:
        count = squad.members_count or 0

        stats.append({
            "name": squad.name,
            "count": count,
            "free": SQUAD_LIMIT - count,
        })

    # Google API is synchronous, therefore run it
    # outside the async event loop.
    await asyncio.to_thread(
        update_google_sheet,
        rows,
    )

    await asyncio.to_thread(
        update_google_stats,
        stats,
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

async def init_database():

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:

        result = await session.execute(
            select(Squad).order_by(Squad.id)
        )

        squads = result.scalars().all()

        if not squads:

            for squad_data in SQUADS:

                squad = Squad(
                    name=squad_data["name"],
                    link=squad_data["link"],
                    members_count=0,
                )

                session.add(squad)

            await session.commit()

        else:

            # Update squad names/links without resetting counts.

            for index, squad_data in enumerate(SQUADS):

                if index < len(squads):

                    squads[index].name = squad_data["name"]
                    squads[index].link = squad_data["link"]

            await session.commit()


# ============================================================
# KEYBOARD
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
# ASSIGN SQUAD
# ============================================================

async def assign_squad(
    telegram_id: int,
    first_name: str,
    last_name: str,
    username: str,
):

    async with SessionLocal() as session:

        # ----------------------------------------------------
        # Check whether user already has a squad.
        # ----------------------------------------------------

        existing_result = await session.execute(
            select(Participant)
            .where(
                Participant.telegram_id == telegram_id
            )
        )

        existing = existing_result.scalar_one_or_none()

        if existing:

            squad_result = await session.execute(
                select(Squad)
                .where(Squad.id == existing.squad_id)
            )

            squad = squad_result.scalar_one()

            return squad, False


        # ----------------------------------------------------
        # Lock squads so simultaneous requests don't
        # overfill a squad.
        # ----------------------------------------------------

        squads_result = await session.execute(
            select(Squad)
            .order_by(Squad.id)
            .with_for_update()
        )

        squads = squads_result.scalars().all()


        # ----------------------------------------------------
        # Create a list of free slots.
        #
        # Example:
        #
        # Squad 1 has 3 free places
        # Squad 2 has 10 free places
        #
        # Squad 1 appears 3 times.
        # Squad 2 appears 10 times.
        #
        # Therefore the selection is random, but every
        # squad can never exceed 20 people.
        # ----------------------------------------------------

        free_slots = []

        for squad in squads:

            free_places = (
                SQUAD_LIMIT - squad.members_count
            )

            if free_places > 0:

                for _ in range(free_places):
                    free_slots.append(squad)


        if not free_slots:
            return None, False


        selected_squad = random.choice(
            free_slots
        )


        # ----------------------------------------------------
        # Create participant.
        # ----------------------------------------------------

        participant = Participant(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            squad_id=selected_squad.id,
        )

        session.add(participant)

        selected_squad.members_count += 1

        try:

            await session.commit()

        except IntegrityError:

            # Another request assigned this user first.
            await session.rollback()

            existing_result = await session.execute(
                select(Participant)
                .where(
                    Participant.telegram_id == telegram_id
                )
            )

            existing = existing_result.scalar_one()

            squad_result = await session.execute(
                select(Squad)
                .where(
                    Squad.id == existing.squad_id
                )
            )

            selected_squad = squad_result.scalar_one()

            return selected_squad, False


        return selected_squad, True


# ============================================================
# SEND TEAM
# ============================================================

async def send_team(
    message: Message,
    squad: Squad,
):

    if squad.link:

        text = (
            f"🎉 <b>Твоя команда — {squad.name}!</b>\n\n"
            f"Переходи в свою команду:\n"
            f"{squad.link}"
        )

    else:

        text = (
            f"🎉 <b>Твоя команда — {squad.name}!</b>\n\n"
            "Ссылка на команду пока не настроена."
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
async def start_handler(message: Message):

    await message.answer(
        "Привет! 👋\n\n"
        "Нажми кнопку ниже, чтобы получить "
        "свою случайную команду.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# BUTTON
# ============================================================

@dp.callback_query(F.data == "get_squad")
async def get_squad_callback(
    callback: CallbackQuery
):

    user = callback.from_user

    squad, newly_assigned = await assign_squad(
        telegram_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        username=user.username or "",
    )

    if squad is None:

        await callback.message.answer(
            "❌ Все команды уже заполнены.",
        )

        await callback.answer()
        return


    await send_team(
        callback.message,
        squad,
    )

    await callback.answer()


    # --------------------------------------------------------
    # Synchronize Google Sheets after a NEW assignment.
    # --------------------------------------------------------

    if newly_assigned:

        try:

            await sync_google_sheets()

        except Exception as error:

            # Assignment is already safely stored in PostgreSQL.
            # Google Sheets failure must NOT break the bot.

            print(
                "Google Sheets synchronization error:",
                repr(error),
            )


# ============================================================
# /TEAM
# ============================================================

@dp.message(Command("team"))
async def team_handler(message: Message):

    user = message.from_user

    async with SessionLocal() as session:

        result = await session.execute(
            select(Participant)
            .where(
                Participant.telegram_id == user.id
            )
        )

        participant = result.scalar_one_or_none()

        if not participant:

            await message.answer(
                "У тебя пока нет команды.\n\n"
                "Нажми кнопку ниже.",
                reply_markup=main_keyboard(),
            )

            return


        squad_result = await session.execute(
            select(Squad)
            .where(
                Squad.id == participant.squad_id
            )
        )

        squad = squad_result.scalar_one()


    await send_team(
        message,
        squad,
    )


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(message: Message):

    return str(message.from_user.id) == str(
        ADMIN_TELEGRAM_ID
    )


# ============================================================
# /ADMIN
# ============================================================

@dp.message(Command("admin"))
async def admin_handler(message: Message):

    if not is_admin(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return


    async with SessionLocal() as session:

        result = await session.execute(
            select(Squad).order_by(Squad.id)
        )

        squads = result.scalars().all()


    lines = [
        "📊 <b>Статистика команд</b>",
        "",
    ]

    total = 0

    for squad in squads:

        count = squad.members_count or 0
        free = SQUAD_LIMIT - count

        total += count

        lines.append(
            f"<b>{squad.name}</b>: "
            f"{count}/{SQUAD_LIMIT} "
            f"(свободно: {free})"
        )


    lines.append("")
    lines.append(
        f"👥 Всего участников: {total}/200"
    )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# /SYNC
# ============================================================

@dp.message(Command("sync"))
async def sync_handler(message: Message):

    if not is_admin(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return


    try:

        await sync_google_sheets()

        await message.answer(
            "✅ Google Таблица синхронизирована."
        )

    except Exception as error:

        print(
            "Google Sheets synchronization error:",
            repr(error),
        )

        await message.answer(
            "❌ Не удалось синхронизировать Google Таблицу.\n"
            "Проверь настройки Google API."
        )


# ============================================================
# /RESET
# ============================================================

@dp.message(Command("reset"))
async def reset_handler(message: Message):

    if not is_admin(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return


    async with SessionLocal() as session:

        # Delete all participants.
        await session.execute(
            delete(Participant)
        )


        # Reset squad counters.
        result = await session.execute(
            select(Squad)
        )

        squads = result.scalars().all()

        for squad in squads:

            squad.members_count = 0


        await session.commit()


    # Also clear/rebuild Google Sheets.
    try:

        await sync_google_sheets()

    except Exception as error:

        print(
            "Google Sheets synchronization error:",
            repr(error),
        )


    await message.answer(
        "♻️ Распределение полностью сброшено.\n\n"
        "Все 10 команд снова пустые."
    )


# ============================================================
# /HELP
# ============================================================

@dp.message(Command("help"))
async def help_handler(message: Message):

    await message.answer(
        "ℹ️ <b>Команды</b>\n\n"
        "/start — начать\n"
        "/team — показать свою команду\n"
        "/help — помощь\n\n"
        "Администратор:\n"
        "/admin — статистика\n"
        "/sync — синхронизация Google Таблицы\n"
        "/reset — сбросить всё распределение",
        parse_mode="HTML",
    )


# ============================================================
# FALLBACK
# ============================================================

@dp.message()
async def fallback_handler(message: Message):

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

    await init_database()

    print("Database initialized.")

    # Initial synchronization.
    try:

        await sync_google_sheets()

        print("Google Sheets synchronized.")

    except Exception as error:

        print(
            "Initial Google Sheets synchronization failed:",
            repr(error),
        )

    print("Bot started.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
