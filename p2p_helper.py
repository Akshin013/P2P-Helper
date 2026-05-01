import re
import requests
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN_TG = "8649973945:AAHsaN1YZ1Vt_rtPTqjNKefLKvpAKHJEASI"

# ───────── НАСТРОЙКИ ─────────
SEARCH_AMOUNT = ["2500"]
MAX_SEARCH_AMOUNT = 7000
MODE = "exact"

USE_PRICE_FILTER = False
MAX_PRICE = 82

USE_BLACKLIST = True

CURRENCY = "RUB"
TOKEN = "USDT"
SIDE = 1

API_URL = "https://api2.bybit.com/fiat/otc/item/online"

BLACKLIST = ["тбанк", "т банк", "т банка", "Т банка", "Т-Банк", "Т-банка", "Т-банк",
             "Т БАНК", "Т-БАНК", "т банком", "Т банком", "тинькофф", "tinkoff"]

running = False
last_status_msg = None

# ───────── КЛАВИАТУРА ─────────
def keyboard():
    return ReplyKeyboardMarkup([
        ["▶️ Старт", "⛔ Стоп"],
        ["⚙️ Режим поиска", "💰 Изменить сумму"],
        ["📉 Фильтр по цене", "🏦 Блок Т-банка"],
        ["📊 Статус бота", "❓ Помощь"]
    ], resize_keyboard=True)

def on_off(x):
    return "🟢 ВКЛ" if x else "🔴 ВЫКЛ"

def mode_name():
    return "Точная сумма" if MODE == "exact" else "До максимума"

# ───────── ЛОГИКА ─────────
def match_amount(text):
    numbers = re.findall(r"\d+", text or "")
    if MODE == "exact":
        return any(x in numbers for x in SEARCH_AMOUNT)
    if MODE == "max":
        return any(int(x) <= MAX_SEARCH_AMOUNT for x in numbers if x.isdigit())
    return False

def is_valid(ad):
    text = ad.get("remark", "").lower()
    if not match_amount(text):
        return False
    if USE_BLACKLIST and any(b.lower() in text for b in BLACKLIST):
        return False
    if USE_PRICE_FILTER:
        try:
            if float(ad["price"]) > MAX_PRICE:
                return False
        except:
            return False
    return True

def build_link(ad_id):
    return f"https://www.bybit.com/fiat/trade/otc?tab=buy&id={ad_id}"

