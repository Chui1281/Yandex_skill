from typing import Any
import random
from aliceio import Dispatcher, Skill
from aliceio.types import AliceResponse, Message, Response
from aliceio.webhook.yandex_functions import (
    OneSkillYandexFunctionsRequestHandler,
    RuntimeContext,
)

# Импортируем вопросы из отдельного файла
from questions import ALL_QUESTIONS

dp = Dispatcher()
skill = Skill(skill_id="f3d7c762-28a8-4bd9-90cc-39d325c6ab4b")
requests_handler = OneSkillYandexFunctionsRequestHandler(dp, skill)

# Настройки
QUESTIONS_PER_GAME = 5
MAX_ATTEMPTS = 2  # Максимальное количество попыток ответа на вопрос

# Фразы
POSITIVE_RESPONSES = [
    "Верно! 🎉",
    "Правильно! 👍", 
    "Точно! 🔥",
    "Именно так! 👏",
    "Браво! 🏆"
]
NEGATIVE_RESPONSES = [
    "Не совсем.",
    "Нет.",
    "Ошибка.",
    "Не угадали.",
    "Почти."
]

sessionStorage = {}

@dp.message()
async def message_handler(
    message: Message,
    ycf_context: RuntimeContext,
) -> AliceResponse:
    user_id = message.session.user_id
    user_message = message.original_utterance.lower().strip()
    
    # Обработка общих команд (работают в любом состоянии)
    if user_message in ["помощь", "help", "правила"]:
        return await show_help(user_id)
    
    # Инициализация новой сессии
    if message.session.new:
        return await start_new_session(user_id)
    
    # Проверка наличия данных сессии
    if user_id not in sessionStorage:
        return await start_new_session(user_id)
    
    session = sessionStorage[user_id]
    
    # Обработка приветствия
    if session["status"] == "greeting":
        if user_message in ["да", "начать", "поехали", "старт", "играть"]:
            return await start_new_game(user_id)
        elif user_message in ["нет", "не хочу", "потом"]:
            return await send_response(user_id,
                "Хорошо! Когда захотите играть - скажите 'Начать'.",
                end_session=True
            )
        else:
            return await send_response(user_id,
                "Я вас не поняла. Скажите 'Начать' для старта игры или 'Помощь' для правил.",
                end_session=False
            )
    
    # Обработка во время викторины
    elif session["status"] == "in_progress":
        # Команды, которые работают во время вопроса
        if user_message in ["стоп", "закончить", "хватит"]:
            session["status"] = "finished"
            return await send_response(user_id,
                f"Игра прервана. Ваш результат: {session['score']} из {len(session['questions'])}. "
                "Скажите 'Начать' для новой игры.",
                end_session=True
            )
        
        if user_message in ["повторить вопрос", "повторить"]:
            return await repeat_question(user_id)
            
        if user_message == "ответ":
            session["waiting_for_answer"] = True
            return await send_response(user_id,
                "Хорошо, слушаю ваш ответ...",
                end_session=False
            )
        
        # Если ждём ответа после команды "ответ"
        if session.get("waiting_for_answer"):
            session["waiting_for_answer"] = False
            return await handle_quiz_answer(user_id, user_message)
        
        # Игнорируем любые другие фразы, кроме команд
        return await send_response(user_id,
            "Я жду от вас одну из команд:\n"
            "'Ответ' - дать ответ на вопрос\n"
            "'Повторить вопрос' - повторить текущий вопрос\n"
            "'Стоп' - закончить игру\n"
            "'Помощь' - правила игры",
            end_session=False
        )
    
    # Обработка после викторины
    elif session["status"] == "finished":
        if user_message in ["да", "еще", "ещё", "сыграем"]:
            return await start_new_game(user_id)
        elif user_message in ["нет", "не хочу"]:
            return await send_response(user_id,
                "Спасибо за игру! До новых встреч!",
                end_session=True
            )
        else:
            return await send_response(user_id,
                "Спасибо за игру в ДубОК! Чтобы начать заново - скажите 'Начать'.",
                end_session=False
            )
    
    return await start_new_session(user_id)

