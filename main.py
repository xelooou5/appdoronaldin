import threading
import os
import asyncio
import logging
import io
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import google.generativeai as genai
from PIL import Image
import openai

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CODEGEEX_API_KEY = os.getenv("CODEGEEX_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

 # Setup AI Clients
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None

if OPENAI_API_KEY:
    openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
WAITING_FOR_YES = 1
WAITING_FOR_REGISTRATION_PRINT = 2
WAITING_FOR_DEPOSIT_PRINT = 3

# Links
LINK_CADASTRO = "https://start.bet.br/signup?btag=CX-48705_445081"
LINK_APP = "https://appdoronaldin.com.br/"
LINK_GRUPO = "https://t.me/+8imjlHQtZTE1MjYx"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
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

    if 'sim' in text or 'quero' in text or 's' in text or 'claro' in text:
        # Send videos if they exist in the current directory
        video_files = [
            "ronaldin-video-1-AD6f.mp4",
            "ronaldin-video-3-fiTl.mp4",
            "ronaldin-video-4-2YrD.mp4"
        ]
        
        # We can send one of them as a "tutorial" or "intro" video if desired.
        # For now, let's just send the first one as an example if it exists, 
        # but wrapped in a try/except so it doesn't crash if file is missing or too large.
        try:
            if os.path.exists("ronaldin-video-1-AD6f.mp4"):
                 await update.message.reply_video(video=open("ronaldin-video-1-AD6f.mp4", 'rb'))
        except Exception as e:
            logger.error(f"Failed to send video: {e}")

        await update.message.reply_text(
            "Só um detalhe importante: para acessar o app, você vai usar o mesmo login e senha da plataforma StartBet, porque o aplicativo é 100% integrado a ela.\n\n"
            "Então é bem simples: crie sua conta na StartBet e me envie o print confirmando o cadastro. Assim que mandar, libero seu acesso ao app 👊\n"
            f"Link de cadastro: {LINK_CADASTRO}"
        )
        
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
    # Try Gemini first
    if gemini_model:
        try:
            logger.info("[AI] Trying Gemini...")
            loop = asyncio.get_running_loop()
            image = Image.open(io.BytesIO(image_bytes))
            response = await loop.run_in_executor(None, lambda: gemini_model.generate_content([prompt, image]))
            if response and response.text:
                logger.info("[AI] Gemini succeeded.")
                return response.text
        except Exception as e:
            logger.error(f"Gemini failed: {e}")

    # Try OpenAI
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
            logger.error(f"OpenAI failed: {e}")
    # Try Groq (if API key provided)
    if GROQ_API_KEY:
        try:
            logger.info("[AI] Trying Groq...")
            # Placeholder for Groq image analysis
            pass
        except Exception as e:
            logger.error(f"Groq failed: {e}")
    # Try DeepSeek (if API key provided)
    if DEEPSEEK_API_KEY:
        try:
            logger.info("[AI] Trying DeepSeek...")
            # Placeholder for DeepSeek image analysis
            pass
        except Exception as e:
            logger.error(f"DeepSeek failed: {e}")
    # Try CodeGeeX (if API key provided)
    if CODEGEEX_API_KEY:
        try:
            logger.info("[AI] Trying CodeGeeX...")
            # Placeholder for CodeGeeX image analysis
            pass
        except Exception as e:
            logger.error(f"CodeGeeX failed: {e}")
    logger.warning("[AI] All AI fallbacks failed.")
    return None
# Admin/manual override command
async def admin_override(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if str(chat_id) in os.getenv("ADMIN_IDS", "").split(","):
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
            return WAITING_FOR_DEPOSIT_PRINT
        else:
            await update.message.reply_text(
                "Não consegui identificar o cadastro corretamente.\n"
                "Certifique-se de que o print mostra que você está logado na plataforma.\n"
                "Tente enviar novamente."
            )
            return WAITING_FOR_REGISTRATION_PRINT
    except Exception as e:
        logger.error(f"Error processing registration print: {e}")
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
            "e saldo maior que 0 (positivo) no mesmo lugar que aparece na LuckBet. Responda 'INVALIDO' se o saldo for 0, se o link não estiver visível, ou se não for possível identificar."
        )
        
        result = await multi_ai_analyze_image(image_bytes, prompt)
        
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
        except:
            pass
        
        if result and "VALIDO" in result.upper():
            await update.message.reply_text(
                "Show! Cadastro e depósito confirmados. Aqui estão seus acessos:\n\n"
                f"📲 Link de acesso ao app: {LINK_APP}\n"
                f"💬 Link do grupo do Telegram (lives): {LINK_GRUPO}\n\n"
                "Boas apostas!"
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "Ainda não identifiquei o saldo positivo. Por favor, envie um print mostrando o saldo atualizado após o depósito."
            )
            return WAITING_FOR_DEPOSIT_PRINT
    except Exception as e:
        logger.error(f"Error processing deposit print: {e}")
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
        except:
            pass
        await update.message.reply_text("Ocorreu um erro ao processar a imagem. Tente novamente.")
        return WAITING_FOR_DEPOSIT_PRINT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada. Digite /start para recomeçar.")
    return ConversationHandler.END

def main():
    # Heartbeat function to keep Railway build alive
    def heartbeat():
        import time
        while True:
            print("[Heartbeat] Bot alive")
            time.sleep(30)

    # Start heartbeat in a background thread
    threading.Thread(target=heartbeat, daemon=True).start()
    print("[Startup] Checking environment variables...")
    print(f"TELEGRAM_TOKEN: {'set' if TELEGRAM_TOKEN else 'missing'}")
    print(f"GEMINI_API_KEY: {'set' if GEMINI_API_KEY else 'missing'}")
    print(f"GROQ_API_KEY: {'set' if GROQ_API_KEY else 'missing'}")
    print(f"DEEPSEEK_API_KEY: {'set' if DEEPSEEK_API_KEY else 'missing'}")
    print(f"CODEGEEX_API_KEY: {'set' if CODEGEEX_API_KEY else 'missing'}")
    print(f"OPENAI_API_KEY: {'set' if OPENAI_API_KEY else 'missing'}")

    if not TELEGRAM_TOKEN:
        print("[ERROR] TELEGRAM_TOKEN not found in .env file. Exiting.")
        exit(1)

    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()

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

        print("[Startup] Bot is running and polling...")
        application.run_polling()
    except Exception as e:
        print(f"[ERROR] Bot failed to start: {e}")
        exit(1)

if __name__ == "__main__":
    main()
