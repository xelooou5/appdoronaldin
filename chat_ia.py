import os
import logging
from typing import Optional
import aiohttp

log = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
GEMINI_KEYS = [k for k in [os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_API_KEY_2'), os.getenv('GEMINI_API_KEY_3')] if k]


class ChatIA:
    def __init__(self):
        pass

    def get_system_prompt(self):
        return (
            "Você é um assistente do StartBet/Ronaldo. Responda de forma natural em português, "
            "curto e direto. Seja útil, educado e objetivo."
        )

    async def responder_groq(self, prompt: str) -> Optional[str]:
        if not GROQ_API_KEY:
            return None
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.8
            }
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            log.warning(f"[GROQ] Erro: {str(e)[:200]}")
        return None

    async def responder_deepseek(self, prompt: str) -> Optional[str]:
        if not DEEPSEEK_API_KEY:
            return None
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.8
            }
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            log.warning(f"[DEEPSEEK] Erro: {str(e)[:200]}")
        return None

    async def responder_gemini(self, prompt: str) -> Optional[str]:
        for i, key in enumerate(GEMINI_KEYS):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": self.get_system_prompt()}, {"text": prompt}]}]
                }
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data['candidates'][0]['content']['parts'][0]['text'].strip()
                        elif resp.status == 429:
                            log.warning(f"[GEMINI-{i+1}] Quota excedida")
                            continue
            except Exception as e:
                log.warning(f"[GEMINI-{i+1}] Erro: {str(e)[:200]}")
                continue
        return None

    async def responder(self, pergunta: str) -> str:
        log.info(f"[IA] Pergunta: {pergunta}")
        for nome, metodo in [("GROQ", self.responder_groq), ("DEEPSEEK", self.responder_deepseek), ("GEMINI", self.responder_gemini)]:
            log.info(f"[IA] Tentando {nome}...")
            try:
                resposta = await metodo(pergunta)
            except Exception as e:
                log.warning(f"[IA {nome}] Exception: {e}")
                resposta = None
            if resposta and len(resposta) > 10:
                log.info(f"[IA] ✅ {nome} respondeu")
                return resposta
        log.error("[IA] Todas as IAs falharam")
        return "Desculpa, tive um problema técnico. Tenta de novo!"


chat_ia = ChatIA()

