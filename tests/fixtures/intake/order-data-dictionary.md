# Order extract data dictionary

Hand authored sample read by the shipped intake tests. Every name, column and
value below is invented. Nothing here came from any system.

## Extract

- Extract name: order-extract
- Source system: order-book
- Delivery mode: nightly file drop
- Cadence: daily
- Access owner: data-owner
- Classification: confidential
- Availability: a frozen extract for August 2026 is in hand

## Columns

| Column | Type | Meaning |
| --- | --- | --- |
| order_id | text | the order key, one row per order |
| settled_on | date | the day the order settled |
| channel | text | where the order was taken |
| order_value | decimal(18,2) | the settled value of the order |

## Reference data

- Reference name: product-master
- Source system: product-catalogue
- Delivery mode: weekly export
- Cadence: weekly
- Access owner: data-owner
- Classification: internal
- Availability: expected by 2026-10-01

## Target output

- Output name: daily-order-report
- Output kind: table
- Grain: one row per order
- Keys: order_id
- Cadence: daily
- Cutoff: orders settled before 22:00 in the reporting timezone
- Effective time: effective dated on the settlement date
- Defined by: orders-specification
