"""Merge training data from multiple agent output files into one clean corpus."""
import json
import sys
import random
from pathlib import Path

def extract_jsonl(filepath):
    """Extract valid JSONL lines from an agent output file."""
    items = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Agent output files contain conversation events; we want the final result
                # Look for lines that have instruction+output (our training data format)
                if "instruction" in obj and "output" in obj:
                    items.append({"instruction": obj["instruction"], "output": obj["output"]})
            except json.JSONDecodeError:
                continue
    return items


def main():
    if len(sys.argv) < 2:
        print("Usage: python merge_train.py <agent_output1> <agent_output2> ... -o <output.jsonl>")
        sys.exit(1)

    # Parse args
    args = sys.argv[1:]
    input_files = []
    output_path = "华为训练语料_自然版.jsonl"

    i = 0
    while i < len(args):
        if args[i] == "-o" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        else:
            input_files.append(args[i])
            i += 1

    if not input_files:
        print("No input files specified")
        sys.exit(1)

    all_items = []
    stats = {}
    for fp in input_files:
        items = extract_jsonl(fp)
        stats[Path(fp).name] = len(items)
        all_items.extend(items)
        print(f"  {Path(fp).name}: {len(items)} items")

    # Deduplicate by instruction
    seen = set()
    unique = []
    for item in all_items:
        key = item["instruction"].strip()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    dupes = len(all_items) - len(unique)

    # Shuffle
    random.seed(42)
    random.shuffle(unique)

    # Write
    with open(output_path, "w", encoding="utf-8") as f:
        for item in unique:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\nTotal raw: {len(all_items)}")
    print(f"Deduplicated: {len(unique)} ({dupes} dupes removed)")
    print(f"Output: {output_path}")

    # Show a few samples
    print("\n--- Samples ---")
    for item in random.sample(unique, min(3, len(unique))):
        print(f"Q: {item['instruction']}")
        print(f"A: {item['output'][:150]}...")
        print()


if __name__ == "__main__":
    main()
