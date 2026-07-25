# CIBIL Coach — Web Interface

**Modern, dark-themed web application for real-time credit analysis with streaming LLM output.**

---

## 🎨 Features

✅ **Dark-Themed UI** — Modern gradient design with smooth animations  
✅ **Real-Time Streaming** — LLM output streams as it's generated  
✅ **Session Persistence** — All analyses saved in browser localStorage  
✅ **PAN Validation** — Format checking (AAAAA9999A) before API call  
✅ **Responsive Design** — Works on desktop, tablet, mobile  
✅ **Error Handling** — Clear error messages for invalid input  
✅ **Score Display** — CIBIL score and band highlighted prominently  
✅ **Session History** — View all previous analyses  

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd /Users/rr/DEV/CIBIL\ Coach
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set Up Database

#### Fresh Installation

```bash
# Initialize database schema (runs Alembic migrations)
alembic upgrade head

# Seed the database with 23 customers
PYTHONPATH=/Users/rr/DEV/CIBIL\ Coach python3 scripts/seed_db.py
```

#### Development (Reset Everything)

```bash
# Drop and recreate schema, then re-seed
PYTHONPATH=/Users/rr/DEV/CIBIL\ Coach python3 scripts/seed_db.py --reset
```

### 3. Start the Server

```bash
bash run_web.sh
```

Or manually:

```bash
python3 -m uvicorn app.web:app --reload --host 0.0.0.0 --port 8000
```

The app will automatically:
- Run pending migrations on first request
- Load label_kb.json into memory
- Connect to SQLite database

### 4. Open in Browser

```
http://localhost:8000
```

---

## 📱 UI/UX Features

### **Color Scheme (Dark Theme)**

