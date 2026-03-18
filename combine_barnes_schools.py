#!/usr/bin/env python3
"""
Combine Barnes & Noble school visit data with Philadelphia School District performance data.

This script:
1. Reads the Barnes CSV (visitor/order data)
2. Reads the School performance CSV (SPREE/SPOTlight data)
3. Cleans and normalizes school names for matching
4. Optionally deduplicates Barnes orders
5. Performs a left join from Barnes → school data
6. Outputs a combined CSV for mapping/analysis
"""

import pandas as pd
import re
from difflib import SequenceMatcher

# ==== CONFIG ====
BARNES_CSV = "barnesschool.csv"
SCHOOL_CSV = "philadelphia_school_reports_2324.csv"
OUTPUT_CSV = "barnes_schools_joined.csv"

# Barnes CSV columns
BARNES_SCHOOL_NAME_COL = "OrganizationName"
BARNES_ZIP_COL = "OrganizationZipCode"

# School CSV columns
SCHOOL_NAME_COL = "school_name"

# Deduplication settings
DEDUP_BARNES = True
BARNES_ORDER_COL = "OrderNumber"
BARNES_DATE_COL = "EventStartTime"

# Fuzzy matching threshold (0.0 to 1.0) - lower = more lenient
FUZZY_MATCH_THRESHOLD = 0.65


# ==== Helper Functions ====

def normalize_school_name(s, keep_type=False):
    """
    Normalize school name for matching.
    
    Args:
        s: School name string
        keep_type: If True, preserve school type indicators (hs, ms, es)
    """
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    
    # Standardize charter school naming (must be done before other normalizations)
    # "Mastery CS - Gratz Campus" -> "mastery charter school at gratz"
    s = re.sub(r'\bcs\b', 'charter school', s)
    s = re.sub(r'\s*-\s*(\w+)\s+campus\b', r' at \1', s)  # "- Gratz Campus" -> "at Gratz"
    s = re.sub(r'\bcampus\b', '', s)
    
    # Handle common abbreviations
    s = re.sub(r'\bel\b', 'elementary', s)  # "Spring Garden El Sch" -> "elementary"
    s = re.sub(r'\bsch\b', 'school', s)  # "Sch" -> "School"
    s = re.sub(r'\bshs\b', 'high school', s)  # "SHS" -> "High School"
    
    # Standardize school type names (keep them for better matching)
    s = re.sub(r'\bhigh school\b', 'hs', s)
    s = re.sub(r'\bmiddle school\b', 'ms', s)
    s = re.sub(r'\belementary school\b', 'es', s)
    s = re.sub(r'\belementary\b', 'es', s)
    
    if not keep_type:
        # Remove type indicators for general matching
        s = re.sub(r'\b(hs|ms|es)\b', '', s)
    
    # Remove common noise words
    noise_words = [
        r'\bschool\b',
        r'\bacademy\b', 
        r'\bcharter\b',
        r'\bthe\b',
        r'\bof\b',
        r'\bat\b',
        r'\band\b',
        r'\bfor\b',
        r'\binstitute\b',
    ]
    for pattern in noise_words:
        s = re.sub(pattern, '', s)
    
    # Remove punctuation and extra spaces
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    
    return s.strip()


def normalize_zip(z):
    """Normalize ZIP code to 5 digits."""
    if pd.isna(z):
        return ""
    z = str(z).strip()
    # Keep only first 5 digits for US ZIP codes
    m = re.match(r"(\d{5})", z)
    return m.group(1) if m else z


def fuzzy_match_score(s1, s2):
    """Calculate fuzzy match score between two strings."""
    return SequenceMatcher(None, s1, s2).ratio()


def get_word_overlap_score(s1, s2):
    """Calculate word overlap score between two strings."""
    words1 = set(s1.split())
    words2 = set(s2.split())
    if not words1 or not words2:
        return 0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def infer_school_type(name):
    """Infer school type from name."""
    name_lower = name.lower()
    if 'high school' in name_lower or name_lower.endswith(' hs'):
        return 'high'
    elif 'middle school' in name_lower or name_lower.endswith(' ms'):
        return 'middle'
    elif 'elementary' in name_lower or name_lower.endswith(' es'):
        return 'elementary'
    return 'unknown'


