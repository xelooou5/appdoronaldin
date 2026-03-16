#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import logging
import re
import uuid
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

from database import Database
from validador_vision import validar_print
from chat_ia import ChatIA

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
if not TELEGRAM_TOKEN:
    log.error("TELEGRAM_TOKEN não configurado!")
    sys.exit(1)

# StartBet Links
LINK_CADASTRO = 'https://start.bet.br/signup?btag=CX-48705_445081'
LINK_APP = 'https://appdoronaldin.com.br/'
LINK_GRUPO = 'https://t.me/+8imjlHQtZTE1MjYx'

BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')

user_states = {}
last_message_time = {}
db = Database()
chat_ia = ChatIA()

# States for StartBet
WAITING_FOR_YES = 'WAITING_FOR_YES'
WAITING_FOR_REGISTRATION_PRINT = 'WAITING_FOR_REGISTRATION_PRINT'
WAITING_FOR_DEPOSIT_PRINT = 'WAITING_FOR_DEPOSIT_PRINT'


def get_main_buttons(is_vip=False):
    if is_vip:
        buttons = [
            [InlineKeyboardButton('📱 ACESSAR APP', url=LINK_APP),
             InlineKeyboardButton('💬 GRUPO VIP', url=LINK_GRUPO)]
        ]
    else:
        buttons = [
            [InlineKeyboardButton('🚀 QUERO ACESSO', callback_data='fluxo_startbet')],
            [InlineKeyboardButton('💎 GRUPO GRATUITO', url=LINK_GRUPO)]
        ]
    return InlineKeyboardMarkup(buttons)

