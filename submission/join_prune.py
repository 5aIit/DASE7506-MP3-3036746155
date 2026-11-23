"""Drop INNER joins whose table is neither used nor named by the question.

Spider-style references avoid joining tables that contribute no output, filter,
grouping or ordering column. A join to such a table can still change rows
(orphans, fan-out), so the shortened query is only a proposal: it must pass an
official check, and a join is kept whenever the question names the table.
No I/O; schema comes from the official schema tool when it is needed.
"""
from sqlglot import exp

from relation_rules import _select
from single_table_rules import _words


def _tables(tree):
    source = tree.args.get("from")
    tables = ([source.this] if source is not None else []) + [j.this for j in tree.args.get("joins") or []]
    if not tables or not all(isinstance(t, exp.Table) and not t.db and not t.catalog
                             and isinstance(t.this, exp.Identifier) for t in tables):
        return None
    aliases = {}
    for table in tables:
        alias = table.alias_or_name.casefold()
        if alias in aliases:
            return None
        aliases[alias] = table
    return aliases


def _columns(schema):
    if not isinstance(schema, list):
        return None
    out = {}
    for item in schema:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            out[item["name"].casefold()] = {c["name"].casefold() for c in item.get("columns", [])
                                            if isinstance(c, dict) and isinstance(c.get("name"), str)}
    return out


def _owner(column, aliases, columns):
    """Alias a column belongs to; None when it cannot be resolved uniquely."""
    if column.table:
        alias = column.table.casefold()
        return alias if alias in aliases else None
    if columns is None:
        return None
    owners = [a for a, t in aliases.items() if column.name.casefold() in columns.get(t.name.casefold(), ())]
    return owners[0] if len(owners) == 1 else None


def _referenced(tree, aliases, columns, skip):
    """Aliases referenced outside the ON condition of join index `skip`."""
    joins = tree.args.get("joins") or []
    excluded = set()
    if skip is not None and joins[skip].args.get("on") is not None:
        excluded = {id(c) for c in joins[skip].args["on"].find_all(exp.Column)}
    refs = set()
    for column in tree.find_all(exp.Column):
        if id(column) in excluded:
            continue
        owner = _owner(column, aliases, columns)
        if owner is None:
            raise LookupError
        refs.add(owner)
    return refs


FILLER = {"of", "and", "the", "in", "to", "for", "by", "a", "an", "on", "at", "with", "has", "is"}


def _hit(tokens, question_words):
    """Token named by the question, allowing inflections (member/membership)."""
    for t in tokens:
        for q in question_words:
            if t == q or (len(t) >= 4 and q.startswith(t)) or (len(q) >= 4 and t.startswith(q)):
                return True
    return False


def _protected(alias, aliases, question_words):
    names = {a: _words(t.name) - FILLER for a, t in aliases.items()}
    own = names[alias]
    others = set().union(*(w for a, w in names.items() if a != alias))
    return _hit((own - others) or own, question_words)


def _multiplicity_sensitive(tree):
    """Row counts matter: dropping a join could change GROUP BY or aggregates."""
    if tree.args.get("group") or tree.args.get("having"):
        return True
    for agg in tree.find_all(exp.AggFunc):
        if isinstance(agg, (exp.Max, exp.Min)):
            continue
        if isinstance(agg, exp.Count) and isinstance(agg.this, exp.Distinct):
            continue
        return True
    return False


def _removable(tree, question_words, columns):
    aliases = _tables(tree)
    joins = tree.args.get("joins") or []
    if aliases is None or not joins:
        return None
    for join in joins:
        if (join.args.get("side") or (join.args.get("kind") or "").upper() not in ("", "INNER")
                or join.args.get("using") or join.args.get("on") is None):
            return None
    order = list(aliases)
    # A joined table (index i>0 is joins[i-1]) is removable when only its own ON uses it.
    for index in range(len(joins) - 1, -1, -1):
        alias = order[index + 1]
        if alias in _referenced(tree, aliases, columns, index):
            continue
        if not _protected(alias, aliases, question_words):
            return ("join", index)
    # The FROM table is removable when exactly the first join's ON uses it.
    first = order[0]
    if first not in _referenced(tree, aliases, columns, 0) and not _protected(first, aliases, question_words):
        return ("from", 0)
    return None


def pruned_query(sql, question, schema):
    """Return the query with every removable join dropped, or None."""
    tree = _select(sql)
    if tree is None or not tree.args.get("joins"):
        return None
    if any(isinstance(e, exp.Star) or (isinstance(e, exp.Column) and e.is_star) for e in tree.expressions):
        return None
    if _multiplicity_sensitive(tree):
        return None
    columns = _columns(schema)
    words = _words(question)
    changed = False
    try:
        while True:
            step = _removable(tree, words, columns)
            if step is None:
                break
            kind, index = step
            joins = list(tree.args["joins"])
            if kind == "join":
                joins.pop(index)
            else:
                first = joins.pop(0)
                tree.set("from", exp.From(this=first.this.copy()))
            tree.set("joins", joins or None)
            changed = True
            if not joins:
                break
    except LookupError:
        return None
    return tree.sql(dialect="sqlite") if changed else None


def needs_schema(sql):
    """True when join pruning would need the schema to bind unqualified columns."""
    tree = _select(sql)
    return bool(tree is not None and tree.args.get("joins")
                and any(not c.table for c in tree.find_all(exp.Column)))
