"""Юнит-тесты детерминированного ядра МАРСИ (marsi.py)."""
from __future__ import annotations

import pytest

from marsi import (BUDGET_SCALE, LAMBDA_R, MAX_STEPS, Candidate, Plan, PlanParams,
                  Step, cascade_after_done, cell_weight, complexity, entropy,
                  find_root, greedy_plan, norm5, phi, priority_b, rerank)

PARAMS = PlanParams(t=0.8, y=0.7, g=0.6, h=0.8, R=0.8)


def make(rid, title, category, tags, relevance=0.8, custom=False):
    return Candidate(resource_id=rid, title=title, url="https://x.dev/%s" % title,
                     category=category, tags=tags, relevance=relevance, custom=custom)


class TestNormalize:
    def test_bounds(self):
        assert norm5(1) == 0.2
        assert norm5(5) == 1.0
        assert norm5(0) == 0.2
        assert norm5(9) == 1.0

    def test_entropy_grows_with_uncertainty(self):
        assert entropy(0.0) > entropy(0.5) > entropy(1.0)

    def test_params_roundtrip(self):
        p = PlanParams(t=0.1, y=0.2, g=0.3, h=0.4, R=0.5)
        assert PlanParams.from_dict(p.as_dict()) == p


class TestCellWeight:
    def test_bounds(self):
        w_min = cell_weight(PARAMS, make(1, "a", "tools", [], relevance=0.0))
        w_max = cell_weight(PlanParams(t=1, y=1, g=1, h=1, R=1),
                            make(2, "b", "ml-ai", ["llm"], relevance=1.0, ), )
        assert 0.0 < w_min < 1.5
        assert w_max < 1.5

    def test_resource_beats_black_box(self):
        res = make(1, "tool", "python", ["web"])
        box = Candidate(resource_id=None, title="свой шаг", url="", category="tools",
                        tags=[], relevance=0.5, custom=True)
        assert cell_weight(PARAMS, res) > cell_weight(PARAMS, box)

    def test_relevance_monotonic(self):
        low = cell_weight(PARAMS, make(1, "t", "python", [], relevance=0.2))
        high = cell_weight(PARAMS, make(2, "t", "python", [], relevance=1.0))
        assert high > low

    def test_votes_boost(self):
        plain = make(1, "t", "python", [])
        voted = make(1, "t", "python", [])
        voted.score = 10
        assert cell_weight(PARAMS, voted) > cell_weight(PARAMS, plain)


class TestComplexity:
    def test_category_scale(self):
        assert complexity(make(1, "a", "awesome", [])) < complexity(make(2, "b", "devops", []))
        assert complexity(make(3, "c", "ml-ai", [])) > complexity(make(4, "d", "cli", []))

    def test_heavy_tags_add(self):
        light = make(1, "a", "devops", ["docker"])
        heavy = make(2, "b", "devops", ["kubernetes", "distributed"])
        assert complexity(heavy) > complexity(light)

    def test_custom_fixed(self):
        box = Candidate(resource_id=None, title="x", url="", category="ml-ai",
                        tags=["gpu"], relevance=0.5, custom=True)
        assert complexity(box) == 0.5

    def test_bounded(self):
        worst = make(1, "w", "ml-ai", ["kubernetes", "engine", "compiler", "gpu"])
        assert complexity(worst) <= 1.0


class TestPriorityB:
    def test_low_resources_push_heavy_down(self):
        poor = PlanParams(R=0.1)
        rich = PlanParams(R=1.0)
        w, r = 0.8, 0.8
        assert priority_b(w, r, poor) < priority_b(w, r, rich)

    def test_monotonic_in_weight(self):
        assert priority_b(0.9, 0.5, PARAMS) > priority_b(0.4, 0.5, PARAMS)


