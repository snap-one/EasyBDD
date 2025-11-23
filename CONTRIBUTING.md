# Contributing to Easy BDD Framework

Thank you for your interest in contributing! This guide will help you get started.

## 🚀 Quick Start

### 1. Set Up Development Environment

```bash
# Clone the repository
git clone <repository-url>
cd Automation-Framework

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with development tools
make dev-install
# Or: pip install -e ".[dev]"

# Install pre-commit hooks
make hooks
# Or: pre-commit install
```

### 2. Verify Setup

```bash
# Run quality checks
make quality

# Run validation
make validate

# Run a quick test
make quick-test
```

## 📋 Development Workflow

### Before You Start
1. Create a new branch for your work
2. Check existing issues or create a new one
3. Discuss major changes before implementing

### Making Changes

1. **Write Your Code**
   ```bash
   # Edit files in easy_bdd/ or tests/
   vim easy_bdd/services/my_service.py
   ```

2. **Format Your Code**
   ```bash
   make format
   ```

3. **Run Quality Checks**
   ```bash
   make quality
   ```

4. **Test Your Changes**
   ```bash
   make test
   make validate
   ```

5. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```
   
   Pre-commit hooks will automatically:
   - Format code with black
   - Sort imports with isort
   - Run linting checks
   - Check for security issues
   - Validate YAML files

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```bash
feat(aws): add connection pooling for S3 operations
fix(runner): resolve safe_eval missing operators
docs(readme): update security section
perf(regex): implement pattern caching
```

## 🏗️ Project Structure

```
Automation-Framework/
├── easy_bdd/              # Framework source code
│   ├── core/             # Core modules (runner, parser, etc.)
│   ├── services/         # Protocol services (browser, API, AWS, etc.)
│   └── tools/            # Utility tools
├── tests/
│   ├── cases/            # Test YAML files
│   ├── unit/             # Unit tests (Python)
│   └── features/         # Generated Gherkin features
├── config/               # Configuration files
├── docs/                 # Documentation
└── reports/              # Test results
```

## 🧪 Testing Guidelines

### Writing Tests

**For Framework Code (Python):**
```python
# tests/unit/test_safe_eval.py
from easy_bdd.core.safe_eval import safe_eval

def test_safe_eval_basic():
    """Test basic arithmetic evaluation."""
    result = safe_eval("2 + 2", {})
    assert result == 4

def test_safe_eval_context():
    """Test evaluation with context."""
    result = safe_eval("x + y", {"x": 5, "y": 3})
    assert result == 8
```

**For Test Cases (YAML):**
```yaml
name: Example Test
description: Test description
tags: [example, unit]

steps:
  - action: test.assert
    expression: "2 + 2 == 4"
```

### Running Tests

```bash
# Run all unit tests
make test

# Run with coverage
make test-cov

# Validate test files
make validate

# Run specific test
pytest tests/unit/test_safe_eval.py -v
```

## 📝 Code Style Guidelines

### Python Code

**Follow PEP 8 with these adjustments:**
- Line length: 88 characters (black default)
- Use type hints where possible
- Write docstrings for all public functions/classes
- Use descriptive variable names

**Good Example:**
```python
from typing import Dict, Any, Optional

def process_data(data: Dict[str, Any], config: Optional[str] = None) -> bool:
    """
    Process data with optional configuration.
    
    Args:
        data: Dictionary containing data to process
        config: Optional configuration string
        
    Returns:
        True if processing succeeded, False otherwise
        
    Raises:
        ValueError: If data is invalid
    """
    if not data:
        raise ValueError("Data cannot be empty")
    
    # Process data here
    return True
```

### YAML Test Files

**Follow these conventions:**
```yaml
name: "Clear, Descriptive Test Name"
description: "What this test does and why"
tags: [category, feature]

variables:
  # Use descriptive names
  base_url: "https://example.com"
  timeout: 30

steps:
  # Use dot notation for actions
  - action: browser.open
    url: "${base_url}"
  
  # Add descriptions for complex steps
  - action: browser.click
    role: button
    name: "Submit"
    description: "Submit the form"
```

## 🔒 Security Guidelines

### Do Not Commit:
- ❌ Passwords or API keys
- ❌ `.env` files with real credentials
- ❌ Private keys or certificates
- ❌ Personal data

### Do Commit:
- ✅ `.env.example` with placeholder values
- ✅ Sanitized test data
- ✅ Public configuration

### Best Practices:
```yaml
# BAD - hardcoded credentials
variables:
  password: "MySecret123"

