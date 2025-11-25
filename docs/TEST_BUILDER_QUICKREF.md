# Test Builder - Quick Reference Card

## 🚀 Getting Started

```bash
# Install dependencies (first time only)
make builder-install

# Start Test Builder
make builder

# Open in browser
http://localhost:8000
```

## 🎯 Common Tasks

### Create a New Test
1. Click **"New Test"** in sidebar
2. Fill in test info (name, description, tags)
3. Click **"Add Step"**
4. Select action from library
5. Fill in parameters
6. Click **"Add Step"**
7. Repeat for all steps
8. Click **"Save"**

### Edit Existing Test
1. Click **"My Tests"** in sidebar
2. Click on test name
3. Make changes
4. Click **"Save"**

### Run a Test
1. Open test in builder
2. Click **"Validate"** (recommended)
3. Click **"Run Test"**
4. Watch output in terminal

### Use a Template
1. Click **"Templates"** in sidebar
2. Click on template
3. Customize as needed
4. Click **"Save"** with new name

## 📚 Action Categories

| Category | Actions | Common Use |
|----------|---------|------------|
| 🌐 **Browser** | 30+ | Web UI testing |
| 🔍 **API** | 5 | REST API testing |
| ☁️ **AWS** | 5 | S3 file operations |
| 📡 **JSON-RPC** | 3+ | WebSocket device control |
| ✅ **Test** | 4 | Assertions, validation |

## 🎨 UI Navigation

| View | Purpose |
|------|---------|
| **My Tests** | Browse all tests |
| **New Test** | Create test from scratch |
| **Templates** | Use pre-built templates |
| **Actions Library** | Browse all actions |

## 🔧 Toolbar Buttons

| Button | Action |
|--------|--------|
| **Validate** | Check test for errors |
| **Save** | Save test to file |
| **Run Test** | Execute test |

## 📝 Test Step Actions

| Button | Action |
|--------|--------|
| ✏️ | Edit step parameters |
| ⬆️ | Move step up |
| ⬇️ | Move step down |
| 🗑️ | Delete step |

## 💡 Tips & Tricks

### Use Variables
```yaml
variables:
  base_url: "https://api.example.com"
  username: "testuser"

steps:
  - browser.open:
      url: "${base_url}/login"
```

### Tag Organization
```yaml
tags: ["smoke", "critical", "browser"]
```
Filter tests by tags later!

### Step Descriptions
Add notes to complex steps:
```yaml
- browser.click:
    selector: "#submit"
  description: "Submit the login form"
```

### Required vs Optional
- **Red asterisk (*)** = Required field
- No asterisk = Optional field

### Parameter Types
- **Text**: Single line (URLs, selectors)
- **Number**: Numeric values
- **Select**: Dropdown choices
- **Textarea**: Multi-line (JavaScript)
- **JSON**: Objects/arrays
- **Checkbox**: True/false

## 🐛 Troubleshooting

### Test Builder Won't Start
```bash
# Install dependencies
pip install -r frontend/requirements_builder.txt

# Check port 8000 is free
lsof -ti:8000 | xargs kill -9

# Start again
python frontend/start_builder.py
```

### Tests Not Loading
1. Check `tests/cases/` directory exists
2. Verify YAML files are valid
3. Check browser console for errors (F12)

### Can't Save Test
1. Ensure test name is filled in
2. Add at least one step
3. Check for validation errors

### Action Not Found
1. Refresh page
2. Check action ID is correct
3. Verify action is in `action_definitions.py`

## 📖 More Resources

- **Full Guide**: [docs/TEST_BUILDER.md](TEST_BUILDER.md)
- **Syntax Reference**: [docs/SYNTAX_CHEATSHEET.md](SYNTAX_CHEATSHEET.md)
- **API Docs**: http://localhost:8000/docs
- **Examples**: [docs/examples.md](examples.md)

## ⌨️ Keyboard Shortcuts (Planned)

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + S` | Save test |
| `Ctrl/Cmd + N` | New test |
| `Ctrl/Cmd + K` | Add step |
| `Escape` | Close modal |

## 🎓 Learning Path

1. **Start with Templates** - Use pre-built tests
2. **Browse Action Library** - See what's available
3. **Create Simple Test** - Login flow
4. **Add Assertions** - Verify results
5. **Use Variables** - Make tests flexible
6. **Tag & Organize** - Build test suite

## 💬 Common Questions

**Q: Do I need to know YAML?**
A: No! The visual builder handles all YAML syntax.

**Q: Can I edit the YAML directly?**
A: Yes! Tests are saved as YAML files you can edit.

**Q: Where are tests saved?**
A: In `tests/cases/*.yaml` - version controlled!

**Q: Can I run tests from CLI?**
A: Yes! `python -m easy_bdd run tests/cases/`

**Q: How do I share tests?**
A: Tests are files - commit to git and share!

**Q: Can I add custom actions?**
A: Yes! Edit `action_definitions.py` and restart.

## 🚦 Test Creation Workflow

```
Start
  ↓
Click "New Test"
  ↓
Fill Test Info (name, description, tags)
  ↓
Click "Add Step"
  ↓
Select Action
  ↓
Fill Parameters
  ↓
Add Step
  ↓
Repeat for all steps
  ↓
Click "Validate"
  ↓
Fix any errors
  ↓
Click "Save"
  ↓
Click "Run Test"
  ↓
Done!
```

## 📊 Status Indicators

| Color | Meaning |
|-------|---------|
| 🟢 Green | Success, valid |
| 🔴 Red | Error, required |
| 🟡 Yellow | Warning |
| 🔵 Blue | Info, selected |

## 🎯 Best Practices

1. ✅ **Descriptive Names** - Clear, searchable test names
2. ✅ **Use Tags** - Organize with consistent tags
3. ✅ **Add Descriptions** - Document complex steps
4. ✅ **Variables** - Don't hardcode URLs/credentials
5. ✅ **Validate First** - Always validate before running
6. ✅ **Version Control** - Commit test files to git
7. ✅ **Templates** - Use templates for consistency
8. ✅ **Review** - Check test logic before saving

## 🔗 Quick Links

- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **GitHub**: https://github.com/mfomin-snapone/Automation-Framework
- **Issues**: https://github.com/mfomin-snapone/Automation-Framework/issues

---

**Need Help?** Check [TEST_BUILDER.md](TEST_BUILDER.md) or open an issue!
