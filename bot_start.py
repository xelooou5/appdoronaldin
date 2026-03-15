#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, logging, re, sqlite3, json, base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import aiohttp
from dotenv import load_dotenv
import uuid
import pytz

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import Database
from validador_vision import validar_print

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
PRINTS_DIR = BASE_DIR / 'auditoria_prints'
PRINTS_DIR.mkdir(exist_ok=True)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_API_KEY_2 = os.getenv('GEMINI_API_KEY_2')
GEMINI_API_KEY_3 = os.getenv('GEMINI_API_KEY_3')


if not TELEGRAM_TOKEN:
    log.error("TELEGRAM_TOKEN não configurado!")
    sys.exit(1)

# StartBet Links (Substituted from original luck.bet links)
LINK_CADASTRO = 'https://start.bet.br/signup?btag=CX-48705_445081'
LINK_APP = 'https://appdoronaldin.com.br/'
LINK_GRUPO = 'https://t.me/+8imjlHQtZTE1MjYx'

BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')

user_states = {}
last_message_time = {}
db = Database()

class ChatIA:
    def __init__(self):
        pass

    def get_system_prompt(self):
        return """Você é o bot do App do Ronaldin.
Fala como brasileiro de verdade: direto, engraçado.
ESPECIALIDADES:
- Sinais, apostas, StartBet
REGRAS:
1. Máximo 5-6 linhas.
2. NUNCA mencione URLs.
3. Emojis moderados.
4. Responda em português."""

    async def responder_groq(self, prompt: str) -> Optional[str]:
        if not GROQ_API_KEY: return None
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": self.get_system_prompt()}, {"role": "user", "content": prompt}], "max_tokens": 1500, "temperature": 0.85}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content'].strip()
            return None
        except: return None

    async def responder_gemini(self, prompt: str) -> Optional[str]:
        keys = [GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3]
        for key in keys:
            if not key: continue
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
                payload = {"contents": [{"parts": [{"text": self.get_system_prompt()}, {"text": prompt}]}]}
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data['candidates'][0]['content']['parts'][0]['text'].strip()
            except: continue
        return None

    async def responder(self, pergunta: str) -> str:
        log.info(f"[IA] Pergunta: {pergunta}")
        for nome, metodo in [("GROQ", self.responder_groq), ("GEMINI", self.responder_gemini)]:
            resposta = await metodo(pergunta)
            if resposta: return resposta
        return "Desculpa, tive um problema técnico. Tenta de novo!"

chat_ia = ChatIA()

