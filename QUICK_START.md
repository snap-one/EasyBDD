# Quick Start Guide

Get up and running with Easy BDD Framework in 5 minutes!

## 🚀 Installation (5 minutes)

### Step 1: Clone and Setup

```bash
git clone <repository-url>
cd Easy_BDD
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
playwright install chromium
```

Add TestRail credentials to `.env` (copy `.env.example` first) — most workflows below
need `TESTRAIL_URL` / `TESTRAIL_USERNAME` / `TESTRAIL_API_KEY`.

### Step 2: Install the TestRail Test Builder

```bash
pip install -r frontend/requirements_builder.txt
```

> The older `frontend/start_builder.py` local-YAML web builder is **deprecated** —
> it prints a deprecation warning on startup. Use the TestRail Test Builder below.

### Step 3: Start the TestRail Test Builder

```bash
python frontend/start_testrail_builder.py --port 8091
```

Open http://localhost:8091 in your browser.

> **Already running for you:** the builder is deployed as a persistent service
> on the main Jenkins server — just open **http://192.168.100.100:8091**
> instead of starting it yourself. See [ONBOARDING.md](ONBOARDING.md#production-instance).

## 🎯 First Test (2 minutes)

### Option 1: Run existing tests

```bash
python -m easybdd run tests/cases/ --headed
```

### Option 2: Author a test in TestRail via the Test Builder

1. Open the Test Builder at http://localhost:8091.
2. Pick a project/suite, create a new case, and add steps (e.g. `browser.open`,
   `browser.click`, `browser.verify_text`).
3. Save — it's written straight to TestRail.
4. Run it: `python -m easybdd testrail-run <project_id>`

## 📚 Next Steps

- **Full walkthrough**: [ONBOARDING.md](ONBOARDING.md) covers every feature in this repo step by step
- **Learn More**: Read the [User Guide](docs/USER_GUIDE.md)
- **Docs index**: [docs/README.md](docs/README.md)
- **Examples**: [docs/examples.md](docs/examples.md)

## 🎓 Learning Path

1. ✅ **Run existing tests** - See the framework in action
2. ✅ **Create a test** - Build your first case in the Test Builder
3. ✅ **Explore actions** - See [docs/actions.md](docs/actions.md) for everything a step can do
4. ✅ **Create a TestRail run** - `python -m easybdd testrail-create-run <project_id> <suite_id>`
5. ✅ **Try the crawler** - Auto-generate tests from a live UI, see [CRAWLER.md](CRAWLER.md)
6. ✅ **Connect an AI assistant** - Drive the framework from chat via the MCP server, see [docs/mcp-setup.md](docs/mcp-setup.md)

## 🆘 Need Help?

- **Documentation** - See [docs/README.md](docs/README.md) for the full index
- **Full walkthrough** - [ONBOARDING.md](ONBOARDING.md)
- **Examples** - [docs/examples.md](docs/examples.md)
- **Troubleshooting** - [docs/troubleshooting.md](docs/troubleshooting.md)

## 🎉 You're Ready!

You now have:
- ✅ Framework installed
- ✅ Test Builder running
- ✅ First test created/run
- ✅ Understanding of basic workflow

**Next**: Read the [User Guide](docs/USER_GUIDE.md) for detailed information!

