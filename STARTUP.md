# MetaAnalysis Cochrane Platform — Startup Guide

## Prerequisites
- Python 3.11+
- Node.js 18+
- An Anthropic API key (`sk-ant-...`)

---

## 1 · Backend Setup

```powershell
cd backend

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key in .env
# Edit backend\.env and replace "your_api_key_here" with your real key

# Start the API server
python run.py
```

The API will be available at **http://localhost:8000**  
Interactive docs: **http://localhost:8000/docs**

---

## 2 · Frontend Setup

Open a second terminal:

```powershell
cd frontend

# Install npm packages
npm install

# Start the dev server
npm run dev
```

The app will be available at **http://localhost:5173**

---

## 3 · Uploading Study Data

Prepare an Excel (.xlsx) or CSV file with these columns (exact names, case-insensitive):

| Column | Description |
|--------|-------------|
| `study_label` | e.g. "Smith 2020" |
| `authors` | Author names |
| `year` | Publication year |
| `study_design` | e.g. "RCT" |
| `events_intervention` | Events in intervention group |
| `total_intervention` | Total in intervention group |
| `events_control` | Events in control group |
| `total_control` | Total in control group |
| `mean_intervention` | Mean (continuous outcomes) |
| `sd_intervention` | SD (continuous outcomes) |
| `n_intervention` | N (continuous outcomes) |
| `mean_control` | Mean (continuous outcomes) |
| `sd_control` | SD (continuous outcomes) |
| `n_control` | N (continuous outcomes) |
| `rob_random_sequence` | `low` / `some_concerns` / `high` |
| `rob_allocation_concealment` | `low` / `some_concerns` / `high` |
| `rob_blinding_participants` | `low` / `some_concerns` / `high` |
| `rob_blinding_outcome` | `low` / `some_concerns` / `high` |
| `rob_incomplete_data` | `low` / `some_concerns` / `high` |
| `rob_selective_reporting` | `low` / `some_concerns` / `high` |
| `rob_other` | `low` / `some_concerns` / `high` |
| `rob_overall` | `low` / `some_concerns` / `high` |

---

## 4 · Workflow

1. **Create review** → fill in title + PICO + effect measure
2. **Import studies** → upload Excel/CSV on the review editor page
3. **Run analysis** → click "Run Meta-Analysis" to get forest plot, funnel plot, RoB chart
4. **Generate text** → click "Generate with AI" in each section (Abstract, Background, Methods, Results, Discussion)
5. **Export PDF** → click "Export PDF" for a Cochrane-formatted document

---

## Project Structure

```
METANALISISCORP/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app + CORS
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   ├── schemas.py        # Pydantic v2 schemas
│   │   ├── config.py         # Settings (reads .env)
│   │   ├── database.py       # SQLite engine
│   │   ├── routers/
│   │   │   ├── reviews.py    # CRUD reviews
│   │   │   ├── studies.py    # CRUD + file upload
│   │   │   ├── analysis.py   # Run meta-analysis + plots
│   │   │   ├── generate.py   # AI text generation
│   │   │   └── export.py     # PDF export
│   │   └── services/
│   │       ├── statistics.py # Fixed/random effects, OR/RR/MD/SMD
│   │       ├── plots.py      # Forest, funnel, RoB traffic light
│   │       ├── ai_generator.py # Claude claude-opus-4-8 section writer
│   │       └── file_parser.py  # Excel/CSV → Study dicts
│   ├── .env                  # API key goes here
│   ├── requirements.txt
│   └── run.py
└── frontend/
    └── src/
        ├── pages/            # Dashboard, NewReview, ReviewEditor
        ├── components/       # Layout, SectionEditor, StudiesTable, AnalysisPanel
        └── services/api.ts   # Axios API client
```
