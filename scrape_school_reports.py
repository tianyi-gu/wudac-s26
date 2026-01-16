#!/usr/bin/env python3
"""
Philadelphia School District SPOTlight & SPREE Report Scraper

This script:
1. Scrapes the Google Sheets spreadsheet to get school list and PDF links
2. Downloads and parses each school's PDF report
3. Extracts performance data from the PDFs
4. Saves all data to a CSV file for analysis
"""

import re
import time
import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd
from io import BytesIO, StringIO
import logging
from typing import Optional, Dict, List, Any

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
SHEET_ID = "2PACX-1vS70o-bkR4qO-SJEZDECEMxsoUATIYOAAjduDS1qMVImXTJoTU91MMxIcddA8PkNmHhqAcFhi0zLo65"
GID = "1872275673"
SPREADSHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={GID}&single=true&output=csv"
PDF_BASE_URL = "https://cdn.philasd.org/offices/performance/SPREE_Files/2023-2024/Reports/"


def get_school_list_from_spreadsheet() -> List[Dict[str, str]]:
    """
    Fetch the Google Sheets spreadsheet as CSV to get the list of schools with their info.
    Returns a list of dictionaries with school data.
    """
    logger.info("Fetching school list from spreadsheet (CSV export)...")
    
    response = requests.get(SPREADSHEET_CSV_URL)
    response.raise_for_status()
    
    # Parse CSV using pandas
    df = pd.read_csv(StringIO(response.text), skiprows=1)  # Skip the title row
    
    schools = []
    
    for _, row in df.iterrows():
        try:
            school_id = str(row.iloc[0]).strip()
            school_name = str(row.iloc[1]).strip()
            network = str(row.iloc[2]).strip()
            district = str(row.iloc[3]).strip()
            
            # Skip invalid entries
            if not school_id or not school_id.isdigit():
                continue
            
            # Construct PDF URL from school ID
            # URL pattern: https://cdn.philasd.org/offices/performance/SPREE_Files/2023-2024/Reports/[SCHOOL_ID]_SP_SPREE_SPOTlight.pdf
            pdf_url = f"{PDF_BASE_URL}%5B{school_id}%5D_SP_SPREE_SPOTlight.pdf"
            
            schools.append({
                'school_id': school_id,
                'school_name': school_name,
                'network': network,
                'district': district,
                'pdf_url': pdf_url
            })
        except Exception as e:
            logger.warning(f"Error parsing row: {e}")
            continue
    
    logger.info(f"Found {len(schools)} schools")
    return schools


