"""Set-difference (EXCEPT) proposals for negated questions with no public match.

Spider references usually express "X that are not / do not / without ..." as
    SELECT out FROM T EXCEPT SELECT out FROM T JOIN ... WHERE <positive condition>
Drafts instead write the negation inline (!=, NOT LIKE, NOT IN, NOT EXISTS,
LEFT JOIN ... ). From one checked candidate this module flips the single
negated WHERE conjunct to its positive form, reaches the condition's table
along the unique foreign-key path from the output table, and builds the EXCEPT
query. Proposals only: the controller checks them, and uses them only when no
candidate matches the public example. No I/O.
"""
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from relation_rules import _graph, _schema, _unique_path

NEGATION = re.compile(r"\b(?:not|no|never|without|except|other than|none)\b|n['’]t\b", re.I)


def _parse(sql):
    if not isinstance(sql, str) or len(sql.encode("utf-8")) > 16000:
        return None
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except (ParseError, TokenError, RecursionError):
        return None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return None
    tree = statements[0]
    if tree.args.get("with") or tree.args.get("limit") or tree.args.get("having"):
        return None
    return tree


def _sources(tree, metadata):
    source = tree.args.get("from")
    tables = ([source.this] if source is not None else []) + [j.this for j in tree.args.get("joins") or []]
    out = {}
    for t in tables:
        if not isinstance(t, exp.Table) or t.db or t.name.casefold() not in metadata:
            return None
        alias = t.alias_or_name.casefold()
        if alias in out:
            return None
        out[alias] = t.name.casefold()
    return out


def _owner(column, sources, metadata):
    name = column.name.casefold()
    if column.table:
        table = sources.get(column.table.casefold())
        return table if table and name in metadata[table]["columns"] else None
    owners = {t for t in sources.values() if name in metadata[t]["columns"]}
    return owners.pop() if len(owners) == 1 else None


def _conjuncts(node):
    return list(node.flatten()) if isinstance(node, exp.And) else [node]


def _positive(pred):
    """Return (column, [positive predicates]) for one negated conjunct, else None."""
    if isinstance(pred, exp.Paren):
        pred = pred.this
    if isinstance(pred, exp.NEQ) and isinstance(pred.this, exp.Column) and isinstance(pred.expression, exp.Literal):
        return pred.this, [exp.EQ(this=pred.this.copy(), expression=pred.expression.copy())]
    if isinstance(pred, exp.Not):
        inner = pred.this.this if isinstance(pred.this, exp.Paren) else pred.this
        if (isinstance(inner, exp.Like) and isinstance(inner.this, exp.Column)
                and isinstance(inner.expression, exp.Literal) and inner.expression.is_string):
            value = inner.expression.this
            core = value.strip("%")
            out = []
            if core and "%" not in core and "_" not in core:
                out.append(exp.EQ(this=inner.this.copy(), expression=exp.Literal.string(core)))
            out.append(inner.copy())
            return inner.this, out
        if isinstance(inner, exp.In) and isinstance(inner.this, exp.Column) and inner.args.get("query"):
            return inner.this, [inner.copy()]
        if isinstance(inner, exp.Exists):
            return None, [inner.copy()]
    return None


def except_queries(sql, question, schema):
    if not NEGATION.search(question or ""):
        return []
    metadata = _schema(schema)
    tree = _parse(sql)
    if metadata is None or tree is None or tree.args.get("where") is None:
        return []
    sources = _sources(tree, metadata)
    if not sources:
        return []
    outputs = []
    for e in tree.expressions:
        col = e.unalias() if isinstance(e, exp.Alias) else e
        if not isinstance(col, exp.Column) or col.is_star:
            return []
        owner = _owner(col, sources, metadata)
        if owner is None:
            return []
        outputs.append((owner, metadata[owner]["columns"][col.name.casefold()]))
    main = {t for t, _ in outputs}
    if len(main) != 1:
        return []
    main = main.pop()
    negated, keep = [], []
    for pred in _conjuncts(tree.args["where"].this):
        flipped = _positive(pred)
        if flipped is not None:
            negated.append(flipped)
            continue
        cols = list(pred.find_all(exp.Column))
        if isinstance(pred, (exp.Is, exp.Not)) and any(isinstance(n, exp.Null) for n in pred.walk()):
            continue  # anti-join scaffolding (IS NULL / IS NOT NULL) is dropped
        if cols and all(_owner(c, sources, metadata) == main for c in cols) and not pred.find(exp.Subquery):
            keep.append(pred)
        else:
            return []
    if len(negated) != 1:
        return []
    column, positives = negated[0]
    target = main if column is None else _owner(column, sources, metadata)
    if target is None:
        return []
    main_name = metadata[main]["name"]
    main_alias = next(a for a, t in sources.items() if t == main)

    def qualify(node, mapping):
        node = node.copy()
        for c in node.find_all(exp.Column):
            owner = _owner(c, sources, metadata)
            if owner in mapping:
                c.set("table", exp.to_identifier(mapping[owner]))
                c.set("this", exp.to_identifier(metadata[owner]["columns"][c.name.casefold()]))
        return node

    def select_part(mapping, joins, preds):
        cols = ", ".join(f"{mapping[main]}.{name}" for _, name in outputs)
        sql = f"SELECT {cols} FROM {main_name} AS {mapping[main]}"
        sql += "".join(joins)
        if preds:
            sql += " WHERE " + " AND ".join(p.sql(dialect="sqlite") for p in preds)
        return sql

    left = select_part({main: "T1"}, [], [qualify(p, {main: "T1"}) for p in keep])
    results = []
    if target == main or column is None:
        mapping = {main: "T1"}
        joins = []
    else:
        path = _unique_path(_graph(metadata), main, target)
        if not path:
            return []
        mapping, joins = {main: "T1"}, []
        for i, (src, dst, lcol, rcol) in enumerate(path, start=2):
            mapping[dst] = f"T{i}"
            joins.append(f" JOIN {metadata[dst]['name']} AS T{i} ON {mapping[src]}.{metadata[src]['columns'][lcol]}"
                         f" = T{i}.{metadata[dst]['columns'][rcol]}")
    for pos in positives:
        if column is None or isinstance(pos, exp.In):
            # Correlated subqueries refer to the draft's alias: keep it for the main table.
            if pos.find(exp.Subquery) or isinstance(pos, exp.Exists):
                right = (f"SELECT {', '.join(f'{main_alias}.{n}' for _, n in outputs)} FROM {main_name} AS {main_alias}"
                         f" WHERE {pos.sql(dialect='sqlite')}")
                results.append(f"{left} EXCEPT {right}")
                continue
        right = select_part(mapping, joins, [qualify(p, mapping) for p in keep] + [qualify(pos, mapping)])
        results.append(f"{left} EXCEPT {right}")
    return [r for r in results if len(r.encode()) <= 16000]


def except_proposals(history, question, schema):
    """Ranked, de-duplicated EXCEPT proposals from all checked candidates."""
    ranked = []
    for order, event in enumerate(e for e in history if e["tool"] == "check"):
        for sql in except_queries(event["sql"], question, schema):
            joined = " JOIN " in sql.split(" EXCEPT ", 1)[1].upper()
            literal = re.findall(r"'([^']+)'", sql.split(" EXCEPT ", 1)[1])
            named = bool(literal) and all(v.casefold() in (question or "").casefold() for v in literal)
            ranked.append(((not named, not joined, -order), sql))
    seen, out = set(), []
    for _, sql in sorted(ranked, key=lambda x: x[0]):
        if sql not in seen:
            seen.add(sql)
            out.append(sql)
    return out
