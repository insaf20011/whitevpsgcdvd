import asyncio
import logging
import uvicorn
from fastapi import FastAPI, Request
from bot import bot, dp, init_db, update_subscription, create_vpn_client, PRODUCTS_PLANS

# Глобальная настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SERVER")

app = FastAPI()

@app.post("/webhook/platega")
async def platega_webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Получен webhook от Platega: {data}")
        
        status = data.get("status")
        payload = data.get("payload", "")

        if status == "completed" and payload.startswith("pay_"):
            try:
                _, user_id, plan_id = payload.split("_")
                user_id = int(user_id)
                plan = PRODUCTS_PLANS.get(plan_id)
                
                if plan:
                    logger.info(f"Обработка успешной оплаты для {user_id}, тариф: {plan_id}")
                    
                    new_expiry = await update_subscription(user_id, plan['days'], float(data.get("amount", 0)))
                    config = await create_vpn_client(user_id, plan['days'], plan['limit_gb'])
                    
                    try:
                        await bot.send_message(
                            user_id, 
                            f"✅ <b>Оплата через Platega получена!</b>\n"
                            f"📅 Подписка продлена до: <code>{new_expiry.strftime('%d.%m.%Y')}</code>\n\n"
                            f"🔑 <b>Ваш ключ:</b>\n<code>{config}</code>",
                            parse_mode="HTML"
                        )
                        logger.info(f"Пользователю {user_id} отправлен конфиг.")
                    except Exception as e:
                        logger.error(f"Не удалось отправить конфиг в Telegram для {user_id}: {e}")
                    
                    return {"status": "ok"}
                else:
                    logger.warning(f"Тариф {plan_id} не найден в настройках.")
            except Exception as inner_e:
                logger.error(f"Ошибка при разборе payload или выдаче VPN: {inner_e}")
        else:
            logger.info(f"Игнорируем webhook (status: {status}, payload: {payload})")
            
    except Exception as e:
        logger.error(f"Критическая ошибка обработки вебхука: {e}")
        
    return {"status": "ignored"}

async def main():
    logger.info("Запуск системы...")
    
    # 1. Инициализируем БД
    await init_db()
    
    # 2. Настраиваем FastAPI сервер
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    # 3. Запускаем FastAPI как фоновую задачу
    loop = asyncio.get_event_loop()
    loop.create_task(server.serve())
    logger.info("FastAPI сервер поднят на порту 8000")
    
    # 4. Стартуем бота
    logger.info("Запуск Telegram бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Система остановлена.")