async def send_video_if_exists(update: Update, filename: str):
    """Sends a video if it exists in the current directory."""
    if os.path.exists(filename):
        try:
            with open(filename, 'rb') as video:
                await update.message.reply_video(video=video)
        except Exception as e:
            log.error(f"Failed to send video {filename}: {e}")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"START: {user.first_name}")
    
    db.create_or_update_user(user.id, user.username, user.first_name)
    is_vip = db.is_user_vip(user.id)
    
    await update.message.reply_text(
        f"Opa! Tudo certo? 🤙\n\n"
        f"Quer acesso ao app e ao grupo gratuito de sinais?",
        reply_markup=get_main_buttons(is_vip)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = update.message.text
    log.info(f"TEXTO: {user.first_name} -> {txt}")
    
    db.create_or_update_user(user.id, user.username, user.first_name)

    now = datetime.now()
    if user.id in last_message_time:
        if (now - last_message_time[user.id]).total_seconds() < 2:
            return
    last_message_time[user.id] = now
    
    txt_norm = txt.lower().replace('ã', 'a').replace('á', 'a').replace('é', 'e').replace('ó', 'o')

    is_validated, _ = db.is_user_validated(user.id)
    
    if any(w in txt_norm for w in ['sim', 'quero', 's', 'claro', 'bora', 'ja criei', 'ja fiz']):
        if is_validated:
             await update.message.reply_text(
                f"Você já tem acesso liberado! 👇",
                reply_markup=get_main_buttons(is_vip=True)
            )
             return
             
        if 'ja fiz' in txt_norm or 'ja criei' in txt_norm:
            await update.message.reply_text("Show! 👊 Me manda o print da tela da sua conta na StartBet pra eu confirmar e liberar seu acesso!")
            user_states[user.id] = WAITING_FOR_REGISTRATION_PRINT
            return

        await update.message.reply_text(
            "Maravilha! 🚀\n\n"
            "Só um detalhe importante: para acessar o app, você vai usar o mesmo login e senha da plataforma StartBet, porque o aplicativo é 100% integrado a ela.\n\n"
            "Então é bem simples: crie sua conta na StartBet e me envie o print confirmando o cadastro. Assim que mandar, libero seu acesso ao app 👊\n"
            f"🔗 Link de cadastro: {LINK_CADASTRO}"
        )
        user_states[user.id] = WAITING_FOR_REGISTRATION_PRINT
        return

    # Check if we should respond with IA
    user_db = db.get_user(user.id)
    is_new = not user_db or user_db['interactions'] < 2

    db.increment_interactions(user.id)
    db.save_message(user.id, 'user', txt)

    prompt = f"Usuário disse: '{txt}'. Responda de forma natural, curta e como brasileiro. Somos do StartBet App do Ronaldin."
    resposta = await chat_ia.responder(prompt)
    db.save_message(user.id, 'assistant', resposta)

    if is_new or any(w in txt_norm for w in ['menu', 'opcoes', 'opcao', 'ajuda', 'help', 'start']):
        is_vip = db.is_user_vip(user.id)
        await update.message.reply_text(resposta, reply_markup=get_main_buttons(is_vip))
    else:
        await update.message.reply_text(resposta)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"FOTO: {user.first_name}")
    
    db.create_or_update_user(user.id, user.username, user.first_name)

    is_validated, _ = db.is_user_validated(user.id)
    if is_validated:
        await update.message.reply_text(
            f"✅ Já tá validado! Não precisa mandar print de novo 😉\n\n"
            f"Usa os botões abaixo pra acessar:",
            reply_markup=get_main_buttons(is_vip=True)
        )
        return
    
    estado_atual = user_states.get(user.id, WAITING_FOR_REGISTRATION_PRINT)
    
    try:
        ph = await update.message.photo[-1].get_file()
        safe_filename = f"{user.id}_{str(uuid.uuid4())[:8]}.jpg"
        fp = PRINTS_DIR / safe_filename
        await ph.download_to_drive(str(fp))
        
        await update.message.reply_text("🔍 Deixa eu analisar seu print...")

        log.info(f"[VALIDACAO] Iniciando validação para user {user.id} no estado {estado_atual}")
        eh_valido, msg_resultado = await validar_print(str(fp))
        log.info(f"[VALIDACAO] OCR Result: valido={eh_valido}, msg={msg_resultado}")

        if not eh_valido:
            await update.message.reply_text(
                f"❌ Hmm, não consegui identificar a plataforma StartBet ou o saldo.\n\n"
                f"Preciso de um screenshot da StartBet mostrando seu saldo.\n"
                f"📸 Tenta tirar um print mais claro e manda de novo!"
            )
            return

        saldo_float = 0.0
        match = re.search(r'(\d+[.,]\d{2})', str(msg_resultado))
        if match:
            saldo_float = float(match.group(1).replace(',', '.'))

        log.info(f"[VALIDACAO] Saldo extraído: {saldo_float}")

        # --- LOGIC: REGISTRATION (0.00) ---
        if estado_atual == WAITING_FOR_REGISTRATION_PRINT:
            if saldo_float <= 1.0: 
                await update.message.reply_text(
                    "- Perfeito, vi que você já criou sua conta, Mas vi que sua conta ainda está sem saldo.\n\n"
                    "👉 **Faça um depósito (mínimo R$ 20,00)** e me mande o print do saldo atualizado para eu liberar seu acesso!"
                )
                await send_video_if_exists(update, "ronaldin-video-3-fiTl.mp4")
                user_states[user.id] = WAITING_FOR_DEPOSIT_PRINT
            elif saldo_float >= 20.0:
                # User already deposited and skipped step 1!
                db.save_validation(user.id, saldo_float)
                await update.message.reply_text(
                    "🎉 **Show! Vi que você já tem conta com saldo!**\n\n"
                    "Aqui estão seus acessos liberados:\n\n"
                    f"📲 **App:** {LINK_APP}\n"
                    f"💬 **Grupo:** {LINK_GRUPO}\n\n"
                    "Boas apostas!"
                )
                user_states.pop(user.id, None)
            else:
                await update.message.reply_text(
                    f"❌ O saldo mínimo para liberar é R$ 20,00. O seu print mostra R$ {saldo_float:.2f}.\n\n"
                    "Faça um depósito para completar o valor e mande o print novamente!"
                )
                user_states[user.id] = WAITING_FOR_DEPOSIT_PRINT

        # --- LOGIC: DEPOSIT (>20.00) ---
        elif estado_atual == WAITING_FOR_DEPOSIT_PRINT:
            if saldo_float >= 20.0:
                db.save_validation(user.id, saldo_float)
                await update.message.reply_text(
                    "🎉 **Show! Depósito confirmado.**\n\n"
                    "Aqui estão seus acessos liberados:\n\n"
                    f"📲 **App:** {LINK_APP}\n"
                    f"💬 **Grupo:** {LINK_GRUPO}\n\n"
                    "Boas apostas!"
                )
                user_states.pop(user.id, None)
            else:
                await update.message.reply_text(
                    f"❌ Ainda não identifiquei o saldo positivo (mínimo R$ 20,00). O seu print mostra R$ {saldo_float:.2f}.\n\n"
                    "Por favor, envie um print mostrando o saldo atualizado após o depósito."
                )

    except Exception as e:
        log.error(f"Erro ao processar foto: {e}")
        await update.message.reply_text("❌ Deu ruim ao processar a imagem. Tenta mandar de novo!")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == 'fluxo_startbet':
        is_validated, _ = db.is_user_validated(uid)
        if is_validated:
            await query.message.reply_text(
                f"✅ Você já tá validado! Acesso liberado 👇",
                reply_markup=get_main_buttons(is_vip=True)
            )
        else:
            user_states[uid] = WAITING_FOR_REGISTRATION_PRINT
            await query.message.reply_text(
                "Maravilha! 🚀\n\n"
                "Só um detalhe importante: para acessar o app, você vai usar o mesmo login e senha da plataforma StartBet, porque o aplicativo é 100% integrado a ela.\n\n"
                "Então é bem simples: crie sua conta na StartBet e me envie o print confirmando o cadastro. Assim que mandar, libero seu acesso ao app 👊\n"
                f"🔗 Link de cadastro: {LINK_CADASTRO}"
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'Conflict' in str(context.error):
        log.warning("Detected 409 Conflict! Another instance is stealing messages. Retrying in 10s...")
    else:
        log.error(f"Erro no handler principal: {context.error}", exc_info=context.error)

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Você: {user.id} - {user.first_name} (@{user.username})")

def main():
    log.info("Iniciando Bot StartBet...")
    
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_TOKEN não configurado!")
        sys.exit(1)

    # Force connection resilience
    request = HTTPXRequest(http_version="1.1", connect_timeout=10.0, read_timeout=10.0)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()
    
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('ping', cmd_ping))
    app.add_handler(CommandHandler('whoami', cmd_whoami))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)
    
    log.info('BOT CONECTADO E POLLING!')
    
    while True:
        try:
            # We explicitly drop_pending_updates=True to forcefully clear any backlogged corrupted queue that could be quietly hanging the updates loop.
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
            break
        except Exception as e:
            if 'Conflict' in str(e):
                log.error("CRITICAL: 409 Conflict hit. Sleeping 15s to let the other instance die...")
                time.sleep(15)
            else:
                log.error(f"Polling crashed: {e}. Retrying in 5s...")
                time.sleep(5)

if __name__ == '__main__':
    main()