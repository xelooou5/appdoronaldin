import os
import asyncio
import logging
import io
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from PIL import Image
import openai
import google.generativeai as genai  # Correct Gemini import
# Database
from database import Database

# --- PYTHON VERSION CHECK ---
import sys
if sys.version_info < (3, 8):
    print("[ERROR] Python 3.8+ is required. Current version:", sys.version)
    exit(1)

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CODEGEEX_API_KEY = os.getenv("CODEGEEX_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

 # Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Setup AI Clients
# Gemini model setup for google-generativeai (correct API)
gemini_model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        gemini_model = None
        logger.error("[Gemini] Initialization failed: %s", e)
else:
    gemini_model = None

if OPENAI_API_KEY:
    openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None


# States
WAITING_FOR_YES = 1
WAITING_FOR_REGISTRATION_PRINT = 2
WAITING_FOR_DEPOSIT_PRINT = 3

# Links
LINK_CADASTRO = "https://start.bet.br/signup?btag=CX-48705_445081"
LINK_APP = "https://appdoronaldin.com.br/"
LINK_GRUPO = "https://t.me/+8imjlHQtZTE1MjYx"

# Initialize Database
db = Database()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Register/Update user in DB
    db.create_or_update_user(user.id, user.username or "", user.first_name)
    user_data = db.get_user(user.id)
    
    # Check if VIP
    if user_data and user_data['is_vip']:
         await update.message.reply_text(
            f"Fala {user.first_name}! Você já tem acesso liberado! 🚀\n\n"
            f"👇 Seus links exclusivos:\n"
            f"📱 APP: {LINK_APP}\n"
            f"💬 Grupo VIP: {LINK_GRUPO}"
        )
         return ConversationHandler.END

    # Cancel any existing warning jobs for this user
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id) + "_2min")
    for job in current_jobs:
        job.schedule_removal()
    
    await update.message.reply_text(
        "Opa! Tudo certo? Quer acesso ao app e ao grupo gratuito de sinais?"
    )
    
    # Schedule warning message after 2 minutes
    context.job_queue.run_once(
        send_warning_2min, 
        120, 
        chat_id=chat_id,
        name=str(chat_id) + "_2min",
        data=chat_id
    )
    
    return WAITING_FOR_YES

async def send_warning_2min(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data
    await context.bot.send_message(
        chat_id=chat_id, 
        text="⚠️ Aviso importante:\nO app começará a ser pago a partir de amanhã.\nHoje é sua última chance de garantir acesso gratuito.\nQuer acesso ao app?"
    )

async def handle_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.lower()
    
    # Cancel the 2 min warning job if it exists
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id) + "_2min")
    for job in current_jobs:
        job.schedule_removal()

    if any(w in text for w in ['sim', 'quero', 's', 'claro', 'bora']):
        # Send videos if they exist in the current directory
        try:
            if os.path.exists("ronaldin-video-1-AD6f.mp4"):
                 await update.message.reply_video(video=open("ronaldin-video-1-AD6f.mp4", 'rb'))
        except Exception as e:
            logger.error("Failed to send video: %s", e)

        await update.message.reply_text(
            "Só um detalhe importante: para acessar o app, você vai usar o mesmo login e senha da plataforma StartBet, porque o aplicativo é 100% integrado a ela.\n\n"
            "Então é bem simples: crie sua conta na StartBet e me envie o print confirmando o cadastro. Assim que mandar, libero seu acesso ao app 👊\n"
            f"Link de cadastro: {LINK_CADASTRO}"
        )
        
        # Update DB step
        db.set_user_step(chat_id, WAITING_FOR_REGISTRATION_PRINT)

        # Schedule warning after 5 minutes
        context.job_queue.run_once(
            send_warning_5min, 
            300, 
            chat_id=chat_id,
            name=str(chat_id) + "_5min",
            data=chat_id
        )
        return WAITING_FOR_REGISTRATION_PRINT
    else:
        await update.message.reply_text("Responda com 'sim' para continuar.")
        return WAITING_FOR_YES

