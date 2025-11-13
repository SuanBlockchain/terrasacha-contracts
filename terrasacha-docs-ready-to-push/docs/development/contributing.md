# Contributing

Thank you for considering contributing to Terrasacha Contracts!

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Install dependencies: `uv sync --extra dev`
4. Create a feature branch: `git checkout -b feature/your-feature`

## Development Workflow

See: [Development Guide](../getting-started/development.md)

## Code Quality Standards

All contributions must pass:

- ✅ Code formatting (ruff format)
- ✅ Import sorting (ruff check --select I)
- ✅ Linting (ruff check)
- ✅ Type checking (mypy)
- ✅ All tests passing (pytest)
- ✅ Test coverage maintained or improved

## Pre-Commit Checklist

```bash
# Format code
uv run ruff format .

# Sort imports
uv run ruff check --select I --fix .

# Lint
uv run ruff check --fix .

# Type check
uv run mypy .

# Run tests
uv run pytest

# Build contracts
uv run python src/scripts/build_contracts.py
```

## Commit Message Format

Follow conventional commits:

```
type: brief description

Longer explanation if needed

Types:
- feat: New feature
- fix: Bug fix
- docs: Documentation changes
- test: Test additions/changes
- refactor: Code refactoring
- perf: Performance improvements
- chore: Maintenance tasks
```

Examples:
```
feat: add burn validation to protocol NFTs
fix: resolve datum immutability check
docs: update architecture overview
test: add integration tests for minting
```

## Pull Request Process

1. Ensure all checks pass locally
2. Update documentation if needed
3. Add/update tests for new functionality
4. Push to your fork
5. Create pull request with clear description
6. Address review comments
7. Wait for approval and merge

## Code Review

What reviewers look for:

- Code correctness and safety
- Test coverage
- Documentation quality
- Performance considerations
- Security implications
- Consistency with codebase

## Testing Requirements

- New features must include tests
- Maintain >80% code coverage
- Tests must pass on all platforms
- Use appropriate test markers

## Documentation Requirements

- Update relevant documentation
- Add docstrings to new functions
- Include code examples where helpful
- Keep documentation accurate

## Questions?

- Open an issue for discussion
- Check existing issues and PRs
- Review documentation thoroughly

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.