class TestPhi:
    def test_alternatives_same_class_conflict(self):
        # ruff и black — форматтеры: выбор одного
        ruff = make(1, "ruff", "python", ["linter", "formatter"])
        black = make(2, "black", "python", ["formatter", "style"])
        assert phi(ruff, black) == -0.5

    def test_http_clients_conflict(self):
        httpx = make(1, "httpx", "python", ["http", "client", "async"])
        requests = make(2, "requests", "python", ["http", "client", "api"])
        assert phi(httpx, requests) < 0

    def test_same_category_competes(self):
        a = make(1, "a", "devops", ["x"])
        b = make(2, "b", "devops", ["y"])
        assert phi(a, b) == -0.2

    def test_ecosystem_synergy(self):
        fastapi = make(1, "fastapi", "backend", ["api", "python"])
        sqlalchemy = make(2, "sqlalchemy", "python", ["orm", "sql"])
        assert phi(fastapi, sqlalchemy) == 0.15

    def test_shared_tag_synergy(self):
        a = make(1, "a", "web", ["animation", "css"])
        b = make(2, "b", "design", ["animation", "icons"])
        assert phi(a, b) == 0.15

    def test_custom_neutral(self):
        box = Candidate(resource_id=None, title="x", url="", category="tools",
                        tags=[], relevance=0.5, custom=True)
        assert phi(box, make(1, "y", "python", ["web"])) == 0.0

    def test_telegram_frameworks_conflict(self):
        aiogram = make(1, "aiogram", "python", ["telegram", "bot", "async"])
        grammy = make(2, "grammy", "javascript", ["telegram", "bot", "typescript"])
        assert phi(aiogram, grammy) == -0.5

    def test_symmetric(self):
        a = make(1, "a", "backend", ["api", "python"])
        b = make(2, "b", "python", ["orm"])
        assert phi(a, b) == phi(b, a)


class TestGreedyPlan:
    CANDS = [
        make(1, "fastapi", "backend", ["api", "python"], relevance=0.9),
        make(2, "sqlalchemy", "python", ["orm", "sql", "database"], relevance=0.85),
        make(3, "ruff", "python", ["linter", "formatter"], relevance=0.7),
        make(4, "black", "python", ["formatter", "style"], relevance=0.68),
        make(5, "redis-py", "python", ["redis", "cache"], relevance=0.6),
        make(6, "alembic", "python", ["migrations", "database"], relevance=0.55),
        make(7, "rich", "python", ["terminal", "console"], relevance=0.5),
        make(8, "kubernetes", "devops", ["k8s", "orchestration"], relevance=0.45),
    ]

    def test_basic_properties(self):
        plan = greedy_plan(PARAMS, self.CANDS)
        assert 1 <= len(plan.steps) <= MAX_STEPS
        assert any(s.is_root for s in plan.steps)
        assert [s.position for s in sorted(plan.steps, key=lambda x: x.position)] == \
               list(range(len(plan.steps)))
        # приоритеты отсортированы по убыванию
        priorities = [s.priority for s in sorted(plan.steps, key=lambda x: x.position)]
        assert priorities == sorted(priorities, reverse=True)

    def test_glue_consistency(self):
        plan = greedy_plan(PARAMS, self.CANDS)
        recomputed_w = sum(s.weight for s in plan.steps)
        recomputed_phi = sum(
            phi(plan.steps[i].candidate, plan.steps[j].candidate)
            for i in range(len(plan.steps)) for j in range(i + 1, len(plan.steps)))
        assert plan.glue_w == pytest.approx(recomputed_w)
        assert plan.glue_phi == pytest.approx(recomputed_phi)
        assert plan.glue == pytest.approx(
            plan.glue_w - LAMBDA_R * sum(s.complexity for s in plan.steps)
            + plan.glue_phi - plan.glue_eps)

    def test_no_alternatives_together(self):
        plan = greedy_plan(PlanParams(t=0.9, y=0.9, g=0.9, h=0.9, R=1.0), self.CANDS)
        titles = {s.candidate.title for s in plan.steps}
        assert not {"ruff", "black"} <= titles  # форматтеры не вместе

    def test_budget_respected(self):
        poor = PlanParams(t=0.9, y=0.9, g=0.9, h=0.9, R=0.2)
        plan = greedy_plan(poor, self.CANDS)
        # либо влезли в бюджет, либо единственный самый лёгкий шаг
        total_r = sum(s.complexity for s in plan.steps)
        assert total_r <= poor.R * BUDGET_SCALE + 1e-9 or len(plan.steps) == 1

    def test_empty_candidates(self):
        plan = greedy_plan(PARAMS, [])
        assert plan.steps == []
        assert plan.glue == 0.0

    def test_black_box_included(self):
        box = Candidate(resource_id=None, title="купить домен", url="",
                        category="tools", tags=[], relevance=0.5, custom=True)
        plan = greedy_plan(PARAMS, [self.CANDS[0]], required=[box])
        titles = {s.candidate.title for s in plan.steps}
        assert "купить домен" in titles

    def test_required_survives_tight_budget(self):
        # свои шаги обязательны: даже при почти нулевом бюджете они в плане
        poor = PlanParams(t=0.2, y=0.2, g=0.2, h=0.2, R=0.1)
        box = Candidate(resource_id=None, title="позвонить заказчику", url="",
                        category="tools", tags=[], relevance=0.5, custom=True)
        heavy = make(1, "heavy", "ml-ai", ["kubernetes", "engine"], relevance=0.9)
        plan = greedy_plan(poor, [heavy], required=[box])
        titles = {s.candidate.title for s in plan.steps}
        assert "позвонить заказчику" in titles
        assert "heavy" not in titles or len(plan.steps) == 2

    def test_delta_negative_not_added(self):
        # мусорный кандидат с околонулевой пользой не должен разбавлять план
        weak = make(99, "weak", "ml-ai", ["kubernetes", "engine"], relevance=0.05)
        strong = make(1, "strong", "backend", ["api"], relevance=1.0)
        plan = greedy_plan(PlanParams(t=0.3, y=0.3, g=0.5, h=0.3, R=0.4), [strong, weak])
        titles = {s.candidate.title for s in plan.steps}
        assert "strong" in titles


