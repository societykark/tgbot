import os
import logging
import asyncio
from datetime import datetime

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== CONFIGURACIÓN ==========
TELEGRAM_TOKEN = os.environ.get("TOKEN")  # Token de @BotFather
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")  # API Key de OpenRouter

if not TELEGRAM_TOKEN or not OPENROUTER_KEY:
    raise ValueError("❌ Faltan variables: TOKEN y OPENROUTER_KEY")

# URL de la API de OpenRouter
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modelo gratuito (puedes cambiar a 'deepseek/deepseek-v4-flash:free' o 'google/gemini-2.0-flash-exp:free')
MODEL = "deepseek/deepseek-v4-flash:free"

# ========== LOGS ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ========== MEMORIA ==========
user_histories = {}  # {chat_id: [{"role": "user", "content": "..."}]}
MAX_HISTORY = 10

async def ask_openrouter(prompt: str, chat_id: int) -> str:
    """Llama a OpenRouter con el modelo gratuito"""
    # Preparar historial
    history = user_histories.get(chat_id, [])
    messages = history + [{"role": "user", "content": prompt}]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/your_bot",  # Cambia por tu bot
        "X-Title": "Bot IA Telegram"
    }
    
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return f"❌ Error {resp.status}: {error_text[:100]}"
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                
                # Guardar historial
                if chat_id not in user_histories:
                    user_histories[chat_id] = []
                user_histories[chat_id].append({"role": "user", "content": prompt})
                user_histories[chat_id].append({"role": "assistant", "content": reply})
                if len(user_histories[chat_id]) > MAX_HISTORY * 2:
                    user_histories[chat_id] = user_histories[chat_id][-MAX_HISTORY * 2:]
                
                return reply
    except asyncio.TimeoutError:
        return "⏳ La IA tardó demasiado. Intenta de nuevo."
    except Exception as e:
        logger.error(f"Error en OpenRouter: {e}")
        return f"❌ Error: {str(e)}"

# ========== COMANDOS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Bot IA Gratis (OpenRouter)*\n\n"
        "Escribeme cualquier cosa y te responderé con IA.\n"
        "Modelo: DeepSeek V4 Flash (gratis)\n\n"
        "Comandos:\n"
        "`/reset` - Reinicia la conversación\n"
        "`/model` - Muestra el modelo actual\n"
        "`/help` - Este mensaje",
        parse_mode="Markdown"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_histories:
        del user_histories[chat_id]
    await update.message.reply_text("🧹 Conversación reiniciada.")

async def model_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🧠 *Modelo actual:* `{MODEL}`\n💰 *Precio:* Gratis (cuota incluida)", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Comandos:*\n"
        "`/start` - Bienvenida\n"
        "`/reset` - Borrar historial\n"
        "`/model` - Ver modelo\n"
        "`/help` - Esta ayuda\n\n"
        "✏️ *Uso:* Solo escríbeme cualquier cosa.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    # No responder a comandos (ya están manejados)
    if user_text.startswith("/"):
        return
    
    # Indicar que está procesando
    await update.message.reply_chat_action("typing")
    
    # Obtener respuesta
    reply = await ask_openrouter(user_text, chat_id)
    
    # Truncar si es muy largo
    if len(reply) > 4000:
        reply = reply[:4000] + "...\n\n*(respuesta truncada)*"
    
    await update.message.reply_text(reply, parse_mode="Markdown")

# ========== MAIN ==========

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("model", model_info))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot de Telegram iniciado. Esperando mensajes...")
    app.run_polling()

if __name__ == "__main__":
    main()