async def send_warning_5min(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data
    await context.bot.send_message(
        chat_id=chat_id, 
        text=f"Ainda não se cadastrou? Entre no grupo para acompanhar as lives: {LINK_GRUPO}"
    )

# Multi-AI image analysis abstraction
async def multi_ai_analyze_image(image_bytes, prompt):
    logger.info("[AI] Starting multi-AI image analysis...")
    
    # Try Gemini FIRST (Best for vision)
    if gemini_model:
        try:
            logger.info("[AI] Trying Gemini...")
            loop = asyncio.get_running_loop()
            image = Image.open(io.BytesIO(image_bytes))
            response = await loop.run_in_executor(None, lambda: gemini_model.generate_content([prompt, image]))
            if response and hasattr(response, 'text') and response.text:
                logger.info("[AI] Gemini succeeded.")
                return response.text
        except Exception as e:
            logger.error("Gemini failed: %s", e)

    # Try OpenAI (GPT-4o) as fallback
    if openai_client:
        try:
            logger.info("[AI] Trying OpenAI...")
            import base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
                max_tokens=300,
            )
            logger.info("[AI] OpenAI succeeded.")
            return response.choices[0].message.content
        except Exception as e:
            logger.error("OpenAI failed: %s", e)
            
    logger.warning("[AI] All AI fallbacks failed.")
    return None

