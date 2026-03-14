import os
import logging
import re
import pytesseract
from PIL import Image, ImageEnhance

log = logging.getLogger(__name__)

async def validar_print(image_path: str) -> tuple[bool, str]:
    """Valida StartBet/Luck-like prints and returns (is_valid, message_or_value).
    Adapted from the working bot's validador_vision.py.
    """
    try:
        img = Image.open(image_path)
        width, height = img.size

        # Improve contrast for better OCR
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(1.5)

        # Read top (URL area) and middle (balance area)
        img_topo = img_enhanced.crop((0, 0, width, min(400, height)))
        img_meio = img_enhanced.crop((0, int(height * 0.15), width, int(height * 0.65)))

        texto_topo = pytesseract.image_to_string(img_topo, lang='por+eng', config='--psm 6')
        texto_meio = pytesseract.image_to_string(img_meio, lang='por+eng', config='--psm 6')
        texto_full = pytesseract.image_to_string(img_enhanced, lang='por+eng', config='--psm 6')

        texto_completo = f"{texto_topo}\n{texto_meio}\n{texto_full}"
        texto_upper = texto_completo.upper()
        texto_lower = texto_completo.lower()

        log.info(f"[OCR] Texto topo:\n{texto_topo[:300]}")
        log.info(f"[OCR] Texto meio:\n{texto_meio[:300]}")

        # === Validate platform (StartBet / Luck-like) ===
        patterns = [
            'start.bet', 'm.start.bet', 'start bet', 'startbet',
            'luck.bet', 'm.luck.bet', 'luck bet', 'luckbet'
        ]
        is_platform = any(p in texto_lower for p in patterns)

        if not is_platform:
            # Fallback: look for keywords
            is_platform = 'START' in texto_upper or 'LUCK' in texto_upper

        if not is_platform:
            log.warning("[OCR] Plataforma StartBet/Luck não encontrada no print")
            return False, "Não é da plataforma StartBet/Luck"

        log.info("[OCR] ✅ Plataforma detectada")

        # === Find monetary amounts ===
        numeros = re.findall(r'R?\$?\s*(\d{1,3}(?:\.\d{3})*)[.,](\d{2})', texto_completo)
        numeros += re.findall(r'(\d+)[.,](\d{2})', texto_completo)

        log.info(f"[OCR] Números encontrados: {numeros}")
        if not numeros:
            log.warning("[OCR] Nenhum valor monetário encontrado")
            return False, "Saldo não identificado na imagem"

        valores_unicos = set()
        for n in numeros:
            inteiro = n[0].replace('.', '')
            try:
                valor = float(f"{inteiro}.{n[1]}")
            except Exception:
                continue
            valores_unicos.add(valor)

        valores = sorted(valores_unicos, reverse=True)
        log.info(f"[OCR] Valores convertidos: {valores}")

        if not valores:
            return False, "Saldo não identificado na imagem"

        # For StartBet flow, we may want to detect 0.00 or > threshold; caller decides threshold
        saldo = max(valores)
        log.info(f"[OCR] Saldo detectado: R${saldo:.2f}")
        return True, f"R${saldo:.2f}"

    except ImportError as e:
        log.error(f"[ERRO] Dependência faltando: {e}")
        return False, "Erro de configuração do OCR"
    except Exception as e:
        log.error(f"[ERRO] {e}")
        return False, "Erro ao processar imagem"