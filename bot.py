import logging
import asyncio
import aiosqlite
import requests
import uuid
import time
import json
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# Настройка логирования для этого модуля
logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ ---
API_TOKEN = '8670852675:AAGYja039C3cDeeTj6QSbUXj1CLuCtPJHEM'[cite: 1]
ADMIN_ID = 5248344207[cite: 1]
DB_NAME = 'vpn_database.db'

# --- НАСТРОЙКИ 3X-UI ---
PANEL_URL = "http://158.160.255.26:13496"[cite: 1]
PANEL_USER = "Q8H6jJBWiO"[cite: 1]
PANEL_PWD = "WjqR9cSMzM"[cite: 1]
INBOUND_ID = 1[cite: 1]
SERVER_IP = "158.160.255.26"[cite: 1]
PORT = 443[cite: 1]
SNI = "ads.x5.ru"[cite: 1]
PBK = "RfGm09DUV0Sxjos4Fhii2YAEHvIJLDuvcrZUPvrF3DM"[cite: 1]
SID = "28"[cite: 1]

# --- НАСТРОЙКИ PLATEGA ---
MERCHANT_ID = "6d9c1339-2026-4149-9669-3eb214abc1bf"[cite: 1]
API_SECRET = "nCecLsqBbfLVKDSJUjJiyDkmxxqCF1Rval6M02Cy2hMq5w1QfPwrrEBzwkYy4RbseeDWBD9qN6v3Yp6hslirV6eGVwCroHHrmHkO"[cite: 1]