def find_best_school_match(barnes_name, school_names_lookup, threshold=FUZZY_MATCH_THRESHOLD):
    """
    Find the best matching school name from the school data.
    Uses multiple matching strategies:
    1. Exact normalized match (with type)
    2. Exact normalized match (without type)
    3. Word overlap + fuzzy matching (with type preference)
    
    Returns (matched_name, score) or (None, 0) if no good match found.
    """
    if pd.isna(barnes_name):
        return None, 0
    
    barnes_name = str(barnes_name).strip()
    norm_barnes_with_type = normalize_school_name(barnes_name, keep_type=True)
    norm_barnes = normalize_school_name(barnes_name, keep_type=False)
    barnes_type = infer_school_type(barnes_name)
    
    if not norm_barnes:
        return None, 0
    
    # Strategy 1: Exact match with type preserved
    for orig_name, (norm_with_type, norm_without_type) in school_names_lookup.items():
        if norm_barnes_with_type == norm_with_type:
            return orig_name, 1.0
    
    # Strategy 2: Exact match without type
    candidates_exact = []
    for orig_name, (norm_with_type, norm_without_type) in school_names_lookup.items():
        if norm_barnes == norm_without_type:
            candidates_exact.append(orig_name)
    
    if len(candidates_exact) == 1:
        return candidates_exact[0], 0.95
    elif len(candidates_exact) > 1:
        # Multiple exact matches - prefer matching school type or non-high school if input has no type
        for candidate in candidates_exact:
            candidate_type = infer_school_type(candidate)
            if barnes_type != 'unknown' and candidate_type == barnes_type:
                return candidate, 0.95
            # If Barnes name has no type indicator, prefer elementary (most common for visits)
            if barnes_type == 'unknown' and candidate_type == 'elementary':
                return candidate, 0.90
        # Return first match if no type preference
        return candidates_exact[0], 0.85
    
    # Strategy 3: Fuzzy matching with word overlap
    best_match = None
    best_score = 0
    
    for orig_name, (norm_with_type, norm_without_type) in school_names_lookup.items():
        # Calculate combined score
        fuzzy_score = fuzzy_match_score(norm_barnes, norm_without_type)
        word_score = get_word_overlap_score(norm_barnes, norm_without_type)
        
        # Combined score weighted toward word overlap
        combined_score = 0.4 * fuzzy_score + 0.6 * word_score
        
        # Bonus for matching school type
        school_type = infer_school_type(orig_name)
        if barnes_type != 'unknown' and school_type == barnes_type:
            combined_score += 0.1
        
        if combined_score > best_score:
            best_score = combined_score
            best_match = orig_name
    
    if best_score >= threshold:
        return best_match, best_score
    
    return None, best_score


def create_school_name_lookup(schools_df):
    """
    Create a lookup dictionary from original names to normalized versions.
    Returns dict: {original_name: (norm_with_type, norm_without_type)}
    """
    lookup = {}
    for name in schools_df[SCHOOL_NAME_COL].dropna().unique():
        norm_with_type = normalize_school_name(name, keep_type=True)
        norm_without_type = normalize_school_name(name, keep_type=False)
        if norm_with_type or norm_without_type:
            lookup[name] = (norm_with_type, norm_without_type)
    return lookup


# ==== Main Script ====

