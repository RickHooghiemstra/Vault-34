# Contributing to Vault-34

## Development Setup

```bash
git clone <repo-url> && cd Vault-34
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # add ANTHROPIC_API_KEY
```

## Running Tests

```bash
python -m pytest tests/ -v
```

All 46 tests must pass before submitting a PR.

## Code Style

- Follow existing naming conventions (snake_case for functions/variables, PascalCase for classes)
- No commented-out dead code
- Add comments only when the **why** is non-obvious
- Keep functions focused: parsers parse, transformers transform — don't mix concerns

## Adding a New Exhaust Brand

1. Add the brand slug to `config/brands.py → TOP_BRANDS`
2. Add the canonical name to `config/brands.py → BRAND_NORM`
3. Run: `python main.py --brands {new-brand-slug}`

## Tuning CSS Selectors

If uitlaatstore.nl updates its page structure:

```bash
python main.py --discover --url https://www.uitlaatstore.nl/{product-slug}
```

Update `config/settings.py → SELECTORS` with the correct CSS paths.

## Adding a Motorcycle Make

Add to `config/makes.py → MOTO_MAKES` (keep longest names first).  
Add any variant spellings to `MAKE_NORM`.

## Submitting Changes

- Create a feature branch from `main`
- Include test coverage for new logic
- Update `docs/` if you change scraping or tagging rules
- Open a pull request with a clear description of what changed and why