# ───────── СКАНЕР ─────────
async def scanner(context: ContextTypes.DEFAULT_TYPE, chat_id):
    global last_status_msg
    seen = set()
    dots = 0

    last_status_msg = await context.bot.send_message(chat_id, "⏳ Запускаю сканер...")

    while running:
        try:
            resp = requests.post(API_URL, json={
                "tokenId": TOKEN,
                "currencyId": CURRENCY,
                "side": str(SIDE),
                "size": "50",
                "page": "1"
            })

            data = resp.json()
            ads = data.get("result", {}).get("items", [])
            found = 0

            for ad in ads:
                if is_valid(ad):
                    ad_id = ad.get("id")
                    if ad_id not in seen:
                        seen.add(ad_id)
                        found += 1

                        try:
                            await last_status_msg.delete()
                        except:
                            pass

                        amount_info = (
                            f"🎯 Ищем: {SEARCH_AMOUNT[0]} {CURRENCY}"
                            if MODE == "exact"
                            else f"🎯 Ищем: до {MAX_SEARCH_AMOUNT} {CURRENCY}"
                        )

                        text = (
                            f"🔥 НОВЫЙ ОРДЕР НАЙДЕН!\n"
                            f"{'─' * 30}\n"
                            f"👤 Продавец: {ad.get('nickName')}\n"
                            f"💰 Курс: {ad.get('price')} {CURRENCY} за {TOKEN}\n"
                            f"📊 Лимиты: {ad.get('minAmount')} – {ad.get('maxAmount')} {CURRENCY}\n"
                            f"📝 Описание: {ad.get('remark') or '—'}\n"
                            f"{'─' * 30}\n"
                            f"{amount_info}"
                        )

                        btn = InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔗 Открыть ордер на Bybit", url=build_link(ad_id))
                        ]])

                        await context.bot.send_message(chat_id, text, reply_markup=btn)
                        last_status_msg = await context.bot.send_message(chat_id, "⏳ Продолжаю поиск...")

            dots = (dots + 1) % 4
            loading = "⏳ Сканирую" + "." * dots

            try:
                await last_status_msg.edit_text(
                    f"{loading}\n\n"
                    f"📦 Проверено объявлений: {len(ads)}\n"
                    f"🔥 Найдено за сессию: {found}\n"
                    f"🕒 Обновлено: {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass

        except Exception as e:
            print("Ошибка:", e)

        await asyncio.sleep(2)

# ───────── ПОМОЩЬ ─────────
HELP_TEXT = """
❓ СПРАВКА ПО КНОПКАМ

▶️ Старт — запустить сканер Bybit P2P
⛔ Стоп — остановить сканер

⚙️ Режим поиска — переключение между:
   • Точная сумма — ищет ордера где в описании написана ИМЕННО твоя сумма (например 2500)
   • До максимума — ищет ордера где сумма НЕ БОЛЬШЕ указанной

💰 Изменить сумму — задать новую сумму для поиска

📉 Фильтр по цене — включить/выключить ограничение по курсу (макс. {max_price} руб за USDT)

🏦 Блок Т-банка — включить/выключить блокировку ордеров где упоминается Т-банк / Тинькофф

📊 Статус бота — показать текущие настройки и состояние сканера
""".format(max_price=MAX_PRICE)

# ───────── ОБРАБОТКА ─────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["wait_amount"] = True
    context.user_data["setup_done"] = False

    await update.message.reply_text(
        "👋 Привет! Я сканирую Bybit P2P и нахожу ордера с нужной суммой в описании.\n\n"
        "Для начала введи сумму которую нужно искать (только цифры, например: 2500):"
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running, MODE, USE_PRICE_FILTER, USE_BLACKLIST, MAX_SEARCH_AMOUNT

    text = update.message.text

    # ── Первичный ввод суммы ──
    if not context.user_data.get("setup_done") and context.user_data.get("wait_amount"):
        raw = text.strip()
        if not raw.isdigit():
            await update.message.reply_text("❌ Введи только цифры, например: 2500")
            return

        SEARCH_AMOUNT[0] = raw
        context.user_data["wait_amount"] = False
        context.user_data["setup_done"] = True

        await update.message.reply_text(
            f"✅ Сумма для поиска: {raw} {CURRENCY}\n\n"
            f"Теперь нажми ▶️ Старт чтобы начать сканирование.\n"
            f"Кнопка ❓ Помощь объяснит остальные функции.",
            reply_markup=keyboard()
        )
        return

    # ── Ввод суммы через кнопку ──
    if context.user_data.get("wait_amount"):
        raw = text.strip()
        if not raw.isdigit():
            await update.message.reply_text("❌ Введи только цифры, например: 2500")
            return

        if MODE == "exact":
            SEARCH_AMOUNT[0] = raw
            await update.message.reply_text(f"✅ Точная сумма обновлена: {raw} {CURRENCY}")
        else:
            MAX_SEARCH_AMOUNT = int(raw)
            await update.message.reply_text(f"✅ Максимальная сумма обновлена: до {raw} {CURRENCY}")

        context.user_data["wait_amount"] = False
        return

    # ── Кнопки управления ──
    if text == "▶️ Старт":
        if not running:
            running = True
            await update.message.reply_text(
                f"✅ Сканер запущен!\n\n"
                f"🔍 Ищу ордера с суммой: {SEARCH_AMOUNT[0] if MODE == 'exact' else f'до {MAX_SEARCH_AMOUNT}'} {CURRENCY}\n"
                f"⚙️ Режим: {mode_name()}\n"
                f"🏦 Блок Т-банка: {on_off(USE_BLACKLIST)}"
            )
            context.application.create_task(scanner(context, update.message.chat_id))
        else:
            await update.message.reply_text("⚠️ Сканер уже работает. Нажми ⛔ Стоп чтобы остановить.")

    elif text == "⛔ Стоп":
        running = False
        await update.message.reply_text("⛔ Сканер остановлен.")

    elif text == "⚙️ Режим поиска":
        MODE = "max" if MODE == "exact" else "exact"
        desc = (
            "🎯 Теперь ищу ордера где в описании написана ТОЧНАЯ сумма."
            if MODE == "exact"
            else "🎯 Теперь ищу ордера где сумма НЕ БОЛЬШЕ указанного максимума."
        )
        await update.message.reply_text(f"⚙️ Режим переключён: {mode_name()}\n\n{desc}")

    elif text == "📉 Фильтр по цене":
        USE_PRICE_FILTER = not USE_PRICE_FILTER
        desc = (
            f"Буду показывать только ордера где курс не выше {MAX_PRICE} руб за USDT."
            if USE_PRICE_FILTER
            else "Буду показывать ордера с любым курсом."
        )
        await update.message.reply_text(f"📉 Фильтр по цене: {on_off(USE_PRICE_FILTER)}\n\n{desc}")

    elif text == "🏦 Блок Т-банка":
        USE_BLACKLIST = not USE_BLACKLIST
        desc = (
            "Ордера где упоминается Т-банк / Тинькофф будут скрыты."
            if USE_BLACKLIST
            else "Ордера с Т-банком теперь тоже будут показываться."
        )
        await update.message.reply_text(f"🏦 Блок Т-банка: {on_off(USE_BLACKLIST)}\n\n{desc}")

    elif text == "📊 Статус бота":
        await update.message.reply_text(
            f"📊 ТЕКУЩИЕ НАСТРОЙКИ\n"
            f"{'─' * 30}\n"
            f"🤖 Сканер: {'🟢 Работает' if running else '🔴 Остановлен'}\n"
            f"⚙️ Режим: {mode_name()}\n"
            f"💰 Сумма: {SEARCH_AMOUNT[0] if MODE == 'exact' else f'до {MAX_SEARCH_AMOUNT}'} {CURRENCY}\n"
            f"📉 Фильтр цены: {on_off(USE_PRICE_FILTER)} (макс. {MAX_PRICE} руб)\n"
            f"🏦 Блок Т-банка: {on_off(USE_BLACKLIST)}\n"
            f"{'─' * 30}\n"
            f"📌 Пара: {TOKEN}/{CURRENCY}"
        )

    elif text == "❓ Помощь":
        await update.message.reply_text(HELP_TEXT)

    elif text == "💰 Изменить сумму":
        context.user_data["wait_amount"] = True
        mode_hint = "точную сумму" if MODE == "exact" else f"максимальную сумму (сейчас: {MAX_SEARCH_AMOUNT})"
        await update.message.reply_text(f"💰 Введи {mode_hint}:")

# ───────── ЗАПУСК ─────────
app = ApplicationBuilder().token(TOKEN_TG).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle))
print('@P2P_Helperr_bot')
app.run_polling()