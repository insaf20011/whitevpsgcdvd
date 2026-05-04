import asyncio
import aiosqlite
import logging
import requests
import uuid
import time
import json
import aiohttp
import uvicorn
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

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

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
app = FastAPI()

class SupportState(StatesGroup):
    waiting_for_msg = State()
    admin_reply = State()

# --- АСИНХРОННАЯ БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:[cite: 1]
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
            (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, 
            referrer_id INTEGER, referrals_count INTEGER DEFAULT 0, total_ref_earnings REAL DEFAULT 0,
            subscription_expiry TEXT, vpn_config_link TEXT, is_first_buy INTEGER DEFAULT 1)''')[cite: 1]
        await db.commit()[cite: 1]

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:[cite: 1]
        db.row_factory = aiosqlite.Row[cite: 1]
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:[cite: 1]
            return await cursor.fetchone()[cite: 1]

async def add_user(user_id, username, referrer_id=None):
    async with aiosqlite.connect(DB_NAME) as db:[cite: 1]
        await db.execute('INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)', 
                       (user_id, username, referrer_id))[cite: 1]
        if referrer_id:
            await db.execute('UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?', (referrer_id,))[cite: 1]
        await db.commit()[cite: 1]

async def update_subscription(user_id, days, amount_paid):
    user = await get_user(user_id)[cite: 1]
    now = datetime.now()[cite: 1]
    
    if user['subscription_expiry']:[cite: 1]
        try:
            current_expiry = datetime.strptime(user['subscription_expiry'], '%Y-%m-%d %H:%M:%S')[cite: 1]
            start_date = max(now, current_expiry)[cite: 1]
        except: start_date = now[cite: 1]
    else: start_date = now[cite: 1]
    
    new_expiry = start_date + timedelta(days=days)[cite: 1]
    
    async with aiosqlite.connect(DB_NAME) as db:[cite: 1]
        if user['referrer_id']:[cite: 1]
            percent = 0.50 if user['is_first_buy'] == 1 else 0.15[cite: 1]
            bonus = amount_paid * percent[cite: 1]
            await db.execute('UPDATE users SET balance = balance + ?, total_ref_earnings = total_ref_earnings + ? WHERE user_id = ?', 
                           (bonus, bonus, user['referrer_id']))[cite: 1]
        
        await db.execute('UPDATE users SET subscription_expiry = ?, is_first_buy = 0 WHERE user_id = ?', 
                       (new_expiry.strftime('%Y-%m-%d %H:%M:%S'), user_id))[cite: 1]
        await db.commit()[cite: 1]
    return new_expiry

# --- API 3X-UI ---
async def create_vpn_client(user_id, days, limit_gb):
    login_url = f"{PANEL_URL}/login"[cite: 1]
    async with aiohttp.ClientSession() as session:
        await session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PWD})[cite: 1]
        client_uuid = str(uuid.uuid4())[cite: 1]
        traffic_limit = limit_gb * 1024 * 1024 * 1024[cite: 1]
        expiry_time = int((time.time() + (days * 86400)) * 1000)[cite: 1]
        
        add_url = f"{PANEL_URL}/panel/api/inbounds/addClient"[cite: 1]
        client_settings = {
            "id": client_uuid, "flow": "", "email": f"user_{user_id}",[cite: 1]
            "limitIp": 2, "totalGB": traffic_limit, "expiryTime": expiry_time, "enable": True[cite: 1]
        }
        payload = {"id": INBOUND_ID, "settings": json.dumps({"clients": [client_settings]})}[cite: 1]
        
        async with session.post(add_url, data=payload) as resp:
            if resp.status == 200:
                vless_link = f"vless://{client_uuid}@{SERVER_IP}:{PORT}?type=tcp&security=reality&sni={SNI}&fp=chrome&pbk={PBK}&sid={SID}#WhiteVPN_{user_id}"[cite: 1]
                async with aiosqlite.connect(DB_NAME) as db:[cite: 1]
                    await db.execute('UPDATE users SET vpn_config_link = ? WHERE user_id = ?', (vless_link, user_id))[cite: 1]
                    await db.commit()[cite: 1]
                return vless_link
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
        r = requests.post(url, headers=headers, json=data)[cite: 1]
        return r.json().get("redirect")[cite: 1]
    except: return None

# --- FASTAPI WEBHOOK ---
@app.post("/webhook/platega")
async def platega_webhook(request: Request):
    data = await request.json()
    if data.get("status") == "completed":
        payload = data.get("payload", "")
        if payload.startswith("pay_"):
            try:
                _, user_id, plan_id = payload.split("_")
                user_id = int(user_id)
                plan = PRODUCTS_PLANS.get(plan_id)
                if plan:
                    new_expiry = await update_subscription(user_id, plan['days'], float(data.get("amount", 0)))
                    config = await create_vpn_client(user_id, plan['days'], plan['limit_gb'])
                    await bot.send_message(user_id, f"✅ <b>Оплата через Platega получена!</b>\n📅 Подписка продлена до: <code>{new_expiry.strftime('%d.%m.%Y')}</code>\n\n🔑 <b>Ваш ключ:</b>\n<code>{config}</code>", parse_mode="HTML")
                    return {"status": "ok"}
            except Exception as e:
                logging.error(f"Webhook error: {e}")
    return {"status": "ignored"}

# --- ОБРАБОТЧИКИ БОТА ---
async def show_profile(event):
    user_id = event.from_user.id[cite: 1]
    user = await get_user(user_id)[cite: 1]
    sub_text, date_text = "🔴 Истекла", "—"[cite: 1]
    
    if user['subscription_expiry']:[cite: 1]
        expiry = datetime.strptime(user['subscription_expiry'], '%Y-%m-%d %H:%M:%S')[cite: 1]
        if expiry > datetime.now():[cite: 1]
            diff = expiry - datetime.now()[cite: 1]
            sub_text, date_text = f"🟢 Активна ({diff.days} дн.)", expiry.strftime('%d.%m.%Y')[cite: 1]

    text = (f"👤 <b>Привет, {event.from_user.first_name}!</b>\n\n"
            f"📱 Статус: {sub_text}\n"
            f"📅 Истекает: <code>{date_text}</code>\n"
            f"💰 Баланс: <code>{user['balance']:.2f} руб.</code>\n\n"
            f"💎 <b>Выбирай лучшее качество соединения!</b>")[cite: 1]
    
    builder = InlineKeyboardBuilder()[cite: 1]
    builder.row(types.InlineKeyboardButton(text="📜 Соглашение", callback_data="policy"), types.InlineKeyboardButton(text="🆘 Саппорт", callback_data="support"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="🎁 Рефералка", callback_data="ref_link"), types.InlineKeyboardButton(text="💳 Купить VPN", callback_data="buy_menu"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="📲 Подключиться", callback_data="connect"))[cite: 1]
    
    kb = builder.as_markup()[cite: 1]
    if isinstance(event, types.Message): await event.answer(text, reply_markup=kb, parse_mode="HTML")[cite: 1]
    else: await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")[cite: 1]

@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject):
    if not await get_user(message.from_user.id):[cite: 1]
        ref_id = int(command.args) if command.args and command.args.isdigit() else None[cite: 1]
        await add_user(message.from_user.id, message.from_user.full_name, ref_id)[cite: 1]
    await show_profile(message)[cite: 1]

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()[cite: 1]
    for k, v in PRODUCTS_PLANS.items(): builder.row(types.InlineKeyboardButton(text=f"{v['name']} — {v['rub']}₽", callback_data=f"plan_{k}"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))[cite: 1]
    await callback.message.edit_text("💎 <b>Выберите ваш тарифный план:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")[cite: 1]

@dp.callback_query(F.data.startswith("plan_"))
async def choose_pay(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1][cite: 1]
    builder = InlineKeyboardBuilder()[cite: 1]
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Карты / СБП", callback_data=f"pay_rub_{plan_id}"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data=f"pay_str_{plan_id}"))[cite: 1]
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_menu"))[cite: 1]
    await callback.message.edit_text("💳 <b>Выберите метод оплаты:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")[cite: 1]

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery):
    _, method, plan_id = callback.data.split("_")[cite: 1]
    plan = PRODUCTS_PLANS[plan_id][cite: 1]
    if method == "rub":[cite: 1]
        await callback.answer("⏳ Создаю ссылку...")[cite: 1]
        link = get_platega_link(plan['rub'], callback.from_user.id, plan_id)[cite: 1]
        if link: await callback.message.answer(f"📦 <b>Тариф:</b> {plan['name']}\n💵 <b>К оплате:</b> {plan['rub']}₽\n\n<i>После оплаты ключ будет выдан автоматически!</i>", reply_markup=InlineKeyboardBuilder().button(text="💳 Перейти к оплате", url=link).as_markup(), parse_mode="HTML")[cite: 1]
        else: await callback.message.answer("❌ Ошибка платежного шлюза.")[cite: 1]
    else: await callback.message.answer_invoice(title=f"VPN: {plan['name']}", description=f"🔥 Доступ на {plan['days']} дней ({plan['limit_gb']} ГБ)", payload=f"vpn_{plan_id}_{plan['rub']}", currency="XTR", prices=[LabeledPrice(label="Оплата", amount=plan['str'])])[cite: 1]
    await callback.answer()[cite: 1]

@dp.pre_checkout_query()
async def checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)[cite: 1]

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    p = message.successful_payment.invoice_payload.split("_")[cite: 1]
    plan = PRODUCTS_PLANS[p[1]][cite: 1]
    new_expiry = await update_subscription(message.from_user.id, plan['days'], int(p[2]))[cite: 1]
    config = await create_vpn_client(message.from_user.id, plan['days'], plan['limit_gb'])[cite: 1]
    await message.answer(f"🎉 <b>Успешно!</b>\n📅 Подписка до: <code>{new_expiry.strftime('%d.%m.%Y')}</code>\n\n🔑 <b>Ваш ключ:</b>\n<code>{config}</code>", parse_mode="HTML")[cite: 1]

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)[cite: 1]
    if user['vpn_config_link']: await callback.message.answer(f"🔌 <b>Ваш актуальный ключ:</b>\n\n<code>{user['vpn_config_link']}</code>\n\n<i>Скопируйте его и вставьте в приложение V2Ray / Shadowrocket / Nekobox</i>", parse_mode="HTML")[cite: 1]
    else: await callback.message.answer("⚠️ <b>У вас нет активной подписки.</b>\nКупите тариф в меню «Карты / СБП».")[cite: 1]
    await callback.answer()[cite: 1]

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery): await show_profile(callback)[cite: 1]

# --- ЗАПУСК ---
async def main():
    await init_db()[cite: 1]
    asyncio.create_task(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000)).serve())
    await bot.delete_webhook(drop_pending_updates=True)[cite: 1]
    await dp.start_polling(bot)[cite: 1]

if __name__ == "__main__":
    try: asyncio.run(main())[cite: 1]
    except KeyboardInterrupt: pass