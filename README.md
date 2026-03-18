# Philadelphia School Data Analysis

This project contains tools for scraping Philadelphia School District performance data and combining it with Barnes Foundation school visit data for analysis and mapping.

## Project Components

### 1. School Report Scraper (`scrape_school_reports.py`)

Scrapes school performance data from the Philadelphia School District's SPOTlight & SPREE reports.

**What it does:**
1. Scrapes a Google Sheets spreadsheet containing a list of ~295 Philadelphia schools
2. Downloads each school's PDF report from the Philadelphia School District CDN
3. Parses the PDFs to extract performance metrics
4. Saves all data to `philadelphia_school_reports_2324.csv`

### 2. Barnes Data Combiner (`combine_barnes_schools.py`)

Joins Barnes Foundation school visit data with Philadelphia school performance metrics.

**What it does:**
1. Reads Barnes visitor/order data (`barnesschool.csv`)
2. Reads school performance data (`philadelphia_school_reports_2324.csv`)
3. Normalizes and fuzzy-matches school names between datasets
4. Deduplicates Barnes orders by OrderNumber + school + date
5. Performs a left join to combine all data
6. Outputs `barnes_schools_joined.csv` for mapping/analysis

## Data Extracted

### School Performance Data (from PDF reports)

| Category | Metrics |
|----------|---------|
| **School Info** | School ID, Name, Principal, Network, Sector, District, Grades Served, Admission Category, Enrollment |
| **Demographics** | Racial/ethnic breakdown (%), Students with IEPs (%), English Learners (%), Economically Disadvantaged (%) |
| **Attendance** | Student attendance rate, Teacher attendance rate, % attending 95%+, % attending 90%+ |
| **Outcomes** | Dropout counts, Graduation rates |
| **Keystone Exams** | Algebra 1, Biology, Literature proficiency (High Schools) |
| **PSSA** | Grade 3 Reading/Math, Grade 3-8 Reading/Math, Science proficiency (Elementary/Middle) |
| **CTE/NOCTI** | Career and Technical Education outcomes |

### Barnes Visit Data

| Field | Description |
|-------|-------------|
| OrderNumber | Unique order identifier |
| EventStartTime | Date of visit/event |
| EventName | Type of program (In-School, Online Learning, etc.) |
| TicketType | Adult, Student grade level |
| OrganizationName | School name |
| OrganizationZipCode | School ZIP code |
| Quantity | Number of tickets |
| School District | District name |
| School Type | Public, Private, Charter |

## Installation

```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Scrape School Performance Data

```bash
source venv/bin/activate
python3 scrape_school_reports.py
```

**Note**: The full scrape takes approximately 10-15 minutes due to downloading ~295 PDFs.

### Combine Barnes + School Data

```bash
source venv/bin/activate
python3 combine_barnes_schools.py
```

## Output Files

| File | Description |
|------|-------------|
| `philadelphia_school_reports_2324.csv` | School performance data (295 schools, 39 columns) |
| `barnes_schools_joined.csv` | Combined Barnes + school data (1,363 orders, 51 columns) |
| `barnes_unmatched_schools.csv` | Schools in Barnes data that couldn't be matched (for review) |

## Matching Results

The Barnes-to-school matching achieves:
- **187/408** unique school names matched (46%)
- **826/1,363** orders matched with school data (60.6%)

**Why some schools don't match:**
- Private/parochial schools (not in Philadelphia public school data)
- Schools outside Philadelphia (Conestoga, Haverford, Emmaus, etc.)
- Non-school entities (camps, community organizations)

## Data Sources

- **School List**: [ERA Reports & Data - 23-24 School-Level SPOTlight & SPREE Reports](https://docs.google.com/spreadsheets/d/e/2PACX-1vS70o-bkR4qO-SJEZDECEMxsoUATIYOAAjduDS1qMVImXTJoTU91MMxIcddA8PkNmHhqAcFhi0zLo65/pubhtml?gid=1872275673&single=true)
- **PDF Reports**: Philadelphia School District CDN (`cdn.philasd.org`)
- **Barnes Data**: Barnes Foundation visitor records

## Technical Notes

### School Name Matching

The combiner script uses a multi-strategy matching approach:
1. **Exact match** with school type preserved (High School, Elementary, etc.)
2. **Exact match** without type (for names like "Benjamin Franklin School")
3. **Fuzzy matching** using word overlap + sequence matching

Name normalization handles:
- Charter school abbreviations: "CS" → "Charter School"
- Campus naming: "- Gratz Campus" → "at Gratz"
- Common abbreviations: "El Sch" → "Elementary School", "SHS" → "High School"

### Deduplication

Barnes data is deduplicated by `(OrderNumber, school_name, EventStartTime)` to consolidate multiple ticket types per order into representative rows.

## License

This project is for educational and research purposes.
