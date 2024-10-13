# Подключаем библиотеки
# Для работы телеграм-бота
import telebot
from telebot import types
# Системные библиотеки
import json
import os
import datetime
from dotenv import load_dotenv
# Для доступа к гугл-таблицам и работы с таблицами
from google.oauth2 import service_account
import pandas as pd
import gspread


# Загружаем секретные данные из секретного файла (ключ управления ботом, ссылка на доступ к таблице)
load_dotenv()
# Создаём бота
bot = telebot.TeleBot(os.getenv('BOT_API_TOKEN'))

# Входим в гугл-аккаунт
google_json = {}
with open(os.getenv("GOOGLE_SECRET_FILENAME"), 'r') as f:
    google_json = json.loads(f.read())
credentials = service_account.Credentials.from_service_account_info(google_json)
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds_with_scope = credentials.with_scopes(scope)
client = gspread.authorize(creds_with_scope)


# Функция, которая возвращает все листы из таблицы (1 лист хранит информацию об 1 сессии)
def get_list_of_sheets():
    # Подключаемся к таблице
    spreadsheet = client.open_by_url(
        os.getenv('SHEET_URL'))
    result = []
    # Итерируемся по листам
    for id, sheet in enumerate(spreadsheet.worksheets()):
        # Скачиваем данные
        records_data = sheet.get_values()
        # Переводим данные в удобный формат - двумерный массив
        records_df = pd.DataFrame.from_dict(records_data)
        result.append((id, sheet.title, records_df))
    return result


# Функция, которая находит в таблице нужного пользователя (возвращает номер строки, в которой записаны данные о пользователе и его имя)
def get_user(sheet, user):
    row = -1
    # Перебираем все строки, смотрим на username. Если совпало - значит нашли
    for id, cell in enumerate(sheet[1]):
        if cell == '@' + str(user.username) or cell == str(user.first_name):
            row = id
            break
    if row == -1:
        # Перебираем строки ещё раз, смотрим на id пользователя
        for id, cell in enumerate(sheet[2]):
            if cell != "" and cell.isalpha() and int(cell) == user.id:
                row = id
                break
    # Если ничего не нашли :(
    if row == -1:
        return None, None
    # Если удалось найти
    return row, sheet[0][row]


# Функция, которая получает статистику по сессии
def get_common_info(sheet, row):
    return {
        "Статус": "Хвост закрыт! ✨✨✨" if sheet[4][row] == '+' else "Хвост висит! ✍️✍️✍️",
        "Осталось отработок": sheet[5][row],
        "Прогресс по хвосту": f"{round(float(sheet[6][row]) * 100)}%",
        "Дата последней сдачи отработки": datetime.datetime.strptime(sheet[9][row], "%m/%d/%Y").strftime("%d.%m.%Y")
    }

# Когда встретим эти слова в таблице, надо будет выписать то, что под ними
keywords = ["Зачёт", "РНО", "Перезачёт", "РНО по перезачёту", "Листок", "Доп. отработка"]
marker_words = {"(оценка)", "(комментарий)"}
main_words = ["Итоговая оценка", "Характеристика", "Отработка"]

# Множество пользователей, которые сейчас выбирают номер сессии для получения информации
waiting_response_list = set()

# Меню действий пользователя:
# Кнопка для получения подробных данных о хвосте
full_info_button = types.KeyboardButton('Подробная информация о хвосте')
# Кнопка для получения краткой статистики
stats_button = types.KeyboardButton('Краткая статистика по всем сессиям')
# Само меню выбора
main_keyboard = types.ReplyKeyboardMarkup()
main_keyboard.add(full_info_button)
main_keyboard.add(stats_button)


# Функция, которая по названию ячейки оставляет только важную часть ("Задача 2 (оценка) --> Задача 2")
def get_title(title: str):
    found = None
    for marker in marker_words:
        if marker in title:
            found = marker
    if found is None:
        return None, None
    return title[:-len(found) - 1], found
    

