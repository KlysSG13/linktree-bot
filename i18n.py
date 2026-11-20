"""Локализация RU/EN. Все ключи существуют в обоих языках (проверяется тестом)."""
from __future__ import annotations

RU = "ru"
EN = "en"
LANGS = (RU, EN)

DEFAULT_LANG = RU

_TR = {
    "start_hello": {
        RU: "Привет, {name}! 👋\n\nЯ <b>LinkTree</b> — бот с личной подборкой проверенных "
            "инструментов и GitHub-репозиториев для разработчиков.\n\n"
            "Просто напиши запрос своими словами — например, "
            "<i>«нужна библиотека для работы с PDF в Python»</i> — и я найду подходящее.\n\n"
            "Полный список команд: /help",
        EN: "Hi, {name}! 👋\n\nI am <b>LinkTree</b> — a bot with a hand-picked collection of "
            "dev tools and GitHub repositories.\n\n"
            "Just describe what you need in your own words — e.g. "
            "<i>“a Python library for working with PDFs”</i> — and I'll find the match.\n\n"
            "Full command list: /help",
    },
    "help": {
        RU: "<b>Что я умею</b>\n\n"
            "🧩 <b>Разбор задачи</b> — /plan: опиши задачу, я разложу её на атомарные шаги,"
            " подберу инструмент к каждому и выстрою порядок (детерминированное ядро МАРСИ).\n"
            "🔍 <b>Поиск</b> — напиши запрос обычным языком, я ищу по смыслу, а не по словам. "
            "Запросы можно писать на русском или английском.\n"
            "🗂 <b>Категории</b> — /cats, обзор всей базы по разделам.\n"
            "🎲 <b>Случайный ресурс</b> — /random, чтобы открывать новое.\n"
            "⭐ <b>Избранное</b> — /fav, личный список сохранённого.\n"
            "💡 <b>Предложить ресурс</b> — /suggest, после проверки админом он попадёт в базу.\n"
            "📮 <b>Ресурс недели</b> — /digest, еженедельная рассылка.\n"
            "🌍 <b>Язык</b> — /lang ru | en.\n\n"
            "Голосуй 👍/👎 под результатами — это влияет на ранжирование.",
        EN: "<b>What I can do</b>\n\n"
            "🧩 <b>Task breakdown</b> — /plan: describe a task, I decompose it into atomic steps,"
            " match a tool to each and order them (deterministic MARSI core).\n"
            "🔍 <b>Search</b> — write a query in plain language; I search by meaning, not keywords. "
            "Russian or English both work.\n"
            "🗂 <b>Categories</b> — /cats, browse the whole base by section.\n"
            "🎲 <b>Random resource</b> — /random, discover something new.\n"
            "⭐ <b>Favorites</b> — /fav, your personal saved list.\n"
            "💡 <b>Suggest a resource</b> — /suggest, after review it joins the base.\n"
            "📮 <b>Resource of the week</b> — /digest, weekly pick in DM.\n"
            "🌍 <b>Language</b> — /lang ru | en.\n\n"
            "Vote 👍/👎 under results — it shapes the ranking.",
    },
    "search_hint": {
        RU: "🔍 Напиши запрос — например: <i>«инструмент для анимации на сайте»</i> "
            "или <i>«python парсинг сайтов»</i>.",
        EN: "🔍 Send me a query — e.g. <i>“tool for website animations”</i> "
            "or <i>“python web scraping”</i>.",
    },
    "no_results": {
        RU: "😕 Ничего подходящего не нашлось. Попробуй переформулировать или взгляни на категории:",
        EN: "😕 Nothing relevant found. Try rephrasing or browse categories:",
    },
    "results_header": {
        RU: "Результаты по запросу <b>«{query}»</b> ({rank} из {total}):\n\n",
        EN: "Results for <b>“{query}”</b> ({rank} of {total}):\n\n",
    },
    "more_btn": {RU: "Ещё ➡️", EN: "More ➡️"},
    "open_btn": {RU: "Открыть", EN: "Open"},
    "related_btn": {RU: "↔️ Похожие", EN: "↔️ Related"},
    "fav_add_btn": {RU: "⭐ В избранное", EN: "⭐ Save"},
    "fav_del_btn": {RU: "💔 Убрать", EN: "💔 Remove"},
    "up_btn": {RU: "👍", EN: "👍"},
    "down_btn": {RU: "👎", EN: "👎"},
    "random_btn": {RU: "🎲 Ещё случайный", EN: "🎲 Another one"},
    "vote_saved": {RU: "Голос учтён, спасибо!", EN: "Vote counted, thanks!"},
    "vote_reset": {RU: "Голос отменён.", EN: "Vote removed."},
    "fav_added": {RU: "Добавлено в избранное ⭐", EN: "Added to favorites ⭐"},
    "fav_removed": {RU: "Убрано из избранного.", EN: "Removed from favorites."},
    "fav_empty": {
        RU: "Избранное пусто. Добавляй ресурсы кнопкой ⭐ под результатами поиска.",
        EN: "No favorites yet. Save resources with the ⭐ button under search results.",
    },
    "fav_header": {RU: "<b>⭐ Твоё избранное:</b>\n\n", EN: "<b>⭐ Your favorites:</b>\n\n"},
    "cats_header": {RU: "🗂 <b>Категории базы:</b>\n", EN: "🗂 <b>Base categories:</b>\n"},
    "cat_items_header": {
        RU: "🗂 <b>{cat}</b> — {count} {word}:\n\n",
        EN: "🗂 <b>{cat}</b> — {count} {word}:\n\n",
    },
    "res_word_one": {RU: "ресурс", EN: "resource"},
    "res_word_many": {RU: "ресурсов", EN: "resources"},
    "back_btn": {RU: "⬅️ Назад", EN: "⬅️ Back"},
    "back_to_cats_btn": {RU: "🗂 Категории", EN: "🗂 Categories"},
    "prev_btn": {RU: "⬅️", EN: "⬅️"},
    "next_btn": {RU: "➡️", EN: "➡️"},
    "related_header": {
        RU: "↔️ <b>Похожее на «{title}»:</b>\n\n{list}",
        EN: "↔️ <b>Similar to “{title}”:</b>\n\n{list}",
    },
    "related_empty": {RU: "Похожего не нашлось 🤷", EN: "Nothing similar found 🤷"},
    "suggest_intro": {
        RU: "💡 Предложи ресурс! Пришли <b>название</b> одним сообщением "
            "(или /cancel для отмены).",
        EN: "💡 Suggest a resource! Send the <b>title</b> as a single message "
            "(or /cancel to abort).",
    },
    "suggest_url": {
        RU: "Теперь <b>ссылку</b> (https://…):",
        EN: "Now the <b>URL</b> (https://…):",
    },
    "suggest_category": {
        RU: "Выбери <b>категорию</b>:",
        EN: "Pick a <b>category</b>:",
    },
    "suggest_comment": {
        RU: "Последний штрих: <b>зачем этот ресурс</b> одним предложением "
            "(или «-», чтобы пропустить).",
        EN: "Final touch: <b>why is it useful</b>, in one sentence "
            "(or “-” to skip).",
    },
    "suggest_done": {
        RU: "Спасибо! Предложение отправлено на модерацию 💡",
        EN: "Thanks! Your suggestion was sent for review 💡",
    },
    "cancelled": {RU: "Отменено.", EN: "Cancelled."},
    "invalid_url": {RU: "Это не похоже на ссылку. Пришли ещё раз:", EN: "That doesn't look like a URL. Try again:"},
    "lang_set": {RU: "Язык: русский 🇷🇺", EN: "Language: English 🇬🇧"},
    "lang_btn": {RU: "🇷🇺 Русский", EN: "🇬🇧 English"},
    "about": {
        RU: "<b>LinkTree</b> — курируемая база полезных инструментов и open-source "
            "репозиториев с семантическим поиском. Никакой воды — только проверенные ссылки.\n\n"
            "Внутри: гибридный поиск по смыслу (векторные представления запроса и ресурсов), "
            "работает офлайн, без внешних API.",
        EN: "<b>LinkTree</b> — a curated base of useful tools and open-source repositories "
            "with semantic search. No fluff — only verified links.\n\n"
            "Under the hood: hybrid meaning-based search (vector representations of queries "
            "and resources), runs offline, no external APIs.",
    },
    "digest_on": {
        RU: "📮 Еженедельный дайджест <b>включён</b> (ресурс недели по понедельникам). "
            "Выключить: /digest",
        EN: "📮 Weekly digest <b>enabled</b> (resource of the week, Mondays). "
            "Disable: /digest",
    },
    "digest_off": {RU: "📮 Дайджест выключен.", EN: "📮 Digest disabled."},
    "digest_msg": {
        RU: "📮 <b>Ресурс недели</b>\n\n{card}",
        EN: "📮 <b>Resource of the week</b>\n\n{card}",
    },
    "flood_warning": {
        RU: "⏳ Не так быстро — подожди пару секунд.",
        EN: "⏳ Easy — wait a couple of seconds.",
    },
    "error_generic": {
        RU: "😮‍💨 Что-то сломалось. Уже разбираюсь — попробуй ещё раз чуть позже.",
        EN: "😮‍💨 Something broke. I'm on it — try again a bit later.",
    },
    "banned_notice": {RU: "Доступ ограничен.", EN: "Access restricted."},
    "unknown_message": {
        RU: "Не понял сообщение 🤔 Напиши запрос текстом, например: <i>«библиотека для графиков»</i>.",
        EN: "Didn't get that 🤔 Send a text query, e.g.: <i>“charting library”</i>.",
    },
    # админка
    "admin_only": {RU: "Только для админов.", EN: "Admins only."},
    "admin_panel": {
        RU: "🛠 <b>Админ-панель</b>\n\nПользователей: <b>{users}</b>\n"
            "Ресурсов в базе: <b>{resources}</b>\nЗапросов за 24 ч: <b>{queries}</b>\n"
            "Предложений на модерации: <b>{pending}</b>\n"
            "Разборов задач: <b>{plans_total}</b> (активных {plans_active}, шагов закрыто {steps_done})\n\n"
            "{top}\n"
            "<code>/add &lt;json&gt;</code> — добавить ресурс\n"
            "<code>/export</code> / <code>/import</code> — выгрузка/загрузка JSON\n"
            "<code>/broadcast &lt;текст&gt;</code> — рассылка\n"
            "<code>/ban &lt;id&gt;</code>, <code>/unban &lt;id&gt;</code>\n"
            "<code>/reindex</code> — пересобрать поисковый индекс",
        EN: "🛠 <b>Admin panel</b>\n\nUsers: <b>{users}</b>\n"
            "Resources: <b>{resources}</b>\nQueries in 24h: <b>{queries}</b>\n"
            "Pending suggestions: <b>{pending}</b>\n"
            "Task breakdowns: <b>{plans_total}</b> (active {plans_active}, steps closed {steps_done})\n\n"
            "{top}\n"
            "<code>/add &lt;json&gt;</code> — add a resource\n"
            "<code>/export</code> / <code>/import</code> — JSON export/import\n"
            "<code>/broadcast &lt;text&gt;</code> — broadcast\n"
            "<code>/ban &lt;id&gt;</code>, <code>/unban &lt;id&gt;</code>\n"
            "<code>/reindex</code> — rebuild the search index",
    },
    "top_queries_header": {RU: "🔥 Топ запросов (24 ч):\n{list}\n", EN: "🔥 Top queries (24h):\n{list}\n"},
    "no_queries_yet": {RU: "Запросов пока нет.", EN: "No queries yet."},
    "res_card": {
        RU: "<b>{i}. {title}</b> {badge}\n{url}\n{desc}\n<i>Категория: {cat} · Теги: {tags}</i>",
        EN: "<b>{i}. {title}</b> {badge}\n{url}\n{desc}\n<i>Category: {cat} · Tags: {tags}</i>",
    },
    "pro_badge": {RU: "⭐", EN: "⭐"},
    "res_footer": {RU: "\n\nРелевантность: {score}%", EN: "\n\nRelevance: {score}%"},
    "admin_res_added": {RU: "✅ Добавлено: {title} (id {rid})", EN: "✅ Added: {title} (id {rid})"},
    "admin_bad_json": {
        RU: "❌ Некорректный JSON. Пример:\n<code>{\"title\":\"FastAPI\",\"url\":\"https://github.com/fastapi/fastapi\",\"category\":\"python\",\"tags\":[\"api\",\"web\"],\"ru\":\"скоростной веб-фреймворк\",\"en\":\"fast web framework\"}</code>",
        EN: "❌ Invalid JSON. Example:\n<code>{\"title\":\"FastAPI\",\"url\":\"https://github.com/fastapi/fastapi\",\"category\":\"python\",\"tags\":[\"api\",\"web\"],\"ru\":\"fast web framework\"}</code>",
    },
    "admin_export_ready": {RU: "📄 Выгрузка базы:", EN: "📄 Base export:"},
    "admin_import_prompt": {
        RU: "Пришли JSON-файл со списком ресурсов (массив объектов) следующим сообщением.",
        EN: "Send a JSON file with a resource list (array of objects) as the next message.",
    },
    "admin_import_done": {
        RU: "✅ Импорт завершён: добавлено {added}, обновлено {updated}.",
        EN: "✅ Import done: {added} added, {updated} updated.",
    },
    "admin_import_bad": {RU: "❌ Не удалось разобрать файл: {err}", EN: "❌ Failed to parse file: {err}"},
    "admin_bc_prompt": {
        RU: "Пришли текст рассылки (HTML) следующим сообщением, либо /cancel.",
        EN: "Send the broadcast text (HTML) as the next message, or /cancel.",
    },
    "admin_bc_confirm": {
        RU: "Отправить это {users} пользователям?\n\n{preview}",
        EN: "Send this to {users} users?\n\n{preview}",
    },
    "admin_bc_done": {RU: "📬 Отправлено: {sent}, ошибок: {errors}", EN: "📬 Delivered: {sent}, errors: {errors}"},
    "admin_no_users": {RU: "Пользователей нет.", EN: "No users yet."},
    "sugg_card": {
        RU: "💡 <b>Новое предложение</b> (id {sid})\nОт: {user}\nНазвание: {title}\nURL: {url}\n"
            "Категория: {cat}\nКомментарий: {comment}",
        EN: "💡 <b>New suggestion</b> (id {sid})\nFrom: {user}\nTitle: {title}\nURL: {url}\n"
            "Category: {cat}\nComment: {comment}",
    },
    "sugg_approved": {RU: "✅ Предложение {sid} одобрено.", EN: "✅ Suggestion {sid} approved."},
    "sugg_rejected": {RU: "🗑 Предложение {sid} отклонено.", EN: "🗑 Suggestion {sid} rejected."},
    "sugg_user_notify": {
        RU: "🎉 Твой ресурс <b>{title}</b> добавлен в базу! Спасибо 💛",
        EN: "🎉 Your resource <b>{title}</b> joined the base! Thanks 💛",
    },
    "sugg_empty": {RU: "Предложений на модерации нет.", EN: "No pending suggestions."},
    "admin_banned": {RU: "🔒 Пользователь {uid} забанен.", EN: "🔒 User {uid} banned."},
    "admin_unbanned": {RU: "🔓 Пользователь {uid} разбанен.", EN: "🔓 User {uid} unbanned."},
    "admin_reindexed": {
        RU: "🔁 Индекс пересобран: {n} ресурсов за {ms} мс.",
        EN: "🔁 Index rebuilt: {n} resources in {ms} ms.",
    },
    "admin_stats_title": {RU: "📊 <b>Статистика</b>\n\n", EN: "📊 <b>Stats</b>\n\n"},
    "ping_ok": {RU: "🏓 Понг! Аптайм: {uptime}", EN: "🏓 Pong! Uptime: {uptime}"},
    # разбор задачи (МАРСИ)
    "plan_btn": {RU: "🧩 Разбор задачи", EN: "🧩 Task breakdown"},
    "plan_intro": {
        RU: "🧩 <b>Разбор задачи</b>\n\nОпиши задачу или проект одним сообщением — я разложу её"
            " на атомарные шаги и подберу к каждому проверенный инструмент из базы.\n\n"
            "Например: <i>«хочу сделать телеграм-бота с оплатой»</i> или"
            " <i>«нужно распарсить сайт и сделать дашборд»</i>\n\n"
            "Дальше — 5 коротких вопросов цифрами от 1 до 5 (или /cancel).",
        EN: "🧩 <b>Task breakdown</b>\n\nDescribe your task or project in one message — I will decompose it"
            " into atomic steps and match a verified tool to each one.\n\n"
            "E.g.: <i>“I want a telegram bot with payments”</i> or"
            " <i>“need to scrape a site and build a dashboard”</i>\n\n"
            "Then 5 quick questions with digits 1–5 (or /cancel).",
    },
    "plan_q_t": {RU: "⏱ <b>Насколько срочно?</b>\n1 — «когда-нибудь» · 5 — «горит сейчас»", EN: "⏱ <b>How urgent?</b>\n1 — “someday” · 5 — “on fire now”"},
    "plan_q_y": {RU: "💥 <b>Что будет, если НЕ сделать?</b>\n1 — ничего страшного · 5 — серьёзный ущерб", EN: "💥 <b>What happens if you DON'T do it?</b>\n1 — nothing bad · 5 — serious damage"},
    "plan_q_g": {
        RU: "🧠 <b>Насколько ясно, что именно делать?</b>\n1 — «вообще не понимаю» · 5 — «всё понятно»\n(или кнопка 🤷)",
        EN: "🧠 <b>How clear is what exactly to do?</b>\n1 — “no idea” · 5 — “crystal clear”\n(or the 🤷 button)",
    },
    "plan_dontknow_btn": {RU: "🤷 Не знаю", EN: "🤷 No idea"},
    "plan_q_h": {RU: "💎 <b>Сколько пользы принесёт?</b>\n1 — немного · 5 — очень много", EN: "💎 <b>How much value will it bring?</b>\n1 — a little · 5 — a lot"},
    "plan_q_r": {
        RU: "🔋 <b>Сколько ресурсов готов вложить?</b>\n(время/силы/бюджет) 1 — мало · 5 — много",
        EN: "🔋 <b>How many resources can you invest?</b>\n(time/energy/budget) 1 — little · 5 — a lot",
    },
    "plan_q_custom": {
        RU: "📝 Можешь добавить свои шаги текстом (по одному в сообщении).\n"
            "Они попадут в план как «чёрные ящики» без ссылки.\n"
            "Отправь «-», чтобы закончить и получить разбор.",
        EN: "📝 You can add your own steps as text (one per message).\n"
            "They will join the plan as “black boxes”.\n"
            "Send “-” to finish and get the breakdown.",
    },
    "plan_bad_digit": {RU: "Пришли цифру от 1 до 5 🙂", EN: "Send a digit from 1 to 5 🙂"},
    "plan_no_resources": {
        RU: "😕 По запросу не нашлось инструментов в базе — разбор не собрать. "
            "Попробуй переформулировать: /plan",
        EN: "😕 No tools found for this query — cannot build a breakdown. "
            "Try rephrasing: /plan",
    },
    "plan_header": {
        RU: "🧩 <b>Разбор задачи:</b> «{query}»\n\n{params}\n"
            "Клей плана: <b>{glue}</b> (ΣW {w} − ресурсы {r} + связи {phi} − ε {eps})\n\n"
            "🎯 <b>Первопричина:</b> шаг {root} — с него начни, обнуление даст максимум эффекта\n",
        EN: "🧩 <b>Task breakdown:</b> “{query}”\n\n{params}\n"
            "Plan glue: <b>{glue}</b> (ΣW {w} − resources {r} + links {phi} − ε {eps})\n\n"
            "🎯 <b>Root cause:</b> step {root} — start here, zeroing it gives the biggest effect\n",
    },
    "plan_params_line": {
        RU: "срочность {t} · ущерб {y} · ясность {g} · ценность {h} · ресурсы {R}",
        EN: "urgency {t} · damage {y} · clarity {g} · value {h} · resources {R}",
    },
    "plan_step_line": {
        RU: "{mark} <b>{n}. {title}</b>{root}\n{url}\n<i>вес {w} · тяжесть {r} · приоритет {p}</i>",
        EN: "{mark} <b>{n}. {title}</b>{root}\n{url}\n<i>weight {w} · heaviness {r} · priority {p}</i>",
    },
    "plan_step_root_mark": {RU: " 🎯", EN: " 🎯"},
    "plan_mark_done": {RU: "✅", EN: "✅"},
    "plan_mark_pending": {RU: "▫️", EN: "▫️"},
    "plan_mark_skipped": {RU: "⏭", EN: "⏭"},
    "plan_done_btn": {RU: "✅ Сделал", EN: "✅ Done"},
    "plan_skip_btn": {RU: "⏭ Заменить", EN: "⏭ Replace"},
    "plan_close_btn": {RU: "🗑 Закрыть план", EN: "🗑 Close plan"},
    "plan_view_btn": {RU: "🧩 Открыть", EN: "🧩 Open"},
    "plan_step_done_msg": {RU: "Шаг закрыт! Пересчитываю план…", EN: "Step closed! Recomputing…"},
    "plan_step_skipped_msg": {RU: "Хорошо, подбираю замену…", EN: "OK, picking a replacement…"},
    "plan_replaced_msg": {RU: "Заменил на следующий кандидат из подборки.", EN: "Replaced with the next candidate."},
    "plan_no_replacement": {RU: "Замены не нашлось — шаг просто пропущен.", EN: "No replacement left — step skipped."},
    "plan_finished": {
        RU: "🏁 <b>План закрыт — все шаги выполнены!</b>\n\nЕсли задача выросла — стартуй новый разбор: /plan",
        EN: "🏁 <b>Plan complete — all steps done!</b>\n\nIf the task grew — start a new breakdown: /plan",
    },
    "plan_list_header": {RU: "📋 <b>Активные разборы:</b>\n\n{list}", EN: "📋 <b>Active breakdowns:</b>\n\n{list}"},
    "plan_list_empty": {RU: "Активных разборов нет. Начни: /plan", EN: "No active breakdowns. Start one: /plan"},
    "plan_deleted": {RU: "План закрыт.", EN: "Plan closed."},
    "plan_own_step_saved": {RU: "Шаг добавлен. Ещё шаг или «-» для разбора.", EN: "Step added. One more, or “-” for the breakdown."},
}

