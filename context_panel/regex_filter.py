"""Isolated regex worker. Input stays on stdin; output contains indices only."""
import json
import re
import sys

if __name__ == '__main__':
    data = json.load(sys.stdin)
    patterns = [re.compile(p, re.IGNORECASE) for p in data['patterns']]
    json.dump([i for i, text in enumerate(data['texts']) if any(p.search(text) for p in patterns)], sys.stdout)
