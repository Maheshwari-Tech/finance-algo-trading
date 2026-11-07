"""Rules and strategies each user saves under their own login.

A saved strategy keeps references (ids) to saved rules, so editing a saved rule changes every strategy that uses it.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Dict, List

from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine

from ..db import saved_rules, saved_strategies
from ..domain.rules import TradeRule
from .sql_repository import _insert

MAX_RULES = 300
MAX_STRATEGIES = 100


class SavedRuleOut(TradeRule):
    used_by: List[str] = Field(default_factory=list, description="Saved strategies that use this rule")


class StrategyIn(BaseModel):
    name: str = Field(max_length=60)
    rule_ids: List[int] = Field(min_length=1, max_length=10)


class StrategyOut(BaseModel):
    name: str
    rule_ids: List[int]
    rules: List[TradeRule]  # current version of each referenced rule, in order
    missing: List[int] = Field(default_factory=list, description="Referenced rules that no longer exist")


class NotFound(LookupError):
    pass


def _clean_name(name: str, what: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError(f"Give the {what} a name before saving")
    return name


class SavedLibrary:
    def __init__(self, engine: Engine):
        self._engine = engine
        self._insert = _insert(engine)

    # ---- rules ----
    def _rules(self, conn, mobile: str) -> Dict[int, TradeRule]:
        rows = conn.execute(select(saved_rules.c.id, saved_rules.c.name, saved_rules.c.rule)
                            .where(saved_rules.c.mobile == mobile).order_by(saved_rules.c.name))
        return {i: TradeRule(**{**json.loads(r), "id": i, "name": n}) for i, n, r in rows}

    def _strategy_rows(self, conn, mobile: str) -> List[tuple]:
        return list(conn.execute(select(saved_strategies.c.name, saved_strategies.c.rules)
                                 .where(saved_strategies.c.mobile == mobile).order_by(saved_strategies.c.name)))

    def list_rules(self, mobile: str) -> List[SavedRuleOut]:
        with self._engine.connect() as conn:
            rules = self._rules(conn, mobile)
            users: Dict[int, List[str]] = {}
            for name, raw in self._strategy_rows(conn, mobile):
                for rid in json.loads(raw).get("rule_ids", []):
                    users.setdefault(rid, []).append(name)
        return [SavedRuleOut(**r.model_dump(), used_by=users.get(i, [])) for i, r in rules.items()]

    def create_rule(self, mobile: str, rule: TradeRule) -> int:
        name = _clean_name(rule.name, "rule")
        body = rule.model_dump_json(exclude={"id", "name"})
        with self._engine.begin() as conn:
            names = {n for (n,) in conn.execute(select(saved_rules.c.name).where(saved_rules.c.mobile == mobile))}
            if name in names:
                raise ValueError(f'You already have a rule called "{name}"')
            if len(names) >= MAX_RULES:
                raise ValueError(f"You can save up to {MAX_RULES} rules; delete one first")
            res = conn.execute(self._insert(saved_rules).values(mobile=mobile, name=name, rule=body, updated_at=datetime.now(UTC)))
            return int(res.inserted_primary_key[0])

    def update_rule(self, mobile: str, rule_id: int, rule: TradeRule) -> None:
        name = _clean_name(rule.name, "rule")
        body = rule.model_dump_json(exclude={"id", "name"})
        with self._engine.begin() as conn:
            clash = conn.execute(select(saved_rules.c.id).where(saved_rules.c.mobile == mobile, saved_rules.c.name == name,
                                                                saved_rules.c.id != rule_id)).first()
            if clash:
                raise ValueError(f'You already have a rule called "{name}"')
            res = conn.execute(update(saved_rules).where(saved_rules.c.mobile == mobile, saved_rules.c.id == rule_id)
                               .values(name=name, rule=body, updated_at=datetime.now(UTC)))
            if res.rowcount == 0:
                raise NotFound("No saved rule with that id")

    def delete_rule(self, mobile: str, rule_id: int) -> None:
        with self._engine.begin() as conn:
            using = [n for n, raw in self._strategy_rows(conn, mobile) if rule_id in json.loads(raw).get("rule_ids", [])]
            if using:
                raise ValueError(f"This rule is used by: {', '.join(using)}. Remove it from those strategies first")
            res = conn.execute(delete(saved_rules).where(saved_rules.c.mobile == mobile, saved_rules.c.id == rule_id))
            if res.rowcount == 0:
                raise NotFound("No saved rule with that id")

    # ---- strategies ----
    def list_strategies(self, mobile: str) -> List[StrategyOut]:
        with self._engine.connect() as conn:
            rules = self._rules(conn, mobile)
            out = []
            for name, raw in self._strategy_rows(conn, mobile):
                data = json.loads(raw)
                if "rule_ids" in data:
                    ids = data["rule_ids"]
                    out.append(StrategyOut(name=name, rule_ids=ids, rules=[rules[i] for i in ids if i in rules],
                                           missing=[i for i in ids if i not in rules]))
                else:  # saved before rules were saved separately: inline rules, no references
                    out.append(StrategyOut(name=name, rule_ids=[], rules=[TradeRule(**r) for r in data.get("rules", [])]))
        return out

    def save_strategy(self, mobile: str, strategy: StrategyIn) -> None:
        name = _clean_name(strategy.name, "strategy")
        with self._engine.begin() as conn:
            mine = {i for (i,) in conn.execute(select(saved_rules.c.id).where(saved_rules.c.mobile == mobile))}
            unknown = [i for i in strategy.rule_ids if i not in mine]
            if unknown:
                raise ValueError("Save every rule before saving the strategy")
            names = {n for n, _ in self._strategy_rows(conn, mobile)}
            if name not in names and len(names) >= MAX_STRATEGIES:
                raise ValueError(f"You can save up to {MAX_STRATEGIES} strategies; delete one first")
            now = datetime.now(UTC)
            body = json.dumps({"rule_ids": strategy.rule_ids})
            stmt = self._insert(saved_strategies).values(mobile=mobile, name=name, rules=body, updated_at=now)
            conn.execute(stmt.on_conflict_do_update(index_elements=["mobile", "name"], set_={"rules": stmt.excluded.rules, "updated_at": now}))

    def delete_strategy(self, mobile: str, name: str) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(delete(saved_strategies).where(saved_strategies.c.mobile == mobile, saved_strategies.c.name == name))
        return res.rowcount > 0
