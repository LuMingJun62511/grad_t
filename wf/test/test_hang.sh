#!/usr/bin/env bash
echo "test_hang: this will sleep 10s..."
sleep 10
echo "test_hang: done (should not reach here with timeout)"
exit 0