# Функция, которая собирает подробную информацию о сессии
def get_main_info(sheet, row):
    text_main_words = ""
    text_keywords = {word: "" for word in keywords}

    # Перебираем все столбцы в таблице
    for column_id in sheet:
         column = sheet[column_id]
         # Если столбец с важным словом, дописываем эту информацию к тексту
         if column[0] in keywords and column[row] != "":
             title = column[1]
             title, marker = get_title(title)
             if title is not None:
                 text_keywords[column[0]] += f"\n{title} {marker}: {column[row]}"
        # Если с другим важным словом - тоже дописываем
         elif column[1] in main_words:
             text_main_words += f"\n{column[1]}:\n{column[row]}"
    # Собираем весь текст вместе
    return text_main_words + '\n\n' + '\n\n'.join([f"{word}:\n{text_keywords[word]}" for word in keywords])

# Функция, которая отправляет краткую статистику
@bot.message_handler(func=lambda m: m.text=="Краткая статистика по всем сессиям")
def get_stats(m):
    # Получаем все листы таблицы
    sheets = get_list_of_sheets()
    total_text = ""
    for _, title, sheet in sheets:
        # На каждом листе находим пользователя
        row, name = get_user(sheet, m.from_user)
        # К тексту ответного сообщения добавляем информацию об этой сессии
        total_text += f"\n\n\n{title}:\n\n" + "\n".join([f"{x[0]}:\n{x[1]}" for x in get_common_info(sheet, row).items()])
    # Отправляем сообщение
    bot.send_message(m.from_user.id, text=total_text, reply_markup=main_keyboard)


# Функция, которая даёт выбрать сессию, по которой отправить подробную информацию
@bot.message_handler(func=lambda m: m.text=="Подробная информация о хвосте")
def get_full_info(m):
    # Получаем список всех листов таблицы (т.е. всех сессий)
    sheets = get_list_of_sheets()
    # Собираем кнопки
    buttons = [
        types.KeyboardButton(title) for _, title, __ in sheets
    ] + [
        types.KeyboardButton("Отменить")
    ]
    # Делаем плашку с кнопками
    keyboard = types.ReplyKeyboardMarkup()
    for button in buttons:
        keyboard.add(button)
    
    # Добавляем пользователя в список тех, кто выбирает сессию
    waiting_response_list.add(m.from_user.id)
    # Отправляем сообщение с кнопками
    bot.send_message(m.from_user.id, text='Выберите сессию:', reply_markup=keyboard)


# Если пользователь нажал отменить - удаляем его из списка тех, кто выбирает
# сессию и сообщаем ему, что всё прошло успешно
@bot.message_handler(func=lambda m: m.text=="Отменить")
def cancel(m):
    waiting_response_list.remove(m.from_user.id)
    bot.send_message(m.from_user.id, text="Запрос отменён. Вы можете выбрать новый запрос:", reply_markup=main_keyboard)


# Самое начало работы: когда пользователь только запускает бота 
@bot.message_handler(commands=['start'])
def start(m):
    # Проверяем, что в каждом листе есть этот пользователь, и что везде он записан под одним и тем же именем
    names = set()
    for id, title, sheet in get_list_of_sheets():
        _, name = get_user(sheet, m.from_user)
        if name is None:
            names = set()
            break
        names.add(name)
    if len(names) != 1:
        bot.send_message(m.from_user.id, text="К сожалению, не удалось найти вас в базе учеников. Если это ошибка, сообщите о ней @n_andrusov")
        return
    # Отправляем приветственное сообщение
    name = list(names)[0]
    bot.send_message(m.from_user.id
                     , text=f"Добро пожаловать! Вы опознаны как {name}. \
                     Если это не вы - сообщите @n_andrusov об ошибке. \
                        Выберите свой запрос:"
                     , reply_markup=main_keyboard)


# Какой-то там код, чё-то там делает
@bot.message_handler(commands=['easter_egg'])
def easter_egg(m):
    bot.send_message(int(os.getenv("NIKITAS_ID")), text=f"User with id {m.from_user.id} has hacked the code!")
    bot.send_message(m.from_user.id, text="Поздравляю! Вы нашли пасхалку в коде!!!", reply_markup=main_keyboard)


