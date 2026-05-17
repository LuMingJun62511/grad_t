#!/usr/bin/env bash
STATE="/tmp/wf_test_flaky_state"
if [[ -f "$STATE" ]]; then
    rm -f "$STATE"
    echo "test_flaky: second run, succeeding!"
    exit 0
else
    touch "$STATE"
    echo "test_flaky: first run, failing (retry will succeed)"
    exit 1
fi
