---
applyTo: '**.py'
---

- Avoid using `Any` whenever possible. Use specific types instead.
    - Create strong types (usually dataclasses) for keeping internal state instead of property bags.

- In general, prefer using existing libraries for common tasks instead of writing your own code.
    - For example, use `pathlib` for file system operations, `json` for JSON handling, etc.

- Use `logging` for logging instead of `print`.
- Use `pytest` for testing
- Don't catch all exceptions in tests. Let tests fail if an unexpected/unknown exception occurs.

- Check for type errors after making code changes
- Run integration tests to validate after code changes