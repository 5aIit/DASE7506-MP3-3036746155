"""Unit tests for R03 rewrites. Run: python dev/tests/test_rewrites.py (needs sqlglot)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "submission"))

from convention_rules import count_star, drop_distinct, like_to_equality, semi_join  # noqa: E402
from join_prune import needs_schema, pruned_query  # noqa: E402

SCHEMA = [
    {"name": "exhibition", "columns": [{"name": "Exhibition_ID"}, {"name": "Theme"},
                                       {"name": "Year"}, {"name": "Ticket_Price"}]},
    {"name": "exhibition_record", "columns": [{"name": "Exhibition_ID"}, {"name": "Date"}]},
]


def flat(s):
    return " ".join(s.split())


def test_prunes_unnamed_join():
    sql = ("SELECT e.Theme, e.Year FROM exhibition e JOIN exhibition_record er "
           "ON e.Exhibition_ID = er.Exhibition_ID WHERE e.Ticket_Price < 15")
    out = pruned_query(sql, "Show theme and year for all exhibitions with ticket prices lower than 15.", None)
    assert out and "JOIN" not in out.upper() and "exhibition_record" not in out, out


def test_keeps_join_named_by_question():
    sql = ("SELECT e.Theme FROM exhibition e JOIN exhibition_record er "
           "ON e.Exhibition_ID = er.Exhibition_ID")
    assert pruned_query(sql, "Which exhibitions have a record?", None) is None


def test_keeps_inflected_name():
    sql = ("SELECT Club.ClubName FROM Club JOIN Member_of_club ON Club.ClubID = Member_of_club.ClubID "
           "WHERE Club.ClubName = 'X'")
    assert pruned_query(sql, "Which club has membership?", None) is None


def test_skips_multiplicity_sensitive():
    sql = ("SELECT COUNT(*) FROM Member_of_club JOIN Club ON Member_of_club.ClubID = Club.ClubID "
           "WHERE Club.ClubName = 'Pen'")
    assert pruned_query(sql, "How many people are in the club Pen?", None) is None
    grouped = ("SELECT p.name FROM p JOIN o ON p.id = o.pid GROUP BY p.id ORDER BY COUNT(*) DESC LIMIT 1")
    assert pruned_query(grouped, "Which p is most common?", None) is None


def test_keeps_bridge_table_used_by_other_join():
    sql = ("SELECT a.x FROM a JOIN b ON a.id = b.aid JOIN c ON b.cid = c.id WHERE c.y = 1")
    assert pruned_query(sql, "what is x for y", None) is None


def test_drops_from_table_used_only_by_first_join():
    sql = "SELECT b.name FROM a JOIN b ON a.bid = b.id WHERE b.v = 1"
    out = pruned_query(sql, "names with v 1", None)
    assert out and flat(out) == "SELECT b.name FROM b WHERE b.v = 1", out


def test_unqualified_columns_need_schema():
    sql = ("SELECT Theme FROM exhibition JOIN exhibition_record "
           "ON exhibition.Exhibition_ID = exhibition_record.Exhibition_ID")
    q = "Show the themes."
    assert needs_schema(sql)
    assert pruned_query(sql, q, None) is None
    out = pruned_query(sql, q, SCHEMA)
    assert out and "exhibition_record" not in out, out


def test_left_join_untouched():
    sql = "SELECT a.x FROM a LEFT JOIN b ON a.id = b.aid"
    assert pruned_query(sql, "show x", None) is None


def test_not_like_to_neq_only():
    neg = "SELECT Name FROM country WHERE NOT Languages LIKE '%German%'"
    out = like_to_equality(neg, 'List countries whose language is not "German".')
    assert out and "<>" in out and "LIKE" not in out.upper(), out
    pos = "SELECT text FROM tweets WHERE text LIKE '%intern%'"
    assert like_to_equality(pos, "Return tweets about the topic 'intern'.") is None
    assert like_to_equality(neg, "Countries whose language does not contain 'German'") is None


def test_drop_distinct_and_count_star_respect_cues():
    q = "Show the names of editors on committees of journals with sales over 3000."
    assert flat(drop_distinct("SELECT DISTINCT e.Name FROM editor e", q)) == "SELECT e.Name FROM editor AS e"
    assert drop_distinct("SELECT DISTINCT Name FROM editor", "Show the distinct names.") is None
    assert drop_distinct("SELECT Name FROM editor", q) is None
    out = count_star("SELECT COUNT(DISTINCT r.id) FROM r", "How many council taxes are collected?")
    assert out and "COUNT(*)" in out, out
    assert count_star("SELECT COUNT(DISTINCT t) FROM r", "How many different types are there?") is None
    nested = "SELECT a FROM t WHERE x IN (SELECT COUNT(DISTINCT y) FROM u)"
    assert count_star(nested, "How many?") is None


def test_semi_join_for_average():
    sql = ("SELECT AVG(customer.credit_score) FROM customer JOIN loan "
           "ON customer.cust_ID = loan.cust_ID")
    out = semi_join(sql, "What is the average credit score for customers who have taken a loan?", None)
    assert out and "JOIN" not in out.upper() and "IN (SELECT loan.cust_ID FROM loan)" in out, out
    assert semi_join("SELECT AVG(loan.amount) FROM customer JOIN loan ON customer.id = loan.cid "
                     "WHERE customer.x = 1", "avg", None) is None
    assert semi_join("SELECT COUNT(*) FROM a JOIN b ON a.id = b.aid", "how many", None) is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