def main():
    print("=" * 60)
    print("Barnes & School Data Combiner")
    print("=" * 60)
    
    # Load data
    print(f"\nLoading Barnes data from: {BARNES_CSV}")
    barnes = pd.read_csv(BARNES_CSV, dtype=str)
    print(f"  Loaded {len(barnes):,} rows")
    
    print(f"\nLoading school data from: {SCHOOL_CSV}")
    schools = pd.read_csv(SCHOOL_CSV, dtype=str)
    print(f"  Loaded {len(schools):,} schools")
    
    # Create normalized columns for deduplication
    print("\nNormalizing school names...")
    barnes["norm_school_name"] = barnes[BARNES_SCHOOL_NAME_COL].apply(lambda x: normalize_school_name(x, keep_type=False))
    
    if BARNES_ZIP_COL in barnes.columns:
        barnes["norm_zip"] = barnes[BARNES_ZIP_COL].apply(normalize_zip)
    else:
        barnes["norm_zip"] = ""
    
    schools["norm_school_name"] = schools[SCHOOL_NAME_COL].apply(lambda x: normalize_school_name(x, keep_type=False))
    
    # Optional: Deduplicate Barnes orders
    if DEDUP_BARNES:
        original_count = len(barnes)
        dedup_keys = [k for k in [BARNES_ORDER_COL, "norm_school_name", BARNES_DATE_COL] 
                      if k in barnes.columns]
        if dedup_keys:
            barnes = barnes.sort_values(dedup_keys).drop_duplicates(
                subset=dedup_keys, keep="first"
            )
            print(f"\nDeduplicated Barnes data: {original_count:,} → {len(barnes):,} rows")
    
    # Create school name lookup for fuzzy matching
    school_name_lookup = create_school_name_lookup(schools)
    print(f"\nCreated lookup with {len(school_name_lookup)} unique school names")
    
    # Find unique Barnes school names and match them
    unique_barnes_schools = barnes[BARNES_SCHOOL_NAME_COL].dropna().unique()
    print(f"\nMatching {len(unique_barnes_schools)} unique Barnes school names...")
    
    # Create a mapping from Barnes school name to matched school name
    match_results = {}
    matched_count = 0
    unmatched_schools = []
    
    for barnes_school in unique_barnes_schools:
        matched_name, score = find_best_school_match(barnes_school, school_name_lookup)
        if matched_name:
            match_results[barnes_school] = matched_name
            matched_count += 1
        else:
            match_results[barnes_school] = None
            unmatched_schools.append((barnes_school, score))
    
    print(f"  Matched: {matched_count}/{len(unique_barnes_schools)} schools")
    
    # Apply the mapping to create a join key
    barnes["matched_school_name"] = barnes[BARNES_SCHOOL_NAME_COL].map(match_results)
    
    # Perform the join
    print("\nPerforming left join...")
    merged = barnes.merge(
        schools,
        left_on="matched_school_name",
        right_on=SCHOOL_NAME_COL,
        how="left",
        suffixes=("", "_school")
    )
    
    # Count successful matches
    matched_rows = merged[SCHOOL_NAME_COL].notna().sum()
    print(f"  Rows with school data: {matched_rows:,}/{len(merged):,} ({100*matched_rows/len(merged):.1f}%)")
    
    # Clean up temporary columns
    cols_to_drop = ["norm_school_name", "norm_zip", "matched_school_name", "norm_school_name_school"]
    merged = merged.drop(columns=[c for c in cols_to_drop if c in merged.columns], errors="ignore")
    
    # Reorder columns: Barnes columns first, then school data columns
    barnes_cols = [c for c in barnes.columns if c in merged.columns and c not in cols_to_drop]
    school_cols = [c for c in schools.columns if c in merged.columns and c not in barnes_cols and c not in cols_to_drop]
    final_cols = barnes_cols + school_cols
    # Add any remaining columns
    remaining = [c for c in merged.columns if c not in final_cols]
    final_cols = final_cols + remaining
    merged = merged[[c for c in final_cols if c in merged.columns]]
    
    # Save result
    merged.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved combined file to: {OUTPUT_CSV}")
    print(f"  Total rows: {len(merged):,}")
    print(f"  Total columns: {len(merged.columns)}")
    
    # Report unmatched schools
    if unmatched_schools:
        print(f"\n{'=' * 60}")
        print("UNMATCHED SCHOOLS (could not find in school performance data):")
        print("=" * 60)
        # Sort by count in Barnes data
        unmatched_counts = barnes[barnes["matched_school_name"].isna()][BARNES_SCHOOL_NAME_COL].value_counts()
        for school_name in unmatched_counts.head(30).index:
            count = unmatched_counts[school_name]
            print(f"  {school_name}: {count} orders")
        
        if len(unmatched_counts) > 30:
            print(f"  ... and {len(unmatched_counts) - 30} more")
    
    # Summary statistics
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Barnes orders: {len(merged):,}")
    print(f"Orders matched to school data: {matched_rows:,} ({100*matched_rows/len(merged):.1f}%)")
    print(f"Unique schools in Barnes data: {len(unique_barnes_schools)}")
    print(f"Schools matched: {matched_count}")
    print(f"Schools unmatched: {len(unique_barnes_schools) - matched_count}")
    
    # Export unmatched schools to a separate file for review
    unmatched_export_file = "barnes_unmatched_schools.csv"
    if unmatched_schools:
        unmatched_df = barnes[barnes["matched_school_name"].isna()][[BARNES_SCHOOL_NAME_COL, BARNES_ZIP_COL, "School District", "School Type"]].drop_duplicates()
        unmatched_df = unmatched_df.sort_values(BARNES_SCHOOL_NAME_COL)
        unmatched_df.to_csv(unmatched_export_file, index=False)
        print(f"\nExported {len(unmatched_df)} unmatched schools to: {unmatched_export_file}")
    
    # Show sample of matched data
    print(f"\n{'=' * 60}")
    print("SAMPLE MATCHED DATA:")
    print("=" * 60)
    sample = merged[merged[SCHOOL_NAME_COL].notna()].head(5)
    for _, row in sample.iterrows():
        print(f"  Barnes: {row[BARNES_SCHOOL_NAME_COL]}")
        print(f"  Matched: {row[SCHOOL_NAME_COL]}")
        print(f"  Enrollment: {row.get('enrollment_oct1', 'N/A')}, Attendance: {row.get('student_attendance_2324', 'N/A')}%")
        print()
    
    # Additional verification statistics
    print(f"{'=' * 60}")
    print("VERIFICATION CHECKS:")
    print("=" * 60)
    
    # Check for potential mismatches by looking at school type consistency
    high_school_barnes = merged[merged[BARNES_SCHOOL_NAME_COL].str.contains('High School', case=False, na=False)]
    high_school_matched_to_non_hs = high_school_barnes[
        (high_school_barnes[SCHOOL_NAME_COL].notna()) & 
        (~high_school_barnes[SCHOOL_NAME_COL].str.contains('High School', case=False, na=False))
    ]
    if len(high_school_matched_to_non_hs) > 0:
        print(f"Warning: {len(high_school_matched_to_non_hs)} 'High School' entries matched to non-high schools")
        for _, row in high_school_matched_to_non_hs.drop_duplicates(BARNES_SCHOOL_NAME_COL).head(3).iterrows():
            print(f"  {row[BARNES_SCHOOL_NAME_COL]} -> {row[SCHOOL_NAME_COL]}")
    else:
        print("✓ All high school matches look consistent")
    
    print(f"\nOutput file ready for mapping: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
