from pathlib import Path
import sys
import json
import time
import os
import subprocess
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from pwdlib import PasswordHash

from database import Base, engine, get_db
from models import (
    User,
    Portfolio,
    PortfolioHistory,
    PortfolioSnapshot,
    HoldingSnapshot,
)


# ============================================================
# AUTHENTICATION
# ============================================================

password_hash = PasswordHash.recommended()

JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "change-this-secret"
)

JWT_ALGORITHM = "HS256"

security = HTTPBearer()

# ============================================================
# PROJECT PATHS
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


sys.path.insert(0, str(BASE_DIR))


# ============================================================
# IMPORT CUSTOMER CHAT
# ============================================================

try:
    from customer_chat import (
    load_data,
    answer_customer_question,
    generate_narrative,
)
except ImportError:
    load_data = None
    answer_customer_question = None
    generate_narrative = None


# ============================================================
# PORTFOLIO FILES
# ============================================================

ANALYSIS_SCRIPT = BASE_DIR / "portfolio_analyzer_v5.py"

PORTFOLIO_FILE = BASE_DIR / "portfolio.json"
ANALYSIS_OUTPUT = BASE_DIR / "portfolio_analysis.json"
EVIDENCE_OUTPUT = BASE_DIR / "portfolio_evidence.json"
NARRATIVE_OUTPUT = BASE_DIR / "portfolio_narrative.json"


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="AI Portfolio API",
    description="Backend API for the AI Portfolio Assistant",
    version="1.0.0",
)

# ============================================================
# DATABASE INITIALIZATION
# ============================================================

Base.metadata.create_all(bind=engine)


# ============================================================
# CORS
# ============================================================


FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REQUEST MODELS
# ============================================================

class ChatRequest(BaseModel):
    question: str

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str

class SavePortfolioRequest(BaseModel):
    name: str
    portfolio_data: dict


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json_file(path: Path):
    """
    Safely load a JSON file.

    Raises 404 if the file does not exist.
    """

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {path.name}"
        )

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=f"{path.name} contains invalid JSON."
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read {path.name}: {error}"
        )