- **Primary:** Cyan (#00d4ff)
- **Secondary:** Pink (#ff6b9d)
- **Background:** Deep blue (#0a0e27)
- **Card:** Dark slate (#141829)
- **Text:** Light blue (#e0e6ff)

### **Layout**

```
┌─────────────────────────────────────┐
│     💳 CIBIL Coach                   │
│  AI-Powered Credit Analysis          │
├─────────────────────────────────────┤
│ Left Side    │    Right Side         │
├──────────────┼──────────────────────┤
│ • PAN Input  │ • Analysis Result    │
│ • Income     │ • Score Display      │
│ • Button     │ • Output Stream      │
├──────────────┴──────────────────────┤
│ Previous Sessions (History)         │
└─────────────────────────────────────┘
```

### **Input Validation**

- **PAN:** Auto-uppercase, format validation (AAAAA9999A)
- **Income:** Numeric only, minimum 1
- Real-time validation feedback
- Disabled submit button during processing

### **Output Display**

1. **Score Badge** — Large, gradient-colored score with band
2. **Loading State** — Spinner during processing
3. **Streaming Text** — Real-time token-by-token output
4. **Auto-scroll** — Automatically scrolls to bottom as text streams
5. **Session Save** — Confirmation when complete

### **Session Persistence**

- All analyses stored in browser localStorage
- Timestamp for each session
- PAN, income, score, analysis text saved
- Survives page refresh
- Displayed in "Previous Sessions" section

---

## 🔌 API Endpoints

### **GET `/`**
Serves the HTML interface.

### **POST `/api/analyze`**

**Request:**
```json
{
  "pan": "ABCPS1234A",
  "income": 75000
}
```

**Response:** Server-Sent Events (streaming)
```
data: {"type": "metadata", "session_id": "...", "score": 715, "band": "Good", "labels_fired": 11}

data: {"type": "token", "content": "Based on your credit profile..."}

data: {"type": "token", "content": " your score of 715 puts you in"}

...

data: {"type": "done", "session_id": "..."}
```

**Error Response (400):**
```json
{
  "detail": "Invalid PAN: PAN format invalid: INVAL****D"
}
```

### **GET `/api/health`**

Simple health check.

**Response:**
```json
{
  "status": "healthy",
  "service": "CIBIL Credit Coach"
}
```

### **GET `/api/sessions`**

Retrieve all sessions from server (for future multi-device sync).

---

## 🎯 User Flow

```
1. User opens http://localhost:8000
   ↓
2. User enters PAN (e.g., ABCPS1234A)
   ↓
3. User enters Income (e.g., 75000)
   ↓
4. User clicks "Analyse My Credit Profile"
   ↓
5. Frontend validates:
   - PAN format: AAAAA9999A ✓
   - Income > 0 ✓
   ↓
6. Frontend calls POST /api/analyze
   ↓
7. Backend:
   - Fetches customer by PAN
   - If PAN invalid or not found → Error "Wrong PAN Number"
   - Sanitises record (masks PII)
   - Computes 74 facts
   - Fires 32 labels
   - Builds prompt
   - Calls LLM
   ↓
8. LLM streams response token-by-token
   ↓
9. Frontend displays:
   - Score + band (e.g., "715 Good")
   - Streaming analysis text
   ↓
10. When complete:
    - Save to localStorage
    - Show confirmation
    - Update "Previous Sessions"
    ↓
11. User can refresh page → Session data persists
```

---

## 💾 Database Setup

### **Architecture**

The app now uses **SQLite** with Alembic migrations for persistent storage:

```
cibil_data.json (fixture)
    ↓ [one-time seed]
    ↓
SQLite Database (cibil_coach.db)
    ├─ customers (23 records)
    ├─ scores (linked to customers)
    ├─ accounts (e.g., credit cards, loans)
    ├─ inquiries (credit inquiries)
    ├─ collections (chargeoffs, collections)
    └─ public_records (tax liens, bankruptcies)
    ↓ [queried at runtime]
    ↓
label_kb.json (static JSON, loaded in memory)
```

### **Key Points**

- ✅ **No fixture dependency at runtime** — App works with only `.db` file
- ✅ **Alembic migrations** — Schema versioning and auto-upgrade
- ✅ **Normalized schema** — 6 tables with proper foreign keys
- ✅ **Fast queries** — All customer data reconstructed from DB per request
- ✅ **Development-friendly** — `--reset` flag to start fresh

### **File Structure**

```
cibil_coach.db              ← Main database (created on first run)
alembic/                    ← Migration scripts
├── env.py                  ← Alembic environment config
├── script.py.mako          ← Migration template
└── versions/
    └── *.py                ← Auto-generated migrations

app/
├── database.py             ← SQLAlchemy engine, session factory
├── models.py               ← ORM models (CustomerModel, ScoreModel, etc.)
├── db.py                   ← Repository (queries DB, returns CustomerRecord)

scripts/
├── seed_db.py              ← Fixture → DB loader
└── e2e_db_test.py          ← End-to-end test (verify full pipeline)
```

### **Configuration**

Environment variable (optional, defaults to SQLite):

```bash
# In .env or shell
export DATABASE_URL="sqlite:///./cibil_coach.db"
# or for PostgreSQL:
# export DATABASE_URL="postgresql://user:pass@localhost/cibil_coach"
```

---

## 💾 Session Persistence

### **How It Works**

1. **LocalStorage** — Browser's client-side storage
2. **JSON Format** — Each session is a JSON object
3. **Array** — All sessions stored in an array
4. **Automatic** — Sessions saved after each analysis

### **What's Stored**

```json
{
  "pan": "ABCPS1234A",
  "income": 75000,
  "score": 715,
  "band": "Good",
  "timestamp": "2026-07-25T16:30:00.000Z",
  "analysis": "Full LLM output text..."
}
```

### **Persistence Features**

- ✅ Survives page refresh
- ✅ Survives browser restart
- ✅ Works offline (data already in browser)
- ✅ Can be cleared by user (browser settings)

---

## 🛡️ Error Handling

### **PAN Validation Errors**

```
Input: "INVALID"
Output: "Invalid PAN format. Expected: AAAAA9999A"
```

```
Input: "UNKNOWN1234Z"
Output: "Invalid PAN: No credit file for PAN UNKNOWN1234Z"
```

### **Income Validation Errors**

```
Input: 0
Output: "Income must be greater than 0"
```

```
Input: -5000
Output: "Income must be greater than 0"
```

### **LLM Errors**

```
Input: OPENAI_API_KEY not set
Output: "LLM Error: OPENAI_API_KEY not set in environment"
```

All errors display in red message boxes with clear instructions.

---

## 📊 Design Principles Applied

### **1. Visual Hierarchy**
- Logo and title at top (most visible)
- Input form on left (primary action)
- Output on right (result focus)
- Sessions below (secondary info)

### **2. Color & Contrast**
- Dark background reduces eye strain
- Cyan primary color stands out on dark bg
- White/light text has high contrast
- Status messages color-coded (green=success, red=error, blue=info)

### **3. Feedback & Responsiveness**
- Button transforms on hover
- Disabled state during processing
- Loading spinner during analysis
- Real-time text streaming (not jumpy)

### **4. Accessibility**
- Form labels clearly marked with `*` for required fields
- Error messages descriptive and actionable
- Button text changes during processing (e.g., "Analysing...")
- Tab order logical (PAN → Income → Submit)

### **5. Mobile Responsiveness**
- Single-column layout on mobile (form, then output)
- Touch-friendly button sizing (14px+ minimum)
- Readable font sizes on all devices
- Scrollable output area

---

## 🔧 Technical Stack

| Component | Tech |
|-----------|------|
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Backend | FastAPI (Python) |
| Streaming | Server-Sent Events (SSE) |
| Storage | Browser localStorage (client-side) |
| Animation | CSS keyframes |
| API | RESTful with JSON |

---

## 📝 Example Session

### **Input:**
```
PAN: ABCPS1234A
Income: ₹75,000/month
```

### **Output Display:**

```
═══════════════════════════════════════════════════════════
💳 CIBIL Coach
AI-Powered Credit Analysis Engine
═══════════════════════════════════════════════════════════

┌─────────────────────┐ ┌────────────────────────────────┐
│ PAN Card *          │ │ Analysis Result                │
│ [ABCPS1234A]        │ │                                │
│                     │ │ ┌──────────────────────────────┤
│ Monthly Income *    │ │ │ 715                  Good    │
│ [75000]             │ │ │ CIBIL Score Band             │
│                     │ │ └──────────────────────────────┤
│ [Analyse...]        │ │                                │
└─────────────────────┘ │ Based on your credit profile:  │
                        │ Your score of 715 puts you in │
                        │ the Good band. This is a solid │
                        │ score...                       │
                        │ [streaming...]                 │
                        └────────────────────────────────┘

📋 Previous Sessions
├─ ABCPS1234A — Score: 715 | 2026-07-25 16:30:00
├─ BCDRM2345B — Score: 612 | 2026-07-25 16:20:00
└─ EFGKD5678E — Score: 748 | 2026-07-25 16:10:00
```

---

## 🐛 Testing

### **Test Valid Input**
```
PAN: ABCPS1234A
Income: 75000
Expected: Score 715, Good band, 11 labels fired
```

### **Test Invalid PAN Format**
```
PAN: INVALID
Expected: "Invalid PAN format. Expected: AAAAA9999A"
```

### **Test Unknown PAN**
```
PAN: XXXXXXX1234X (formatted correctly but not in DB)
Expected: "Invalid PAN: No credit file for PAN XXXXXXX1234X"
```

### **Test Zero Income**
```
PAN: ABCPS1234A
Income: 0
Expected: "Income must be greater than 0"
```

---

## 🚀 Future Enhancements

1. **Export to PDF** — Download analysis as PDF
2. **Share Session** — Generate shareable link
3. **Multi-language** — Hindi, regional language support
4. **Dark/Light Toggle** — User preference
5. **Advanced Charts** — Visualize score trends
6. **Comparative Analysis** — Multiple profiles side-by-side
7. **Recommendation Actions** — Clickable action items
8. **Rate Limiting** — Per-IP request limits
9. **Authentication** — User accounts for cloud sync
10. **Mobile App** — Native iOS/Android

---

## 📞 Support

If you encounter issues:

1. **PAN not found?** — Ensure you're using one of the 23 seed customers (ABCPS1234A, BCDRM2345B, etc.)
2. **API not responding?** — Check that `python3 -m uvicorn app.web:app` is running
3. **No output?** — Verify OPENAI_API_KEY is set in `.env`
4. **Sessions not saving?** — Enable localStorage in browser settings

---

## 📄 License

CIBIL Coach — AI-Powered Credit Analysis Engine
Built with ❤️ for Indian credit profiles
2026-07-25 | Build: Mavis