async def handle_quiz_answer(user_id, user_answer):
    session = sessionStorage[user_id]
    current_question = session["questions"][session["current_question"]]
    
    # Нормализация ответа для проверки
    normalized_answer = user_answer.translate(str.maketrans('', '', '!?.,'))
    
    # Проверка ответа
    is_correct = any(
        keyword in normalized_answer 
        for keyword in current_question["a"]
    )
    
    if is_correct:
        response_text = f"{random.choice(POSITIVE_RESPONSES)} {current_question['full']}"
        session["score"] += 1
    else:
        session["attempts"] += 1
        if session["attempts"] < MAX_ATTEMPTS:
            return await send_response(user_id,
                "Попробуйте еще раз!",
                end_session=False
            )
        response_text = f"{random.choice(NEGATIVE_RESPONSES)} {current_question['full']}"
    
    # Переход к следующему вопросу
    session["current_question"] += 1
    session["attempts"] = 0
    
    if session["current_question"] >= len(session["questions"]):
        return await finish_quiz(user_id)
    else:
        next_question = session["questions"][session["current_question"]]["q"]
        return await send_response(user_id,
            f"{response_text}\n\nВопрос {session['current_question'] + 1}: {next_question}\n\n"
            "Скажите 'Ответ', чтобы дать ответ.",
            end_session=False
        )

async def repeat_question(user_id):
    if user_id not in sessionStorage or sessionStorage[user_id]["status"] != "in_progress":
        return await send_response(user_id,
            "Сейчас нет активного вопроса. Скажите 'Начать' для новой игры.",
            end_session=False
        )
    
    session = sessionStorage[user_id]
    question = session["questions"][session["current_question"]]["q"]
    return await send_response(user_id,
        f"Вопрос {session['current_question'] + 1}: {question}\n\n"
        "Скажите 'Ответ', чтобы дать ответ.",
        end_session=False
    )

async def finish_quiz(user_id):
    session = sessionStorage[user_id]
    session["status"] = "finished"
    score = session["score"]
    total = len(session["questions"])
    
    if score == total:
        result = "💎 Потрясающе! Вы ответили правильно на все вопросы!"
    elif score >= total/2:
        result = f"👍 Хороший результат! {score} из {total} правильных ответов!"
    else:
        result = f"😊 В следующий раз получится лучше! Правильных ответов: {score} из {total}"
    
    return await send_response(user_id,
        f"{result}\n\nХотите сыграть еще раз? (скажите 'Да' или 'Нет')",
        end_session=False
    )

async def ask_question(user_id):
    session = sessionStorage[user_id]
    question = session["questions"][session["current_question"]]["q"]
    return await send_response(user_id,
        f"Вопрос {session['current_question'] + 1}: {question}\n\n"
        "Скажите 'Ответ', чтобы дать ответ.",
        end_session=False
    )

async def start_new_game(user_id):
    sessionStorage[user_id] = {
        "status": "in_progress",
        "questions": random.sample(ALL_QUESTIONS, QUESTIONS_PER_GAME),
        "current_question": 0,
        "score": 0,
        "attempts": 0,
        "waiting_for_answer": False
    }
    return await ask_question(user_id)

async def start_new_session(user_id):
    sessionStorage[user_id] = {
        "status": "greeting",
        "questions": [],
        "current_question": 0,
        "score": 0,
        "attempts": 0,
        "waiting_for_answer": False
    }
    return await send_response(user_id,
        "Привет! Я - ДубОК, викторина с неожиданными вопросами! 🌳\n\n"
        "Я задам вам 5 интересных вопросов. Ваша задача - ответить на них. "
        "Я проверю ваш ответ и скажу, правильный ли он.\n\n"
        "Готовы начать? Скажите 'Да' или 'Начать'!",
        end_session=False
    )

async def show_help(user_id):
    return await send_response(user_id,
        "📚 Правила викторины ДубОК:\n\n"
        "1. Я задаю 5 случайных вопросов из базы\n"
        "2. Вам нужно ответить на вопрос\n"
        "3. После каждого ответа я назову правильный ответ\n"
        "4. На каждый вопрос дается 2 попытки\n"
        "5. В конце вы узнаете свой результат\n\n"
        "🔹 Доступные команды:\n"
        "'Начать' - начать новую игру\n"
        "'Ответ' - дать ответ на вопрос\n"
        "'Повторить вопрос' - повторить текущий вопрос\n"
        "'Стоп' - закончить игру\n"
        "'Помощь' - показать это сообщение\n\n"
        "Готовы играть? Скажите 'Начать'!",
        end_session=False
    )

async def send_response(user_id, text, end_session=False):
    return AliceResponse(
        response=Response(
            text=text,
            end_session=end_session
        ),
        session_state=sessionStorage.get(user_id, {})
    )

async def main(event: dict[str, Any], context: RuntimeContext) -> Any:
    return await requests_handler(event, context)