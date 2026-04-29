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

BLACKLIST = ["тбанк", "т банк", "т банка", "Т банка", "Т-банка", "Т-банк", "Т банк",
             "Т БАНК", "Т-БАНК", "т банком", "Т банком", "тинькофф", "tinkoff"]

running = False
last_status_msg = None

# ───────── КЛАВИАТУРА ─────────
def keyboard():
    return ReplyKeyboardMarkup([
        ["▶️ Старт", "⛔ Стоп"],
        ["⚙️ Режим", "💰 Сумма"],
        ["📉 Цена", "🏦 Банк"],
        ["📊 Статус"]
    ], resize_keyboard=True)

def on_off(x):
    return "🟢 ВКЛ" if x else "🔴 ВЫКЛ"

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
    if USE_BLACKLIST and any(b in text for b in BLACKLIST):
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

    last_status_msg = await context.bot.send_message(chat_id, "⏳ Запуск...")

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

                        text = (
                            f"🔥 НАЙДЕНО\n\n"
                            f"👤 {ad.get('nickName')}\n"
                            f"💰 {ad.get('price')} {CURRENCY}/{TOKEN}\n"
                            f"📊 {ad.get('minAmount')} - {ad.get('maxAmount')}\n"
                            f"📝 {ad.get('remark')}"
                        )

                        btn = InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔗 Открыть ордер", url=build_link(ad_id))
                        ]])

                        await context.bot.send_message(chat_id, text, reply_markup=btn)
                        last_status_msg = await context.bot.send_message(chat_id, "⏳ продолжаем поиск...")

            dots = (dots + 1) % 4
            loading = "⏳ Ищем" + "." * dots

            try:
                await last_status_msg.edit_text(
                    f"{loading}\n\n"
                    f"📦 Проверено: {len(ads)}\n"
                    f"🔥 Найдено: {found}\n"
                    f"🕒 {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass

        except Exception as e:
            print("Ошибка:", e)

        await asyncio.sleep(2)

# ───────── ОБРАБОТКА ─────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """При /start — сразу спрашиваем сумму, кнопки не показываем пока."""
    context.user_data["wait_amount"] = True
    context.user_data["setup_done"] = False

    await update.message.reply_text(
        "👋 Привет! Для начала введи сумму для поиска (например: 2500):"
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running, MODE, USE_PRICE_FILTER, USE_BLACKLIST, MAX_SEARCH_AMOUNT

    text = update.message.text

    # ── Первичная настройка суммы при старте ──
    if not context.user_data.get("setup_done") and context.user_data.get("wait_amount"):
        raw = text.strip()
        if not raw.isdigit():
            await update.message.reply_text("❌ Введи только число, например: 2500")
            return

        if MODE == "exact":
            SEARCH_AMOUNT[0] = raw
        else:
            MAX_SEARCH_AMOUNT = int(raw)

        context.user_data["wait_amount"] = False
        context.user_data["setup_done"] = True

        await update.message.reply_text(
            f"✅ Сумма установлена: {raw}\n\nТеперь нажми ▶️ Старт чтобы начать поиск.",
            reply_markup=keyboard()
        )
        return

    # ── Ввод суммы через кнопку 💰 Сумма ──
    if context.user_data.get("wait_amount"):
        raw = text.strip()
        if not raw.isdigit():
            await update.message.reply_text("❌ Введи только число, например: 2500")
            return

        if MODE == "exact":
            SEARCH_AMOUNT[0] = raw
            await update.message.reply_text(f"💰 Точная сумма: {raw}")
        else:
            MAX_SEARCH_AMOUNT = int(raw)
            await update.message.reply_text(f"💰 Максимум до: {raw}")

        context.user_data["wait_amount"] = False
        return

    # ── Основные кнопки ──
    if text == "▶️ Старт":
        if not running:
            running = True
            await update.message.reply_text("✅ Запущено")
            context.application.create_task(scanner(context, update.message.chat_id))
        else:
            await update.message.reply_text("⚠️ Уже запущено")

    elif text == "⛔ Стоп":
        running = False
        await update.message.reply_text("⛔ Остановлено")

    elif text == "⚙️ Режим":
        MODE = "max" if MODE == "exact" else "exact"
        await update.message.reply_text(
            f"⚙️ Режим: {'До суммы' if MODE == 'max' else 'Точный'}"
        )

    elif text == "📉 Цена":
        USE_PRICE_FILTER = not USE_PRICE_FILTER
        await update.message.reply_text(f"📉 Фильтр цены: {on_off(USE_PRICE_FILTER)}")

    elif text == "🏦 Банк":
        USE_BLACKLIST = not USE_BLACKLIST
        await update.message.reply_text(f"🏦 Блокировка банков: {on_off(USE_BLACKLIST)}")

    elif text == "📊 Статус":
        await update.message.reply_text(
            f"📊 СТАТУС\n\n"
            f"⚙️ Режим: {'До суммы' if MODE == 'max' else 'Точный'}\n"
            f"💰 Сумма: {SEARCH_AMOUNT[0] if MODE == 'exact' else f'<= {MAX_SEARCH_AMOUNT}'}\n"
            f"📉 Цена: {on_off(USE_PRICE_FILTER)}\n"
            f"🏦 Банк: {on_off(USE_BLACKLIST)}\n"
            f"🤖 Сканер: {'🟢 Работает' if running else '🔴 Остановлен'}"
        )

    elif text == "💰 Сумма":
        context.user_data["wait_amount"] = True
        await update.message.reply_text("Введи новую сумму:")

# ───────── ЗАПУСК ─────────
app = ApplicationBuilder().token(TOKEN_TG).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle))

app.run_polling()