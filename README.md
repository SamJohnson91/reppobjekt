# Reppobjekt

Lav pris, egen innsats — a marketplace for cheap fixer-upper items (cars, bikes, tools, electronics).

## Run locally

Open `index.html` in a browser. Product photos are in `bilder/`.

## Notes

- Login, favourites and settings are stored in the browser (`localStorage`); there is no backend yet.
- The AI price estimator calls the Anthropic API directly and needs a backend/proxy holding the API key before it will work.
