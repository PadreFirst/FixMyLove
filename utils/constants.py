from enum import Enum


class Gender(str, Enum):
    MALE = "m"
    FEMALE = "f"
    OTHER = "other"
    UNKNOWN = "unknown"


class RelationshipStatus(str, Enum):
    DATING = "встречаемся"
    LIVING_TOGETHER = "живём вместе"
    MARRIED = "брак"
    BROKE_UP = "расстались"
    LOOKING = "ищу"
    UNCERTAIN = "неопределённость"
    FREE = "свободные"


class AttachmentStyle(str, Enum):
    SECURE = "надёжный"
    ANXIOUS = "тревожный"
    AVOIDANT = "избегающий"
    DISORGANIZED = "дезорганизованный"


class SituationType(str, Enum):
    ACUTE = "acute"
    CHRONIC = "chronic"


class UserGoal(str, Enum):
    VENT = "vent"
    UNDERSTAND = "understand"
    PLAN = "plan"
    PREPARE = "prepare"


class Initiator(str, Enum):
    PARTNER = "partner"
    SELF_JUSTIFIED = "self_justified"
    SELF_UNJUSTIFIED = "self_unjustified"
    UNCLEAR = "unclear"
    BOTH = "both"


class SessionPhase(str, Enum):
    VALIDATION = "validation"
    MAPPING = "mapping"
    PARTNER_PERSPECTIVE = "partner_perspective"
    AGENCY = "agency"
    TRAINER = "trainer"


class Tone(str, Enum):
    SOFT = "soft"
    ANALYTICAL = "analytical"
    EMERGENCY = "emergency"


class MessageType(str, Enum):
    SESSION = "session"
    DIARY_UPDATE = "diary_update"
    TRAINER = "trainer"
    REFLECTION = "reflection"
    ADMIN = "admin"
    CRISIS = "crisis"
    OFF_TOPIC = "off_topic"


class DominantPattern(str, Enum):
    PURSUE_WITHDRAW = "pursue_withdraw"
    STONEWALLING = "stonewalling"
    PASSIVE_AGGRESSION = "passive_aggression"
    INTERMITTENT = "intermittent"
    CONTEMPT = "contempt"
    DEFENSIVENESS = "defensiveness"
    UNDEFINED = "undefined"


CRISIS_KEYWORDS = [
    "хочу умереть", "не хочу жить", "покончить с собой",
    "суицид", "убить себя", "конец жизни", "нет смысла жить",
    "не вижу смысла жить", "не вижу смысла",
    "лучше бы меня не было", "всем будет лучше без меня",
    "не вижу выхода", "хочу исчезнуть", "устал жить", "устала жить",
    "жизнь не имеет смысла", "повеситься", "наглотаться таблеток",
    "прыгнуть с крыши", "перерезать вены", "жить не хочу",
    "зачем мне жить", "лучше бы я умер", "лучше бы я умерла",
]

DIARY_KEYWORDS = [
    "/diary", "запиши в дневник", "дневник", "внеси запись",
    "добавь в дневник", "запись в дневник",
]

ADMIN_KEYWORDS = [
    "/settings",
    "измени имя", "смени партнёра", "обнови данные",
    "включи напоминания", "выключи напоминания",
    "поменяй имя", "поменяй настройки",
    "напоминай", "поменяй расписание", "смени расписание",
    "измени расписание", "пиши мне", "писать мне",
    "присылай", "уведомляй", "напоминание",
    "можешь писать", "раз в неделю", "раз в месяц", "раз в день",
]

DIARY_SHOW_KEYWORDS = [
    "покажи дневник", "показать дневник", "мой дневник",
    "записи дневника", "что в дневнике",
]

ONBOARDING_WELCOME = (
    "Привет! Я — твой ИИ-помощник по отношениям. "
    "Без банальных советов и осуждения — помогу разобраться "
    "в том что происходит, и сделать конкретный шаг.\n\n"
    "Давай знакомиться — как тебя зовут?"
)

ATTACHMENT_QUESTIONS = [
    {
        "text": "Сейчас несколько вопросов — помогут мне лучше тебя понять.\n\nКогда возникает конфликт — как ты обычно реагируешь?",
        "options": [
            ("А", "Сразу говорю и разбираюсь"),
            ("Б", "Тревожусь, хочу помириться"),
            ("В", "Ухожу в себя, нужно время"),
            ("Г", "По-разному, сам не пойму"),
        ],
    },
    {
        "text": "Просить партнёра о поддержке — это для тебя...",
        "options": [
            ("А", "Легко, не проблема"),
            ("Б", "Боюсь быть в тягость"),
            ("В", "Справляюсь сам"),
            ("Г", "То прошу, то жалею"),
        ],
    },
    {
        "text": "Партнёр занят и не уделяет внимания — что чувствуешь?",
        "options": [
            ("А", "Спокоен, у всех свои дела"),
            ("Б", "Тревожусь — всё ли ок?"),
            ("В", "Отлично, мне тоже нужно время"),
            ("Г", "Сначала норм, потом накрывает"),
        ],
    },
    {
        "text": "Что для тебя важнее в отношениях?",
        "options": [
            ("А", "Баланс близости и свободы"),
            ("Б", "Знать что не бросят"),
            ("В", "Уважение моих границ"),
            ("Г", "Хочу всё, но что-то мешает"),
        ],
    },
    {
        "text": "Что чаще вспоминается о прошлых или текущих отношениях?",
        "options": [
            ("А", "Уверенность, несмотря ни на что"),
            ("Б", "Тревога и страх потери"),
            ("В", "Близость давалась тяжело"),
            ("Г", "Хаос и непредсказуемость"),
        ],
    },
]

ATTACHMENT_KEY = {
    "А": AttachmentStyle.SECURE,
    "Б": AttachmentStyle.ANXIOUS,
    "В": AttachmentStyle.AVOIDANT,
    "Г": AttachmentStyle.DISORGANIZED,
}
