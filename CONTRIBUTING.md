# Contributing to CIBIL Coach

Thanks for your interest in contributing! Here's how to help.

## Getting Started

1. Fork the repo
2. Clone your fork: `git clone https://github.com/yourusername/cibil-coach.git`
3. Create a branch: `git checkout -b feature/your-feature`
4. Set up your environment: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

## Making Changes

### Before you start
- Check existing issues to avoid duplicates
- For new features, open an issue first to discuss the approach

### Code style
- Follow PEP 8
- Use type hints for function arguments and returns
- Write docstrings for modules, classes, and functions
- Keep functions focused and testable

### Testing
Before submitting a PR:

```bash
# Run the full pipeline test
python3 scripts/e2e_db_test.py

# Test with real LLM (if modifying LLM logic)
export OPENAI_API_KEY="sk-..."
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

## Submitting Changes

1. Push to your fork: `git push origin feature/your-feature`
2. Create a pull request with:
   - Clear title (e.g., "Add score improvement tips to output")
   - Description of what changed and why
   - Any testing you did
3. Address review feedback
4. Merge once approved

## Areas to Contribute

### High Priority
- Real CIBIL API integration (currently uses sample data)
- Multi-bureau support (add Experian, Equifax)
- Better error handling and validation
- Production deployment guide

### Nice to Have
- UI improvements
- Additional credit metrics
- Localization (Hindi, regional languages)
- Performance optimizations
- Documentation improvements

## Code of Conduct

Be respectful and constructive. We welcome all contributions.

## Questions?

Open an issue or start a discussion. No question is too small.

Thanks for helping make CIBIL Coach better! 🙌
