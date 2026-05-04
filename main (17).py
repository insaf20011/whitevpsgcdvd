import asyncio
import sqlite3
import logging
import requests
import uuid
import time
import json
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- НАСТРОЙКИ ---
API_TOKEN = '8670852675:AAGYja039C3cDeeTj6QSbUXj1CLuCtPJHEM'
ADMIN_ID = 5248344207 

# --- НАСТРОЙКИ 3X-UI ---
PANEL_URL = "http://158.160.255.26:13496"
PANEL_USER = "Q8H6jJBWiO"
PANEL_PWD = "WjqR9cSMzM"
INBOUND_ID = 1
SERVER_IP = "158.160.255.26"
PORT = 443
SNI = "ads.x5.ru"
PBK = "RfGm09DUV0Sxjos4Fhii2YAEHvIJLDuvcrZUPvrF3DM"
SID = "28"

# --- НАСТРОЙКИ PLATEGA ---
MERCHANT_ID = "6d9c1339-2026-4149-9669-3eb214abc1bf"
API_SECRET = "nCecLsqBbfLVKDSJUjJiyDkmxxqCF1Rval6M02Cy2hMq5w1QfPwrrEBzwkYy4RbseeDWBD9qN6v3Yp6hslirV6eGVwCroHHrmHkO"

