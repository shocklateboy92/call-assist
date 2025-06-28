#!/bin/bash

set -xe

# Switch to the directory where the script is located
cd "$(dirname "$0")"

# Do the checking/linting outside the call_assist directory,
# because it's also installed as an editable package.
pushd ..

# Type check the project
mypy call_assist

# lint the project
ruff check call_assist --fix

popd

# Run the broker
python3 call_assist.addon.broker