def compare_portfolios(previous_portfolio, current_portfolio):
    """
    Compare two portfolio snapshots and calculate
    the change in total portfolio value and each holding.
    """

    previous_data = previous_portfolio["portfolio"]
    current_data = current_portfolio["portfolio"]

    # --------------------------------------------------------
    # PORTFOLIO-LEVEL COMPARISON
    # --------------------------------------------------------

    previous_value = previous_data["summary"]["total_current_value"]
    current_value = current_data["summary"]["total_current_value"]

    total_change = current_value - previous_value

    if previous_value != 0:
        total_change_percent = (
            total_change / previous_value
        ) * 100
    else:
        total_change_percent = 0

    # --------------------------------------------------------
    # CREATE HOLDING LOOKUPS
    # --------------------------------------------------------

    previous_holdings = {
        holding["ticker"]: holding
        for holding in previous_data.get("holdings", [])
    }

    current_holdings = {
        holding["ticker"]: holding
        for holding in current_data.get("holdings", [])
    }

    # --------------------------------------------------------
    # COMPARE HOLDINGS
    # --------------------------------------------------------

    holding_changes = []

    all_tickers = set(previous_holdings) | set(current_holdings)

    for ticker in all_tickers:

        previous_holding = previous_holdings.get(ticker)
        current_holding = current_holdings.get(ticker)

        # ----------------------------------------------------
        # HOLDING EXISTS IN BOTH SNAPSHOTS
        # ----------------------------------------------------

        if previous_holding and current_holding:

            previous_holding_value = previous_holding.get(
                "current_value", 0
            )

            current_holding_value = current_holding.get(
                "current_value", 0
            )

            change = (
                current_holding_value
                - previous_holding_value
            )

            if previous_holding_value != 0:
                change_percent = (
                    change / previous_holding_value
                ) * 100
            else:
                change_percent = None

            holding_changes.append({
                "ticker": ticker,
                "company_name": current_holding.get(
                    "company_name"
                ),
                "previous_value": round(
                    previous_holding_value, 2
                ),
                "current_value": round(
                    current_holding_value, 2
                ),
                "change": round(
                    change, 2
                ),
                "change_percent": (
                    round(change_percent, 2)
                    if change_percent is not None
                    else None
                ),
                "status": "existing"
            })

        # ----------------------------------------------------
        # NEW HOLDING
        # ----------------------------------------------------

        elif current_holding:

            current_holding_value = current_holding.get(
                "current_value", 0
            )

            holding_changes.append({
                "ticker": ticker,
                "company_name": current_holding.get(
                    "company_name"
                ),
                "previous_value": 0,
                "current_value": round(
                    current_holding_value, 2
                ),
                "change": round(
                    current_holding_value, 2
                ),
                "change_percent": None,
                "status": "added"
            })

        # ----------------------------------------------------
        # REMOVED HOLDING
        # ----------------------------------------------------

        elif previous_holding:

            previous_holding_value = previous_holding.get(
                "current_value", 0
            )

            holding_changes.append({
                "ticker": ticker,
                "company_name": previous_holding.get(
                    "company_name"
                ),
                "previous_value": round(
                    previous_holding_value, 2
                ),
                "current_value": 0,
                "change": round(
                    -previous_holding_value, 2
                ),
                "change_percent": -100,
                "status": "removed"
            })

    # --------------------------------------------------------
    # SORT BIGGEST MOVERS
    # --------------------------------------------------------

    holding_changes.sort(
        key=lambda holding: abs(
            holding["change"]
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # POSITIVE / NEGATIVE CONTRIBUTORS
    # --------------------------------------------------------

    positive_contributors = [
        holding
        for holding in holding_changes
        if holding["change"] > 0
    ]

    negative_contributors = [
        holding
        for holding in holding_changes
        if holding["change"] < 0
    ]

    # --------------------------------------------------------
    # RETURN COMPARISON RESULT
    # --------------------------------------------------------

    return {
        "previous_date": previous_data.get(
            "last_updated"
        ),

        "current_date": current_data.get(
            "last_updated"
        ),

        "previous_portfolio_value": round(
            previous_value, 2
        ),

        "current_portfolio_value": round(
            current_value, 2
        ),

        "total_change": round(
            total_change, 2
        ),

        "total_change_percent": round(
            total_change_percent, 2
        ),

        "holdings": holding_changes,

        "positive_contributors":
            positive_contributors,

        "negative_contributors":
            negative_contributors
    }

def delete_old_results():
    """
    Remove stale analysis/evidence/narrative files before a new
    upload, so a failed analyzer run can't leave old results behind
    that appear to belong to the newly uploaded portfolio.

    NOTE: portfolio.json is intentionally NOT deleted here. It gets
    overwritten in "w" mode a moment later regardless of whether this
    function runs, so pre-deleting it serves no purpose -- and on
    Windows, deleting files inside a OneDrive-synced folder can hit
    a transient file lock (WinError 32) while OneDrive is mid-sync,
    which previously crashed the whole upload.
    """

    files_to_remove = [
        ANALYSIS_OUTPUT,
        EVIDENCE_OUTPUT,
        NARRATIVE_OUTPUT,
    ]

    for path in files_to_remove:

        if not path.exists():
            continue

        # Retry briefly in case OneDrive (or an antivirus scan, or
        # Explorer's preview pane) has the file locked for a moment.
        # This is a transient condition on Windows/OneDrive folders,
        # not a real error -- it usually clears within milliseconds.
        last_error = None

        for attempt in range(5):
            try:
                path.unlink()
                print(f"Removed old file: {path.name}")
                last_error = None
                break

            except PermissionError as error:
                last_error = error
                time.sleep(0.3)

        if last_error is not None:
            print(
                f"WARNING: Could not remove old file {path.name} "
                f"(still locked after retries): {last_error}"
            )

def validate_portfolio_data(portfolio_data):
    """
    Validate the uploaded portfolio before saving it.
    """

    # --------------------------------------------------------
    # ROOT OBJECT
    # --------------------------------------------------------

    if not isinstance(portfolio_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Portfolio JSON must be an object."
        )

    # --------------------------------------------------------
    # PORTFOLIO OBJECT
    # --------------------------------------------------------

    if "portfolio" not in portfolio_data:
        raise HTTPException(
            status_code=400,
            detail="JSON must contain a 'portfolio' object."
        )

    portfolio = portfolio_data["portfolio"]

    if not isinstance(portfolio, dict):
        raise HTTPException(
            status_code=400,
            detail="'portfolio' must be an object."
        )

    # --------------------------------------------------------
    # HOLDINGS
    # --------------------------------------------------------

    if "holdings" not in portfolio:
        raise HTTPException(
            status_code=400,
            detail="Portfolio must contain 'holdings'."
        )

    holdings = portfolio["holdings"]

    if not isinstance(holdings, list):
        raise HTTPException(
            status_code=400,
            detail="'holdings' must be a list."
        )

    if not holdings:
        raise HTTPException(
            status_code=400,
            detail="Portfolio must contain at least one holding."
        )

    # --------------------------------------------------------
    # REQUIRED HOLDING FIELDS
    # --------------------------------------------------------

    required_fields = [
        "ticker",
        "company_name",
        "shares_owned",
    ]

    for index, holding in enumerate(holdings):

        if not isinstance(holding, dict):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Holding #{index + 1} must be an object."
                )
            )

        missing = [
            field
            for field in required_fields
            if field not in holding
        ]

        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Holding #{index + 1} is missing fields: "
                    f"{', '.join(missing)}"
                )
            )

        # ----------------------------------------------------
        # TICKER
        # ----------------------------------------------------

        ticker = str(
            holding["ticker"]
        ).strip()

        if not ticker:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Holding #{index + 1} "
                    "has an empty ticker."
                )
            )

        # ----------------------------------------------------
        # SHARES
        # ----------------------------------------------------

        try:
            shares = float(
                holding["shares_owned"]
            )

        except (TypeError, ValueError):

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Holding {ticker} has an invalid "
                    "'shares_owned' value."
                )
            )

        if shares < 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Holding {ticker} cannot have negative "
                    "shares_owned."
                )
            )

    return portfolio_data


