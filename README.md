# Philadelphia School District Report Scraper

This project scrapes school performance data from the Philadelphia School District's SPOTlight & SPREE reports.

## Overview

The script:
1. Scrapes a Google Sheets spreadsheet containing a list of ~295 Philadelphia schools
2. Downloads each school's PDF report from the Philadelphia School District CDN
3. Parses the PDFs to extract performance metrics
4. Saves all data to a single CSV file for analysis

## Data Extracted

### School Information
- School ID, Name, Principal
- Network, Sector, District
- Grades Served, Admission Category
- Enrollment

### Demographics
- Racial/ethnic breakdown (%)
- Students with IEPs (%)
- English Learners (%)
- Economically Disadvantaged (%)

### Performance Metrics
- **Attendance**: Student and Teacher attendance rates
- **Conditions for Success**: Dropout counts, Graduation rates
- **Keystone Exams** (High Schools): Algebra 1, Biology, Literature proficiency
- **PSSA** (Elementary/Middle): Reading, Math, Science proficiency
- **CTE/NOCTI**: Career and Technical Education outcomes

## Installation

```bash
# Create a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python scrape_school_reports.py
```

The script will:
1. Fetch the list of schools from the Google Sheet
2. Download and parse each school's PDF report
3. Output progress to the console
4. Save results to `philadelphia_school_reports_2324.csv`

**Note**: The full scrape takes approximately 10-15 minutes due to downloading ~295 PDFs.

## Output

The output CSV file `philadelphia_school_reports_2324.csv` contains one row per school with columns for all extracted metrics.

## Data Source

- **Spreadsheet**: [ERA Reports & Data - 23-24 School-Level SPOTlight & SPREE Reports](https://docs.google.com/spreadsheets/d/e/2PACX-1vS70o-bkR4qO-SJEZDECEMxsoUATIYOAAjduDS1qMVImXTJoTU91MMxIcddA8PkNmHhqAcFhi0zLo65/pubhtml?gid=1872275673&single=true)
- **PDF Reports**: Philadelphia School District CDN (`cdn.philasd.org`)

## License

This project is for educational and research purposes.
