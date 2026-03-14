import os
import asyncio
import logging
import io
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from PIL import Image
# --- AI and HTTP ---
import openai
import requests
import base64
# Database
from database import Database

 # --- PYTHON VERSION CHECK ---
# Deployment trigger: 2026-03-13 - force redeploy for webhook mode test
import sys
import atexit
import tempfile
LOCKFILE_PATH = os.path.join(tempfile.gettempdir(), 'appronaldin_bot.lock')

def remove_lockfile():
    try:
        if os.path.exists(LOCKFILE_PATH):
            os.remove(LOCKFILE_PATH)
    except Exception as e:
        print(f"[ERROR] Could not remove lock file: {e}")
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

# New: Ecreasy and HuggingFace
ECREASY_API_KEY = os.getenv("ECREASY_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

 # Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Only OpenAI client setup

# OpenAI client setup
if OPENAI_API_KEY:
    openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None

# Gemini (google-genai) setup (for fallback only)
try:
    import google.genai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    else:
        gemini_model = None
except Exception:
    gemini_model = None


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

# Multi-AI image analysis abstraction (now OpenAI only)

# Modular multi-AI image analysis abstraction
async def multi_ai_analyze_image(image_bytes, prompt):
    logger.info("[AI] Starting multi-AI image analysis...")

    # 1. Ecreasy Vision API (https://ecreasy.com/vision-api/)
    if ECREASY_API_KEY:
        try:
            logger.info("[AI] Trying Ecreasy Vision API...")
            ecreasy_url = "https://api.ecreasy.com/v1/vision/ocr"
            files = {"image": ("image.jpg", image_bytes, "image/jpeg")}
            headers = {"Authorization": f"Bearer {ECREASY_API_KEY}"}
            data = {"prompt": prompt}
            resp = requests.post(ecreasy_url, headers=headers, files=files, data=data, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                if "result" in result and result["result"]:
                    logger.info("[AI] Ecreasy succeeded.")
                    return result["result"]
            logger.warning(f"[AI] Ecreasy failed: {resp.text}")
        except Exception as e:
            logger.error(f"Ecreasy Vision API failed: {e}")

    # 2. HuggingFace Inference API (e.g., BLIP, TrOCR, Donut)
    if HUGGINGFACE_API_KEY:
        try:
            logger.info("[AI] Trying HuggingFace Inference API...")
            hf_url = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"
            headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
            resp = requests.post(hf_url, headers=headers, data=image_bytes, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                # BLIP returns a list of dicts with 'generated_text'
                if isinstance(result, list) and result and "generated_text" in result[0]:
                    logger.info("[AI] HuggingFace succeeded.")
                    return result[0]["generated_text"]
            logger.warning(f"[AI] HuggingFace failed: {resp.text}")
        except Exception as e:
            logger.error(f"HuggingFace Inference API failed: {e}")

    # 3. OpenAI Vision (GPT-4o)
    if openai_client:
        try:
            logger.info("[AI] Trying OpenAI...")
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

    # 4. Gemini (Google GenAI) as backup only
    if gemini_model:
        try:
            logger.info("[AI] Trying Gemini (backup)...")
            import io as _io
            image = Image.open(_io.BytesIO(image_bytes))
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: gemini_model.generate_content([prompt, image]))
            if response and hasattr(response, 'text') and response.text:
                logger.info("[AI] Gemini succeeded.")
                return response.text
        except Exception as e:
            logger.error("Gemini failed: %s", e)

    logger.warning("[AI] All AI image analysis services failed.")
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


async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only diagnostic: returns getWebhookInfo from Telegram."""
    user_id = update.effective_user.id
    admin_ids = [s for s in os.getenv("ADMIN_IDS", "").split(",") if s]
    if str(user_id) not in admin_ids:
        await update.message.reply_text("Você não tem permissão para usar este comando.")
        return
    try:
        tg_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        resp = requests.post(tg_base + "/getWebhookInfo", timeout=10)
        text = resp.text
    except Exception as e:
        text = f"Failed to getWebhookInfo: {e}"
    # Telegram messages have length limits; if long, truncate and offer to check logs
    if len(text) > 3500:
        text = text[:3500] + "\n...[truncated]"
    await update.message.reply_text(f"/diag result:\n{text}")

async def catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Try to produce a compact representation of the update for logs
        upd_repr = None
        if hasattr(update, 'to_dict'):
            upd_repr = update.to_dict()
        else:
            upd_repr = str(update)
    except Exception:
        upd_repr = str(update)
    logger.debug("[CatchAll] Received update: %s", upd_repr)
    # Diagnostic reply to confirm handler is active and webhook is delivering updates
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("[DEBUG] Mensagem recebida pelo catch-all handler. O bot está online e recebeu sua mensagem.")
        else:
            logger.info("[CatchAll] Update received without message field: %s", update)
    except Exception:
        logger.exception("[CatchAll] Failed to send diagnostic reply")

def main():
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

    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    # Prefer the platform-provided PORT (Railway sets PORT). Fall back to WEBHOOK_PORT or 8443.
    WEBHOOK_PORT = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8443")))
    # Normalize path (ensure leading slash for printing, but run_webhook wants path without leading slash)
    raw_path = os.getenv("WEBHOOK_PATH", f"/webhook/{TELEGRAM_TOKEN}")
    WEBHOOK_PATH = raw_path if raw_path.startswith("/") else "/" + raw_path

    # --- LOCK FILE CHECK ---
    try:
        if os.path.exists(LOCKFILE_PATH):
            print(f"[ERROR] Lock file found at {LOCKFILE_PATH}. Another instance may be running.\nIf you are sure no other instance is running, run: python bot_start.py --remove-lockfile\nThen try again.")
            exit(1)
        with open(LOCKFILE_PATH, 'w') as lockfile:
            lockfile.write(str(os.getpid()))
        atexit.register(remove_lockfile)
    except Exception as e:
        print(f"[ERROR] Could not create lock file: {e}")
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
    application.add_handler(CommandHandler("diag", diag))
    # Add catch-all handler for diagnostics
    application.add_handler(MessageHandler(filters.ALL, catch_all))

    # --- Startup diagnostics: verify Telegram token and webhook info ---
    def check_telegram_webhook():
        try:
            tg_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
            resp_getme = requests.post(tg_base + "/getMe", timeout=10)
            logger.info("[StartupDiag] getMe status: %s %s", resp_getme.status_code, resp_getme.text)
        except Exception as e:
            logger.exception("[StartupDiag] getMe failed: %s", e)
        try:
            resp_wh = requests.post(tg_base + "/getWebhookInfo", timeout=10)
            logger.info("[StartupDiag] getWebhookInfo status: %s %s", resp_wh.status_code, resp_wh.text)
        except Exception as e:
            logger.exception("[StartupDiag] getWebhookInfo failed: %s", e)

    # Run diagnostics synchronously before starting the webhook server (helps debug misconfig)
    try:
        check_telegram_webhook()
    except Exception:
        logger.exception("[StartupDiag] Unexpected error while checking Telegram API")

    def send_startup_message(text: str):
        """Send a startup message to ADMIN_NOTIFY_ID or first ADMIN_IDS if configured."""
        admin_id = os.getenv("ADMIN_NOTIFY_ID")
        if not admin_id:
            admin_ids = [s for s in os.getenv("ADMIN_IDS", "").split(",") if s]
            admin_id = admin_ids[0] if admin_ids else None
        if not admin_id:
            logger.debug("[StartupNotify] No admin id configured; skipping startup notification")
            return
        try:
            tg_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
            resp = requests.post(tg_base + "/sendMessage", json={"chat_id": admin_id, "text": text}, timeout=10)
            logger.info("[StartupNotify] sendMessage status: %s %s", resp.status_code, resp.text)
        except Exception as e:
            logger.exception("[StartupNotify] Failed to send startup message: %s", e)

    if WEBHOOK_URL:
        # run_webhook expects url_path without leading slash
        url_path = WEBHOOK_PATH.lstrip('/')
        webhook_full_url = WEBHOOK_URL.rstrip('/') + '/' + url_path
        print(f"[Startup] Webhook mode enabled. URL: {webhook_full_url} (listening on port {WEBHOOK_PORT})")
        logger.info(f"[Startup] Webhook mode enabled. URL: {webhook_full_url} (listening on port {WEBHOOK_PORT})")
        try:
            # Note: do not call Telegram setWebhook here to avoid racing with the server startup.
            # The Application.run_webhook(...) call will register the webhook when the server is ready.

            # Re-check webhook info and decide whether to run webhook or fall back to polling.
            try:
                tg_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
                resp_wh = requests.post(tg_base + "/getWebhookInfo", timeout=10)
                wh_json = resp_wh.json() if resp_wh is not None else {}
            except Exception as e:
                logger.exception("[StartupDiag] Failed to re-check getWebhookInfo: %s", e)
                wh_json = {}

            wh_result = wh_json.get('result', {}) if isinstance(wh_json, dict) else {}
            wh_url = wh_result.get('url', '')
            # Consider any last error/message/date as a sign webhook may be unreliable
            last_error_msg = None
            last_error_date = None
            if isinstance(wh_result, dict):
                last_error_msg = wh_result.get('last_error_message') or wh_result.get('last_synchronization_error_message')
                last_error_date = wh_result.get('last_error_date') or wh_result.get('last_synchronization_error_date')

            # If Telegram isn't pointing to our webhook URL or there is any recorded sync error/date, fall back to polling.
            if not wh_url or wh_url.rstrip('/') != webhook_full_url.rstrip('/') or last_error_msg or last_error_date:
                logger.warning("[StartupDiag] Webhook not usable (url=%s, last_error_msg=%s, last_error_date=%s). Falling back to polling.", wh_url, last_error_msg, last_error_date)
                print("[Startup] Webhook appears misconfigured or failing; falling back to polling mode.")
                # delete webhook to ensure polling can start without conflict
                try:
                    tg_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
                    requests.post(tg_base + "/deleteWebhook", timeout=10)
                except Exception:
                    logger.exception("[StartupDiag] Failed to delete webhook before polling fallback")
                send_startup_message("Bot starting in polling mode due to webhook issues.")
                application.run_polling()
                return

            # Otherwise run webhook as planned (and notify admin)
            send_startup_message(f"Bot starting in webhook mode. URL: {webhook_full_url}")
            application.run_webhook(
                listen="0.0.0.0",
                port=WEBHOOK_PORT,
                url_path=url_path,
                webhook_url=webhook_full_url,
                max_connections=40,
                drop_pending_updates=False,
            )
        except Exception as e:
            print(f"[ERROR] Bot failed to start in webhook mode: {e}")
            logger.exception("Bot failed to start in webhook mode")
            # If webhook startup fails, try polling as a last resort
            try:
                logger.info("[StartupDiag] Attempting to start in polling mode as fallback")
                application.run_polling()
            except Exception as e2:
                logger.exception("[StartupDiag] Polling fallback also failed: %s", e2)
                exit(1)
    else:
        print("[Startup] Bot is running and polling...")
        logger.info("[Startup] Bot is running and polling...")
        try:
            application.run_polling()
        except Exception as e:
            if 'Conflict: terminated by other getUpdates request' in str(e):
                print("[ERROR] Telegram polling conflict: Another bot instance is running. Please ensure only one instance is active.\nIf you see this, check for other running bot processes locally, on Railway, or any other server.\n\nIf you are sure no other instance is running, try removing the lock file and restarting.")
            else:
                print(f"[ERROR] Bot failed to start: {e}")
            remove_lockfile()
            exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--remove-lockfile":
        remove_lockfile()
        print(f"Lock file {LOCKFILE_PATH} removed.")
    else:
        main()