# --- ТАРИФЫ ---
PRODUCTS_PLANS = {
    "1": {"name": "🚀 1 месяц", "rub": 150, "str": 200, "days": 30, "limit_gb": 15},
    "3": {"name": "⚡️ 3 месяца", "rub": 400, "str": 450, "days": 90, "limit_gb": 45},
    "12": {"name": "👑 1 год", "rub": 900, "str": 1000, "days": 365, "limit_gb": 150}
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class SupportState(StatesGroup):
    waiting_for_msg = State()
    admin_reply = State()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('vpn_database.db')
    cursor = conn.cursor()
    # Добавили is_first_buy для логики 50%
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
        (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, 
        referrer_id INTEGER, referrals_count INTEGER DEFAULT 0, total_ref_earnings REAL DEFAULT 0,
        subscription_expiry TEXT, vpn_config_link TEXT, is_first_buy INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('vpn_database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect('vpn_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)', 
                   (user_id, username, referrer_id))
    if referrer_id:
        cursor.execute('UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?', (referrer_id,))
    conn.commit()
    conn.close()

def update_subscription(user_id, days, amount_paid):
    conn = sqlite3.connect('vpn_database.db')
    cursor = conn.cursor()
    user = get_user(user_id)
    
    # Расчет даты
    now = datetime.now()
    if user['subscription_expiry']:
        try:
            current_expiry = datetime.strptime(user['subscription_expiry'], '%Y-%m-%d %H:%M:%S')
            start_date = max(now, current_expiry)
        except: start_date = now
    else: start_date = now
    new_expiry = start_date + timedelta(days=days)
    
    # Начисление реферальных (50% если первая покупка)
    if user['referrer_id']:
        percent = 0.50 if user['is_first_buy'] == 1 else 0.15
        bonus = amount_paid * percent
        cursor.execute('UPDATE users SET balance = balance + ?, total_ref_earnings = total_ref_earnings + ? WHERE user_id = ?', 
                       (bonus, bonus, user['referrer_id']))
    
    cursor.execute('UPDATE users SET subscription_expiry = ?, is_first_buy = 0 WHERE user_id = ?', 
                   (new_expiry.strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()
    return new_expiry

# --- API 3X-UI ---
async def create_vpn_client(user_id, days, limit_gb):
    login_url = f"{PANEL_URL}/login"
    async with aiohttp.ClientSession() as session:
        await session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PWD})
        client_uuid = str(uuid.uuid4())
        traffic_limit = limit_gb * 1024 * 1024 * 1024
        expiry_time = int((time.time() + (days * 86400)) * 1000)
        
        add_url = f"{PANEL_URL}/panel/api/inbounds/addClient"
        client_settings = {
            "id": client_uuid, "flow": "", "email": f"user_{user_id}",
            "limitIp": 2, "totalGB": traffic_limit, "expiryTime": expiry_time, "enable": True
        }
        payload = {"id": INBOUND_ID, "settings": json.dumps({"clients": [client_settings]})}
        
        async with session.post(add_url, data=payload) as resp:
            if resp.status == 200:
                vless_link = f"vless://{client_uuid}@{SERVER_IP}:{PORT}?type=tcp&security=reality&sni={SNI}&fp=chrome&pbk={PBK}&sid={SID}#WhiteVPN_{user_id}"
                conn = sqlite3.connect('vpn_database.db')
                conn.execute('UPDATE users SET vpn_config_link = ? WHERE user_id = ?', (vless_link, user_id))
                conn.commit()
                conn.close()
                return vless_link
    return None

def get_platega_link(amount, user_id, plan_id):
    url = "https://app.platega.io/transaction/process"
    headers = {"X-MerchantId": MERCHANT_ID, "X-Secret": API_SECRET, "Content-Type": "application/json"}
    data = {
        "paymentMethod": 2,
        "paymentDetails": {"amount": float(amount), "currency": "RUB"},
        "description": f"VPN План {plan_id}",
        "payload": f"pay_{user_id}_{plan_id}"
    }
    try:
        r = requests.post(url, headers=headers, json=data)
        return r.json().get("redirect")
    except: return None

# --- МЕНЮ ---
async def show_profile(event):
    user_id = event.from_user.id
    user = get_user(user_id)
    sub_text = "🔴 Истекла"
    date_text = "—"
    if user['subscription_expiry']:
        expiry = datetime.strptime(user['subscription_expiry'], '%Y-%m-%d %H:%M:%S')
        if expiry > datetime.now():
            diff = expiry - datetime.now()
            sub_text = f"🟢 Активна ({diff.days} дн.)"
            date_text = expiry.strftime('%d.%m.%Y')

    text = (f"👤 <b>Привет, {event.from_user.first_name}!</b>\n\n"
            f"📱 Статус: {sub_text}\n"
            f"📅 Истекает: <code>{date_text}</code>\n"
            f"💰 Баланс: <code>{user['balance']:.2f} руб.</code>\n\n"
            f"💎 <b>Выбирай лучшее качество соединения!</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📜 Соглашение", callback_data="policy"), 
                types.InlineKeyboardButton(text="🆘 Саппорт", callback_data="support"))
    builder.row(types.InlineKeyboardButton(text="🎁 Рефералка", callback_data="ref_link"), 
                types.InlineKeyboardButton(text="💳 Купить VPN", callback_data="buy_menu"))
    builder.row(types.InlineKeyboardButton(text="📲 Подключиться", callback_data="connect"))
    
    if isinstance(event, types.Message): 
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else: 
        await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject):
    if not get_user(message.from_user.id):
        ref_id = int(command.args) if command.args and command.args.isdigit() else None
        add_user(message.from_user.id, message.from_user.full_name, ref_id)
    await show_profile(message)

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for k, v in PRODUCTS_PLANS.items():
        builder.row(types.InlineKeyboardButton(text=f"{v['name']} — {v['rub']}₽", callback_data=f"plan_{k}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await callback.message.edit_text("💎 <b>Выберите ваш тарифный план:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("plan_"))
async def choose_pay(callback: types.CallbackQuery):
    plan = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Карты / СБП", callback_data=f"pay_rub_{plan}"))
    builder.row(types.InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data=f"pay_str_{plan}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_menu"))
    await callback.message.edit_text("💳 <b>Выберите метод оплаты:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery):
    _, method, plan_id = callback.data.split("_")
    plan = PRODUCTS_PLANS[plan_id]
    
    if method == "rub":
        await callback.answer("⏳ Создаю ссылку...")
        link = get_platega_link(plan['rub'], callback.from_user.id, plan_id)
        if link:
            kb = InlineKeyboardBuilder().button(text="💳 Перейти к оплате", url=link).as_markup()
            await callback.message.answer(f"📦 <b>Тариф:</b> {plan['name']}\n💵 <b>К оплате:</b> {plan['rub']}₽\n\n<i>После оплаты ключ будет выдан автоматически!</i>", reply_markup=kb, parse_mode="HTML")
        else: await callback.message.answer("❌ Ошибка платежного шлюза.")
    else:
        await callback.message.answer_invoice(
            title=f"VPN: {plan['name']}", description=f"🔥 Доступ на {plan['days']} дней ({plan['limit_gb']} ГБ)",
            payload=f"vpn_{plan_id}_{plan['rub']}", currency="XTR",
            prices=[LabeledPrice(label="Оплата", amount=plan['str'])]
        )
    await callback.answer()

@dp.pre_checkout_query()
async def checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    p = message.successful_payment.invoice_payload.split("_")
    plan_id = p[1]
    plan = PRODUCTS_PLANS[plan_id]
    
    new_expiry = update_subscription(message.from_user.id, plan['days'], int(p[2]))
    config = await create_vpn_client(message.from_user.id, plan['days'], plan['limit_gb'])
    
    await message.answer(f"🎉 <b>Успешно!</b>\n📅 Подписка до: <code>{new_expiry.strftime('%d.%m.%Y')}</code>\n\n🔑 <b>Ваш ключ:</b>\n<code>{config}</code>", parse_mode="HTML")

@dp.callback_query(F.data == "policy")
async def policy(callback: types.CallbackQuery):
    text = ("📑 <b>Юридическая информация:</b>\n\n"
            "👤 <a href='https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19'>Пользовательское соглашение</a>\n\n"
            "🔒 <a href='https://telegra.ph/Politika-konfidencialnosti-04-01-26'>Политика конфиденциальности</a>")
    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=False)
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def ref(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    
    text = (f"🎁 <b>Партнерская программа</b>\n\n"
            f"💰 Вы получаете <b>50%</b> с первой покупки друга и <b>15%</b> со всех последующих!\n\n"
            f"🔗 Ваша ссылка:\n<code>{link}</code>\n\n"
            f"👥 Приглашено: <code>{user['referrals_count']}</code> чел.\n"
            f"💸 Заработано: <code>{user['total_ref_earnings']:.2f}₽</code>")
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# --- СИСТЕМА ПОДДЕРЖКИ ---
@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("👨‍💻 <b>Напишите ваше обращение:</b>\nАдминистратор ответит вам в ближайшее время.")
    await state.set_state(SupportState.waiting_for_msg)
    await callback.answer()

@dp.message(SupportState.waiting_for_msg)
async def to_admin(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder().button(text="✉️ Ответить", callback_data=f"reply_{message.from_user.id}")
    await bot.send_message(ADMIN_ID, f"🔔 <b>Новый вопрос!</b>\nОт: {message.from_user.id}\nТекст: {message.text}", reply_markup=builder.as_markup(), parse_mode="HTML")
    await message.answer("✅ <b>Сообщение отправлено!</b> Ожидайте ответа.")
    await state.clear()

@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    user_to_reply = callback.data.split("_")[1]
    await callback.message.answer(f"✍️ Пишите ответ для пользователя <code>{user_to_reply}</code>:", parse_mode="HTML")
    await state.update_data(reply_to=user_to_reply)
    await state.set_state(SupportState.admin_reply)
    await callback.answer()

@dp.message(SupportState.admin_reply)
async def to_user_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['reply_to']
    try:
        await bot.send_message(user_id, f"📩 <b>Ответ от поддержки:</b>\n\n{message.text}", parse_mode="HTML")
        await message.answer("🚀 Ответ доставлен пользователю!")
    except:
        await message.answer("❌ Не удалось отправить (бот заблокирован?)")
    await state.clear()

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if user['vpn_config_link']:
        await callback.message.answer(f"🔌 <b>Ваш актуальный ключ:</b>\n\n<code>{user['vpn_config_link']}</code>\n\n<i>Скопируйте его и вставьте в приложение V2Ray / Shadowrocket / Nekobox</i>", parse_mode="HTML")
    else:
        await callback.message.answer("⚠️ <b>У вас нет активной подписки.</b>\nКупите тариф в меню «Карты / СБП».")
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await show_profile(callback)

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())