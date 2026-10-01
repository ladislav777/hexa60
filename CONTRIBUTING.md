# Contributing to HEXA60

Thank you for your interest in contributing to **HEXA60**! We welcome contributions from the community, including bug reports, feature proposals, documentation fixes, and code optimizations.

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful, welcoming, and collaborative environment for all contributors.

---

## How to Contribute

### 1. Reporting Bugs
Before submitting an issue, please search existing open and closed issues to avoid duplicates.
When creating a bug report, include:
- A clear, descriptive title.
- Python version, operating system, and HEXA60 version.
- Minimal reproducible example (code snippet and input data).
- Expected vs. actual behavior (including full exception tracebacks).

### 2. Suggesting Enhancements
Feature requests are welcome! Please explain:
- The specific problem or bottleneck you are facing.
- How the proposed feature solves it.
- Examples of API usage if applicable.

### 3. Submitting Pull Requests (PRs)

1. **Fork the Repository** and create your branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Development & Environment Setup:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   ```

3. **Code Quality & Testing Rules:**
   - Follow **PEP 8** style guidelines.
   - All public functions must include type annotations and clear docstrings.
   - Maintain 100% unit test coverage.
   - Run tests locally before opening a PR:
     ```bash
     pytest tests/ --cov=hexa60
     ```

4. **Contributor License Agreement (CLA):**
   Because HEXA60 is offered under a dual-licensing model (AGPLv3 / Commercial OEM), all contributors must sign a standard Contributor License Agreement (CLA) or Developer Certificate of Origin (DCO) granting the project maintainers rights to relicense contributions under commercial terms.

---

## Contact & Maintainers

For questions regarding development, bug reports, or contributing, reach out to `mullerladislav20@gmail.com`.
