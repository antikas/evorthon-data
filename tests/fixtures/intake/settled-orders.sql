-- Hand authored sample read by the shipped intake tests. Invented names only.
-- It names the step between the extract and the report, and how the report is
-- built from that step.

CREATE TABLE settled_orders AS
SELECT
    order_id,
    settled_on,
    channel,
    order_value
FROM order_extract
WHERE settled_on IS NOT NULL
  AND order_value >= 0;

CREATE TABLE daily_order_report AS
SELECT
    order_id,
    settled_on,
    channel,
    order_value
FROM settled_orders;