def download_pdf(url: str) -> Optional[bytes]:
    """Download a PDF from the given URL."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logger.warning(f"Failed to download PDF from {url}: {e}")
        return None


def extract_number(text: str) -> Optional[float]:
    """Extract a number from text, handling percentages and negative numbers."""
    if not text or text.lower() in ['not applicable', 'insufficient sample', 'insufficient data', 'n/a', '']:
        return None
    
    # Remove commas and whitespace
    text = text.replace(',', '').strip()
    
    # Try to find a number (including negative and decimal)
    match = re.search(r'-?\d+\.?\d*', text)
    if match:
        return float(match.group())
    return None


def parse_pdf_report(pdf_content: bytes, school_id: str) -> Dict[str, Any]:
    """
    Parse a school's PDF report and extract performance data.
    Returns a dictionary with all extracted metrics.
    """
    data = {'school_id': school_id}
    
    try:
        with pdfplumber.open(BytesIO(pdf_content)) as pdf:
            full_text = ""
            tables = []
            
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
                
                # Extract tables from each page
                page_tables = page.extract_tables()
                tables.extend(page_tables)
            
            # Extract school info from first page
            data.update(extract_school_info(full_text))
            
            # Extract SPOTlight metrics
            data.update(extract_spotlight_metrics(full_text, tables))
            
            # Extract SPREE demographics
            data.update(extract_demographics(full_text))
            
            # Extract academic performance
            data.update(extract_academic_performance(full_text, tables))
            
    except Exception as e:
        logger.error(f"Error parsing PDF for school {school_id}: {e}")
    
    return data


def extract_school_info(text: str) -> Dict[str, Any]:
    """Extract basic school information from PDF text."""
    info = {}
    
    # School Code
    match = re.search(r'School Code\s*[|\s]*(\d+)', text)
    if match:
        info['school_code'] = match.group(1)
    
    # Principal Name
    match = re.search(r'Principal Name\s*[|\s]*([A-Za-z\s\.]+?)(?:\s*Address|\s*$)', text)
    if match:
        info['principal_name'] = match.group(1).strip()
    
    # Sector
    match = re.search(r'Sector\s*[|\s]*(District|Charter)', text, re.IGNORECASE)
    if match:
        info['sector'] = match.group(1)
    
    # Network
    match = re.search(r'Network\s*[|\s]*(Network\s*\d+|Charters)', text)
    if match:
        info['network_from_pdf'] = match.group(1)
    
    # Grades Served
    match = re.search(r'Grades Served\s*[|\s]*([K0-9\-]+)', text)
    if match:
        info['grades_served'] = match.group(1)
    
    # Admission Category
    match = re.search(r'Admission Category\s*[|\s]*(\w+)', text)
    if match:
        info['admission_category'] = match.group(1)
    
    # October 1 Enrollment
    match = re.search(r'October 1 Enrollment\s*[|\s]*(\d+)', text)
    if match:
        info['enrollment_oct1'] = int(match.group(1))
    
    # Report Type
    if 'High School' in text or 'Keystone' in text:
        info['report_type'] = 'High School'
    elif 'Elementary' in text or 'PSSA' in text:
        info['report_type'] = 'Elementary/Middle'
    
    return info


def extract_spotlight_metrics(text: str, tables: List) -> Dict[str, Any]:
    """Extract SPOTlight metrics (Conditions for Success)."""
    metrics = {}
    
    # Student Attendance 2023-24
    match = re.search(r'Student Attendance\s*[\d\.]+%?\s*[\d\.]+%?\s*[+\-]?[\d\.]+\s*%-?pts?\s*[\d\.]+%?\s*([\d\.]+)%', text)
    if match:
        metrics['student_attendance_2324'] = float(match.group(1))
    else:
        # Alternative pattern
        match = re.search(r'Student Attendance.*?(\d+\.?\d*)%\s*[+\-]?\d+\.?\d*\s*%-?pts?$', text, re.MULTILINE)
        if match:
            metrics['student_attendance_2324'] = float(match.group(1))
    
    # Teacher Attendance 2023-24
    match = re.search(r'Teacher Attendance\s*[\d\.]+%?\s*[\d\.]+%?\s*[+\-]?[\d\.]+\s*%-?pts?\s*[\d\.]+%?\s*([\d\.]+)%', text)
    if match:
        metrics['teacher_attendance_2324'] = float(match.group(1))
    
    # Student Dropouts 2023-24
    match = re.search(r'Student Dropouts.*?(\d+)\s*-\d+\s*$', text, re.MULTILINE)
    if match:
        metrics['dropouts_2324'] = int(match.group(1))
    else:
        match = re.search(r'Student Dropouts[^\d]*(\d+)[^\d]+(\d+)[^\d]+(-?\d+)[^\d]+(\d+)[^\d]+(\d+)', text)
        if match:
            metrics['dropouts_2324'] = int(match.group(5))
    
    # Graduation Rate (4-Year Cohort) 2023-24
    match = re.search(r'Graduation Rate.*?([\d\.]+)%\s*[+\-][\d\.]+\s*%-?pts?\s*$', text, re.MULTILINE)
    if match:
        metrics['graduation_rate_2324'] = float(match.group(1))
    
    # Also try to extract from tables
    for table in tables:
        if not table:
            continue
        for row in table:
            if not row:
                continue
            row_text = ' '.join(str(cell or '') for cell in row)
            
            # Student Attendance
            if 'Student Attendance' in row_text and len(row) >= 6:
                val = extract_number(str(row[-2] if row[-2] else row[-1]))
                if val and 'student_attendance_2324' not in metrics:
                    metrics['student_attendance_2324'] = val
            
            # Teacher Attendance
            if 'Teacher Attendance' in row_text and len(row) >= 6:
                val = extract_number(str(row[-2] if row[-2] else row[-1]))
                if val and 'teacher_attendance_2324' not in metrics:
                    metrics['teacher_attendance_2324'] = val
            
            # Graduation Rate
            if 'Graduation Rate' in row_text and len(row) >= 6:
                val = extract_number(str(row[-2] if row[-2] else row[-1]))
                if val and 'graduation_rate_2324' not in metrics:
                    metrics['graduation_rate_2324'] = val
    
    return metrics


def extract_demographics(text: str) -> Dict[str, Any]:
    """Extract student demographics and enrollment info."""
    demographics = {}
    
    # Racial/ethnic demographics
    patterns = [
        (r'([\d\.]+)%\s*American Indian\s*/\s*Alaskan Native', 'pct_american_indian'),
        (r'([\d\.]+)%\s*Asian', 'pct_asian'),
        (r'([\d\.]+)%\s*Black\s*/\s*African American', 'pct_black'),
        (r'([\d\.]+)%\s*Hispanic\s*/\s*Latino', 'pct_hispanic'),
        (r'([\d\.]+)%\s*Multi\s*Racial\s*/\s*Other', 'pct_multiracial'),
        (r'([\d\.]+)%\s*Native Hawaiian\s*/\s*Pacific Islander', 'pct_pacific_islander'),
        (r'([\d\.]+)%\s*White', 'pct_white'),
    ]
    
    for pattern, key in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            demographics[key] = float(match.group(1))
    
    # The PDF text has specific patterns based on layout:
    # Line: "679 24.3% for Score for Score" - 679 is students served, 24.3% is IEPs
    # Line: "21.8% 80.7%" - 21.8% is English Learners, 80.7% is Economically Disadvantaged
    # Line: "25.6% 40.4% Economically Disadvantaged" - 25.6% is attending 95%, 40.4% is attending 90%
    
    # Students served and IEPs - pattern like "679 24.3% for Score"
    match = re.search(r'(\d{2,4})\s+([\d\.]+)%\s*(?:for\s*Score)?', text)
    if match:
        val1, val2 = int(match.group(1)), float(match.group(2))
        # The larger number is students served, the smaller is IEPs percentage
        if val1 > 100:
            demographics['students_served_full_year'] = val1
            demographics['pct_iep'] = val2
    
    # English Learners and Economically Disadvantaged - pattern like "21.8% 80.7%"
    # This appears AFTER IEP line and BEFORE attendance line
    match = re.search(r'([\d\.]+)%\s+([\d\.]+)%\s*\n.*?%\s*of\s*Students\s*Identified\s*as.*?English\s*Learners.*?Economically\s*Disadvantaged', text, re.IGNORECASE | re.DOTALL)
    if match:
        demographics['pct_english_learners'] = float(match.group(1))
        demographics['pct_economically_disadvantaged'] = float(match.group(2))
    
    # Attendance metrics - pattern like "25.6% 40.4% Economically Disadvantaged" followed by "% of Students Attending"
    # Need to match the line that ends with "Economically Disadvantaged" and then "% of Students Attending"
    match = re.search(r'([\d\.]+)%\s+([\d\.]+)%\s+Economically\s*Disadvantaged\s*\n.*?%\s*of\s*Students\s*Attending', text, re.IGNORECASE | re.DOTALL)
    if match:
        demographics['pct_attend_95plus'] = float(match.group(1))
        demographics['pct_attend_90plus'] = float(match.group(2))
    
    return demographics


def extract_academic_performance(text: str, tables: List) -> Dict[str, Any]:
    """Extract academic performance metrics (PSSA/Keystone scores)."""
    performance = {}
    
    # Keystone scores (for high schools)
    # Algebra 1
    match = re.search(r'Algebra\s*1?\s*[\d\.]+%?\s*[\d\.]+%?\s*[+\-]?[\d\.]+\s*%-?pts?\s*[\d\.]+%?\s*([\d\.]+)%', text)
    if match:
        performance['keystone_algebra_2324'] = float(match.group(1))
    else:
        match = re.search(r'Algebra\s*1?\s*.*?Score:\s*([\d\.]+)%', text)
        if match:
            performance['keystone_algebra_2324'] = float(match.group(1))
    
    # Biology
    match = re.search(r'Biology\s*[\d\.]+%?\s*[\d\.]+%?\s*[+\-]?[\d\.]+\s*%-?pts?\s*[\d\.]+%?\s*([\d\.]+)%', text)
    if match:
        performance['keystone_biology_2324'] = float(match.group(1))
    else:
        match = re.search(r'Biology\s*.*?Score:\s*([\d\.]+)%', text)
        if match:
            performance['keystone_biology_2324'] = float(match.group(1))
    
    # Literature
    match = re.search(r'Literature\s*[\d\.]+%?\s*[\d\.]+%?\s*[+\-]?[\d\.]+\s*%-?pts?\s*[\d\.]+%?\s*([\d\.]+)%', text)
    if match:
        performance['keystone_literature_2324'] = float(match.group(1))
    else:
        match = re.search(r'Literature\s*.*?Score:\s*([\d\.]+)%', text)
        if match:
            performance['keystone_literature_2324'] = float(match.group(1))
    
    # PSSA scores (for elementary/middle schools)
    # Format: "Grade 3 Reading 51.1% 46.4% -4.7 %-pts 46.4% 46.3% -0.1 %-pts"
    # We need the 5th percentage (2023-24 results), which is the second-to-last before the final progress
    
    # Grade 3 Reading - get the 2023-24 value (5th percentage or pattern with %-pts before it)
    match = re.search(r'Grade 3 Reading\s+[\d\.]+%\s+[\d\.]+%\s+[+\-]?[\d\.]+\s*%-?pts\s+[\d\.]+%\s+([\d\.]+)%', text)
    if match:
        performance['pssa_grade3_reading'] = float(match.group(1))
    
    # Grade 3-8 Reading
    match = re.search(r'Grade 3\s*-?\s*8 Reading\s+[\d\.]+%\s+[\d\.]+%\s+[+\-]?[\d\.]+\s*%-?pts\s+[\d\.]+%\s+([\d\.]+)%', text)
    if match:
        performance['pssa_grade3_8_reading'] = float(match.group(1))
    
    # Grade 3 Math
    match = re.search(r'Grade 3 Math\s+[\d\.]+%\s+[\d\.]+%\s+[+\-]?[\d\.]+\s*%-?pts\s+[\d\.]+%\s+([\d\.]+)%', text)
    if match:
        performance['pssa_grade3_math'] = float(match.group(1))
    
    # Grade 3-8 Math
    match = re.search(r'Grade 3\s*-?\s*8 Math\s+[\d\.]+%\s+[\d\.]+%\s+[+\-]?[\d\.]+\s*%-?pts\s+[\d\.]+%\s+([\d\.]+)%', text)
    if match:
        performance['pssa_grade3_8_math'] = float(match.group(1))
    
    # Grade 4 and 8 Science
    match = re.search(r'Grade 4 and 8 Science\s+[\d\.]+%\s+[\d\.]+%\s+[+\-]?[\d\.]+\s*%-?pts\s+[\d\.]+%\s+([\d\.]+)%', text)
    if match:
        performance['pssa_science'] = float(match.group(1))
    
    # NOCTI (CTE)
    match = re.search(r'NOCTI.*?([\d\.]+)%', text)
    if match:
        performance['nocti_2324'] = float(match.group(1))
    
    # Try to extract from tables as well, but skip if "Not Applicable" is in the row
    for table in tables:
        if not table:
            continue
        for row in table:
            if not row:
                continue
            row_text = ' '.join(str(cell or '') for cell in row)
            
            # Skip rows with "Not Applicable"
            if 'Not Applicable' in row_text:
                continue
            
            # Keystone Algebra - only extract if we have a percentage and it's a valid score
            if 'Algebra' in row_text and 'keystone_algebra_2324' not in performance:
                # Look for a cell with a percentage value
                for cell in row:
                    cell_str = str(cell or '')
                    if '%' in cell_str:
                        val = extract_number(cell_str)
                        if val and 0 < val <= 100:
                            performance['keystone_algebra_2324'] = val
                            break
            
            # Keystone Biology - only extract if we have a percentage
            if 'Biology' in row_text and 'keystone_biology_2324' not in performance:
                for cell in row:
                    cell_str = str(cell or '')
                    if '%' in cell_str:
                        val = extract_number(cell_str)
                        if val and 0 < val <= 100:
                            performance['keystone_biology_2324'] = val
                            break
            
            # Keystone Literature - only extract if we have a percentage
            if 'Literature' in row_text and 'keystone_literature_2324' not in performance:
                for cell in row:
                    cell_str = str(cell or '')
                    if '%' in cell_str:
                        val = extract_number(cell_str)
                        if val and 0 < val <= 100:
                            performance['keystone_literature_2324'] = val
                            break
    
    return performance


def main():
    """Main function to orchestrate the scraping and parsing."""
    logger.info("Starting Philadelphia School Report Scraper")
    
    # Get list of schools from spreadsheet
    schools = get_school_list_from_spreadsheet()
    
    if not schools:
        logger.error("No schools found in spreadsheet")
        return
    
    # Process each school's PDF
    all_data = []
    total = len(schools)
    
    for i, school in enumerate(schools, 1):
        school_id = school['school_id']
        school_name = school['school_name']
        pdf_url = school['pdf_url']
        
        logger.info(f"[{i}/{total}] Processing {school_name} (ID: {school_id})")
        
        # Start with spreadsheet data
        school_data = {
            'school_id': school_id,
            'school_name': school_name,
            'network': school['network'],
            'city_council_district': school['district'],
            'pdf_url': pdf_url
        }
        
        # Download and parse PDF
        pdf_content = download_pdf(pdf_url)
        
        if pdf_content:
            pdf_data = parse_pdf_report(pdf_content, school_id)
            # Merge PDF data with school data (PDF data takes precedence for overlapping fields)
            for key, value in pdf_data.items():
                if value is not None:
                    school_data[key] = value
        else:
            logger.warning(f"Could not download PDF for {school_name}")
        
        all_data.append(school_data)
        
        # Be nice to the server
        time.sleep(0.5)
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(all_data)
    
    # Reorder columns for better readability
    column_order = [
        # Basic info
        'school_id', 'school_code', 'school_name', 'principal_name',
        'sector', 'network', 'network_from_pdf', 'city_council_district',
        'grades_served', 'admission_category', 'report_type',
        
        # Enrollment
        'enrollment_oct1', 'students_served_full_year',
        
        # Demographics
        'pct_american_indian', 'pct_asian', 'pct_black', 'pct_hispanic',
        'pct_multiracial', 'pct_pacific_islander', 'pct_white',
        'pct_iep', 'pct_english_learners', 'pct_economically_disadvantaged',
        
        # Attendance
        'student_attendance_2324', 'teacher_attendance_2324',
        'pct_attend_95plus', 'pct_attend_90plus',
        
        # Conditions for Success
        'dropouts_2324', 'graduation_rate_2324',
        
        # Academic Performance - Keystone
        'keystone_algebra_2324', 'keystone_biology_2324', 'keystone_literature_2324',
        
        # Academic Performance - PSSA
        'pssa_grade3_reading', 'pssa_grade3_8_reading',
        'pssa_grade3_math', 'pssa_grade3_8_math', 'pssa_science',
        
        # CTE
        'nocti_2324',
        
        # Metadata
        'pdf_url'
    ]
    
    # Only include columns that exist in the data
    existing_columns = [col for col in column_order if col in df.columns]
    # Add any columns we might have missed
    extra_columns = [col for col in df.columns if col not in column_order]
    final_columns = existing_columns + extra_columns
    
    df = df[final_columns]
    
    # Save to CSV
    output_file = 'philadelphia_school_reports_2324.csv'
    df.to_csv(output_file, index=False)
    logger.info(f"Data saved to {output_file}")
    logger.info(f"Total schools processed: {len(df)}")
    logger.info(f"Columns: {len(df.columns)}")
    
    # Print summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Total schools: {len(df)}")
    
    if 'graduation_rate_2324' in df.columns:
        grad_data = df['graduation_rate_2324'].dropna()
        if len(grad_data) > 0:
            print(f"Schools with graduation rate: {len(grad_data)}")
            print(f"Average graduation rate: {grad_data.mean():.1f}%")
    
    if 'student_attendance_2324' in df.columns:
        attend_data = df['student_attendance_2324'].dropna()
        if len(attend_data) > 0:
            print(f"Schools with attendance data: {len(attend_data)}")
            print(f"Average student attendance: {attend_data.mean():.1f}%")
    
    print(f"\nOutput saved to: {output_file}")


if __name__ == '__main__':
    main()

