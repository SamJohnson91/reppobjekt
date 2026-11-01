# Reppobjekt

Lav pris, egen innsats — a marketplace for cheap fixer-upper items (cars, bikes, tools, electronics).

## Run locally

Open `index.html` in a browser. Product photos are in `bilder/`.

## Notes

- Login, favourites and settings are stored in the browser (`localStorage`); there is no backend yet.
- The AI price estimator calls the Anthropic API directly and needs a backend/proxy holding the API key before it will work.

## Server and chatbot

`server.py` (Python standard library only) serves the site and two AI endpoints, `/api/chat` and `/api/estimate`.
It reads the Anthropic key from the `ANTHROPIC_API_KEY` environment variable, so the key never reaches the browser.

Run locally: `ANTHROPIC_API_KEY=... python server.py`, then open http://localhost:8000.

Deployed on Render as a Python web service (start command `python server.py`, see `render.yaml`).