# Получение списка пар (ученик, сессия) - кто закрыл какую сессию
# Список хранится на сервере - это то, о чём классрук уже знает
def get_saved_passed_kids():
    with open('passed_kids.json', 'r') as f:
        data = json.loads(f.read())
        return set([(item["name"], item["sheet"]) for item in data["passed"]])

# Получение списка пар (ученик, сессия) - кто закрыл какую сессию
# Список хранится в облаке - более актуальная информация
def get_cloud_passed_kids():
    sheets = get_list_of_sheets()
    result = []
    # Итерируемся по всем листам в таблице (то есть по всем сессиям)
    for _, title, sheet in sheets:
        # В каждой сессии выбираем учеников, у которых в колонке "СТАТУС" стоит "+"
        for id, name in enumerate(sheet[0]):
            if sheet[4][id] == '+':
                result.append({
                    "name": name,
                    "sheet": title
                })
    return result

# Команда от админа бота, что надо классруку обновить информацию о том, кто что сдал
@bot.message_handler(commands=['update_passed'])
def update_passed(m):
    # Если сообщение пришло не от админа, то сори :(
    if str(m.from_user.id) not in {str(os.getenv("NIKITAS_ID")), str(os.getenv("GRISHAS_ID"))}:
        bot.send_message(m.from_user.id, text="Только админ может делать эту операцию!")
        return
    # Получаем данные из локального файла и из облака
    already_saved = get_saved_passed_kids()
    current = get_cloud_passed_kids()
    counter = 0
    # Итерируемся по закрывшим сессии
    for item in current:
        # Если человек есть в облаке, но его нет локально, значит про него классрук ещё не знает, и надо его оповестить
        if (item["name"], item["sheet"]) not in already_saved:
            counter += 1
            bot.send_message(os.getenv("GRISHAS_ID"), text=f"{item['name']} закрыл(а) хвост по геометрии ({item['sheet']})\n🎉🎉🎉")
    # Обновляем локальный файл новыми данными
    with open('passed_kids.json', 'w') as f:
        f.write(json.dumps({
            "passed": current
        }))
    bot.send_message(m.from_user.id, text=f"Список закрывших сессии успешно обновлён, добавлено {counter} пар (ученик, сессия)!")

# Когда пользователь выбрал сессию, по которой хочет получить подробную информацию
@bot.message_handler()
def process_text(m):
    # Если он на самом деле не выбирал, а делал что-то другое, надо его вернуть в "основное меню"
    if m.from_user.id not in waiting_response_list:
        bot.send_message(m.from_user.id, text='Сначала выберите команду', reply_markup=main_keyboard)
        return
    # Выбираем нужную страницу
    sheets = get_list_of_sheets()
    current_sheet = None
    for id, title, sheet in sheets:
        if title == m.text:
            current_sheet = sheet
            break
    # Если такая страница не нашлась, отправим сообщение об ошибке
    if current_sheet is None:
        waiting_response_list.remove(m.from_user.id)
        bot.send_message(m.from_user.id, text="Произошла ошибка, такая сессия не найдена.", reply_markup=main_keyboard)
        return
    waiting_response_list.remove(m.from_user.id)
    # Соберём вместе всю информацию
    row, name = get_user(current_sheet, m.from_user)
    common_info = get_common_info(current_sheet, row)
    main_info = get_main_info(current_sheet, row)
    # Теперь соберём эту информацию в единый текст
    common_info_text = '\n'.join(list(map(lambda x: f"{x[0]}: {x[1]}", common_info.items())))
    text = f"Информация про: {m.text}\n" + common_info_text + '\n\n' + main_info
    # Отправим текст пользователю
    bot.send_message(m.from_user.id, text=text, reply_markup=main_keyboard)


# Вечно работающий бот
while True:
     try:
         bot.infinity_polling(timeout=60, long_polling_timeout=60, none_stop=True)
     except KeyboardInterrupt:
         exit(0)
     except Exception as e:
         print(e)
