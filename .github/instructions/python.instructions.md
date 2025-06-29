---
applyTo: '**.py'
---

- Avoid using `Any` whenever possible. Use specific types instead.
- Avoid using untyped dictionaries. 
    - Create dataclasses to pass around internal state/data
    - Use `TypedDict` if a dictionary makes sense

- In general, prefer using existing libraries for common tasks instead of writing your own code.
    - For example, use `pathlib` for file system operations, `json` for JSON handling, etc.

- Always import at the top of the file, avoid importing inside functions or methods unless absolutely necessary.

- Use `logging` for logging instead of `print`.
- Use `pytest` for testing
- Don't catch all exceptions in tests. Let tests fail if an unexpected/unknown exception occurs.

- Check for type errors after making code changes
- Run integration tests to validate after code changes

- Avoid catching `Exception` or `BaseException` unless you have a very good reason.
  - This is a server, with a global exception handler, so exceptions should bubble up to the top level.
  - Only catch specific exceptions that you expect and can handle appropriately.