CATEGORIES = {
    "python": {RU: "🐍 Python", EN: "🐍 Python"},
    "javascript": {RU: "🟨 JavaScript / TS", EN: "🟨 JavaScript / TS"},
    "web": {RU: "🌐 Веб и фронтенд", EN: "🌐 Web & frontend"},
    "backend": {RU: "🔧 Бэкенд и API", EN: "🔧 Backend & APIs"},
    "data": {RU: "📊 Данные и визуализация", EN: "📊 Data & visualization"},
    "ml-ai": {RU: "🤖 ML и AI", EN: "🤖 ML & AI"},
    "devops": {RU: "🐳 DevOps и инфраструктура", EN: "🐳 DevOps & infra"},
    "cli": {RU: "⌨️ Терминал и CLI", EN: "⌨️ Terminal & CLI"},
    "security": {RU: "🔐 Безопасность", EN: "🔐 Security"},
    "learning": {RU: "🎓 Обучение и роадмапы", EN: "🎓 Learning & roadmaps"},
    "design": {RU: "🎨 Дизайн и UI", EN: "🎨 Design & UI"},
    "game-dev": {RU: "🎮 Геймдев", EN: "🎮 Game dev"},
    "tools": {RU: "🧰 Инструменты и сервисы", EN: "🧰 Tools & services"},
    "awesome": {RU: "💎 Подборки (awesome)", EN: "💎 Curated lists (awesome)"},
}


