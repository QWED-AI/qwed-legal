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

QWED-Legal is licensed under the [Apache License 2.0](./LICENSE), and contributions are accepted under the same licence:

- **Inbound = outbound.** Under section 5 of the licence, a contribution you submit for inclusion is licensed under the Apache License 2.0, with no additional terms, unless you explicitly state otherwise.
- **You keep your copyright.** The licence lets everyone, the maintainer included, use, change and redistribute your contribution. Under section 3 you also grant a patent licence, limited to the patent claims you can license that your contribution necessarily infringes, alone or combined with QWED-Legal.
- **Only submit what you have the right to submit:** your own work, or code under a licence that is compatible with Apache-2.0, with its notices kept. Code under the GPL, the AGPL or another licence that is not compatible cannot be accepted.
- **The names are not licensed.** See [TRADEMARKS.md](./TRADEMARKS.md) for using "QWED" and its logo, and [NOTICE](./NOTICE) for the attribution that redistributions keep.

## 🙏 Thank You!

Every contribution helps make legal AI safer. We appreciate your time and effort!
