"""Мультиязычность кабинета клиента: русский (исходный), английский, китайский.

Бэкенд формирует тексты на русском — так их видят андеррайтер и журнал аудита.
Для клиента ответ API переводится одним слоем (middleware в main.py) по каталогу
сообщений: точные строки и шаблоны с подстановками, как в gettext с русскими msgid.
Поэтому сохранённые в БД события и решения тоже показываются на выбранном языке,
без хранения копий на трёх языках. Строки, которых нет в каталоге (имена,
реквизиты, текст клиента), остаются как есть.

Составные ответы, которые собираются прямо в запросе (чат Альфика, диалог
«Расскажите Альфику»), формируются сразу на нужном языке через L().
"""
import re
from contextvars import ContextVar

from app.i18n.catalog import EXACT, PATTERNS

LANGS = ("ru", "en", "zh")
_lang: ContextVar[str] = ContextVar("lang", default="ru")

# Поля, значения которых — данные пользователя или реестров, а не тексты интерфейса
SKIP_KEYS = {"source", "filename", "purpose_comment", "collateral_description", "login", "full_name", "position",
             "director", "address", "okved_name", "region", "inn", "ogrn", "number", "account", "contract_number",
             "demo_code", "signature_id", "comment", "by_name", "prefill", "name_raw"}

_EXACT_LOWER = {k[0].lower() + k[1:]: v for k, v in EXACT.items() if k}
_PATTERNS = [(re.compile(rf"^{p}$", re.DOTALL), en, zh) for p, en, zh in PATTERNS]


def get_lang() -> str:
    return _lang.get()


def set_lang(lang: str):
    return _lang.set(lang if lang in LANGS else "ru")


def reset_lang(token) -> None:
    _lang.reset(token)


def parse_lang(x_lang: str | None, accept_language: str | None) -> str:
    for candidate in (x_lang, (accept_language or "").split(",")[0]):
        code = (candidate or "").strip().lower()[:2]
        if code in LANGS:
            return code
    return "ru"


def L(ru: str, en: str, zh: str) -> str:
    """Выбор варианта текста по языку текущего запроса."""
    return {"en": en, "zh": zh}.get(get_lang(), ru)


def _pick(pair: tuple[str, str], lang: str) -> str:
    return pair[0] if lang == "en" else pair[1]


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def tr(text: str, lang: str | None = None) -> str:
    lang = lang or get_lang()
    if lang == "ru" or not text or not isinstance(text, str):
        return text
    if text in EXACT:
        return _pick(EXACT[text], lang)
    if text in _EXACT_LOWER:  # «одобрено» ← «Одобрено», «купить оборудование…» внутри фраз
        out = _pick(_EXACT_LOWER[text], lang)
        return _lower_first(out) if lang == "en" else out
    stripped = text.strip()
    if stripped != text:
        return text.replace(stripped, tr(stripped, lang))
    for rx, en, zh in _PATTERNS:
        m = rx.match(text)
        if m:
            groups = [_tr_part(g or "", lang) for g in m.groups()]
            return (en if lang == "en" else zh).format(*groups)
    return text


def _tr_part(part: str, lang: str) -> str:
    """Подстановка внутри шаблона: целиком или как перечисление через «; » / «, »."""
    whole = tr(part, lang)
    if whole != part:
        return whole
    for sep in ("; ", ", "):
        if sep in part:
            items = part.split(sep)
            out = [tr(i, lang) for i in items]
            if out != items:
                return (sep if lang == "en" else {"; ": "；", ", ": "、"}[sep]).join(out)
    return part


def localize(obj, lang: str | None = None):
    """Рекурсивный перевод JSON-ответа (значения строк; ключи и коды не трогаем)."""
    lang = lang or get_lang()
    if lang == "ru":
        return obj
    if isinstance(obj, str):
        return tr(obj, lang)
    if isinstance(obj, list):
        return [localize(v, lang) for v in obj]
    if isinstance(obj, dict):
        user_msg = obj.get("role") == "user"  # реплики клиента в истории чата не переводим
        return {k: v if (k in SKIP_KEYS or (user_msg and k == "content")) else localize(v, lang) for k, v in obj.items()}
    return obj
