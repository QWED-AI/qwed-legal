# Contributing to QWED-Legal

Thank you for your interest in contributing to QWED-Legal! 🏛️

## 📋 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- pip

### Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/qwed-legal.git
   cd qwed-legal
   ```

2. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Run tests**
   ```bash
   pytest tests/ -v
   ```

4. **Run linter**
   ```bash
   ruff check .
   ```

## 🔧 Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Write code following our style guide (enforced by ruff)
- Add tests for new functionality
- Update documentation as needed

### 3. Test Your Changes

```bash
# Run all tests
pytest tests/ -v

# Run linter
ruff check .

# Fix lint issues automatically
ruff check . --fix
```

### 4. Commit Your Changes

Use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add jurisdiction support for Canada"
git commit -m "fix: handle leap year edge case in DeadlineGuard"
git commit -m "docs: improve ClauseGuard examples"
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## 📝 What to Contribute

### Good First Issues

Look for issues labeled `good first issue`:
- [Good First Issues](https://github.com/QWED-AI/qwed-legal/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)

### Areas We Need Help

| Area | Examples |
|------|----------|
| 🌍 **Jurisdictions** | Add holiday calendars for more countries |
| 📚 **Citations** | Add support for more legal reporters |
| 🧪 **Testing** | Edge case tests, property-based testing |
| 📖 **Documentation** | Tutorials, examples, translations |
| 🔧 **Features** | New guards (e.g., JurisdictionGuard) |

## 📐 Architecture Overview

```
qwed_legal/
├── __init__.py          # Package exports, LegalGuard class
├── guards/
│   ├── deadline_guard.py    # Date/time calculations
│   ├── liability_guard.py   # Financial math
│   ├── clause_guard.py      # Z3-based logic checking
│   └── citation_guard.py    # Bluebook citation validation
└── utils/                   # (future) Shared utilities
```

### Key Principles

1. **Deterministic**: No probabilistic outputs. Use symbolic/math engines.
2. **Zero Dependencies on LLMs**: We verify LLM output, not generate it.
3. **Type-Safe**: All functions should have type hints.
4. **Well-Tested**: Aim for >90% coverage.

## 🧪 Testing Guidelines

- Write tests in `tests/test_guards.py` or create new test files
- Use descriptive test names: `test_deadline_leap_year_february`
- Test edge cases: empty inputs, extreme values, boundary conditions

## 📄 License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.

## 🙏 Thank You!

Every contribution helps make legal AI safer. We appreciate your time and effort!
