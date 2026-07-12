# Data model

## Principle: separate the axes

One expense has several independent dimensions. Don't collapse them into a single
"category" — otherwise you end up with 40 categories and analytics break.

| Axis | Examples | Why |
|---|---|---|
| **Category** | Groceries, Dining out, Fuel | budget and plan/actual |
| **Group** | Food, Transport, Housing | top-level rollup (from the reference) |
| **Place** | supermarket, market, station | compare where it's pricier; a field, NOT a category |
| **Method** | cash / card | cash vs card breakdown |
| **Essential** | yes / no | feeds the emergency-fund target (6 months of essentials) |
| **Fuel attributes** | liters, price/L, brand | fuel economy, cost per 100 km |

## Spreadsheet tabs

- **Reference** — `Category → Group → Essential`. The single source of truth in the sheet;
  it is generated from `bot/categories.py`, so they always match.
- **Journal** — raw rows. Columns:
  `A Date · B Category · C Amount · D Place · E Method · F Liters · G Price/L (formula) ·
   H Note · I Month (formula) · J Group (VLOOKUP) · K Essential (VLOOKUP)`.
  The bot writes A–F and H; G, I, J, K are template formulas.
- **Expenses** — plan vs actual per category, rolled up into groups.
- **Dashboard** — income, plan/actual, surplus, emergency fund, group rollup, debts.
- **Income**, **Assets** — planned income and savings (buffer vs risk).
- **Debts**, **Debt repayments** — see below.

## Debts

Debt is its own axis, separate from expenses/income — lending or borrowing money isn't a
budget category, it's a claim between you and another person that gets settled later.

- **Debts** — one row per debt (created once, via `/debt дал|занял`). Columns:
  `A Date · B Person · C Direction (lent/borrowed) · D Amount · E Currency · F Note ·
   G ID (formula, = ROW()) · H Repaid (formula, SUMIF over Debt repayments) ·
   I Remaining (formula, D − H) · J Status (formula)`.
  The bot writes A–F; G–J are template formulas for display. `lent` = you gave money, the
  person owes you. `borrowed` = you took money, you owe the person.
- **Debt repayments** — one row per repayment (via `/debt вернул|вернули`), append-only:
  `A Date · B DebtID · C Amount · D Note`. `DebtID` is the row number of the debt in the
  Debts sheet — a debt can have several repayments (partial or full), so it's tracked to
  the exact debt even when a person has more than one open at once.
- The bot computes repaid/remaining/open-vs-closed in Python (same pattern as `range_summary`,
  `income_summary`, etc.) by scanning both sheets — the sheet-side G–J formulas are only for
  a human reading the sheet directly, not something the bot relies on.
- Dashboard shows "Owed to you" / "You owe" / "Net debt position", summed over open debts
  (`Remaining > 0`) by direction.

## Category rule

A category answers "what did I spend on", not "where". "Groceries at a market" is
category `Groceries` + place `market`. That way you can ask both "how much on food" and
"how much at that market across all categories" without bloating the list.

## When to analyze

Collect attributes (place, liters, brand) from day one — you can't analyze what you didn't
record. The analysis itself (store A vs market, premium vs economy, cost per 100 km) comes
once you have 2–3 months of data.
