"""Quick diagnostic: dump the fields from a known shop item."""
import json, os

cache_path = os.path.join(".cache", "items.json")
if not os.path.exists(cache_path):
    print("No cache found. Run the main tool first to populate .cache/items.json")
    exit(1)

with open(cache_path, encoding="utf-8") as f:
    items = json.load(f)

# Find some known shop items
targets = ["metal skin", "boundless spirit", "burst fire", "healing nova", "weighted shots"]
found = 0

for item in items:
    name = (item.get("name") or "").lower()
    if name in targets:
        found += 1
        print(f"\n{'='*60}")
        print(f"NAME: {item.get('name')}")
        print(f"CLASS: {item.get('class_name')}")
        print(f"{'='*60}")
        # Print all top-level keys and their types/values (skip huge nested objects)
        for key, val in sorted(item.items()):
            if key in ("properties", "description", "upgrades"):
                print(f"  {key}: <{type(val).__name__}, {len(str(val))} chars>")
            elif isinstance(val, dict):
                print(f"  {key}: {json.dumps(val, indent=4)[:200]}")
            elif isinstance(val, list):
                print(f"  {key}: [{len(val)} items] {str(val)[:150]}")
            else:
                print(f"  {key}: {val}")
        if found >= 3:
            break

if not found:
    print("No known shop items found. Dumping first 3 'upgrade_' items instead:")
    count = 0
    for item in items:
        cn = item.get("class_name", "")
        if cn.startswith("upgrade_"):
            count += 1
            print(f"\n  {item.get('name')} ({cn})")
            for key, val in sorted(item.items()):
                if key in ("properties", "description", "upgrades"):
                    continue
                if isinstance(val, (dict, list)):
                    print(f"    {key}: {str(val)[:120]}")
                else:
                    print(f"    {key}: {val}")
            if count >= 3:
                break