# Admin/manual override command
async def admin_override(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if str(chat_id) in os.getenv("ADMIN_IDS", "").split(","):
        db.set_vip(chat_id, True)
        await update.message.reply_text("Override: acesso liberado manualmente pelo admin.")
        await update.message.reply_text(
            f"📲 Link de acesso ao app: {LINK_APP}\n"
            f"💬 Link do grupo do Telegram (lives): {LINK_GRUPO}\n\n"
            "Boas apostas!"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("Você não tem permissão para usar este comando.")
        return ConversationHandler.END

async def handle_registration_print(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Cancel the 5 min warning job if it exists
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id) + "_5min")
    for job in current_jobs:
        job.schedule_removal()

    if not update.message.photo:
        await update.message.reply_text("Por favor, envie o print da tela de cadastro.")
        return WAITING_FOR_REGISTRATION_PRINT

    processing_msg = await update.message.reply_text("Analisando seu print, aguarde um momento...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        prompt = (
            "Você é um assistente verificando prints de cadastro em casas de apostas. "
            "Analise a imagem e responda 'VALIDO' se parecer um print de uma conta logada na plataforma m.start.bet.br, "
            "com o link m.start.bet.br visível no topo ou embaixo da tela (dependendo do celular), e saldo 0,00 (ou próximo de zero) "
            "no mesmo lugar que aparece na LuckBet. Responda 'INVALIDO' se não parecer uma conta logada, se o link não estiver visível, "
            "ou se for algo totalmente diferente."
        )

        result = await multi_ai_analyze_image(image_bytes, prompt)

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
        except:
            pass

        if result and "VALIDO" in result.upper():
            await update.message.reply_text(
                "Perfeito, vi que você já criou sua conta.\n"
                "Mas vi que sua conta ainda está sem saldo.\n\n"
                "Para ativar o app e copiar os sinais, você precisa ter saldo na corretora.\n"
                "Faça um depósito (mínimo R$ 20,00) e me mande o print do saldo atualizado para eu liberar seu acesso!"
            )
            # Send tutorial video for deposit
            try:
                if os.path.exists("ronaldin-video-3-fiTl.mp4"):
                    await update.message.reply_video(video=open("ronaldin-video-3-fiTl.mp4", 'rb'))
            except Exception as e:
                logger.error("Failed to send video: %s", e)

            db.set_user_step(chat_id, WAITING_FOR_DEPOSIT_PRINT)
            return WAITING_FOR_DEPOSIT_PRINT
        else:
            await update.message.reply_text(
                "Não consegui identificar o cadastro corretamente.\n"
                "Certifique-se de que o print mostra que você está logado na plataforma.\n"
                "Tente enviar novamente."
            )
            return WAITING_FOR_REGISTRATION_PRINT
    except Exception as e:
        logger.error("Error processing registration print: %s", e)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
    except:
        pass
    await update.message.reply_text("Ocorreu um erro ao processar a imagem. Tente novamente.")
    return WAITING_FOR_REGISTRATION_PRINT

async def handle_deposit_print(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Por favor, envie o print do saldo atualizado.")
        return WAITING_FOR_DEPOSIT_PRINT

    chat_id = update.effective_chat.id
    processing_msg = await update.message.reply_text("Conferindo seu depósito...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        prompt = (
            "Você é um assistente verificando prints de depósito em casas de apostas. "
            "Analise a imagem e responda 'VALIDO' se o print for da plataforma m.start.bet.br, com o link m.start.bet.br visível no topo ou embaixo da tela (dependendo do celular), "
            "e saldo maior que R$ 10,00 (positivo, acima de dez reais) no mesmo lugar que aparece na LuckBet. Responda 'INVALIDO' se o saldo for 10 ou menos, se o link não estiver visível, ou se não for possível identificar."
        )

        result = await multi_ai_analyze_image(image_bytes, prompt)

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
        except:
            pass

        if result and "VALIDO" in result.upper():
            db.set_vip(chat_id, True)
            await update.message.reply_text(
                "Show! Cadastro e depósito confirmados. Aqui estão seus acessos:\n\n"
                f"📲 Link de acesso ao app: {LINK_APP}\n"
                f"💬 Link do grupo do Telegram (lives): {LINK_GRUPO}\n\n"
                "Boas apostas!"
            )
             # Send final video
            try:
                if os.path.exists("ronaldin-video-4-2YrD.mp4"):
                    await update.message.reply_video(video=open("ronaldin-video-4-2YrD.mp4", 'rb'))
            except Exception as e:
                logger.error(f"Failed to send video: {e}")

            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "Ainda não identifiquei o saldo positivo. Por favor, envie um print mostrando o saldo atualizado após o depósito."
            )
            return WAITING_FOR_DEPOSIT_PRINT
    except Exception as e:
        logger.error("Error processing deposit print: %s", e)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
    except:
        pass
    await update.message.reply_text("Ocorreu um erro ao processar a imagem. Tente novamente.")
    return WAITING_FOR_DEPOSIT_PRINT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada. Digite /start para recomeçar.")
    return ConversationHandler.END

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("/ping received from %s", update.effective_user.id)
    await update.message.reply_text("pong")

async def catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("[CatchAll] Received update: %s", update)
    # Optionally reply to show activity
    # await update.message.reply_text("Mensagem recebida (catch-all handler)")

def main():
    print("[Startup] Checking environment variables...")
    print(f"TELEGRAM_TOKEN: {'set' if TELEGRAM_TOKEN else 'missing'}")
    print(f"GEMINI_API_KEY: {'set' if GEMINI_API_KEY else 'missing'}")
    print(f"GROQ_API_KEY: {'set' if GEMINI_API_KEY else 'missing'}")
    print(f"DEEPSEEK_API_KEY: {'set' if GEMINI_API_KEY else 'missing'}")
    print(f"CODEGEEX_API_KEY: {'set' if CODEGEEX_API_KEY else 'missing'}")
    print(f"OPENAI_API_KEY: {'set' if OPENAI_API_KEY else 'missing'}")

    if not TELEGRAM_TOKEN:
        print("[ERROR] TELEGRAM_TOKEN not found in .env file. Exiting.")
        exit(1)



    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add a global error handler
    async def error_handler(update, context):
        logger.error("Exception while handling an update:", exc_info=context.error)
        if update and hasattr(update, 'message') and update.message:
            await update.message.reply_text("Ocorreu um erro inesperado. Tente novamente mais tarde.")

    application.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_YES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_yes)],
            WAITING_FOR_REGISTRATION_PRINT: [MessageHandler(filters.PHOTO, handle_registration_print)],
            WAITING_FOR_DEPOSIT_PRINT: [MessageHandler(filters.PHOTO, handle_deposit_print)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("override", admin_override)],
    )
    application.add_handler(conv_handler)
    # Add /ping command for basic test
    application.add_handler(CommandHandler("ping", ping))
    # Add catch-all handler for diagnostics
    application.add_handler(MessageHandler(filters.ALL, catch_all))
    print("[Startup] Bot is running and polling...")
    logger.info("[Startup] Bot is running and polling...")
    try:
        application.run_polling()
    except Exception as e:
        if 'Conflict: terminated by other getUpdates request' in str(e):
            print("[ERROR] Telegram polling conflict: Another bot instance is running. Please ensure only one instance is active.\nIf you see this, check for other running bot processes locally, on Railway, or any other server.")
        else:
            print(f"[ERROR] Bot failed to start: {e}")
        exit(1)


if __name__ == "__main__":
    main()

