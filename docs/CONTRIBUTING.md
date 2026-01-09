# Contributing to Himotoki

Thank you for your interest in contributing to Himotoki! We welcome contributions of all kinds, from bug fixes and feature implementations to documentation improvements.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- `pip` and `venv` (recommended)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/himotoki/himotoki.git
   cd himotoki
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the package in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Development Workflow

### Coding Standards

- Follow PEP 8 style guidelines.
- Use descriptive variable and function names.
- Include docstrings for all public modules, classes, and functions.
- Keep functions focused and manageable in size.

### Running Tests

We use `pytest` for testing. Before submitting a pull request, ensure all tests pass:

```bash
pytest
```

To run tests with coverage:

```bash
pytest --cov=himotoki
```

### Submitting Changes

1. Create a new branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Commit your changes with clear, descriptive commit messages.
3. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

4. Open a Pull Request on GitHub. Provide a clear description of the changes and link to any relevant issues.

## Reporting Issues

If you find a bug or have a feature request, please open an issue on the [GitHub Issues](https://github.com/himotoki/himotoki/issues) page.

Include the following information in bug reports:
- A clear, descriptive title.
- Steps to reproduce the issue.
- Expected behavior vs. actual behavior.
- Your environment (Python version, OS, etc.).
- Relevant code snippets or error messages.

---

Thank you for making Himotoki better!
