"""🧩 Разбор задачи (детерминированное ядро МАРСИ).

Анкета кнопками → числа 0..1 → декомпозиция на ячейки-шаги → микро-методы из
курируемой базы (семантический поиск) → клей Φ и приоритеты B → план с
первопричиной Z → цикл i→i+1 («сделал»/«заменил» → пересчёт). Без LLM.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import keyboards as kb
from i18n import tr
from marsi import (Candidate, PlanParams, Step, cascade_after_done, cell_weight,
                   complexity, entropy, greedy_plan, norm5, phi, priority_b, rerank)
from services import category_hints_from_query, safe_edit, send_long

log = logging.getLogger("linktree.plan")

MAX_POOL = 10  # глубина пула кандидатов из поиска


class PlanStates(StatesGroup):
    query = State()
    t = State()
    y = State()
    g = State()
    h = State()
    r = State()
    custom = State()


# ---------------------------------------------------------------- утилиты

def _is_menu_text(message: Message) -> bool:
    text = message.text
    return bool(text) and text in kb.all_menu_texts()


def _parse_digit(text: str) -> float:
    """«1»..«5» → 0.2..1.0; «🤷 …» → 0.5 (не знаю). ValueError если мусор."""
    text = (text or "").strip()
    if text and text[0] == "\U0001f937":  # 🤷
        return 0.5
    if text.isdigit() and 1 <= int(text) <= 5:
        return norm5(int(text))
    raise ValueError(text)


def _candidate_from_item(item: dict) -> Candidate:
    return Candidate(
        resource_id=item.get("resource_id"), title=item["title"],
        url=item.get("url") or "", category=item.get("category") or "tools",
        tags=item.get("tags") or [], relevance=0.5,
        custom=bool(item.get("custom")),
    )


def _steps_from_items(items: list) -> list:
    steps = []
    for item in items:
        steps.append(Step(
            candidate=_candidate_from_item(item),
            weight=item["weight"], complexity=item["complexity"],
            priority=item["priority"], position=item["position"],
            is_root=bool(item["is_root"]), status=item["status"],
        ))
    return steps


def _fmt(x: float) -> str:
    return "%.2f" % x


def render_plan_text(plan: dict, lang: str) -> str:
    """Текст разбора: параметры, клей, первопричина, шаги."""
    params = PlanParams.from_dict(_load_json(plan["params"], {}))
    items = plan["items"]
    params_line = tr("plan_params_line", lang, t=_fmt(params.t), y=_fmt(params.y),
                     g=_fmt(params.g), h=_fmt(params.h), R=_fmt(params.R))
    pending = [i for i in items if i["status"] == "pending"]
    glue_w = sum(i["weight"] for i in items)
    glue_r = 0.6 * sum(i["complexity"] for i in items)
    cands = [_candidate_from_item(i) for i in items]
    phi_sum = 0.0
    for a in range(len(cands)):
        for b in range(a + 1, len(cands)):
            phi_sum += phi(cands[a], cands[b])
    eps = len(pending) * entropy(params.g)
    glue = glue_w - glue_r + phi_sum - eps
    root_num = next((i["position"] + 1 for i in items if i["is_root"] and i["status"] == "pending"), None)
    root_line = str(root_num) if root_num else "—"
    text = tr("plan_header", lang, query=plan["query"], params=params_line,
              glue=_fmt(glue), w=_fmt(glue_w), r=_fmt(glue_r),
              phi=_fmt(phi_sum), eps=_fmt(eps), root=root_line)
    marks = {"done": tr("plan_mark_done", lang), "pending": tr("plan_mark_pending", lang),
             "skipped": tr("plan_mark_skipped", lang)}
    for item in items:
        text += "\n" + tr("plan_step_line", lang,
                          mark=marks.get(item["status"], "▫️"),
                          n=item["position"] + 1, title=item["title"],
                          root=tr("plan_step_root_mark", lang) if item["is_root"] and item["status"] == "pending" else "",
                          url=item["url"] or "—", w=_fmt(item["weight"]),
                          r=_fmt(item["complexity"]), p=int(item["priority"] * 100))
    return text


def _load_json(raw, default):
    import json as _json
    try:
        return _json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------- FSM анкеты

async def cmd_plan(message: Message, lang: str, state: FSMContext) -> None:
    await state.set_state(PlanStates.query)
    await state.set_data({})
    await message.answer(tr("plan_intro", lang), reply_markup=kb.cancel_kb(lang))


async def plan_button_entry(message: Message, lang: str, state: FSMContext) -> None:
    await cmd_plan(message, lang, state)


async def plan_query_input(message: Message, lang: str, state: FSMContext) -> None:
    if _is_menu_text(message):
        await message.answer(tr("plan_intro", lang))
        return
    query = (message.text or "").strip()
    if not query:
        await message.answer(tr("plan_intro", lang))
        return
    await state.update_data(query=query[:300])
    await state.set_state(PlanStates.t)
    await message.answer(tr("plan_q_t", lang), reply_markup=kb.scale_kb(lang))


async def _ask_next(message: Message, lang: str, state: FSMContext,
                    current: str, next_state, next_key: str) -> None:
    try:
        value = _parse_digit(message.text)
    except ValueError:
        await message.answer(tr("plan_bad_digit", lang))
        return
    await state.update_data(**{current: value})
    await state.set_state(next_state)
    await message.answer(tr(next_key, lang),
                         reply_markup=kb.scale_kb(lang, include_dontknow=(next_state == PlanStates.g)))


async def plan_t(message: Message, lang: str, state: FSMContext) -> None:
    await _ask_next(message, lang, state, "t", PlanStates.y, "plan_q_y")


async def plan_y(message: Message, lang: str, state: FSMContext) -> None:
    await _ask_next(message, lang, state, "y", PlanStates.g, "plan_q_g")


async def plan_g(message: Message, lang: str, state: FSMContext) -> None:
    await _ask_next(message, lang, state, "g", PlanStates.h, "plan_q_h")


async def plan_h(message: Message, lang: str, state: FSMContext) -> None:
    await _ask_next(message, lang, state, "h", PlanStates.r, "plan_q_r")


async def plan_r(message: Message, lang: str, state: FSMContext, db, engine) -> None:
    try:
        value = _parse_digit(message.text)
    except ValueError:
        await message.answer(tr("plan_bad_digit", lang))
        return
    await state.update_data(r=value)
    await state.set_state(PlanStates.custom)
    await message.answer(tr("plan_q_custom", lang), reply_markup=kb.cancel_kb(lang))


async def plan_custom_input(message: Message, lang: str, state: FSMContext, db, engine) -> None:
    """Свои шаги (чёрные ящики): по одному в сообщении; «-» — построить план."""
    text = (message.text or "").strip()
    if _is_menu_text(message):
        await message.answer(tr("plan_q_custom", lang))
        return
    if text in ("-", "–", "—", "."):
        await build_plan(message, lang, state, db, engine)
        return
    steps = (await state.get_data()).get("custom_steps", [])
    steps.append(text[:200])
    await state.update_data(custom_steps=steps)
    await message.answer(tr("plan_own_step_saved", lang))


# ---------------------------------------------------------------- сборка плана

async def build_plan(message: Message, lang: str, state: FSMContext, db, engine) -> None:
    data = await state.get_data()
    await state.clear()
    query = data.get("query", "").strip()
    if not query:
        await cmd_plan(message, lang, state)
        return
    params = PlanParams(
        t=data.get("t", 0.6), y=data.get("y", 0.6), g=data.get("g", 0.6),
        h=data.get("h", 0.7), R=data.get("r", 0.6),
    )
    hits = await engine.search_async(query, k=MAX_POOL,
                                     category_hints=category_hints_from_query(query))
    candidates = [
        Candidate(resource_id=h.doc.rid, title=h.doc.title, url=h.doc.url,
                  category=h.doc.category, tags=h.doc.tags,
                  relevance=min(1.0, max(h.score, 0.0)), score=h.doc.score)
        for h in hits
    ]
    custom_titles = data.get("custom_steps", [])
    if not candidates and not custom_titles:
        await message.answer(tr("plan_no_resources", lang), reply_markup=kb.main_menu(lang))
        return
    custom_candidates = [
        Candidate(resource_id=None, title=t, url="", category="tools", tags=[],
                  relevance=0.5, custom=True)
        for t in custom_titles
    ]
    # свои шаги — обязательные ячейки; ресурсы добираются жадным отбором
    plan = greedy_plan(params, candidates, required=custom_candidates)
    if not plan.steps:
        await message.answer(tr("plan_no_resources", lang), reply_markup=kb.main_menu(lang))
        return
    spare_pool = [
        {"resource_id": c.resource_id, "title": c.title, "url": c.url,
         "category": c.category, "tags": c.tags, "relevance": c.relevance}
        for c in candidates
        if c.resource_id not in {s.candidate.resource_id for s in plan.steps}
    ]
    plan_id = await db.create_plan(message.from_user.id, query, params.as_dict(), spare_pool)
    for step in plan.steps:
        await db.add_plan_item(
            plan_id=plan_id, resource_id=step.candidate.resource_id,
            title=step.candidate.title, url=step.candidate.url,
            category=step.candidate.category, tags=step.candidate.tags,
            custom=step.candidate.custom, weight=step.weight,
            complexity=step.complexity, priority=step.priority,
            position=step.position, is_root=step.is_root,
        )
    stored = await db.get_plan(plan_id)
    await send_long(message, render_plan_text(stored, lang),
                    reply_markup=kb.plan_steps_kb(stored["items"], plan_id, lang))


# ---------------------------------------------------------------- действия с планом

def _steps_payload(steps: list) -> list:
    import time as _time
    payload = []
    for s in steps:
        payload.append({
            "id": s.item_id, "weight": s.weight, "priority": s.priority,
            "position": s.position, "is_root": s.is_root, "status": s.status,
            "done_at": int(_time.time()) if s.status == "done" else s.prev_done_at,
        })
    return payload


class _TaggedStep(Step):
    """Step с привязкой к id строки БД."""
    def __init__(self, item_id: int, base: Step, prev_done_at: int = 0) -> None:
        super().__init__(candidate=base.candidate, weight=base.weight,
                         complexity=base.complexity, priority=base.priority,
                         position=base.position, is_root=base.is_root, status=base.status)
        self.item_id = item_id
        self.prev_done_at = prev_done_at


def _steps_with_ids(items: list) -> list:
    steps = _steps_from_items(items)
    return [_TaggedStep(item["id"], s, item.get("done_at") or 0)
            for item, s in zip(items, steps)]


async def _recompute_and_render(callback: CallbackQuery, plan_id: int, lang: str, db,
                                steps=None) -> None:
    plan = await db.get_plan(plan_id)
    if plan is None:
        await callback.answer()
        return
    if steps is None:
        steps = _steps_with_ids(plan["items"])
    params = PlanParams.from_dict(_load_json(plan["params"], {}))
    rerank(steps, params)
    await db.save_plan_state(plan_id, _steps_payload(steps))
    if await db.finish_plan_if_done(plan_id):
        try:
            await callback.message.edit_text(tr("plan_finished", lang))
        except Exception:  # noqa: BLE001
            await callback.message.answer(tr("plan_finished", lang))
        return
    plan = await db.get_plan(plan_id)
    await safe_edit(callback, render_plan_text(plan, lang),
                    kb.plan_steps_kb(plan["items"], plan_id, lang))


async def cb_plan_done(callback: CallbackQuery, lang: str, db) -> None:
    try:
        item_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    item = await db.get_plan_item(item_id)
    if item is None or item["status"] != "pending":
        await callback.answer()
        return
    plan_id = item["plan_id"]
    if await db.get_plan_owner(plan_id) != callback.from_user.id:
        await callback.answer()
        return
    await callback.answer(tr("plan_step_done_msg", lang))
    plan = await db.get_plan(plan_id)
    steps = _steps_with_ids(plan["items"])
    idx = next(i for i, s in enumerate(steps) if s.item_id == item_id)
    cascade_after_done(steps, idx)
    await _recompute_and_render(callback, plan_id, lang, db, steps=steps)


async def cb_plan_skip(callback: CallbackQuery, lang: str, db) -> None:
    try:
        item_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    item = await db.get_plan_item(item_id)
    if item is None or item["status"] != "pending":
        await callback.answer()
        return
    plan_id = item["plan_id"]
    if await db.get_plan_owner(plan_id) != callback.from_user.id:
        await callback.answer()
        return
    await callback.answer(tr("plan_step_skipped_msg", lang))
    # фиксируем skipped в БД (вес обнуляем — ячейка больше не тянет ресурс)
    await db.set_item_status(item_id, "skipped", weight=0.0)
    plan = await db.get_plan(plan_id)
    spare = _load_json(plan["candidates"], [])
    used = {i["resource_id"] for i in plan["items"] if i["resource_id"]}
    params = PlanParams.from_dict(_load_json(plan["params"], {}))
    replaced = False
    remaining = []
    for cand in spare:
        if replaced or (cand.get("resource_id") in used):
            remaining.append(cand)
            continue
        new_cand = Candidate(resource_id=cand.get("resource_id"), title=cand["title"],
                             url=cand.get("url", ""), category=cand.get("category", "tools"),
                             tags=cand.get("tags", []),
                             relevance=float(cand.get("relevance", 0.5)))
        w = cell_weight(params, new_cand)
        r = complexity(new_cand)
        await db.add_plan_item(
            plan_id=plan_id, resource_id=new_cand.resource_id, title=new_cand.title,
            url=new_cand.url, category=new_cand.category, tags=new_cand.tags,
            custom=False, weight=w, complexity=r, priority=priority_b(w, r, params),
            position=999, is_root=False,
        )
        replaced = True
    await db.update_plan_candidates(plan_id, remaining)
    # пересчёт: skipped фиксируем через состояние шагов
    plan = await db.get_plan(plan_id)
    await _recompute_and_render(callback, plan_id, lang, db)
    if replaced:
        await callback.message.answer(tr("plan_replaced_msg", lang))
    else:
        await callback.message.answer(tr("plan_no_replacement", lang))


async def cb_plan_view(callback: CallbackQuery, lang: str, db) -> None:
    try:
        plan_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    if await db.get_plan_owner(plan_id) != callback.from_user.id:
        await callback.answer()
        return
    plan = await db.get_plan(plan_id)
    if plan is None:
        await callback.answer()
        return
    await callback.message.answer(render_plan_text(plan, lang),
                                  reply_markup=kb.plan_steps_kb(plan["items"], plan_id, lang),
                                  disable_web_page_preview=True)
    await callback.answer()


async def cb_plan_delete(callback: CallbackQuery, lang: str, db) -> None:
    try:
        plan_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    if await db.get_plan_owner(plan_id) != callback.from_user.id:
        await callback.answer()
        return
    await db.archive_plan(plan_id)
    await callback.answer(tr("plan_deleted", lang))
    try:
        await callback.message.delete()
    except Exception:  # noqa: BLE001
        await callback.message.answer(tr("plan_deleted", lang))


async def cmd_plans(message: Message, lang: str, db) -> None:
    plans = await db.active_plans(message.from_user.id)
    if not plans:
        await message.answer(tr("plan_list_empty", lang))
        return
    lines = ["• %s · осталось ⬜ %d" % (p["query"][:60], p["pending"]) for p in plans]
    await message.answer(tr("plan_list_header", lang, list="\n".join(lines)),
                         reply_markup=kb.plans_list_kb(plans, lang))


# ---------------------------------------------------------------- регистрация


def menu_plan_filter(message: Message) -> bool:
    return message.text in (kb.BTN_PLAN["ru"], kb.BTN_PLAN["en"])


def create_router() -> Router:
    """Свежий Router с хендлерами разбора задачи (фабрика — см. handlers.user)."""
    router = Router()
    router.message.filter(F.chat.type == "private")
    router.message.register(cmd_plan, Command("plan"))
    router.message.register(cmd_plans, Command("plans"))
    router.message.register(plan_button_entry, menu_plan_filter)
    router.message.register(plan_query_input, StateFilter(PlanStates.query), F.text)
    router.message.register(plan_t, StateFilter(PlanStates.t), F.text)
    router.message.register(plan_y, StateFilter(PlanStates.y), F.text)
    router.message.register(plan_g, StateFilter(PlanStates.g), F.text)
    router.message.register(plan_h, StateFilter(PlanStates.h), F.text)
    router.message.register(plan_r, StateFilter(PlanStates.r), F.text)
    router.message.register(plan_custom_input, StateFilter(PlanStates.custom), F.text)
    router.callback_query.register(cb_plan_done, F.data.startswith("pl:done:"))
    router.callback_query.register(cb_plan_skip, F.data.startswith("pl:skip:"))
    router.callback_query.register(cb_plan_view, F.data.startswith("pl:view:"))
    router.callback_query.register(cb_plan_delete, F.data.startswith("pl:del:"))
    return router