# GOOD - environment variables
variables:
  password: "${DEVICE_PASSWORD}"
```

## 📚 Documentation Guidelines

### Code Documentation

**Always include:**
- Module docstrings
- Class docstrings
- Function docstrings with Args/Returns/Raises
- Inline comments for complex logic

**Example:**
```python
"""
AWS Service for firmware management.

This module provides S3 operations with connection pooling
and regex caching for optimal performance.
"""

class AWSService:
    """
    Service for AWS S3 operations with firmware file handling.
    
    Features:
    - Connection pooling for 30-100% faster operations
    - Regex caching for 20% faster version extraction
    - CloudFront URL generation
    """
    
    def upload_file(self, bucket_name: str, local_file: str) -> str:
        """
        Upload a file to S3.
        
        Args:
            bucket_name: Target S3 bucket
            local_file: Path to local file
            
        Returns:
            S3 URL of uploaded file
            
        Raises:
            FileNotFoundError: If local file doesn't exist
            boto3.exceptions.S3UploadFailedError: If upload fails
        """
```

### Documentation Files

**Update when:**
- Adding new features → Update README.md and relevant docs
- Changing APIs → Update action reference
- Adding examples → Add to docs/examples.md
- Fixing bugs → Add to troubleshooting guide

## 🐛 Bug Reports

### Before Reporting
1. Search existing issues
2. Try latest version
3. Isolate the problem
4. Gather debug information

### Good Bug Report Template

```markdown
## Description
Clear description of the issue

## Steps to Reproduce
1. Run command X
2. With config Y
3. See error Z

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: macOS 14.0
- Python: 3.12.0
- Framework version: 1.0.0

## Test File
```yaml
name: Minimal reproduction
steps:
  - action: browser.open
    url: "https://example.com"
```

## Error Output
```
Traceback or error message here
```
```

## 🚀 Feature Requests

### Template

```markdown
## Feature Description
Clear description of the feature

## Use Case
Why is this needed? What problem does it solve?

## Proposed Solution
How it could work

## Alternatives Considered
Other approaches you thought about

## Example Usage
```yaml
# How the feature would be used
- action: new.feature
  option: value
```
```

## 🔍 Code Review Process

### What We Look For
- ✅ Code follows style guidelines
- ✅ Tests pass and have good coverage
- ✅ Documentation is updated
- ✅ No security issues
- ✅ Backward compatibility maintained
- ✅ Performance impact considered

### Review Checklist
- [ ] Code is well-structured and readable
- [ ] Type hints are present
- [ ] Docstrings are complete
- [ ] Tests cover new code
- [ ] Security best practices followed
- [ ] No hardcoded credentials
- [ ] Error handling is appropriate
- [ ] Performance is acceptable

## 📊 Performance Considerations

### When Adding Features
- Consider impact on test execution time
- Use connection pooling where applicable
- Cache expensive operations (regex, connections)
- Avoid N+1 queries
- Profile if uncertain

### Benchmarking
```bash
# Time your changes
make benchmark

# Compare before and after
time python -m easy_bdd run tests/cases/your_test.yaml
```

## 🎯 What to Contribute

### Good First Issues
- Documentation improvements
- Adding test examples
- Fixing typos
- Adding error messages
- Improving log output

### Needed Features
- [ ] Additional protocol services
- [ ] More browser actions
- [ ] Better error reporting
- [ ] Test retry logic
- [ ] Parallel execution improvements

### Code Quality
- [ ] Add unit tests
- [ ] Improve type hints
- [ ] Add docstrings
- [ ] Refactor complex functions
- [ ] Performance optimizations

## 💬 Getting Help

### Resources
- 📚 [Documentation](docs/README.md)
- 🔒 [Security Guide](SECURITY_IMPLEMENTATION.md)
- ⚡ [Performance Guide](WEEK2_PERFORMANCE.md)
- 📋 [Recommendations](RECOMMENDATIONS.md)

### Communication
- 💬 Open an issue for bugs/features
- 📧 Email maintainers for private concerns
- 💡 Start a discussion for ideas

## ✅ Pull Request Checklist

Before submitting your PR:

- [ ] Code follows style guidelines (run `make format`)
- [ ] All quality checks pass (run `make quality`)
- [ ] Tests pass (run `make test`)
- [ ] Test files validate (run `make validate`)
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] No merge conflicts
- [ ] PR description is clear
- [ ] Related issue is linked

## 📜 License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to Easy BDD Framework! 🙏
