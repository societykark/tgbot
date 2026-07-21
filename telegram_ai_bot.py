import os
import logging
import asyncio
import json

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== CONFIGURACIÓN ==========
TELEGRAM_TOKEN = os.environ.get("TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

if not TELEGRAM_TOKEN or not OPENROUTER_KEY:
    raise ValueError("❌ Faltan variables: TOKEN y OPENROUTER_KEY")

# ========== MODELOS DISPONIBLES ==========
AVAILABLE_MODELS = {
    "1": {
        "id": "nvidia/nemotron-3-super-120b-a12b:free",
        "name": "NVIDIA Nemotron 3 Super",
        "desc": "120B params, 1M contexto. El más balanceado."
    },
    "2": {
        "id": "google/gemma-4-31b-instruct:free",
        "name": "Google Gemma 4 31B",
        "desc": "Multimodal, 140+ idiomas, 256K contexto."
    },
    "3": {
        "id": "tencent/hy3:free",
        "name": "Tencent Hy3",
        "desc": "295B params (21B activos), experto en razonamiento."
    },
    "4": {
        "id": "poolside/laguna-m1:free",
        "name": "Poolside Laguna M.1",
        "desc": "Especializado en coding, 256K contexto."
    }
}

# Modelo por defecto (el #1)
DEFAULT_MODEL = AVAILABLE_MODELS["1"]["id"]

# ========== LOGS ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ========== MEMORIA POR USUARIO ==========
user_data = {}  # {chat_id: {"history": [], "model": "..."}}

def get_user_model(chat_id):
    if chat_id not in user_data:
        user_data[chat_id] = {"history": [], "model": DEFAULT_MODEL}
    return user_data[chat_id]["model"]

def get_user_history(chat_id):
    if chat_id not in user_data:
        user_data[chat_id] = {"history": [], "model": DEFAULT_MODEL}
    return user_data[chat_id]["history"]

def save_history(chat_id, role, content):
    history = get_user_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > 20:  # Máximo 10 mensajes de cada lado
        history.pop(0)

# ========== LLAMADA A OPENROUTER ==========
async def ask_openrouter(prompt: str, chat_id: int, model_override: str = None) -> str:
    model = model_override or get_user_model(chat_id)
    history = get_user_history(chat_id)
    messages = history + [{"role": "user", "content": prompt}]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/tu_bot",
        "X-Title": "Bot IA Telegram"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return f"❌ Error {resp.status}: {error_text[:100]}"
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                
                # Guardar historial
                save_history(chat_id, "user", prompt)
                save_history(chat_id, "assistant", reply)
                
                return reply
    except asyncio.TimeoutError:
        return "⏳ La IA tardó demasiado. Intenta de nuevo."
    except Exception as e:
        logger.error(f"Error en OpenRouter: {e}")
        return f"❌ Error: {str(e)}"

# ========== COMANDOS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Bot IA con modelos múltiples*\n\n"
        "Escribeme cualquier cosa y te responderé.\n\n"
        "Comandos:\n"
        "`/model` - Ver modelo actual y cambiarlo\n"
        "`/reset` - Reiniciar conversación\n"
        "`/help` - Esta ayuda\n\n"
        "Modelos disponibles:\n"
        "1️⃣ NVIDIA Nemotron 3 Super\n"
        "2️⃣ Google Gemma 4 31B\n"
        "3️⃣ Tencent Hy3\n"
        "4️⃣ Poolside Laguna M.1",
        parse_mode="Markdown"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_data:
        user_data[chat_id]["history"] = []
    await update.message.reply_text("🧹 Conversación reiniciada.")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current = get_user_model(chat_id)
    
    # Mostrar modelos disponibles
    text = "📋 *Modelos disponibles:*\n\n"
    for key, model in AVAILABLE_MODELS.items():
        marker = "✅ " if model["id"] == current else "   "
        text += f"{marker} `{key}` - {model['name']}\n"
        text += f"      _{model['desc']}_\n\n"
    text += "Para cambiar, usa `/model <número>`\nEjemplo: `/model 2`"
    await update.message.reply_text(text, parse_mode="Markdown")

async def change_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await model_command(update, context)
        return
    
    num = context.args[0]
    if num not in AVAILABLE_MODELS:
        await update.message.reply_text("❌ Número inválido. Usa 1, 2, 3 o 4.")
        return
    
    if chat_id not in user_data:
        user_data[chat_id] = {"history": [], "model": DEFAULT_MODEL}
    user_data[chat_id]["model"] = AVAILABLE_MODELS[num]["id"]
    
    await update.message.reply_text(
        f"✅ Modelo cambiado a: *{AVAILABLE_MODELS[num]['name']}*",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Comandos:*\n"
        "`/start` - Bienvenida\n"
        "`/reset` - Borrar historial\n"
        "`/model` - Ver modelos y cambiarlos\n"
        "`/model <1-4>` - Cambiar al modelo indicado\n"
        "`/help` - Esta ayuda\n\n"
        "✏️ *Uso:* Escríbeme cualquier cosa.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    if user_text.startswith("/"):
        return
    
    await update.message.reply_chat_action("typing")
    reply = await ask_openrouter(user_text, chat_id)
    
    if len(reply) > 4000:
        reply = reply[:4000] + "...\n\n*(respuesta truncada)*"
    
    await update.message.reply_text(reply, parse_mode="Markdown")

# ========== MAIN ==========

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("model", change_model))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot de Telegram con modelos múltiples iniciado.")
    app.run_polling()

if __name__ == "__main__":
    main()