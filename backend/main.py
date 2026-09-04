from os import error
from pathlib import Path
import sys
import json
import time
import os
import subprocess
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import Depends
import jwt
from pwdlib import PasswordHash

from database import Base, engine, get_db
from models import User


# ============================================================
# AUTHENTICATION
# ============================================================

password_hash = PasswordHash.recommended()

JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "change-this-secret"
)

JWT_ALGORITHM = "HS256"

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
            # Don't hard-fail the whole upload over a stale file that
            # couldn't be removed -- log it and continue. The analyzer
            # will overwrite this file in "w" mode anyway if it
            # succeeds; the only downside of skipping this is that a
            # *failed* analyzer run could leave a stale file behind,
            # which is a much smaller problem than blocking every
            # upload on a transient OneDrive lock.
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

# ============================================================
# PORTFOLIO UPLOAD
# ============================================================

@app.post("/portfolio/upload")
async def upload_portfolio(
    file: UploadFile = File(...)
):
    """
    Upload and process a portfolio.

    Workflow:

        1. Receive JSON file
        2. Validate filename
        3. Read file
        4. Parse JSON
        5. Validate portfolio structure
        6. Remove old portfolio/results
        7. Save new portfolio
        8. Run analyzer
        9. Load generated results
        10. Return everything to React
    """

    print("\n" + "=" * 60)
    print("NEW PORTFOLIO UPLOAD")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. CHECK FILE
    # --------------------------------------------------------

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="No file was provided."
        )

    print("Uploaded filename:")
    print(file.filename)

    # --------------------------------------------------------
    # 2. CHECK EXTENSION
    # --------------------------------------------------------

    if not file.filename.lower().endswith(".json"):

        raise HTTPException(
            status_code=400,
            detail="Please upload a JSON file."
        )

    # --------------------------------------------------------
    # 3. READ FILE
    # --------------------------------------------------------

    try:

        contents = await file.read()

    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not read uploaded file: "
                f"{error}"
            )
        )

    if not contents:

        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty."
        )

    print(
        f"Uploaded file size: {len(contents)} bytes"
    )

    # --------------------------------------------------------
    # 4. PARSE JSON
    # --------------------------------------------------------

    try:

        portfolio_data = json.loads(
            contents.decode("utf-8")
        )

    except UnicodeDecodeError:

        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file is not valid "
                "UTF-8 JSON."
            )
        )

    except json.JSONDecodeError as error:

        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file contains invalid "
                f"JSON: {error}"
            )
        )

    # --------------------------------------------------------
    # 5. VALIDATE
    # --------------------------------------------------------

    portfolio_data = validate_portfolio_data(
        portfolio_data
    )

    holdings = (
        portfolio_data["portfolio"]["holdings"]
    )

    print(
        f"Validated portfolio with "
        f"{len(holdings)} holdings."
    )

    # --------------------------------------------------------
    # 6. REMOVE OLD DATA
    # --------------------------------------------------------

    print("\nRemoving previous portfolio data...")

    delete_old_results()

    # --------------------------------------------------------
    # 7. SAVE NEW PORTFOLIO
    # --------------------------------------------------------

    try:

        with open(
            PORTFOLIO_FILE,
            "w",
            encoding="utf-8"
        ) as file_handle:

            json.dump(
                portfolio_data,
                file_handle,
                indent=4,
                ensure_ascii=False,
            )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not save portfolio.json: "
                f"{error}"
            )
        )

    print("\nNew portfolio saved:")
    print(PORTFOLIO_FILE)

    # --------------------------------------------------------
    # 8. RUN ANALYZER
    # --------------------------------------------------------

    run_portfolio_analysis()
    # --------------------------------------------------------
    # 9. LOAD GENERATED RESULTS + GENERATE NARRATIVE
    # --------------------------------------------------------

    try:
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
        print("Narrative generation error:")
        print(error)

        raise HTTPException(
            status_code=500,
            detail=(
                "Portfolio analysis completed, but "
                f"AI narrative generation failed: {error}"
            )
        )

    # --------------------------------------------------------
    # 10. RETURN PROCESSED DATA
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("PORTFOLIO PROCESSING COMPLETE")
    print("=" * 60)

    return {
        "message":
            "Portfolio uploaded and analyzed successfully.",

        "filename":
            file.filename,

        "holdings":
            len(holdings),

        "portfolio":
            portfolio_data,

        "analysis":
            analysis,

        "evidence":
            evidence,

        "narrative":
            narrative,
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