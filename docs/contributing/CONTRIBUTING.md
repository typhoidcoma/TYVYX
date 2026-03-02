# Contributing

## Setup

1. Fork and clone the repo
2. Python environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Frontend (if contributing to UI):
   ```bash
   cd frontend && npm install
   ```
4. Create a feature branch: `git checkout -b feature/your-feature`

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed environment setup.

## Types of Contributions

- **Code**: Bug fixes, features, performance improvements
- **Protocol discoveries**: New UDP commands, telemetry parsing, video improvements
- **Documentation**: Tutorials, API docs, troubleshooting
- **Testing**: Flight test results, calibration data, bug reports

## Workflow

1. Create an issue describing your change (optional but recommended)
2. Make focused changes (one feature/fix per PR)
3. Run checks:
   ```bash
   ruff check .          # Python lint
   black .               # Python format
   pytest                # Tests
   cd frontend && npm run lint && npm run build  # Frontend
   ```
4. Commit with descriptive messages:
   ```
   feat: Add altitude hold PID controller
   fix: Resolve video reconnection issue
   docs: Update protocol specification
   ```
5. Push and create a pull request

## Code Style

**Python**: Use ruff + black. 100 char line length. Follow existing patterns.

**TypeScript/React**: Use ESLint. Functional components with hooks. Follow existing patterns.

## PR Checklist

- [ ] Linters pass (ruff, ESLint)
- [ ] Tests pass (pytest, npm run build)
- [ ] Documentation updated if needed
- [ ] Focused changes (one feature/fix)
- [ ] Branch up to date with main

## Protocol Discoveries

Document new findings in [docs/technical/reverse-engineering.md](../technical/reverse-engineering.md) with:
- Command bytes (hex)
- Observed behavior
- Test conditions
- Packet captures if available

Use `python -m tyvyx.tools.packet_sniffer` for capture.

## License

By contributing, you agree that your contributions are licensed under the same license as the project.
