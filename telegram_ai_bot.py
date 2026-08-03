import os
import logging
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== CONFIGURACIÓN ==========
TOKEN = os.environ.get("TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

if not TOKEN or not OPENROUTER_KEY:
    raise ValueError("❌ Faltan TOKEN o OPENROUTER_KEY")

# ========== MODELOS DISPONIBLES ==========
MODELOS = {
    "1": {"id": "google/gemini-2.0-flash-exp:free", "nombre": "Gemini 2.0 Flash", "desc": "Multimodal, rápido y gratis."},
    "2": {"id": "deepseek/deepseek-v4-flash:free", "nombre": "DeepSeek V4 Flash", "desc": "200 req/día, muy bueno."},
    "3": {"id": "meta-llama/llama-3.2-3b-instruct:free", "nombre": "Llama 3.2 3B", "desc": "Rápido y confiable."},
    "4": {"id": "nvidia/nemotron-3-super-120b-a12b:free", "nombre": "NVIDIA Nemotron 3", "desc": "120B params, 1M contexto."},
}
MODELO_DEFECTO = MODELOS["1"]["id"]

# ========== LOGS ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== MEMORIA POR USUARIO ==========
memoria = {}  # {chat_id: {"historial": [], "modelo": MODELO_DEFECTO, "modo": "normal"}}

def obtener_usuario(chat_id):
    if chat_id not in memoria:
        memoria[chat_id] = {"historial": [], "modelo": MODELO_DEFECTO, "modo": "normal"}
    return memoria[chat_id]

# ========== LLAMADA A OPENROUTER (CON REINTENTOS) ==========
async def preguntar_ai(prompt, chat_id, reintentos=2):
    usuario = obtener_usuario(chat_id)
    historial = usuario["historial"]
    modelo = usuario["modelo"]
    
    # Sistema prompt para que responda como un humano
    system_msg = "Eres un asistente útil, conversacional y natural. Responde como si fueras una persona inteligente y amigable. Sé conciso pero completo."
    
    mensajes = [
        {"role": "system", "content": system_msg},
        *historial,
        {"role": "user", "content": prompt}
    ]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/tu_bot",
        "X-Title": "Bot IA Pro"
    }
    payload = {
        "model": modelo,
        "messages": mensajes,
        "max_tokens": 1000,
        "temperature": 0.8,
        "top_p": 0.95,
    }
    
    for intento in range(reintentos + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        reply = data["choices"][0]["message"]["content"].strip()
                        # Guardar historial
                        usuario["historial"].append({"role": "user", "content": prompt})
                        usuario["historial"].append({"role": "assistant", "content": reply})
                        # Limitar historial a 20 mensajes
                        if len(usuario["historial"]) > 20:
                            usuario["historial"] = usuario["historial"][-20:]
                        return reply
                    else:
                        error = data.get("error", {}).get("message", "Error desconocido")
                        if "rate limit" in error.lower() and intento < reintentos:
                            await asyncio.sleep(2 ** intento)
                            continue
                        return f"❌ Error {resp.status}: {error}"
        except asyncio.TimeoutError:
            if intento < reintentos:
                await asyncio.sleep(2)
                continue
            return "⏳ La IA tardó demasiado. Intenta de nuevo."
        except Exception as e:
            logger.error(f"Error en intento {intento}: {e}")
            if intento < reintentos:
                await asyncio.sleep(2)
                continue
            return f"❌ Error inesperado: {str(e)[:100]}"
    return "❌ No se pudo obtener respuesta después de varios intentos."

# ========== FORMATEAR RESPUESTA LARGA (SIN CORTES) ==========
async def enviar_respuesta(update, texto):
    """Envía texto largo en partes sin cortar palabras"""
    if len(texto) <= 4000:
        await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Dividir por párrafos o saltos de línea
    partes = []
    for parrafo in texto.split('\n\n'):
        if not parrafo.strip():
            continue
        if len(parrafo) > 4000:
            # Si un párrafo es muy largo, dividir por oraciones
            for oracion in parrafo.split('. '):
                if oracion:
                    partes.append(oracion + '. ')
        else:
            partes.append(parrafo)
    
    # Unir partes sin exceder 4000 caracteres
    mensajes = []
    actual = ""
    for parte in partes:
        if len(actual) + len(parte) + 2 <= 4000:
            actual += parte + "\n\n"
        else:
            if actual:
                mensajes.append(actual.strip())
            actual = parte + "\n\n"
    if actual:
        mensajes.append(actual.strip())
    
    # Enviar cada parte
    for i, msg in enumerate(mensajes):
        if i == 0:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"[Continuación]\n\n{msg}", parse_mode=ParseMode.MARKDOWN)

