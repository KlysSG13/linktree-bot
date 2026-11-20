"""Детерминированное ядро МАРСИ в применении к разбору dev-задач в LinkTree.

Соответствие терминов статьи и реализации:

  Монолит V            → запрос пользователя («сделать телеграм-бота с оплатой»)
  Ячейка A_n           → атомарный шаг плана (аспект задачи, закрываемый одним ресурсом)
  Микро-метод          → ресурс курируемой базы (библиотека/инструмент/гайд)
  W (вес ячейки)       → cell_weight: нормированная сумма (t+m+f+e+y+g+h)/7 + ε
  r (ресурсозатраты)   → complexity: тяжесть категории + надбавки за тяжёлые теги
  B (приоритет)        → W · R/(R+r): ограничитель «не назначать то, на что нет сил»
  Φ_jk («клей» пары)   → phi: синергия (+), нейтральность (0), конфликт (−),
                         альтернативы одного класса (−0.5, выбор одного)
  КЛЕЙ плана           → ΣW − λ·Σr + ΣΦ − N·ε (максимизируется жадным отбором)
  Z (первопричина)     → argmax impact: обнуление шага гасит максимум веса системы
  ε (энтропия)         → растёт при низкой уверенности пользователя в данных
  i → i+1              → «✅ сделал»/«⏭ пропустил» → пересчёт плана

Никаких LLM: анкета кнопками даёт строгие числа, поиск по базе — релевантность.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

EPS_BASE = 0.03          # базовая энтропия
LAMBDA_R = 0.6           # штраф за ресурсозатраты в формуле клея
BUDGET_SCALE = 3.0       # бюджет плана = R пользователя × масштаб
MAX_STEPS = 5            # верхняя граница шагов в плане
MIN_STEPS = 1
CUSTOM_FACTS = 0.4       # «факты реальности» у шага без ресурса (чёрный ящик)
CUSTOM_RELEVANCE = 0.5   # контекст собственного шага — середина шкалы
CASCADE_DISCOUNT = 0.75  # скидка связанным шагам после закрытия первопричины

# Тяжесть освоения/внедрения по категориям (r базовое)
CATEGORY_COMPLEXITY: Dict[str, float] = {
    "awesome": 0.30, "tools": 0.35, "cli": 0.35, "learning": 0.40,
    "design": 0.45, "python": 0.45, "javascript": 0.45, "web": 0.50,
    "backend": 0.55, "data": 0.60, "security": 0.60, "game-dev": 0.65,
    "devops": 0.70, "ml-ai": 0.75,
}
DEFAULT_COMPLEXITY = 0.5

# Теги-утяжелители: тяжесть конкретного инструмента внутри категории
HEAVY_TAGS: Dict[str, float] = {
    "kubernetes": 0.15, "k8s": 0.15, "engine": 0.15, "compiler": 0.15,
    "distributed": 0.10, "enterprise": 0.10, "gpu": 0.10, "neural": 0.10,
    "microservices": 0.10, "vision": 0.05, "llm": 0.05, "3d": 0.05,
}

# Теги, маркирующие класс инструментов: два метода одного класса — альтернативы
ALTERNATIVE_CLASS_TAGS = frozenset({
    "formatter", "linter", "http", "orm", "monitoring", "editor", "terminal",
    "notes", "screenshots", "charts", "pdf", "excel", "icons", "web-server",
    "proxy", "telegram", "bot", "bots", "crawler", "spider", "dashboard",
})

# Пары категорий из одной экосистемы: синергия (+0.15)
SYNERGY_CATEGORY_PAIRS = frozenset({
    ("python", "backend"), ("python", "data"), ("python", "ml-ai"),
    ("python", "cli"), ("javascript", "web"), ("javascript", "backend"),
    ("javascript", "game-dev"), ("web", "design"), ("backend", "devops"),
    ("devops", "cli"), ("ml-ai", "data"), ("backend", "data"),
    ("learning", "python"), ("learning", "javascript"), ("learning", "web"),
})


def norm5(x: float) -> float:
    """Ответ анкеты 1..5 → нормализация в 0.2..1.0."""
    return min(max(float(x), 1.0), 5.0) / 5.0


@dataclass
class PlanParams:
    """Нормированные параметры задачи из анкеты (все 0..1)."""
    t: float = 0.6   # время/срочность
    y: float = 0.6   # критичность ущерба
    g: float = 0.6   # достоверность/уверенность в данных
    h: float = 0.7   # ценность решения / ROI
    R: float = 0.6   # доступные ресурсы (энергия/время/бюджет)

    def as_dict(self) -> Dict[str, float]:
        return {"t": round(self.t, 3), "y": round(self.y, 3), "g": round(self.g, 3),
                "h": round(self.h, 3), "R": round(self.R, 3)}

    @staticmethod
    def from_dict(data: Dict[str, float]) -> "PlanParams":
        return PlanParams(
            t=float(data.get("t", 0.6)), y=float(data.get("y", 0.6)),
            g=float(data.get("g", 0.6)), h=float(data.get("h", 0.7)),
            R=float(data.get("R", 0.6)),
        )


def entropy(g: float) -> float:
    """Коэффициент энтропии ε: чем ниже уверенность, тем больше шума поглощаем."""
    return EPS_BASE * (2.0 - min(max(g, 0.0), 1.0))


@dataclass
class Candidate:
    """Кандидат в шаги плана: ресурс базы или собственный шаг (чёрный ящик)."""
    resource_id: Optional[int]
    title: str
    url: str
    category: str
    tags: List[str]
    relevance: float          # близость к запросу (из семантического поиска)
    custom: bool = False      # свой шаг без ресурса
    score: int = 0            # индекс доверия: чистые голоса 👍/👎 по ресурсу


@dataclass
class Step:
    """Отобранный шаг плана (ячейка + назначенный микро-метод)."""
    candidate: Candidate
    weight: float        # W
    complexity: float    # r
    priority: float      # B = W·R/(R+r)
    position: int = 0
    is_root: bool = False
    status: str = "pending"   # pending | done | skipped

    def as_tuple(self) -> Tuple:
        return (self.candidate.resource_id, self.candidate.title, self.weight,
                self.complexity, self.priority)


@dataclass
class Plan:
    steps: List[Step] = field(default_factory=list)
    root_index: int = 0
    glue_w: float = 0.0
    glue_r: float = 0.0
    glue_phi: float = 0.0
    glue_eps: float = 0.0

    @property
    def glue(self) -> float:
        return self.glue_w - self.glue_r + self.glue_phi - self.glue_eps

    @property
    def total_weight(self) -> float:
        return sum(s.weight for s in self.steps)


def cell_weight(params: PlanParams, cand: Candidate) -> float:
    """W^{A_n} = (t + m + f + e + y + g + h) / 7 + ε.

    m — контекст (релевантность аспекта запросу), f — факты (есть проверенный
    ресурс = 1.0, свой шаг-«чёрный ящик» = 0.4), e — осознанная цель (задача
    сформулирована = 1.0). g дополнительно участвует в ε.
    """
    m = CUSTOM_RELEVANCE if cand.custom else min(max(cand.relevance, 0.0), 1.0)
    f = CUSTOM_FACTS if cand.custom else 1.0
    e = 1.0
    trust = 1.0 + 0.02 * max(cand.score, 0)  # индекс доверия: голоса чуть поднимают вес
    raw = (params.t + m + f + e + params.y + params.g + params.h) / 7.0
    return min(raw * trust + entropy(params.g), 1.35)


def complexity(cand: Candidate) -> float:
    """r — ресурсозатраты микро-метода: категория + надбавки за тяжёлые теги."""
    r = CATEGORY_COMPLEXITY.get(cand.category, DEFAULT_COMPLEXITY)
    if cand.custom:
        return 0.5
    for tag in cand.tags:
        r += HEAVY_TAGS.get(tag.lower(), 0.0)
    return min(r, 1.0)


def priority_b(weight: float, r: float, params: PlanParams) -> float:
    """B = W · R/(R+r): при малых ресурсах тяжёлый метод уезжает вниз списка."""
    res = min(max(params.R, 0.05), 1.0)
    return weight * res / (res + max(r, 0.05))


def phi(a: Candidate, b: Candidate) -> float:
    """Клей пары микро-методов: синергия > 0, нейтраль 0, конфликт < 0."""
    if a.custom or b.custom:
        return 0.0  # собственные шаги не взаимодействуют с инструментами
    tags_a = {t.lower() for t in a.tags}
    tags_b = {t.lower() for t in b.tags}
    # 1) один и тот же класс инструментов → выбор одного из двух
    if tags_a & tags_b & ALTERNATIVE_CLASS_TAGS:
        return -0.5
    same_cat = a.category == b.category
    shared = len(tags_a & tags_b)
    # 2) прямые альтернативы внутри категории
    if same_cat and shared >= 2:
        return -0.5
    # 3) конкуренты одной категории
    if same_cat:
        return -0.2
    # 4) комплементарные теги из разных категорий → усиливают друг друга
    if shared >= 1:
        return 0.15
    # 5) известные синергетические пары категорий (единая экосистема)
    pair = (a.category, b.category)
    if pair in SYNERGY_CATEGORY_PAIRS or (pair[1], pair[0]) in SYNERGY_CATEGORY_PAIRS:
        return 0.15
    return 0.0


def _related(cand_a: Candidate, cand_b: Candidate) -> bool:
    """Связанность ячеек для каскадного эффекта и поиска первопричины."""
    if cand_a.custom or cand_b.custom:
        return False
    tags_a = {t.lower() for t in cand_a.tags}
    tags_b = {t.lower() for t in cand_b.tags}
    if tags_a & tags_b:
        return True
    pair = (cand_a.category, cand_b.category)
    return pair in SYNERGY_CATEGORY_PAIRS or (pair[1], pair[0]) in SYNERGY_CATEGORY_PAIRS


def greedy_plan(params: PlanParams, candidates: Sequence[Candidate],
                required: Sequence[Candidate] = (),
                max_steps: int = MAX_STEPS) -> Plan:
    """Жадная сборка плана: максимизация КЛЕЙ = ΣW − λ·Σr + ΣΦ − N·ε
    с бюджетом Σr ≤ R·BUDGET_SCALE. Первопричина Z = argmax impact.

    required — обязательные ячейки (собственные шаги пользователя): попадают
    в план без отбора, их ресурсозатраты учитываются в бюджете.
    """
    pool = sorted(candidates,
                  key=lambda c: priority_b(cell_weight(params, c), complexity(c), params),
                  reverse=True)
    chosen: List[Step] = []
    budget = params.R * BUDGET_SCALE
    spent = 0.0
    for cand in sorted(required,
                       key=lambda c: priority_b(cell_weight(params, c), complexity(c), params),
                       reverse=True):
        if len(chosen) >= max_steps:
            break
        w = cell_weight(params, cand)
        r = complexity(cand)
        chosen.append(Step(candidate=cand, weight=w, complexity=r,
                           priority=priority_b(w, r, params)))
        spent += r
    for cand in pool:
        if len(chosen) >= max_steps:
            break
        w = cell_weight(params, cand)
        r = complexity(cand)
        if spent + r > budget:
            continue  # ограничитель r_obj: на это уже нет ресурсов
        phi_sum = sum(phi(cand, s.candidate) for s in chosen)
        delta = w - LAMBDA_R * r + phi_sum - entropy(params.g)
        if chosen and delta <= 0:
            continue  # шаг не увеличивает клей — не берём
        chosen.append(Step(candidate=cand, weight=w, complexity=r,
                           priority=priority_b(w, r, params)))
        spent += r
    if not chosen and pool:
        # ничего не влезло в бюджет — берём самый лёгкий метод, чтобы план существовал
        cand = min(pool, key=complexity)
        w = cell_weight(params, cand)
        r = complexity(cand)
        chosen.append(Step(candidate=cand, weight=w, complexity=r,
                           priority=priority_b(w, r, params)))
    # ранжируем шаги по приоритету B
    chosen.sort(key=lambda s: s.priority, reverse=True)
    for i, step in enumerate(chosen):
        step.position = i
    plan = Plan(steps=chosen)
    plan.glue_w = sum(s.weight for s in chosen)
    plan.glue_r = LAMBDA_R * sum(s.complexity for s in chosen)
    plan.glue_phi = sum(phi(chosen[i].candidate, chosen[j].candidate)
                        for i in range(len(chosen)) for j in range(i + 1, len(chosen)))
    plan.glue_eps = len(chosen) * entropy(params.g)
    if chosen:
        plan.root_index = find_root(chosen)
        chosen[plan.root_index].is_root = True
    return plan


def find_root(steps: Sequence[Step]) -> int:
    """Z — шаг, обнуление которого максимально снижает общий вес системы:
    impact_i = W_i + 0.3 · Σ W_j связанных (каскад гасит и их)."""
    best_idx, best_impact = 0, -1.0
    for i, step in enumerate(steps):
        impact = step.weight + 0.3 * sum(
            steps[j].weight for j in range(len(steps))
            if j != i and _related(step.candidate, steps[j].candidate)
        )
        if impact > best_impact:
            best_idx, best_impact = i, impact
    return best_idx


def cascade_after_done(steps: List[Step], done_index: int) -> List[Step]:
    """Итерация i → i+1: закрытая ячейка обнуляется, связанные получают скидку."""
    done = steps[done_index]
    done.status = "done"
    done.weight = 0.0
    for other in steps:
        if other.status == "pending" and _related(done.candidate, other.candidate):
            other.weight *= CASCADE_DISCOUNT
    return steps


def rerank(steps: List[Step], params: PlanParams) -> List[Step]:
    """Пересчёт приоритетов и позиций после изменений состояния."""
    pending = [s for s in steps if s.status == "pending"]
    for s in pending:
        s.priority = priority_b(s.weight, s.complexity, params)
    pending.sort(key=lambda s: s.priority, reverse=True)
    ordered: List[Step] = pending + [s for s in steps if s.status != "pending"]
    for i, s in enumerate(ordered):
        s.position = i
    for s in steps:
        s.is_root = False
    if pending:
        root = find_root(pending)
        pending[root].is_root = True
    return ordered
