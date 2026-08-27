-- Restore the accounting views that the deleted db/schema.sql defined.
--
-- 001_baseline.sql recreated schema.sql's tables and indexes but not its
-- views, so no database this pipeline builds has ever had them -- while the
-- spec states plainly that "Accounting views (v_spending, v_income) are
-- unchanged", categorise.py's comment points at v_needs_review, and
-- db/README describes the spending and income views. Definitions recovered
-- verbatim from commit 8ccf33e.

-- Real spending, transfers removed. Incoming Vipps nets against its category.
CREATE VIEW IF NOT EXISTS v_spending AS
SELECT c.name AS category, ROUND(SUM(-t.amount), 2) AS spent, COUNT(*) AS n
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.is_transfer = 0 AND c.kind = 'expense'
GROUP BY c.name ORDER BY spent DESC;

CREATE VIEW IF NOT EXISTS v_income AS
SELECT c.name AS category, ROUND(SUM(t.amount), 2) AS received, COUNT(*) AS n
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.is_transfer = 0 AND c.kind = 'income'
GROUP BY c.name ORDER BY received DESC;

CREATE VIEW IF NOT EXISTS v_needs_review AS
SELECT t.date, a.name AS account, t.description, t.amount, c.name AS guessed_category
FROM transactions t
JOIN accounts a ON a.id = t.account_id
LEFT JOIN categories c ON c.id = t.category_id
WHERE t.needs_review = 1 ORDER BY t.date;
