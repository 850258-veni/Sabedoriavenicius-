# AutoReport Business

> **Real-time sales reporting automation for operations teams — from raw database to interactive dashboard in under 30 seconds.**

---

## The Business Problem

Operations teams waste **4 to 8 hours every week** manually exporting, filtering, and consolidating sales data across spreadsheets just to deliver routine reports to stakeholders.

**AutoReport Business eliminates this entirely.**

It connects directly to a live PostgreSQL database, processes sales records in real time, and serves an interactive visual dashboard — replacing multi-step Excel workflows with a single, automated pipeline.

---

## Live Demo

> Local demo available on request. Screenshots below show the system running against a live Supabase PostgreSQL instance.

---

## Key Features

| Feature | Description |
|---|---|
| Real-Time KPIs | Live total revenue and item count metrics updated on every load |
| Sales Flow Chart | Time-series line chart of daily revenue built from live transaction data |
| Multi-Tenant Auth | API key authentication isolates each company's data at query level |
| PDF Report Export | One-click generation and download of a formatted sales report |
| Secure DB Connection | Environment-variable credential injection — zero hardcoded secrets |

---

## System Architecture

```
User (API Key)
      │
      ▼
Streamlit Frontend (app.py)
      │
      ▼
psycopg2 → PostgreSQL (Supabase)
      │
      ▼
Pandas DataFrame Processing
      │
      ├── KPI Metrics (st.metric)
      ├── Time-Series Chart (st.line_chart)
      ├── Interactive Table (st.dataframe)
      └── PDF Export (fpdf → st.download_button)
```

---

## Performance & Impact

- **Reporting time reduced from 4 hours to under 30 seconds**
- Processes hundreds of sales records per query with zero manual formatting
- Eliminates human error in data consolidation and type mismatches
- Multi-tenant isolation ensures each company only sees their own data

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Data Processing | Pandas |
| Database | PostgreSQL via psycopg2 (Supabase) |
| Report Generation | FPDF |
| Configuration | Environment Variables (os.getenv) |
| Language | Python 3.11 |

---

## Running Locally

```bash
# Clone the repository
git clone https://github.com/850258-veni/Sabedoriavenicius-
cd Sabedoriavenicius-

# Install dependencies
pip install -r requirements.txt

# Set environment variable
export DATABASE_URL="your_postgresql_connection_string"

# Run the application
streamlit run app.py
```

---

## Security Notes

- All database credentials are injected via environment variables
- API key authentication isolates tenant data at SQL query level
- No credentials are stored in source code

---

## Author

Built by **Vinícius** — Python Backend Developer specialising in data automation and internal tooling for operations teams.

- Open to remote backend engineering opportunities
- Focus: Python, PostgreSQL, Pandas, Streamlit, data pipelines