# ========== COMANDOS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📋 Modelos", callback_data="modelos")],
        [InlineKeyboardButton("🧹 Reiniciar", callback_data="reset")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="ayuda")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *Bot IA Pro*\n\n"
        "Soy un asistente con IA avanzada. Puedo ayudarte con:\n"
        "• Preguntas generales\n"
        "• Programación\n"
        "• Análisis de texto\n"
        "• Ideas y creatividad\n\n"
        "Comandos:\n"
        "`/modelo` - Cambiar modelo de IA\n"
        "`/reset` - Reiniciar conversación\n"
        "`/stats` - Ver estadísticas\n"
        "`/help` - Ayuda\n\n"
        "✏️ *Escríbeme cualquier cosa*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in memoria:
        memoria[chat_id]["historial"] = []
    await update.message.reply_text("🧹 *Historial reiniciado.*\nAhora podemos empezar de nuevo.", parse_mode=ParseMode.MARKDOWN)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuario = obtener_usuario(chat_id)
    modelo_actual = usuario["modelo"]
    nombre_modelo = next((m["nombre"] for m in MODELOS.values() if m["id"] == modelo_actual), "Desconocido")
    total_mensajes = len(usuario["historial"]) // 2
    
    await update.message.reply_text(
        f"📊 *Estadísticas de tu chat*\n\n"
        f"• Modelo actual: *{nombre_modelo}*\n"
        f"• Mensajes intercambiados: *{total_mensajes}*\n"
        f"• Mensajes en memoria: *{len(usuario['historial'])}*\n"
        f"• Última interacción: *{datetime.now().strftime('%H:%M:%S')}*\n\n"
        f"💡 Usa `/modelo` para cambiar de IA.",
        parse_mode=ParseMode.MARKDOWN
    )

async def modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuario = obtener_usuario(chat_id)
    actual = usuario["modelo"]
    
    keyboard = []
    for key, mod in MODELOS.items():
        marca = "✅ " if mod["id"] == actual else ""
        keyboard.append([InlineKeyboardButton(f"{marca}{mod['nombre']}", callback_data=f"mod_{key}")])
    keyboard.append([InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")])
    
    await update.message.reply_text(
        "📋 *Selecciona un modelo de IA:*\n\n"
        "Cada modelo tiene sus características y límites diarios.\n"
        "El modelo actual está marcado con ✅.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Ayuda del Bot*\n\n"
        "Comandos disponibles:\n"
        "`/start` - Mensaje de bienvenida\n"
        "`/modelo` - Cambiar el modelo de IA\n"
        "`/reset` - Borrar el historial de la conversación\n"
        "`/stats` - Ver estadísticas de uso\n"
        "`/help` - Mostrar esta ayuda\n\n"
        "💡 *Consejos:*\n"
        "• El bot recuerda el contexto de la conversación.\n"
        "• Usa `/reset` si quieres empezar de cero.\n"
        "• Cambia de modelo si uno no responde bien.\n\n"
        "📌 *Modelos disponibles:*\n"
        "1. Gemini 2.0 Flash - Multimodal y rápido\n"
        "2. DeepSeek V4 Flash - Muy inteligente\n"
        "3. Llama 3.2 3B - Rápido y confiable\n"
        "4. NVIDIA Nemotron 3 - Potente y con gran contexto",
        parse_mode=ParseMode.MARKDOWN
    )

# ========== CALLBACKS PARA BOTONES ==========
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data
    
    if data == "modelos":
        await modelo(update, context)
        await query.delete_message()
        return
    
    if data == "reset":
        if chat_id in memoria:
            memoria[chat_id]["historial"] = []
        await query.edit_message_text("🧹 *Historial reiniciado.*", parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "ayuda":
        await help_command(update, context)
        await query.delete_message()
        return
    
    if data == "cerrar":
        await query.delete_message()
        return
    
    if data.startswith("mod_"):
        key = data.split("_")[1]
        if key in MODELOS:
            usuario = obtener_usuario(chat_id)
            usuario["modelo"] = MODELOS[key]["id"]
            await query.edit_message_text(
                f"✅ *Modelo cambiado a:* {MODELOS[key]['nombre']}\n\n"
                f"Descripción: {MODELOS[key]['desc']}\n"
                f"Ahora puedes seguir conversando.",
                parse_mode=ParseMode.MARKDOWN
            )

# ========== MANEJAR MENSAJES ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto = update.message.text
    
    if not texto or texto.startswith("/"):
        return
    
    # Indicador de escritura
    await update.message.reply_chat_action("typing")
    
    # Obtener respuesta de la IA
    respuesta = await preguntar_ai(texto, chat_id)
    
    # Enviar respuesta formateada
    await enviar_respuesta(update, respuesta)

# ========== ERROR HANDLER ==========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Intenta de nuevo o usa `/reset` si el problema persiste.",
            parse_mode=ParseMode.MARKDOWN
        )

# ========== MAIN ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("modelo", modelo))
    app.add_handler(CommandHandler("help", help_command))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Mensajes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Errores
    app.add_error_handler(error_handler)
    
    print("✅ Bot IA Pro iniciado correctamente.")
    app.run_polling()

if __name__ == "__main__":
    main()