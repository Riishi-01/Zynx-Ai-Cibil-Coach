"""FastAPI web server with streaming LLM response."""

import os
import json
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.data_fetch import fetch_customer_by_pan
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.prompt_builder import build_prompt
from app.llm_invoke import invoke_llm
from app.schemas import InvalidPAN, CustomerNotFound, LLMError

# Initialize FastAPI app
app = FastAPI(
    title="CIBIL Credit Coach",
    description="AI-powered credit analysis engine for Indian credit profiles",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store session data (in-memory for now; use Redis in production)
sessions: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Serve the main HTML page."""
    html_content = get_html_page()
    return html_content


@app.post("/api/analyze")
async def analyze_customer(request: Request):
    """Analyse a customer by PAN and stream LLM response."""
    try:
        body = await request.json()
        pan = body.get("pan", "").strip().upper()
        income_inr = int(body.get("income", 0))

        # Validation
        if not pan:
            raise HTTPException(status_code=400, detail="PAN is required")
        if income_inr <= 0:
            raise HTTPException(status_code=400, detail="Income must be > 0")

        # Fetch customer
        try:
            record = fetch_customer_by_pan(pan)
        except (InvalidPAN, CustomerNotFound) as e:
            raise HTTPException(status_code=400, detail=f"Invalid PAN: {str(e)}")

        # Process pipeline
        sanitised = sanitise_record(record)
        facts = precompute_facts(sanitised, monthly_income_inr=income_inr)
        fired = fire_labels(facts)
        sys_prompt, user_msg = build_prompt(sanitised, facts, fired)

        # Store session
        session_id = f"{pan}_{datetime.utcnow().timestamp()}"
        sessions[session_id] = {
            "pan": pan,
            "income": income_inr,
            "score": facts.score,
            "band": facts.score_band.value,
            "labels_fired": len(fired),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Stream LLM response
        async def stream_response() -> AsyncGenerator[str, None]:
            try:
                # Send initial metadata
                yield f"data: {json.dumps({'type': 'metadata', 'session_id': session_id, 'score': facts.score, 'band': facts.score_band.value, 'labels_fired': len(fired)})}\n\n"

                # Call LLM and stream tokens
                llm_output = invoke_llm(sys_prompt, user_msg)
                
                # Stream the output in chunks (larger chunks for smoother flow)
                chunk_size = 30
                for i in range(0, len(llm_output), chunk_size):
                    chunk = llm_output[i : i + chunk_size]
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                
                # Send completion (no final message, just done event)
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

            except LLMError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'LLM Error: {str(e)}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Error: {str(e)}'})}\n\n"

        return StreamingResponse(stream_response(), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions")
async def get_sessions():
    """Get all previous sessions for persistence."""
    return {"sessions": list(sessions.values())}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "CIBIL Credit Coach"}


def get_html_page() -> str:
    """Return the complete HTML page."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CIBIL Credit Coach — AI Credit Analysis</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #00d4ff;
            --primary-dark: #0099cc;
            --secondary: #ff6b9d;
            --bg-dark: #0a0e27;
            --bg-card: #141829;
            --bg-input: #1a1f3a;
            --text-primary: #e0e6ff;
            --text-secondary: #a0a6c0;
            --success: #00d084;
            --warning: #ffa500;
            --error: #ff4757;
            --border: #2a2f4a;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, var(--bg-dark) 0%, #0f1535 100%);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
        }

        /* Header */
        header {
            text-align: center;
            margin-bottom: 40px;
            padding: 30px 0;
        }

        .logo {
            font-size: 32px;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }

        .tagline {
            color: var(--text-secondary);
            font-size: 14px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        /* Main layout */
        .layout {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            align-items: start;
        }

        /* Form section */
        .form-section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 14px;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.1);
        }

        .form-group input::placeholder {
            color: var(--text-secondary);
        }

        .required {
            color: var(--error);
        }

        /* Button */
        .btn {
            width: 100%;
            padding: 14px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            border: none;
            border-radius: 8px;
            color: var(--bg-dark);
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 10px;
        }

        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 212, 255, 0.3);
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Output section */
        .output-section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 30px;
            backdrop-filter: blur(10px);
            min-height: 300px;
        }

        .output-header {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 20px;
            color: var(--text-primary);
        }

        .score-display {
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
            padding: 20px;
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(255, 107, 157, 0.1) 100%);
            border-radius: 12px;
            border: 1px solid var(--border);
        }

        .score-number {
            font-size: 48px;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .score-info {
            flex: 1;
        }

        .score-band {
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 5px;
        }

        .score-label {
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
        }

        /* Analysis output */
        .analysis-output {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 10px;
        }

        .analysis-output::-webkit-scrollbar {
            width: 6px;
        }

        .analysis-output::-webkit-scrollbar-track {
            background: var(--bg-input);
            border-radius: 3px;
        }

        .analysis-output::-webkit-scrollbar-thumb {
            background: var(--primary);
            border-radius: 3px;
        }

        .analysis-output::-webkit-scrollbar-thumb:hover {
            background: var(--primary-dark);
        }

        .analysis-text {
            line-height: 1.8;
            color: var(--text-primary);
            font-size: 15px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        /* Rich text formatting */
        .analysis-text strong {
            color: var(--primary);
            font-weight: 700;
        }

        .analysis-text em {
            color: var(--secondary);
            font-style: italic;
        }

        .analysis-text p {
            margin-bottom: 12px;
        }

        .analysis-text ol, .analysis-text ul {
            margin-left: 20px;
            margin-bottom: 12px;
        }

        .analysis-text li {
            margin-bottom: 8px;
        }

        /* Status messages */
        .status-message {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-info {
            background: rgba(0, 212, 255, 0.1);
            border: 1px solid var(--primary);
            color: var(--primary);
        }

        .status-error {
            background: rgba(255, 71, 87, 0.1);
            border: 1px solid var(--error);
            color: var(--error);
        }

        .status-success {
            background: rgba(0, 208, 132, 0.1);
            border: 1px solid var(--success);
            color: var(--success);
        }

        .spinner {
            display: inline-block;
            width: 4px;
            height: 4px;
            background: currentColor;
            border-radius: 50%;
            animation: spin 1s infinite;
        }

        @keyframes spin {
            0%, 100% { opacity: 0.3; }
            50% { opacity: 1; }
        }

        /* Sessions history */
        .sessions-section {
            grid-column: 1 / -1;
            margin-top: 30px;
        }

        .sessions-header {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 15px;
            color: var(--text-primary);
        }

        .session-item {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 10px;
            font-size: 13px;
            color: var(--text-secondary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .session-info {
            flex: 1;
        }

        .session-badge {
            display: inline-block;
            padding: 4px 8px;
            background: rgba(0, 212, 255, 0.1);
            border-radius: 4px;
            color: var(--primary);
            font-size: 11px;
            margin-left: 10px;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .layout {
                grid-template-columns: 1fr;
            }

            .logo {
                font-size: 24px;
            }

            .score-number {
                font-size: 36px;
            }
        }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-secondary);
        }

        .empty-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="logo">💳 CIBIL Coach</div>
            <div class="tagline">AI-Powered Credit Analysis Engine</div>
        </header>

        <!-- Main Layout -->
        <div class="layout">
            <!-- Form Section -->
            <div class="form-section">
                <form id="analyzeForm" autocomplete="off" onsubmit="return false;">
                    <div class="form-group">
                        <label>PAN Card <span class="required">*</span></label>
                        <input 
                            type="text" 
                            id="panInput" 
                            placeholder="e.g., ABCPS1234A" 
                            maxlength="10"
                            autocomplete="off"
                            required
                        >
                    </div>

                    <div class="form-group">
                        <label>Monthly Income (INR) <span class="required">*</span></label>
                        <input 
                            type="number" 
                            id="incomeInput" 
                            placeholder="e.g., 75000" 
                            min="1"
                            autocomplete="off"
                            required
                        >
                    </div>

                    <button type="submit" class="btn" id="submitBtn">
                        Analyse My Credit Profile
                    </button>
                </form>
            </div>

            <!-- Output Section -->
            <div class="output-section">
                <div class="output-header">Analysis Result</div>
                
                <div id="outputContent">
                    <div class="empty-state">
                        <div class="empty-icon">📊</div>
                        <div>Enter your PAN and income to get started</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Sessions History -->
        <div class="sessions-section">
            <div class="sessions-header">📋 Previous Sessions</div>
            <div id="sessionsList">
                <div class="status-message status-info">
                    <span>No previous sessions. Analyse your credit profile to get started.</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const form = document.getElementById('analyzeForm');
        const panInput = document.getElementById('panInput');
        const incomeInput = document.getElementById('incomeInput');
        const submitBtn = document.getElementById('submitBtn');
        const outputContent = document.getElementById('outputContent');
        const sessionsList = document.getElementById('sessionsList');

        // Format text as rich HTML (convert markdown-like patterns)
        function formatRichText(text) {
            // Replace **text** with <strong>text</strong>
            text = text.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            
            // Replace *text* with <em>text</em>
            text = text.replace(/\\*(.*?)\\*/g, '<em>$1</em>');
            
            // Preserve line breaks and paragraphs
            const lines = text.split('\\n');
            let formatted = '';
            let inList = false;
            let listType = null;

            for (let line of lines) {
                line = line.trim();
                
                if (!line) {
                    if (inList) {
                        formatted += listType === 'ul' ? '</ul>' : '</ol>';
                        inList = false;
                    }
                    formatted += '<p></p>';
                    continue;
                }

                // Detect ordered list
                if (/^\\d+\\./.test(line)) {
                    if (!inList || listType !== 'ol') {
                        if (inList) formatted += listType === 'ul' ? '</ul>' : '</ol>';
                        formatted += '<ol>';
                        inList = true;
                        listType = 'ol';
                    }
                    formatted += '<li>' + line.replace(/^\\d+\\.\\s*/, '') + '</li>';
                }
                // Detect unordered list
                else if (/^[-•]/.test(line)) {
                    if (!inList || listType !== 'ul') {
                        if (inList) formatted += listType === 'ul' ? '</ul>' : '</ol>';
                        formatted += '<ul>';
                        inList = true;
                        listType = 'ul';
                    }
                    formatted += '<li>' + line.replace(/^[-•]\\s*/, '') + '</li>';
                }
                // Regular paragraph
                else {
                    if (inList) {
                        formatted += listType === 'ul' ? '</ul>' : '</ol>';
                        inList = false;
                    }
                    formatted += '<p>' + line + '</p>';
                }
            }

            if (inList) {
                formatted += listType === 'ul' ? '</ul>' : '</ol>';
            }

            return formatted;
        }

        // Load sessions from localStorage
        function loadSessions() {
            const stored = localStorage.getItem('cibilCoachSessions');
            return stored ? JSON.parse(stored) : [];
        }

        function saveSessions(sessions) {
            localStorage.setItem('cibilCoachSessions', JSON.stringify(sessions));
        }

        function displaySessions() {
            const sessions = loadSessions();
            if (sessions.length === 0) {
                sessionsList.innerHTML = '<div class="status-message status-info">No previous sessions.</div>';
                return;
            }

            sessionsList.innerHTML = sessions
                .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
                .map(s => `
                    <div class="session-item">
                        <div class="session-info">
                            <strong>${s.pan}</strong>
                            <span class="session-badge">Score: ${s.score}</span>
                            <br>
                            <small>${new Date(s.timestamp).toLocaleString()}</small>
                        </div>
                    </div>
                `).join('');
        }

        // Persist form values to localStorage
        function saveFormValues() {
            localStorage.setItem('cibilCoachPan', panInput.value);
            localStorage.setItem('cibilCoachIncome', incomeInput.value);
        }

        function loadFormValues() {
            const savedPan = localStorage.getItem('cibilCoachPan');
            const savedIncome = localStorage.getItem('cibilCoachIncome');
            
            if (savedPan) panInput.value = savedPan;
            if (savedIncome) incomeInput.value = savedIncome;
        }

        // Form submission - COMPLETELY PREVENT PAGE RELOAD
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('Form submitted - preventDefault and stopPropagation called');
            // IMPORTANT: Do NOT clear or reset the form - fields must persist!

            const pan = panInput.value.trim().toUpperCase();
            const income = parseInt(incomeInput.value);

            // Normalise PAN in place (income is left untouched so it can't be blanked)
            panInput.value = pan;
            saveFormValues();

            // Validation
            if (!pan || !/^[A-Z]{5}\\d{4}[A-Z]$/.test(pan)) {
                showError('Invalid PAN format. Expected: AAAAA9999A');
                return;
            }

            if (!Number.isFinite(income) || income <= 0) {
                showError('Income must be greater than 0');
                return;
            }

            // Disable form
            submitBtn.disabled = true;
            submitBtn.textContent = 'Analysing...';

            try {
                // Call API
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pan, income }),
                });

                if (!response.ok) {
                    const error = await response.json();
                    showError(error.detail || 'Analysis failed');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Analyse My Credit Profile';
                    return;
                }

                // Stream response
                await handleStream(response, pan, income);

            } catch (err) {
                showError(`Error: ${err.message}`);
                submitBtn.disabled = false;
                submitBtn.textContent = 'Analyse My Credit Profile';
            }
            
            // Return false to prevent any default form behavior
            return false;
        });

        async function handleStream(response, pan, income) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let analysisText = '';
            let sessionId = '';
            let score = 0;
            let band = '';

            // PRESERVE FORM VALUES - DO NOT LET THEM GET CLEARED
            panInput.value = pan;
            incomeInput.value = income;

            outputContent.innerHTML = '<div class="status-message status-info"><span class="spinner"></span> Processing your profile...</div>';

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));

                                if (data.type === 'metadata') {
                                    sessionId = data.session_id;
                                    score = data.score;
                                    band = data.band;
                                    
                                    // PRESERVE FORM VALUES
                                    panInput.value = pan;
                                    incomeInput.value = income;
                                    
                                    outputContent.innerHTML = `
                                        <div class="score-display">
                                            <div class="score-number">${score}</div>
                                            <div class="score-info">
                                                <div class="score-band">CIBIL Score Band</div>
                                                <div class="score-label">${band}</div>
                                            </div>
                                        </div>
                                        <div class="analysis-output">
                                            <div class="analysis-text" id="analysisText"></div>
                                        </div>
                                    `;
                                }

                                if (data.type === 'token') {
                                    analysisText += data.content;
                                    // Format as rich text instead of markdown
                                    document.getElementById('analysisText').innerHTML = formatRichText(analysisText);
                                    // Auto-scroll to bottom
                                    const output = document.querySelector('.analysis-output');
                                    output.scrollTop = output.scrollHeight;
                                    
                                    // PRESERVE FORM VALUES DURING STREAMING
                                    panInput.value = pan;
                                    incomeInput.value = income;
                                }

                                if (data.type === 'done') {
                                    // Save session
                                    const sessions = loadSessions();
                                    sessions.push({
                                        pan,
                                        income,
                                        score,
                                        band,
                                        timestamp: new Date().toISOString(),
                                        analysis: analysisText,
                                    });
                                    saveSessions(sessions);
                                    displaySessions();

                                    // FINAL PRESERVATION OF FORM VALUES
                                    panInput.value = pan;
                                    incomeInput.value = income;
                                    saveFormValues();

                                    submitBtn.disabled = false;
                                    submitBtn.textContent = 'Analyse My Credit Profile';
                                }

                                if (data.type === 'error') {
                                    showError(data.message);
                                    
                                    // PRESERVE FORM ON ERROR
                                    panInput.value = pan;
                                    incomeInput.value = income;
                                    
                                    submitBtn.disabled = false;
                                    submitBtn.textContent = 'Analyse My Credit Profile';
                                }

                            } catch (e) {
                                console.error('Parse error:', e);
                            }
                        }
                    }
                }
            } catch (err) {
                showError(`Stream error: ${err.message}`);
                
                // PRESERVE FORM ON ANY ERROR
                panInput.value = pan;
                incomeInput.value = income;
                
                submitBtn.disabled = false;
                submitBtn.textContent = 'Analyse My Credit Profile';
            }
        }

        function showError(message) {
            outputContent.innerHTML = `
                <div class="status-message status-error">
                    ${message}
                </div>
                <div class="empty-state">
                    <div>❌ Analysis Failed</div>
                </div>
            `;
        }

        // Load sessions on page load
        displaySessions();
        
        // Load form values on page load
        loadFormValues();

        // Auto-format PAN input
        panInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.toUpperCase();
            saveFormValues();
        });

        // Format income input (allow only numbers)
        incomeInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
            saveFormValues();
        });

        // Enter key triggers a real (cancelable) submit event
        panInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                form.requestSubmit();
            }
        });

        incomeInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                form.requestSubmit();
            }
        });
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