def run_portfolio_analysis():
    """
    Run portfolio_analyzer_v6.py using the uploaded portfolio.json.

    The analyzer must create:

        portfolio_analysis.json
        portfolio_evidence.json
    """

    # --------------------------------------------------------
    # CHECK ANALYZER
    # --------------------------------------------------------

    if not ANALYSIS_SCRIPT.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                "Analyzer script not found:\n"
                f"{ANALYSIS_SCRIPT}\n\n"
                "Make sure portfolio_analyzer_v6.py "
                "is located in the project root."
            )
        )

    # --------------------------------------------------------
    # CHECK PORTFOLIO
    # --------------------------------------------------------

    if not PORTFOLIO_FILE.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                "portfolio.json does not exist. "
                "Upload a portfolio first."
            )
        )

    # --------------------------------------------------------
    # COMMAND
    # --------------------------------------------------------

    command = [
        sys.executable,
        str(ANALYSIS_SCRIPT),

        "--portfolio-file",
        str(PORTFOLIO_FILE),

        "--analysis-output",
        str(ANALYSIS_OUTPUT),

        "--evidence-output",
        str(EVIDENCE_OUTPUT),
    ]

    print("\n" + "=" * 60)
    print("RUNNING PORTFOLIO ANALYZER")
    print("=" * 60)

    print("Analyzer:")
    print(ANALYSIS_SCRIPT)

    print("Portfolio:")
    print(PORTFOLIO_FILE)

    print("Analysis output:")
    print(ANALYSIS_OUTPUT)

    print("Evidence output:")
    print(EVIDENCE_OUTPUT)

    # --------------------------------------------------------
    # RUN ANALYZER
    # --------------------------------------------------------

    try:

        result = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
        )

    except subprocess.TimeoutExpired:

        raise HTTPException(
            status_code=504,
            detail=(
                "Portfolio analysis timed out "
                "after 120 seconds."
            )
        )

    except Exception as error:

        print("Analyzer execution error:")
        print(error)

        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not run portfolio analyzer: "
                f"{error}"
            )
        )

    # --------------------------------------------------------
    # DEBUG OUTPUT
    # --------------------------------------------------------

    if result.stdout:

        print("\nANALYZER STDOUT:")
        print(result.stdout)

    if result.stderr:

        print("\nANALYZER STDERR:")
        print(result.stderr)

    # --------------------------------------------------------
    # CHECK RETURN CODE
    # --------------------------------------------------------

    if result.returncode != 0:

        stderr_lines = [
            line.strip()
            for line in result.stderr.splitlines()
            if line.strip()
        ]

        if stderr_lines:
            error_detail = stderr_lines[-1]
        else:
            error_detail = (
                "Unknown analyzer error."
            )

        raise HTTPException(
            status_code=500,
            detail=(
                "Portfolio analysis failed: "
                f"{error_detail}"
            )
        )

    # --------------------------------------------------------
    # CHECK OUTPUT FILES
    # --------------------------------------------------------

    if not ANALYSIS_OUTPUT.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                "Analyzer completed successfully, "
                "but portfolio_analysis.json "
                "was not created."
            )
        )

    if not EVIDENCE_OUTPUT.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                "Analyzer completed successfully, "
                "but portfolio_evidence.json "
                "was not created."
            )
        )

    print("\nPortfolio analysis completed successfully.")

    return result

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token."
            )

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token."
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found."
        )

    return user

