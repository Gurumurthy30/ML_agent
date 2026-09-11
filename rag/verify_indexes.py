"""
rag/verify_indexes.py — Verification tests for built Chroma RAG indexes

Runs two verification queries:
1. Technique cheatsheet check:
   query_technique_cheatsheet("tabular baseline approach", top_k=3)
   Asserts at least one result mentions LightGBM, XGBoost, or CatBoost and has when_to_use content.
2. Library docs check:
   query_library_docs("LightGBM categorical feature handling", top_k=3)
   Asserts at least one result mentions categorical_feature or cat_features.

Run standalone:
    python rag/verify_indexes.py
"""

import sys
from pathlib import Path

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.retriever import query_library_docs, query_technique_cheatsheet


def verify_technique_cheatsheet() -> bool:
    print("\n[Verify 1/2] Querying technique_cheatsheet for 'tabular baseline approach'...")
    results = query_technique_cheatsheet("tabular baseline approach", modality="tabular", top_k=3)

    if not results:
        print("[FAIL] No results returned from technique_cheatsheet query.")
        return False

    matched = False
    for idx, item in enumerate(results):
        content = item.get("content", "")
        meta = item.get("metadata", {})
        print(f"  Result #{idx + 1}: {meta.get('technique_name', 'Unknown')} (source: {meta.get('source_type')})")
        print(f"    Snippet: {content[:150]}...\n")

        has_target_model = any(name in content for name in ["LightGBM", "XGBoost", "CatBoost"])
        has_when_to_use = "when to use" in content.lower() or "when_to_use" in content.lower()

        if has_target_model and has_when_to_use:
            matched = True

    if matched:
        print("[PASS] Technique cheatsheet returned relevant baseline entry with 'when_to_use' guidance.")
        return True
    else:
        print("[FAIL] None of the top results mentioned LightGBM/XGBoost/CatBoost with 'when_to_use' content.")
        return False


def verify_library_docs() -> bool:
    print("\n[Verify 2/2] Querying library_docs for 'LightGBM categorical feature handling'...")
    results = query_library_docs("LightGBM categorical feature handling", top_k=3)

    if not results:
        print("[FAIL] No results returned from library_docs query.")
        return False

    matched = False
    for idx, item in enumerate(results):
        content = item.get("content", "")
        meta = item.get("metadata", {})
        print(f"  Result #{idx + 1}: {meta.get('symbol', meta.get('library', 'Unknown'))} (source: {meta.get('source_type')})")
        print(f"    Snippet: {content[:150]}...\n")

        has_cat_feature = any(term in content.lower() for term in ["categorical_feature", "cat_features", "categorical"])
        if has_cat_feature:
            matched = True

    if matched:
        print("[PASS] Library docs returned relevant entry mentioning categorical features.")
        return True
    else:
        print("[FAIL] None of the top results mentioned categorical_feature or cat_features.")
        return False


def main():
    print("=" * 80)
    print("RAG INDEX VERIFICATION SUITE")
    print("=" * 80)

    ok1 = verify_technique_cheatsheet()
    ok2 = verify_library_docs()

    print("\n" + "=" * 80)
    print(f"VERIFICATION SUMMARY:")
    print(f"  1. Technique Cheatsheet Query: {'[PASS]' if ok1 else '[FAIL]'}")
    print(f"  2. Library Docs Query:         {'[PASS]' if ok2 else '[FAIL]'}")
    print("=" * 80)

    if ok1 and ok2:
        print("ALL VERIFICATION CHECKS PASSED.")
        sys.exit(0)
    else:
        print("SOME VERIFICATION CHECKS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
