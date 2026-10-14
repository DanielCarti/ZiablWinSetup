"""
ZiablWinSetup — Модуль интеграции с VirusTotal API (v3).
Позволяет пользователю мгновенно проверять подозрительные файлы и инсталляторы
по SHA-256 хэшу и 70+ антивирусным движкам через официальный бесплатный API ключ.
"""

import os
import sys
import json
import re
import time
import uuid
import hashlib
import logging
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from app.settings import get_virustotal_api_key, set_virustotal_api_key

logger = logging.getLogger("WinSetup")

VT_API_BASE = "https://www.virustotal.com/api/v3"
MAX_UPLOAD_SIZE = 32 * 1024 * 1024  # 32 МБ для бесплатного публичного эндпоинта


def validate_virustotal_api_key(api_key: str, lang: str = "ru") -> tuple[bool, str]:
    """
    Проверяет формат ключа VirusTotal и делает контрольный запрос к API.
    Официальный ключ VirusTotal v3 состоит ровно из 64 шестнадцатеричных символов.
    """
    key = (api_key or "").strip()
    if not key:
        msg = "Ключ API не может быть пустым." if lang == "ru" else "API key cannot be empty."
        return False, msg

    if len(key) != 64 or not re.match(r"^[a-fA-F0-9]{64}$", key):
        msg = (
            "Неверный формат ключа VirusTotal. Официальный API ключ должен состоять ровно из 64 шестнадцатеричных символов (0-9, a-f)."
            if lang == "ru"
            else "Invalid VirusTotal API key format. Official API key must be exactly 64 hexadecimal characters (0-9, a-f)."
        )
        return False, msg

    # Проверка ключа запросом к VirusTotal API
    try:
        url = f"{VT_API_BASE}/users/current"
        req = urllib.request.Request(
            url,
            headers={
                "x-apikey": key,
                "User-Agent": "ZiablWinSetup/1.4.21",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, ""
    except urllib.error.HTTPError as e:
        if e.code == 401:
            msg = (
                "Ключ отклонен сервисом VirusTotal (ошибка 401: неверный или неактивный ключ). Проверьте ключ в личном кабинете virustotal.com."
                if lang == "ru"
                else "Key rejected by VirusTotal (401 Unauthorized: invalid or inactive key). Please check your key at virustotal.com."
            )
            return False, msg
    except Exception as e:
        logger.debug(f"VT key network validation check (non-fatal): {e}")

    return True, ""


def format_file_size(size_bytes: int) -> str:
    """Форматирует размер файла в удобочитаемый вид (КБ, МБ, ГБ)."""
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} КБ"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} МБ"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} ГБ"


def calculate_file_sha256(filepath: str | Path) -> tuple[str, int]:
    """
    Вычисляет SHA-256 хэш файла потоково без загрузки всего файла в память.
    Возвращает кортеж (хэш_в_нижнем_регистре, размер_в_байтах).
    """
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError(f"Файл не найден: {filepath}")

    h = hashlib.sha256()
    size = 0
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest().lower(), size