@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username
    }

# Health check endpoint
@app.get("/healthz")
def healthz():
    return {"status": "ok"}
# ============================================================
# PORTFOLIO
# ============================================================

@app.get("/portfolio")
def get_portfolio():
    """
    Return the currently uploaded portfolio.

    If the user has not uploaded a portfolio,
    this returns 404.

    IMPORTANT:
    This endpoint never creates portfolio data.
    """

    return load_json_file(
        PORTFOLIO_FILE
    )


# ============================================================
# ANALYSIS
# ============================================================

@app.get("/analysis")
def get_analysis():
    """
    Return the analysis generated from the
    currently uploaded portfolio.
    """

    return load_json_file(
        ANALYSIS_OUTPUT
    )


# ============================================================
# EVIDENCE
# ============================================================

@app.get("/evidence")
def get_evidence():
    """
    Return evidence generated from the
    currently uploaded portfolio.
    """

    return load_json_file(
        EVIDENCE_OUTPUT
    )


# ============================================================
# NARRATIVE
# ============================================================

@app.get("/narrative")
def get_narrative():
    """
    Return the generated narrative.

    If no narrative exists, return a harmless
    default response.
    """

    if not NARRATIVE_OUTPUT.exists():

        return {
            "narrative": {
                "overall_assessment":
                    "No summary generated yet."
            }
        }

    return load_json_file(
        NARRATIVE_OUTPUT
    )

# ============================================================
# REGISTER
# ============================================================

@app.post("/register")
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    username = request.username.strip()

    if not username:
        raise HTTPException(
            status_code=400,
            detail="Username cannot be empty."
        )

    if len(request.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters."
        )

    existing_user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already exists."
        )

    hashed_password = password_hash.hash(
        request.password
    )

    user = User(
        username=username,
        password_hash=hashed_password
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "User registered successfully.",
        "user_id": user.id,
        "username": user.username
    }

# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    username = request.username.strip()

    user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password."
        )

    if not password_hash.verify(
        request.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password."
        )

    token = jwt.encode(
        {
            "user_id": user.id,
            "username": user.username
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    return {
        "message": "Login successful.",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username
        }
    }


@app.get("/portfolios")
def get_saved_portfolios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    portfolios = (
        db.query(Portfolio)
        .filter(Portfolio.user_id == current_user.id)
        .order_by(
            Portfolio.updated_at.desc(),
            Portfolio.created_at.desc()
        )
        .all()
    )

    return {
        "portfolios": [
            {
                "id": portfolio.id,
                "name": portfolio.name,
                "created_at": portfolio.created_at,
                "updated_at": portfolio.updated_at
            }
            for portfolio in portfolios
        ]
    }


@app.post("/portfolios/save")
def save_portfolio(
    request: SavePortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    name = request.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Portfolio name cannot be empty."
        )

    portfolio = Portfolio(
        user_id=current_user.id,
        name=name,
        portfolio_data=json.dumps(request.portfolio_data)
    )

    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    return {
        "message": "Portfolio saved successfully.",
        "portfolio": {
            "id": portfolio.id,
            "name": portfolio.name,
            "created_at": portfolio.created_at,
            "updated_at": portfolio.updated_at
        }
    }

@app.get("/portfolios/{portfolio_id}")
def get_saved_portfolio(
    portfolio_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id
        )
        .first()
    )

    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio not found."
        )

    # Load the saved portfolio JSON
    portfolio_data = json.loads(
        portfolio.portfolio_data
    )

    try:
        delete_old_results()

        # Write the saved portfolio into portfolio.json
        with open(
            PORTFOLIO_FILE,
            "w",
            encoding="utf-8"
        ) as file_handle:

            json.dump(
                portfolio_data,
                file_handle,
                indent=4,
                ensure_ascii=False
            )

        # Run analyzer for this saved portfolio
        run_portfolio_analysis()

        # Load newly generated results
        analysis = load_json_file(
            ANALYSIS_OUTPUT
        )

        evidence = load_json_file(
            EVIDENCE_OUTPUT
        )

        narrative = generate_narrative(
            evidence
        )

    except HTTPException:
        raise

    except Exception as error:
        print("Saved portfolio analysis error:")
        print(error)

        raise HTTPException(
            status_code=500,
            detail=(
                "Portfolio was loaded, but its analysis "
                f"could not be generated: {error}"
            )
        )

    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "portfolio_data": portfolio_data,
        "analysis": analysis,
        "evidence": evidence,
        "narrative": narrative,
        "created_at": portfolio.created_at,
        "updated_at": portfolio.updated_at
    }

# ============================================================
# PORTFOLIO UPLOAD
# ============================================================