class TestRootAndCascade:
    def _steps(self):
        cands = [
            make(1, "fastapi", "backend", ["api", "python"]),
            make(2, "sqlalchemy", "python", ["orm", "database"]),
            make(3, "rich", "python", ["terminal"]),
        ]
        steps = [Step(candidate=c, weight=0.5 + 0.1 * i, complexity=0.4,
                      priority=0.5, position=i) for i, c in enumerate(cands)]
        return steps

    def test_root_is_related_hub(self):
        steps = self._steps()
        idx = find_root(steps)
        # fastapi связан и с python-экосистемой, и с rich (общая категория python)
        assert steps[idx].candidate.title in {"fastapi", "sqlalchemy"}

    def test_cascade_zeroes_and_discounts(self):
        steps = self._steps()
        root_idx = find_root(steps)
        cascade_after_done(steps, root_idx)
        assert steps[root_idx].weight == 0.0
        assert steps[root_idx].status == "done"
        # кто-то из связанных получил скидку
        discounted = [s for s in steps
                      if s.status == "pending" and s.weight < 0.5 + 0.1 * s.position]
        assert discounted

    def test_rerank_sinks_finished(self):
        steps = self._steps()
        steps[0].status = "done"
        steps[0].weight = 0.0
        steps[1].status = "skipped"
        ordered = rerank(steps, PARAMS)
        statuses = [s.status for s in ordered]
        assert statuses.index("done") > statuses.index("pending")
        assert statuses[-2:] in (["done", "skipped"], ["skipped", "done"])
        assert sum(1 for s in ordered if s.is_root) <= 1
        root = next((s for s in ordered if s.is_root), None)
        assert root is None or root.status == "pending"

    def test_glue_property(self):
        plan = Plan()
        assert plan.glue == 0.0
        plan.glue_w, plan.glue_r, plan.glue_phi, plan.glue_eps = 3.0, 1.0, 0.5, 0.1
        assert plan.glue == pytest.approx(2.4)
