#!/bin/bash

set -xe

# Switch to the directory where the script is located
cd "$(dirname "$0")"

# Type check the project
mypy --explicit-package-bases .

# lint the project
ruff check --fix .

# Run the broker
python3 -m call_assist.addon.broker