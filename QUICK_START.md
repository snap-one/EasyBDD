# Quick Start Guide

Get up and running with Easy BDD Framework in 5 minutes!

## 🚀 Installation (5 minutes)

### Step 1: Clone and Setup

```bash
git clone <repository-url>
cd easy_bdd
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
playwright install chromium
```

### Step 2: Install Test Builder (Recommended)

```bash
cd frontend
pip install -r requirements_builder.txt
cd ..
```

### Step 3: Start Test Builder

```bash
cd frontend
python start_builder.py
```

Open http://localhost:8000 in your browser.

## 🎯 First Test (2 minutes)

### Option 1: Run Demo Tests

1. Click **Test Suites** in sidebar
2. Find **Demo Test Suite**
3. Click **Execute Suite**
4. Watch tests run!

### Option 2: Create Your First Test

1. Click **New Test** in sidebar
2. Enter:
   - Name: "My First Test"
   - Description: "Testing the framework"
3. Click **Add Step**
4. Select **Browser Actions** → **Open Browser**
5. Enter URL: `https://example.com`
6. Click **Add Step**
7. Click **Save**
8. Click **Run Test**

## 📚 Next Steps

- **Learn More**: Read the [User Guide](docs/USER_GUIDE.md)
- **New Features**: Check [New Features Guide](docs/NEW_FEATURES.md)
- **Examples**: Explore demo tests in Test Suites
- **AI Help**: Click chat icon (💬) to ask questions

## 🎓 Learning Path

1. ✅ **Run Demo Tests** - See the framework in action
2. ✅ **Create Simple Test** - Build your first test
3. ✅ **Explore Actions** - Browse Actions Library
4. ✅ **Try Templates** - Start from templates
5. ✅ **Create Suite** - Group multiple tests
6. ✅ **View Metrics** - Check test analytics
7. ✅ **Use AI Assistant** - Get help with questions

## 💡 Pro Tips

- **Use Templates** - Start from pre-built templates
- **Browse Actions** - Actions Library shows all available actions
- **Check Metrics** - Monitor test health regularly
- **Ask AI** - Use AI Assistant for help
- **Organize with Workspaces** - Group related tests

## 🆘 Need Help?

- **AI Assistant** - Click chat icon (💬) in top-right
- **Documentation** - See `/docs` folder
- **Examples** - Check demo tests
- **Troubleshooting** - See [Troubleshooting Guide](docs/troubleshooting.md)

## 🎉 You're Ready!

You now have:
- ✅ Framework installed
- ✅ Test Builder running
- ✅ First test created/run
- ✅ Understanding of basic workflow

**Next**: Read the [User Guide](docs/USER_GUIDE.md) for detailed information!