def tr(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    lang = lang if lang in LANGS else DEFAULT_LANG
    entry = _TR.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**kwargs) if kwargs else text


def cat_name(key: str, lang: str = DEFAULT_LANG) -> str:
    lang = lang if lang in LANGS else DEFAULT_LANG
    entry = CATEGORIES.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry[DEFAULT_LANG]


def plural_ru(n: int, lang: str) -> str:
    """Форма слова «ресурсов» для счётчика в списке категорий."""
    if lang == RU:
        if n % 10 == 1 and n % 100 != 11:
            return tr("res_word_one", lang)
        return tr("res_word_many", lang)
    return "resource" if n == 1 else "resources"


# Псевдонимы категорий для пользовательских запросов («для пдф» и т.п.)
CATEGORY_ALIASES = {
    "питон": "python", "питоне": "python", "пайтона": "python", "пайтон": "python",
    "js": "javascript", "джаваскрипт": "javascript", "тайпскрипт": "javascript",
    "фронтенд": "web", "веб": "web", "сайт": "web", "сайты": "web",
    "бэкенд": "backend", "бэк": "backend", "апи": "backend",
    "данные": "data", "графики": "data",
    "нейросети": "ml-ai", "нейросеть": "ml-ai", "ии": "ml-ai", "мл": "ml-ai",
    "девопс": "devops", "докер": "devops", "кубернетес": "devops",
    "терминал": "cli", "консоль": "cli", "шелл": "cli",
    "безопасность": "security", "хакинг": "security",
    "обучение": "learning", "новичку": "learning", "учеба": "learning",
    "дизайн": "design", "иконки": "design",
    "геймдев": "game-dev", "игры": "game-dev", "игра": "game-dev",
    "инструменты": "tools", "сервисы": "tools",
    "подборки": "awesome", "списки": "awesome",
}
