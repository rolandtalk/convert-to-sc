# Product Spec

## Working Name

Convert to SC

## Problem

Users often have a message, email subject, note, or market commentary that contains stock symbols mixed with ordinary text. They need a faster way to:

- isolate the symbols
- fetch the relevant charts
- view the results in one place

## Primary User Flow

1. User pastes a chart description or free-form text.
2. Convert to SC extracts likely symbols from the text.
3. User reviews the extracted list.
4. CSC opens the chart source for each symbol.
5. CSC captures screenshots.
6. CSC publishes the screenshots to a web page for browsing.

## Inputs

- email subject lines
- watchlist descriptions
- market notes
- free-form chart commentary

## Outputs

- extracted symbols
- job status
- screenshot gallery
- optional export of symbol and chart metadata

## First Release Scope

- manual text input
- ticker extraction rules
- chart URL generation
- screenshot capture service
- simple gallery page

## Non-Goals For First Release

- user accounts
- live brokerage integrations
- advanced annotation tools
- complex portfolio analytics

## Open Questions

- Should Convert to SC use only one chart source, or support multiple sources later?
- Should users confirm symbols before screenshots start?
- Should the first version store screenshots locally or in cloud storage?