def _build_multipart_payload(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    """Формирует multipart/form-data тело для HTTP запроса без внешних библиотек."""
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    for field_name, (filename, file_bytes) in files.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type


def scan_file_by_path(filepath: str | Path, api_key: str | None = None) -> dict[str, Any]:
    """
    Проверяет файл в VirusTotal по его SHA-256 хэшу.
    Если файл уже есть в базе — мгновенно возвращает вердикт и результаты по всем антивирусам.
    Если файла нет — возвращает статус 'found: False' с возможностью отправки.
    """
    path_obj = Path(filepath)
    if not path_obj.is_file():
        return {
            "success": False,
            "error_type": "file_not_found",
            "message": f"Файл не найден на диске: {filepath}"
        }

    key = (api_key or get_virustotal_api_key()).strip()
    if not key:
        return {
            "success": False,
            "error_type": "no_key",
            "message": "Для сканирования требуется бесплатный API ключ VirusTotal. Укажите его в поле ниже."
        }

    try:
        sha256_hash, file_size = calculate_file_sha256(path_obj)
    except Exception as e:
        return {
            "success": False,
            "error_type": "hash_error",
            "message": f"Не удалось прочитать файл и вычислить хэш: {e}"
        }

    url = f"{VT_API_BASE}/files/{sha256_hash}"
    req = urllib.request.Request(
        url,
        headers={
            "x-apikey": key,
            "User-Agent": "ZiablWinSetup/1.4.21",
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return _parse_vt_file_response(data, sha256_hash, path_obj.name, file_size)

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "success": True,
                "found": False,
                "sha256": sha256_hash,
                "file_name": path_obj.name,
                "file_path": str(path_obj.resolve()),
                "file_size": file_size,
                "file_size_formatted": format_file_size(file_size),
                "can_upload": file_size <= MAX_UPLOAD_SIZE,
                "message": "Данный файл ранее не исследовался в VirusTotal (хэш отсутствует в базе). Вы можете отправить его на сканирование."
            }
        elif e.code == 401:
            return {
                "success": False,
                "error_type": "invalid_key",
                "message": "Неверный API ключ VirusTotal. Пожалуйста, проверьте и обновите ключ."
            }
        elif e.code == 429:
            return {
                "success": False,
                "error_type": "rate_limit",
                "message": "Превышен лимит запросов VirusTotal (бесплатный тариф: до 4 запросов в минуту и до 500 в день). Подождите 1 минуту."
            }
        else:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            return {
                "success": False,
                "error_type": f"http_{e.code}",
                "message": f"Ошибка сервера VirusTotal (HTTP {e.code}): {err_body or e.reason}"
            }
    except Exception as e:
        logger.error(f"VirusTotal scan error: {e}")
        return {
            "success": False,
            "error_type": "network_error",
            "message": f"Ошибка сетевого соединения с VirusTotal: {e}"
        }


def _parse_vt_file_response(data: dict, sha256_hash: str, local_filename: str, local_size: int) -> dict[str, Any]:
    """Форматирует ответ VirusTotal v3 в чистую структуру для фронтенда."""
    attrs = data.get("data", {}).get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})
    results = attrs.get("last_analysis_results", {})

    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    undetected = stats.get("undetected", 0)
    harmless = stats.get("harmless", 0)
    total_scanners = malicious + suspicious + undetected + harmless

    # Список движков
    engines_list = []
    for eng_name, eng_info in results.items():
        cat = eng_info.get("category", "undetected")
        res = eng_info.get("result")
        engines_list.append({
            "name": eng_name,
            "category": cat,  # malicious, suspicious, undetected, harmless, type-unsupported
            "result": res or "Чисто (Clean)",
            "version": eng_info.get("engine_version", ""),
            "updated": eng_info.get("engine_update", ""),
        })

    # Сортируем: опасные и подозрительные всегда наверху
    def _sort_key(item):
        cat = item["category"]
        if cat == "malicious":
            return (0, item["name"])
        elif cat == "suspicious":
            return (1, item["name"])
        elif cat == "undetected":
            return (2, item["name"])
        return (3, item["name"])

    engines_list.sort(key=_sort_key)

    last_analysis_ts = attrs.get("last_analysis_date")
    date_str = ""
    if last_analysis_ts:
        try:
            dt = datetime.datetime.fromtimestamp(last_analysis_ts)
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            date_str = str(last_analysis_ts)

    verdict = "clean"
    if malicious > 0:
        verdict = "malicious"
    elif suspicious > 0:
        verdict = "suspicious"

    meaningful_name = attrs.get("meaningful_name") or local_filename
    size_bytes = attrs.get("size") or local_size

    return {
        "success": True,
        "found": True,
        "verdict": verdict,
        "sha256": sha256_hash,
        "file_name": meaningful_name,
        "file_size": size_bytes,
        "file_size_formatted": format_file_size(size_bytes),
        "malicious_count": malicious,
        "suspicious_count": suspicious,
        "undetected_count": undetected,
        "harmless_count": harmless,
        "total_scanners": total_scanners,
        "score_text": f"{malicious} / {total_scanners}",
        "reputation": attrs.get("reputation", 0),
        "type_description": attrs.get("type_description", "Исполняемый файл Windows"),
        "last_analysis_date": date_str,
        "permalink": f"https://www.virustotal.com/gui/file/{sha256_hash}",
        "engines": engines_list,
    }


def upload_and_scan_file(filepath: str | Path, api_key: str | None = None) -> dict[str, Any]:
    """
    Загружает файл (до 32 МБ) в VirusTotal для первичного анализа.
    Опрашивает статус анализа до завершения и возвращает полный отчет.
    """
    path_obj = Path(filepath)
    if not path_obj.is_file():
        return {"success": False, "message": f"Файл не найден: {filepath}"}

    key = (api_key or get_virustotal_api_key()).strip()
    if not key:
        return {"success": False, "message": "API ключ VirusTotal не указан."}

    file_size = path_obj.stat().st_size
    if file_size > MAX_UPLOAD_SIZE:
        return {
            "success": False,
            "message": f"Размер файла ({format_file_size(file_size)}) превышает лимит бесплатной отправки (32 МБ). Вы можете вручную загрузить его на virustotal.com."
        }

    try:
        with open(path_obj, "rb") as f:
            file_bytes = f.read()

        payload, content_type = _build_multipart_payload({}, {"file": (path_obj.name, file_bytes)})

        upload_req = urllib.request.Request(
            f"{VT_API_BASE}/files",
            data=payload,
            headers={
                "x-apikey": key,
                "Content-Type": content_type,
                "User-Agent": "ZiablWinSetup/1.4.21"
            },
            method="POST"
        )

        with urllib.request.urlopen(upload_req, timeout=30) as resp:
            up_data = json.loads(resp.read().decode("utf-8"))

        analysis_id = up_data.get("data", {}).get("id")
        if not analysis_id:
            return {"success": False, "message": "VirusTotal не вернул идентификатор анализа."}

        # Ожидаем завершения анализа (до 60 секунд)
        for _ in range(20):
            time.sleep(3)
            check_req = urllib.request.Request(
                f"{VT_API_BASE}/analyses/{analysis_id}",
                headers={"x-apikey": key, "User-Agent": "ZiablWinSetup/1.4.21"}
            )
            with urllib.request.urlopen(check_req, timeout=15) as a_resp:
                a_data = json.loads(a_resp.read().decode("utf-8"))
                status = a_data.get("data", {}).get("attributes", {}).get("status")
                if status == "completed":
                    break

        # Получаем итоговый отчет
        return scan_file_by_path(path_obj, key)

    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"success": False, "message": "Превышен лимит запросов VirusTotal (4/мин). Подождите 1 минуту."}
        return {"success": False, "message": f"Ошибка отправки файла на VirusTotal (HTTP {e.code}): {e.reason}"}
    except Exception as e:
        logger.error(f"Error uploading file to VirusTotal: {e}")
        return {"success": False, "message": f"Ошибка отправки файла на VirusTotal: {e}"}
