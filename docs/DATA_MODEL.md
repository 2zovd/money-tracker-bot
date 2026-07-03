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
- **Dashboard** — income, plan/actual, surplus, emergency fund, group rollup.
- **Income**, **Assets** — planned income and savings (buffer vs risk).

## Category rule

A category answers "what did I spend on", not "where". "Groceries at a market" is
category `Groceries` + place `market`. That way you can ask both "how much on food" and
"how much at that market across all categories" without bloating the list.

## When to analyze

Collect attributes (place, liters, brand) from day one — you can't analyze what you didn't
record. The analysis itself (store A vs market, premium vs economy, cost per 100 km) comes
once you have 2–3 months of data.