# --- ТАРИФЫ ---
PRODUCTS_PLANS = {
    "1": {"name": "🚀 1 месяц", "rub": 150, "str": 200, "days": 30, "limit_gb": 15},[cite: 1]
    "3": {"name": "⚡️ 3 месяца", "rub": 400, "str": 450, "days": 90, "limit_gb": 45},[cite: 1]
    "12": {"name": "👑 1 год", "rub": 900, "str": 1000, "days": 365, "limit_gb": 150}[cite: 1]
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class SupportState(StatesGroup):
    waiting_for_msg = State()
    admin_reply = State()

# --- АСИНХРОННАЯ БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
            (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, 
            referrer_id INTEGER, referrals_count INTEGER DEFAULT 0, total_ref_earnings REAL DEFAULT 0,
            subscription_expiry TEXT, vpn_config_link TEXT, is_first_buy INTEGER DEFAULT 1)''')[cite: 1]
        await db.commit()
        logger.info("База данных инициализирована.")

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id, username, referrer_id=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)', 
                       (user_id, username, referrer_id))
        if referrer_id:
            await db.execute('UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?', (referrer_id,))[cite: 1]
            logger.info(f"Юзеру {referrer_id} добавлен новый реферал {user_id}.")
        await db.commit()

async def update_subscription(user_id, days, amount_paid):
    user = await get_user(user_id)
    now = datetime.now()
    
    if user['subscription_expiry']:
        try:
            current_expiry = datetime.strptime(user['subscription_expiry'], '%Y-%m-%d %H:%M:%S')
            start_date = max(now, current_expiry)
        except Exception as e:
            logger.warning(f"Ошибка парсинга даты для {user_id}: {e}. Используем текущее время.")
            start_date = now
    else: 
        start_date = now
    
    new_expiry = start_date + timedelta(days=days)
    
    async with aiosqlite.connect(DB_NAME) as db:
        if user['referrer_id']:
            percent = 0.50 if user['is_first_buy'] == 1 else 0.15[cite: 1]
            bonus = amount_paid * percent
            await db.execute('UPDATE users SET balance = balance + ?, total_ref_earnings = total_ref_earnings + ? WHERE user_id = ?', 
                           (bonus, bonus, user['referrer_id']))[cite: 1]
            logger.info(f"Начислен реф. бонус {bonus} руб. рефереру {user['referrer_id']}.")
        
        await db.execute('UPDATE users SET subscription_expiry = ?, is_first_buy = 0 WHERE user_id = ?', 
                       (new_expiry.strftime('%Y-%m-%d %H:%M:%S'), user_id))[cite: 1]
        await db.commit()
        
    logger.info(f"Подписка юзера {user_id} обновлена до {new_expiry}.")
    return new_expiry

# --- API 3X-UI ---
async def create_vpn_client(user_id, days, limit_gb):
    login_url = f"{PANEL_URL}/login"[cite: 1]
    logger.info(f"Создание VPN конфига для {user_id}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            login_resp = await session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PWD})
            if login_resp.status != 200:
                logger.error("Ошибка авторизации в 3x-ui!")
                return None

            client_uuid = str(uuid.uuid4())
            traffic_limit = limit_gb * 1024 * 1024 * 1024[cite: 1]
            expiry_time = int((time.time() + (days * 86400)) * 1000)[cite: 1]
            
            add_url = f"{PANEL_URL}/panel/api/inbounds/addClient"[cite: 1]
            client_settings = {
                "id": client_uuid, "flow": "", "email": f"user_{user_id}",
                "limitIp": 2, "totalGB": traffic_limit, "expiryTime": expiry_time, "enable": True[cite: 1]
            }
            payload = {"id": INBOUND_ID, "settings": json.dumps({"clients": [client_settings]})}[cite: 1]
            
            async with session.post(add_url, data=payload) as resp:
                if resp.status == 200:
                    vless_link = f"vless://{client_uuid}@{SERVER_IP}:{PORT}?type=tcp&security=reality&sni={SNI}&fp=chrome&pbk={PBK}&sid={SID}#WhiteVPN_{user_id}"[cite: 1]
                    async with aiosqlite.connect(DB_NAME) as db:
                        await db.execute('UPDATE users SET vpn_config_link = ? WHERE user_id = ?', (vless_link, user_id))
                        await db.commit()
                    logger.info(f"Конфиг для {user_id} успешно создан.")
                    return vless_link
                else:
                    logger.error(f"Ошибка создания клиента в панели: {await resp.text()}")
    except Exception as e:
        logger.error(f"Исключение при создании VPN: {e}")
    return None

def get_platega_link(amount, user_id, plan_id):
    url = "https://app.platega.io/transaction/process"[cite: 1]
    headers = {"X-MerchantId": MERCHANT_ID, "X-Secret": API_SECRET, "Content-Type": "application/json"}[cite: 1]
    data = {
        "paymentMethod": 2,[cite: 1]
        "paymentDetails": {"amount": float(amount), "currency": "RUB"},[cite: 1]
        "description": f"VPN План {plan_id}",[cite: 1]
        "payload": f"pay_{user_id}_{plan_id}"[cite: 1]
    }
    try:
        r = requests.post(url, headers=headers, json=data)
        r.raise_for_status()
        return r.json().get("redirect")[cite: 1]
    except Exception as e:
        logger.error(f"Ошибка Platega API: {e}")
        return None

# --- ОБРАБОТЧИКИ БОТА ---
async def show_profile(event):
    user_id = event.from_user.id
    user = await get_user(user_id)
    sub_text, date_text = "🔴 Истекла", "—"[cite: 1]
    
    if user['subscription_expiry']:
        expiry = datetime.strptime(user['subscription_expiry'], '%Y-%m-%d %H:%M:%S')
        if expiry > datetime.now():
            diff = expiry - datetime.now()
            sub_text, date_text = f"🟢 Активна ({diff.days} дн.)", expiry.strftime('%d.%m.%Y')[cite: 1]

    text = (f"👤 <b>Привет, {event.from_user.first_name}!</b>\n\n"
            f"📱 Статус: {sub_text}\n"
            f"📅 Истекает: <code>{date_text}</code>\n"
            f"💰 Баланс: <code>{user['balance']:.2f} руб.</code>\n\n"
            f"💎 <b>Выбирай лучшее качество соединения!</b>")[cite: 1]
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📜 Соглашение", callback_data="policy"), types.InlineKeyboardButton(text="🆘 Саппорт", callback_data="support"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="🎁 Рефералка", callback_data="ref_link"), types.InlineKeyboardButton(text="💳 Купить VPN", callback_data="buy_menu"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="📲 Подключиться", callback_data="connect"))[cite: 1]
    
    kb = builder.as_markup()
    if isinstance(event, types.Message): 
        await event.answer(text, reply_markup=kb, parse_mode="HTML")[cite: 1]
    else: 
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")[cite: 1]

@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject):
    if not await get_user(message.from_user.id):
        ref_id = int(command.args) if command.args and command.args.isdigit() else None
        await add_user(message.from_user.id, message.from_user.full_name, ref_id)
        logger.info(f"Новый пользователь {message.from_user.id} зарегистрирован.")
    await show_profile(message)

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for k, v in PRODUCTS_PLANS.items(): 
        builder.row(types.InlineKeyboardButton(text=f"{v['name']} — {v['rub']}₽", callback_data=f"plan_{k}"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await callback.message.edit_text("💎 <b>Выберите ваш тарифный план:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")[cite: 1]

@dp.callback_query(F.data.startswith("plan_"))
async def choose_pay(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Карты / СБП", callback_data=f"pay_rub_{plan_id}"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data=f"pay_str_{plan_id}"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_menu"))
    await callback.message.edit_text("💳 <b>Выберите метод оплаты:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")[cite: 1]

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery):
    _, method, plan_id = callback.data.split("_")
    plan = PRODUCTS_PLANS[plan_id]
    
    if method == "rub":
        await callback.answer("⏳ Создаю ссылку...")
        link = get_platega_link(plan['rub'], callback.from_user.id, plan_id)
        if link: 
            await callback.message.answer(f"📦 <b>Тариф:</b> {plan['name']}\n💵 <b>К оплате:</b> {plan['rub']}₽\n\n<i>После оплаты ключ будет выдан автоматически!</i>", reply_markup=InlineKeyboardBuilder().button(text="💳 Перейти к оплате", url=link).as_markup(), parse_mode="HTML")[cite: 1]
            logger.info(f"Сгенерирована ссылка Platega для {callback.from_user.id} на сумму {plan['rub']} руб.")
        else: 
            await callback.message.answer("❌ Ошибка платежного шлюза.")
    else: 
        await callback.message.answer_invoice(title=f"VPN: {plan['name']}", description=f"🔥 Доступ на {plan['days']} дней ({plan['limit_gb']} ГБ)", payload=f"vpn_{plan_id}_{plan['rub']}", currency="XTR", prices=[LabeledPrice(label="Оплата", amount=plan['str'])])[cite: 1]
        logger.info(f"Сгенерирован инвойс Stars для {callback.from_user.id}")
    await callback.answer()

@dp.pre_checkout_query()
async def checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    p = message.successful_payment.invoice_payload.split("_")
    plan = PRODUCTS_PLANS[p[1]]
    
    logger.info(f"Успешная оплата Stars от {message.from_user.id} за тариф {p[1]}")
    new_expiry = await update_subscription(message.from_user.id, plan['days'], int(p[2]))
    config = await create_vpn_client(message.from_user.id, plan['days'], plan['limit_gb'])
    
    await message.answer(f"🎉 <b>Успешно!</b>\n📅 Подписка до: <code>{new_expiry.strftime('%d.%m.%Y')}</code>\n\n🔑 <b>Ваш ключ:</b>\n<code>{config}</code>", parse_mode="HTML")[cite: 1]

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user['vpn_config_link']: 
        await callback.message.answer(f"🔌 <b>Ваш актуальный ключ:</b>\n\n<code>{user['vpn_config_link']}</code>\n\n<i>Скопируйте его и вставьте в приложение V2Ray / Shadowrocket / Nekobox</i>", parse_mode="HTML")[cite: 1]
    else: 
        await callback.message.answer("⚠️ <b>У вас нет активной подписки.</b>\nКупите тариф в меню «Карты / СБП».")[cite: 1]
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def ref(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    
    text = (f"🎁 <b>Партнерская программа</b>\n\n"
            f"💰 Вы получаете <b>50%</b> с первой покупки друга и <b>15%</b> со всех последующих!\n\n"
            f"🔗 Ваша ссылка:\n<code>{link}</code>\n\n"
            f"👥 Приглашено: <code>{user['referrals_count']}</code> чел.\n"
            f"💸 Заработано: <code>{user['total_ref_earnings']:.2f}₽</code>")[cite: 1]
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery): 
    await show_profile(callback)