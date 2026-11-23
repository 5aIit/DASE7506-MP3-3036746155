"""Spider-convention rewrites of a finished query, proposed for official check.

Every function returns rewritten SQL or None. They are proposals only; the
controller keeps a rewrite only if it matches the public example.

- `like_to_equality`: `NOT LIKE '%v%'` -> `!= 'v'` when the question quotes v.
- `drop_distinct`: remove top-level SELECT DISTINCT without a distinctness cue.
- `count_star`: COUNT(DISTINCT x) -> COUNT(*) without a distinctness cue.
- `semi_join`: AVG/SUM over A JOIN B, B used only for membership ->
  A WHERE A.k IN (SELECT B.f FROM B), so join fan-out cannot repeat A rows.

Cue thresholds come from train *discovery* gold only (dev/gold_stats.py):
without a cue, gold uses top-level DISTINCT in 8/239 queries and
COUNT(DISTINCT) in 4/90.
"""
import re

from sqlglot import exp

from join_prune import _columns, _owner, _tables
from relation_rules import _select
from submission import _parse

QUOTED = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{1,80})[\"'“”‘’]")
SUBSTRING = re.compile(r"\b(?:contain\w*|includ\w*|substring|word|words|like|start\w*|begin\w*|"
                       r"end\w*|prefix|suffix|part|partial|mention\w*|keyword\w*|pattern)\b", re.I)
DISTINCT_CUE = re.compile(r"\b(?:distinct|different|unique|kinds?|types?|various|variety)\b", re.I)


def like_to_equality(sql, question):
    if SUBSTRING.search(question):
        return None
    quoted = {q.strip().casefold() for q in QUOTED.findall(question)}
    if not quoted:
        return None
    tree = _parse(sql)
    if tree is None:
        return None
    changed = False
    for like in list(tree.find_all(exp.Like)):
        pattern = like.expression
        if not (isinstance(like.this, exp.Column) and isinstance(pattern, exp.Literal)
                and pattern.is_string):
            continue
        parent = like.parent
        if not isinstance(parent, exp.Not):
            # "tweets about the topic 'intern'" really is a substring match:
            # only the negated form is rewritten (train discovery evidence).
            continue
        m = re.fullmatch(r"%([^%_]+)%", pattern.this)
        if not m or m.group(1).strip().casefold() not in quoted:
            continue
        parent.replace(exp.NEQ(this=like.this.copy(), expression=exp.Literal.string(m.group(1))))
        changed = True
    return tree.sql(dialect="sqlite") if changed else None


def drop_distinct(sql, question):
    if DISTINCT_CUE.search(question):
        return None
    tree = _parse(sql)
    if not isinstance(tree, exp.Select) or not tree.args.get("distinct"):
        return None
    tree.set("distinct", None)
    return tree.sql(dialect="sqlite")


def count_star(sql, question):
    if DISTINCT_CUE.search(question):
        return None
    tree = _parse(sql)
    if not isinstance(tree, exp.Select):
        return None
    changed = False
    for count in list(tree.find_all(exp.Count)):
        if isinstance(count.this, exp.Distinct) and count.find_ancestor(exp.Select) is tree:
            count.set("this", exp.Star())
            changed = True
    return tree.sql(dialect="sqlite") if changed else None


def semi_join(sql, question, schema):
    tree = _select(sql)
    if tree is None or len(tree.args.get("joins") or []) != 1:
        return None
    if tree.args.get("group") or tree.args.get("having") or tree.args.get("distinct"):
        return None
    aggs = list(tree.find_all(exp.AggFunc))
    if not aggs or not all(isinstance(a, (exp.Avg, exp.Sum)) for a in aggs):
        return None
    join = tree.args["joins"][0]
    on = join.args.get("on")
    if (join.args.get("side") or (join.args.get("kind") or "").upper() not in ("", "INNER")
            or not isinstance(on, exp.EQ) or not isinstance(on.this, exp.Column)
            or not isinstance(on.expression, exp.Column)):
        return None
    aliases = _tables(tree)
    if aliases is None or len(aliases) != 2:
        return None
    columns = _columns(schema)
    left, right = (_owner(c, aliases, columns) for c in (on.this, on.expression))
    if left is None or right is None or left == right:
        return None
    on_ids = {id(c) for c in on.find_all(exp.Column)}
    used = set()
    for column in tree.find_all(exp.Column):
        if id(column) in on_ids:
            continue
        owner = _owner(column, aliases, columns)
        if owner is None:
            return None
        used.add(owner)
    if len(used) != 1:
        return None
    keep = used.pop()
    drop = right if keep == left else left
    keep_col, drop_col = (on.this, on.expression) if keep == left else (on.expression, on.this)
    sub = exp.select(exp.column(drop_col.name, table=drop_col.table or None)).from_(aliases[drop].copy())
    membership = keep_col.copy().isin(query=sub)
    tree.set("from", exp.From(this=aliases[keep].copy()))
    tree.set("joins", None)
    where = tree.args.get("where")
    tree.set("where", exp.Where(this=exp.and_(where.this, membership) if where else membership))
    return tree.sql(dialect="sqlite")