def get_main_buttons(is_vip=False):
    if is_vip:
        buttons = [
            [InlineKeyboardButton('📱 ACESSAR APP', url=LINK_APP), InlineKeyboardButton('💬 GRUPO VIP', url=LINK_GRUPO)]
        ]
    else:
        buttons = [
            [InlineKeyboardButton('🚀 QUERO ACESSO', callback_data='fluxo_startbet')],
            [InlineKeyboardButton('💎 GRUPO GRATUITO', url=LINK_GRUPO)]
        ]
    return InlineKeyboardMarkup(buttons)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"START: {user.first_name}")
    db.create_or_update_user(user.id, user.username, user.first_name)
    is_vip = db.is_user_vip(user.id)
    await update.message.reply_text(
        f"Opa {user.first_name}! Tudo certo?\n\nQuer acesso ao app e ao grupo VIP gratuito de sinais?\n\n👇 Escolha abaixo:",
        reply_markup=get_main_buttons(is_vip)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = update.message.text
    log.info(f"TEXTO: {user.first_name} -> {txt}")
    db.create_or_update_user(user.id, user.username, user.first_name)

    now = datetime.now()
    if user.id in last_message_time and (now - last_message_time[user.id]).total_seconds() < 2: return
    last_message_time[user.id] = now
    
    txt_norm = txt.lower()

    if any(w in txt_norm for w in ['sim', 'quero', 's', 'claro']):
        if db.is_user_vip(user.id):
            await update.message.reply_text("Você já tem acesso! 👇", reply_markup=get_main_buttons(is_vip=True))
            return
        user_states[user.id] = 'WAITING_FOR_REGISTRATION_PRINT'
        await update.message.reply_text(
            f"Só um detalhe importante: para acessar o app, você vai usar o mesmo login e senha da plataforma StartBet.\n\n"
            f"Crie sua conta na StartBet e me envie o print confirmando o cadastro (saldo 0,00).\n\n"
            f"Link: {LINK_CADASTRO}"
        )
        return

    is_new = not db.get_user(user.id) or (db.get_user(user.id) and db.get_user(user.id)['interactions'] < 2)
    db.increment_interactions(user.id)
    resposta = await chat_ia.responder(txt)
    
    if is_new or any(w in txt_norm for w in ['menu', 'start']):
        await update.message.reply_text(resposta, reply_markup=get_main_buttons(db.is_user_vip(user.id)))
    else:
        await update.message.reply_text(resposta)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"FOTO: {user.first_name}")
    db.create_or_update_user(user.id, user.username, user.first_name)

    if db.is_user_vip(user.id):
        await update.message.reply_text("✅ Já tá validado!", reply_markup=get_main_buttons(is_vip=True))
        return
    
    estado_atual = user_states.get(user.id, 'WAITING_FOR_REGISTRATION_PRINT')
    
    try:
        ph = await update.message.photo[-1].get_file()
        safe_filename = f"{user.id}_{str(uuid.uuid4())[:8]}.jpg"
        fp = PRINTS_DIR / safe_filename
        await ph.download_to_drive(str(fp))
        await update.message.reply_text("🔍 Deixa eu dar uma olhada...")

        eh_valido, msg_resultado = await validar_print(str(fp))
        log.info(f"[VALIDACAO] Resultado: {eh_valido}, msg={msg_resultado}")

        if not eh_valido:
            await update.message.reply_text("❌ Não identifiquei a StartBet. Tenta de novo!")
            return

        saldo = 0.0
        match = re.search(r'(\d+[.,]\d{2})', str(msg_resultado))
        if match: saldo = float(match.group(1).replace(',', '.'))

        if estado_atual == 'WAITING_FOR_REGISTRATION_PRINT':
            if saldo <= 1.0:
                await update.message.reply_text("Perfeito, vi que criou a conta. Mas tá sem saldo!\n\nFaça um depósito (mínimo R$20) e mande o print para liberar o acesso.")
                user_states[user.id] = 'WAITING_FOR_DEPOSIT_PRINT'
            elif saldo >= 20.0:
                db.set_vip(user.id, True)
                await update.message.reply_text(f"Show! Acesso liberado:\nApp: {LINK_APP}\nGrupo: {LINK_GRUPO}")
            else:
                await update.message.reply_text("O saldo mínimo é R$20. Faça um depósito!")
                user_states[user.id] = 'WAITING_FOR_DEPOSIT_PRINT'
        elif estado_atual == 'WAITING_FOR_DEPOSIT_PRINT':
            if saldo >= 20.0:
                db.set_vip(user.id, True)
                await update.message.reply_text(f"Show! Acesso liberado:\nApp: {LINK_APP}\nGrupo: {LINK_GRUPO}")
            else:
                await update.message.reply_text("Ainda não vi os R$20+. Mande o print atualizado!")
    except Exception as e:
        log.error(f"Erro foto: {e}")
        await update.message.reply_text("❌ Deu erro ao processar. Tenta de novo.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == 'fluxo_startbet':
        if db.is_user_vip(uid):
            await query.message.reply_text("✅ Já validado!", reply_markup=get_main_buttons(is_vip=True))
        else:
            user_states[uid] = 'WAITING_FOR_REGISTRATION_PRINT'
            await query.message.reply_text(
                f"1️⃣ Crie sua conta na StartBet pelo link abaixo.\n"
                f"2️⃣ Tire um print com saldo 0,00.\n"
                f"3️⃣ Me envie o print aqui!\n\nLink: {LINK_CADASTRO}"
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.error(f"Erro: {context.error}")

def main():
    log.info("Iniciando Bot StartBet (Clone exato da Luck)...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(HTTPXRequest(http_version="1.1")).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)
    
    log.info('BOT CONECTADO!')
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()