@app.post("/portfolio/upload")
async def upload_portfolio(
    file: UploadFile = File(...),
    portfolio_id: int | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a portfolio JSON file.

    If portfolio_id is provided:
    - Save the previous portfolio version to portfolio_history.
    - Update the saved portfolio with the new data.

    If portfolio_id is not provided:
    - Analyze the uploaded portfolio only.
    """

    # --------------------------------------------------------
    # CHECK FILE TYPE
    # --------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was selected."
        )

    if not file.filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a JSON portfolio file."
        )

    # --------------------------------------------------------
    # READ FILE
    # --------------------------------------------------------

    try:
        contents = await file.read()

        portfolio_data = json.loads(
            contents.decode("utf-8")
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file contains invalid JSON."
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read uploaded file: {error}"
        )

    # --------------------------------------------------------
    # VALIDATE PORTFOLIO
    # --------------------------------------------------------

    validate_portfolio_data(
        portfolio_data
    )

    # --------------------------------------------------------
    # FIND SAVED PORTFOLIO IF PROVIDED
    # --------------------------------------------------------

    saved_portfolio = None

    if portfolio_id is not None:

        saved_portfolio = (
            db.query(Portfolio)
            .filter(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == current_user.id
            )
            .first()
        )

        if saved_portfolio is None:
            raise HTTPException(
                status_code=404,
                detail="Saved portfolio not found."
            )

    # --------------------------------------------------------
    # SAVE PREVIOUS VERSION TO HISTORY
    # --------------------------------------------------------

    if saved_portfolio is not None:

        history_record = PortfolioHistory(
            portfolio_id=saved_portfolio.id,
            user_id=current_user.id,
            portfolio_data=saved_portfolio.portfolio_data
        )

        db.add(history_record)

        # Update saved portfolio
        saved_portfolio.portfolio_data = json.dumps(
            portfolio_data,
            ensure_ascii=False
        )

        db.commit()
        db.refresh(saved_portfolio)

    # --------------------------------------------------------
    # WRITE CURRENT PORTFOLIO FILE
    # --------------------------------------------------------

    try:

        delete_old_results()

        with open(
            PORTFOLIO_FILE,
            "w",
            encoding="utf-8"
        ) as file_handle:

            json.dump(
                portfolio_data,
                file_handle,
                indent=4,
                ensure_ascii=False
            )

        # ----------------------------------------------------
        # RUN ANALYSIS
        # ----------------------------------------------------

        run_portfolio_analysis()

        analysis = load_json_file(
            ANALYSIS_OUTPUT
        )

        evidence = load_json_file(
            EVIDENCE_OUTPUT
        )

        narrative = generate_narrative(
            evidence
        )

    except HTTPException:
        raise

    except Exception as error:

        print("Portfolio upload error:")
        print(error)

        raise HTTPException(
            status_code=500,
            detail=(
                "Portfolio was uploaded, but analysis "
                f"could not be generated: {error}"
            )
        )

    # --------------------------------------------------------
    # RETURN RESULTS
    # --------------------------------------------------------

    return {
        "message": "Portfolio uploaded successfully.",
        "portfolio": portfolio_data,
        "analysis": analysis,
        "evidence": evidence,
        "narrative": narrative
    }

# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(request: ChatRequest):
    """
    Answer a question about the currently uploaded portfolio.

    Chat is only available after a portfolio has been uploaded.
    """

    # --------------------------------------------------------
    # CHECK CHAT MODULE
    # --------------------------------------------------------

    if answer_customer_question is None:

        raise HTTPException(
            status_code=500,
            detail=(
                "customer_chat.py could not be imported."
            )
        )

    # --------------------------------------------------------
    # CHECK PORTFOLIO
    # --------------------------------------------------------

    if not PORTFOLIO_FILE.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "No portfolio has been uploaded yet. "
                "Upload a portfolio before asking questions."
            )
        )

    # --------------------------------------------------------
    # CHECK QUESTION
    # --------------------------------------------------------

    if not request.question.strip():

        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    # --------------------------------------------------------
    # ANSWER QUESTION
    # --------------------------------------------------------

    try:

        portfolio_data = load_json_file(
            PORTFOLIO_FILE
        )

        evidence = load_json_file(EVIDENCE_OUTPUT)
        if NARRATIVE_OUTPUT.exists():
            narrative = load_json_file(NARRATIVE_OUTPUT)
        else:
            narrative = generate_narrative(evidence)

        answer = answer_customer_question(
            request.question,
            evidence,
            narrative
        )

        return {
            "question":
                request.question,

            "answer":
                answer,
        }

    except HTTPException:

        raise

    except Exception as error:

        print("Chat error:")
        print(error)

        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not answer question: "
                f"{error}"
            )
        )
# ============================================================
# REACT FRONTEND
# ============================================================

if FRONTEND_DIST.exists():

    @app.get("/")
    async def serve_frontend():
        return FileResponse(
            FRONTEND_DIST / "index.html"
        )

    app.mount(
        "/assets",
        StaticFiles(
            directory=FRONTEND_DIST / "assets"
        ),
        name="assets"
    )

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):

        requested_file = FRONTEND_DIST / full_path

        if requested_file.exists() and requested_file.is_file():
            return FileResponse(requested_file)

        return FileResponse(
            FRONTEND_DIST / "index.html"
        )