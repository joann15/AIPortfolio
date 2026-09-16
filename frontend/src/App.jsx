import { useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from 'recharts'
import './App.css'

const API_URL = "";

const SECTOR_COLORS = [
  '#2563eb',
  '#16a34a',
  '#f59e0b',
  '#dc2626',
  '#9333ea',
  '#0891b2',
  '#ea580c',
  '#4f46e5',
  '#65a30d',
  '#db2777',
]

function App() {
  // ============================================================
  // AUTHENTICATION
  // ============================================================

  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authChecking, setAuthChecking] = useState(true)
  const [username, setUsername] = useState('')
  const [authMode, setAuthMode] = useState('login')

  const [savedPortfolios, setSavedPortfolios] = useState([])
  const [savedPortfoliosLoading, setSavedPortfoliosLoading] = useState(false)
  const [selectedSavedPortfolio, setSelectedSavedPortfolio] = useState(null)
  const [savedPortfolioDropdownOpen, setSavedPortfolioDropdownOpen] = useState(false)
  const [portfolioFiles, setPortfolioFiles] = useState([])
  
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')

  // ============================================================
  // DATA
  // ============================================================

  const [portfolio, setPortfolio] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [evidence, setEvidence] = useState(null)
  const [narrative, setNarrative] = useState(null)
  const [performance, setPerformance] = useState(null)
  const [performanceLoading, setPerformanceLoading] = useState(false)

  // ============================================================
  // CHAT
  // ============================================================

  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)

  // ============================================================
  // PAGE
  // ============================================================

  const [pageLoading, setPageLoading] = useState(false)
  const [error, setError] = useState('')

  // ============================================================
  // UPLOAD
  // ============================================================

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')

  const [savePortfolioName, setSavePortfolioName] = useState('')
  const [savingPortfolio, setSavingPortfolio] = useState(false)
  const [savePortfolioError, setSavePortfolioError] = useState('')

  // ============================================================
  // NEWS
  // ============================================================

  const newsStripArticles =
    analysis?.news_strip?.articles || []
    
    async function checkAuthentication() {
      const token = localStorage.getItem('access_token')
      
      if (!token) {
        setAuthChecking(false)
        return
      }
      
      try {
        const response = await fetch(`${API_URL}/me`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
        
        if (!response.ok) {
          localStorage.removeItem('access_token')
          setIsAuthenticated(false)
          setUsername('')
          return
        }
        const data = await response.json()
        
        setUsername(data.username)
        setIsAuthenticated(true)
      
      } catch (err) {
        console.error('Authentication check failed:', err)

        localStorage.removeItem('access_token')
        setIsAuthenticated(false)
        setUsername('')
      } finally {
        setAuthChecking(false)
      }
    }

    async function handleLogin(event) {
      event.preventDefault()

      setAuthLoading(true)
      setAuthError('')

      try {
        const response = await fetch(`${API_URL}/login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: authUsername.trim(),
            password: authPassword,
          }),
        })
        let data

        try {
          data = await response.json()
        } catch {
          throw new Error('The server returned an invalid response.')
        }
        
        if (!response.ok) {
          throw new Error(
            data.detail || 'Invalid username or password.'
          )
        }
        
        localStorage.setItem(
          'access_token',
          data.access_token
        )

        setUsername(data.user.username)
        setIsAuthenticated(true)

        setAuthUsername('')
        setAuthPassword('')
        setAuthError('')
      
      } catch (err) {
        console.error('Login error:', err)
        
        setAuthError(
          err.message || 'Unable to log in.'
        )
      } finally {
        setAuthLoading(false)
      }
    }

    async function handleRegister(event) {
      event.preventDefault()
      
      setAuthLoading(true)
      setAuthError('')
      
      try {
        const response = await fetch(`${API_URL}/register`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: authUsername.trim(),
            password: authPassword,
          }),
        })
        
        let data
        try {
          data = await response.json()
        } catch {
          throw new Error('The server returned an invalid response.')
        }
        
        if (!response.ok) {
          throw new Error(
            data.detail || 'Registration failed.'
          )
        }
      
        setAuthMode('login')
        setAuthError('Registration successful. Please log in.')
        setAuthPassword('')
      
      } catch (err) {
        console.error('Registration error:', err)
        
        setAuthError(
          err.message || 'Unable to register.'
        )
      } finally {
        setAuthLoading(false)
      }
    }

    function handleLogout() {
      localStorage.removeItem('access_token')

      setIsAuthenticated(false)
      setUsername('')
      setPortfolio(null)
      setAnalysis(null)
      setEvidence(null)
      setNarrative(null)
      setPerformance(null)
      setAnswer('')
      setQuestion('')
    }
  
  // ============================================================
  // LOAD PORTFOLIO DATA
  // ============================================================

  async function loadPortfolioData() {
    try {
      setPageLoading(true)
      setError('')

      const [
        portfolioRes,
        analysisRes,
        evidenceRes,
        narrativeRes,
      ] = await Promise.all([
        fetch(`${API_URL}/portfolio`),
        fetch(`${API_URL}/analysis`),
        fetch(`${API_URL}/evidence`),
        fetch(`${API_URL}/narrative`),
      ])

      if (!portfolioRes.ok) {
        throw new Error('Could not load portfolio data.')
      }

      if (!analysisRes.ok) {
        throw new Error(
          'Could not load portfolio analysis data.'
        )
      }

      if (!evidenceRes.ok) {
        throw new Error('Could not load evidence data.')
      }

      if (!narrativeRes.ok) {
        throw new Error('Could not load narrative data.')
      }

      const portfolioData = await portfolioRes.json()
      const analysisData = await analysisRes.json()
      const evidenceData = await evidenceRes.json()
      const narrativeData = await narrativeRes.json()

      setPortfolio(portfolioData)
      setAnalysis(analysisData)
      setEvidence(evidenceData)
      setNarrative(narrativeData)
    } catch (err) {
      console.error('Portfolio loading error:', err)

      setError(
        'Unable to load portfolio data. Make sure FastAPI is running and a portfolio has been uploaded.'
      )
    } finally {
      setPageLoading(false)
    }
  }

  const loadPortfolioFiles = async (portfolioId) => {
  const token = localStorage.getItem('access_token')

  if (!token || !portfolioId) {
    setPortfolioFiles([])
    return
  }

  try {
    const response = await fetch(
      `/portfolios/${portfolioId}/files`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    )

    const data = await response.json()

    if (!response.ok) {
      throw new Error(
        data.detail || 'Failed to load portfolio files.'
      )
    }

    console.log(
      'FILES FOR PORTFOLIO:',
      portfolioId,
      data.files
    )

    setPortfolioFiles(data.files || [])

  } catch (error) {
    console.error(
      'Error loading portfolio files:',
      error
    )

    setPortfolioFiles([])
  }
}

  const loadSavedPortfolios = async () => {
  const token = localStorage.getItem('access_token')

  if (!token) {
    return
  }

  setSavedPortfoliosLoading(true)

  try {
    const response = await fetch('/portfolios', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      throw new Error('Failed to load saved portfolios.')
    }

    const data = await response.json()

    setSavedPortfolios(data.portfolios || [])
  } catch (error) {
    console.error('Error loading saved portfolios:', error)
    setSavedPortfolios([])
  } finally {
    setSavedPortfoliosLoading(false)
  }
}

async function deletePortfolioFile(fileId) {
  const token = localStorage.getItem('access_token');

  if (!token || !selectedSavedPortfolio?.id) {
    return;
  }

  const confirmed = window.confirm(
    'Delete this file from the portfolio history?'
  );

  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(
      `${API_URL}/portfolios/${selectedSavedPortfolio.id}/files/${fileId}`,
      {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.detail || 'Could not delete portfolio file.'
      );
    }

    await loadPortfolioFiles(selectedSavedPortfolio.id);

  } catch (error) {
    console.error('Delete file error:', error);
    setError(
      error.message || 'Could not delete portfolio file.'
    );
  }
}

const loadPortfolioPerformance = async (portfolioId) => {
    const token = localStorage.getItem("access_token")

    if (!token || !portfolioId) {
        return
    }

    setPerformanceLoading(true)

    try {
        const response = await fetch(
            `/portfolios/${portfolioId}/performance`,
            {
                headers: {
                    Authorization: `Bearer ${token}`
                }
            }
        )

        const data = await response.json()

        if (!response.ok) {
            throw new Error(
                data.detail || "Failed to load portfolio performance."
            )
        }

        setPerformance(data)

    } catch (error) {
        console.error("Performance error:", error)
        setPerformance(null)

    } finally {
        setPerformanceLoading(false)
    }
}

const loadSavedPortfolio = async (portfolioId) => {
  const token = localStorage.getItem('access_token')

  if (!token) {
    return
  }

  try {
    const response = await fetch(
      `/portfolios/${portfolioId}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    )

    if (!response.ok) {
      throw new Error('Failed to load saved portfolio.')
    }

    const data = await response.json()

    console.log('Saved portfolio loaded:', data)
    console.log('ANALYSIS DATA:', data.analysis)
    console.log('EVIDENCE DATA:', data.evidence)
    console.log('NARRATIVE DATA:', data.narrative)

    setSelectedSavedPortfolio({
      id: data.id,
      name: data.name,
    })

    console.log(
      "SELECTED PORTFOLIO ID:",
      data.id
    )

    await loadPortfolioFiles(data.id)
    await loadPortfolioPerformance(data.id)

    // Load portfolio data
    setPortfolio(data.portfolio_data)

    // Load analysis data
    if (data.analysis) {
      setAnalysis(data.analysis)
    }

    // Load evidence data
    if (data.evidence) {
      setEvidence(data.evidence)
    }

    // Load AI narrative
    if (data.narrative) {
      setNarrative(data.narrative)
    }

    // Clear previous errors
    setError('')
    setUploadError('')

  } catch (error) {
    console.error(
      'Error loading saved portfolio:',
      error
    )

    setError(
      error.message ||
      'Could not load saved portfolio.'
    )
  }
}

const savePortfolio = async () => {
  const token = localStorage.getItem('access_token')

  if (!token) {
    setSavePortfolioError('Please log in again.')
    return
  }

  if (!portfolio) {
    setSavePortfolioError('Please upload a portfolio first.')
    return
  }

  if (!savePortfolioName.trim()) {
    setSavePortfolioError('Please enter a portfolio name.')
    return
  }

  setSavingPortfolio(true)
  setSavePortfolioError('')

  try {
    const response = await fetch('/portfolios/save', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        name: savePortfolioName.trim(),
        portfolio_data: portfolio,
      }),
    })

    let data

    try {
      data = await response.json()
    } catch {
      throw new Error('The server returned an invalid response.')
    }

    if (!response.ok) {
      throw new Error(
        data.detail || 'Failed to save portfolio.'
      )
    }

    setSavePortfolioName('')
    setSavePortfolioError('')
    await loadSavedPortfolios()
    
    if (data.portfolio?.id) {
      await loadSavedPortfolio(data.portfolio.id)
    }

  } catch (error) {
    console.error('Save portfolio error:', error)

    setSavePortfolioError(
      error.message || 'Failed to save portfolio.'
    )
  } finally {
    setSavingPortfolio(false)
  }
}

  useEffect(() => {
    checkAuthentication()
  }, [])
  
  useEffect(() => {
    if (isAuthenticated) {
      loadSavedPortfolios()
    }
  }, [isAuthenticated])


//Delete Portfolio

const handleDeletePortfolio = async (portfolioId) => {
  const confirmed = window.confirm(
    'Are you sure you want to delete this saved portfolio?'
  )

  if (!confirmed) {
    return
  }

  try {
    const token = localStorage.getItem('access_token')

    if (!token) {
      alert('Please log in again.')
      return
    }

    const response = await fetch(
      `${API_URL}/portfolios/${portfolioId}`,
      {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    )

    const data = await response.json()

    if (!response.ok) {
      throw new Error(
        data.detail || 'Failed to delete portfolio.'
      )
    }

    // Remove the deleted portfolio from the list
    setSavedPortfolios((currentPortfolios) =>
      currentPortfolios.filter(
        (portfolio) => portfolio.id !== portfolioId
      )
    )

    // If the deleted portfolio was selected,
    // clear the current selection
    if (selectedSavedPortfolio?.id === portfolioId) {
      setSelectedSavedPortfolio(null)
    }

  } catch (error) {
    console.error('Delete portfolio error:', error)
    alert(error.message)
  }
}
  // ============================================================
  // UPLOAD PORTFOLIO JSON
  // ============================================================

  async function uploadPortfolio(event) {
  const file = event.target.files?.[0];

  if (!file) return;

  const token = localStorage.getItem("access_token");

  if (!token) {
    setUploadError("Please log in again.");
    return;
  }

  if (!selectedSavedPortfolio?.id) {
    setUploadError(
      "Please select a saved portfolio before uploading."
    );
    return;
  }

  setUploading(true);
  setUploadError("");
  setError("");
  setAnswer("");

  try {
    if (!file.name.toLowerCase().endsWith(".json")) {
      throw new Error("Please select a valid portfolio JSON file.");
    }

    const formData = new FormData()
    formData.append('file', file)
    
    formData.append(
      'portfolio_id',
      String(selectedSavedPortfolio.id)
    )

    const response = await fetch(
      `${API_URL}/portfolio/upload`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Portfolio upload failed.");
    }

    setPortfolio(data.portfolio)
    setAnalysis(data.analysis)
    setEvidence(data.evidence)
    setNarrative(data.narrative)
    
    await loadSavedPortfolios()
    
    if (selectedSavedPortfolio?.id) {
      await loadSavedPortfolio(selectedSavedPortfolio.id)
    }
  } catch (err) {
    console.error("Upload error:", err);
    setUploadError(err.message || "Could not upload portfolio.");
  } finally {
    setUploading(false);
    event.target.value = "";
  }
}

  // ============================================================
  // FORMATTING
  // ============================================================

  function formatMoney(value) {
    if (value === undefined || value === null) {
      return '—'
    }

    const number = Number(value)

    if (Number.isNaN(number)) {
      return '—'
    }

    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(number)
  }

  function formatPercent(value) {
    if (value === undefined || value === null) {
      return '—'
    }

    const number = Number(value)

    if (Number.isNaN(number)) {
      return '—'
    }

    return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`
  }

  function formatSignedMoney(value) {
    if (value === undefined || value === null) {
      return '—'
    }

    const number = Number(value)

    if (Number.isNaN(number)) {
      return '—'
    }

    const absoluteValue = Math.abs(number)

    return `${number >= 0 ? '+' : '-'}${formatMoney(
      absoluteValue
    )}`
  }

  function formatNewsDate(value) {
    if (!value) {
      return 'Unknown date'
    }

    const date = new Date(value)

    if (Number.isNaN(date.getTime())) {
      return 'Unknown date'
    }

    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(date)
  }

  // ============================================================
  // PORTFOLIO JSON
  // ============================================================

  const portfolioData = portfolio?.portfolio || {}

  const currency = portfolioData.currency || 'USD'

  const portfolioSummary =
    portfolioData.summary || {}

  const portfolioHoldings =
    portfolioData.holdings || []

  // ============================================================
  // PORTFOLIO VALUES
  // ============================================================

  const totalOriginallyInvested =
    portfolioSummary.total_originally_invested ?? null

  const totalCurrentValue =
    portfolioSummary.total_current_value ?? null

  const totalReturnAmount =
    portfolioSummary.total_return_amount ?? null

  const totalReturnPercentage =
    portfolioSummary.total_return_percentage ?? null

  // ============================================================
  // ANALYSIS JSON
  // ============================================================

  const analysisSummary =
    analysis?.portfolio_summary || {}

  const previousPortfolioValue =
    analysisSummary.previous_portfolio_value ?? null

  const currentPortfolioValue =
    analysisSummary.current_portfolio_value ??
    totalCurrentValue

  const totalDailyImpact =
    analysisSummary.total_daily_impact ?? null

  const dailyChangePercent =
    analysisSummary.daily_change_percent ?? null

  const holdingsAnalyzed =
    analysisSummary.holdings_analyzed ?? null

  // ============================================================
  // SECTORS
  // ============================================================

  const sectorSummary =
    analysis?.sector_summary || {}

  const sectors = Object.entries(sectorSummary).map(
    ([name, data]) => ({
      name,
      holdings: data.holdings || [],
      previousValue:
        data.previous_value ?? null,
      currentValue:
        data.current_value ?? null,
      impact:
        data.daily_impact ?? null,
      returnPercent:
        data.daily_return_percent ?? null,
      forces:
        data.forces || {},
    })
  )

  const sectorChartData = sectors
    .filter(
      (sector) =>
        sector.currentValue !== null &&
        Number(sector.currentValue) > 0
    )
    .map((sector) => ({
      name: sector.name,
      value: Number(sector.currentValue),
    }))

  // ============================================================
  // CONTRIBUTORS
  // ============================================================

  const positiveContributors =
    analysis?.top_positive_contributors || []

  const negativeContributors =
    analysis?.top_negative_contributors || []

  const contributorChartData = [
    ...positiveContributors.map((stock) => ({
      ticker: stock.ticker,
      impact: Number(stock.impact) || 0,
    })),
    ...negativeContributors.map((stock) => ({
      ticker: stock.ticker,
      impact: Number(stock.impact) || 0,
    })),
  ]

  const contributorProgressMax =
    contributorChartData.length > 0
      ? Math.max(
          ...contributorChartData.map((stock) =>
            Math.abs(stock.impact)
          )
        )
      : 1

  // ============================================================
  // NARRATIVE
  // ============================================================

  const overallAssessment =
    narrative?.narrative?.overall_assessment ||
    narrative?.overall_assessment ||
    'No portfolio summary available.'

  // ============================================================
  // EVIDENCE
  // ============================================================

  const evidenceHoldings =
    evidence?.holding_evidence || []

    // ============================================================
  // AUTH CHECKING
  // ============================================================

  if (authChecking) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Checking login...</p>
      </div>
    )
  }

  // ============================================================
  // LOGIN / REGISTER
  // ============================================================

  if (!isAuthenticated) {
    return (
      <div className="auth-page">
        <div className="auth-card">

          <h1>AI Portfolio Assistant</h1>

          <p className="auth-subtitle">
            {authMode === 'login'
              ? 'Log in to access your portfolio.'
              : 'Create an account to get started.'}
          </p>

          <form
            onSubmit={
              authMode === 'login'
                ? handleLogin
                : handleRegister
            }
          >

            <label>
              Username
            </label>

            <input
              type="text"
              value={authUsername}
              onChange={(event) =>
                setAuthUsername(event.target.value)
              }
              placeholder="Enter username"
              required
              disabled={authLoading}
            />

            <label>
              Password
            </label>

            <input
              type="password"
              value={authPassword}
              onChange={(event) =>
                setAuthPassword(event.target.value)
              }
              placeholder="Enter password"
              required
              disabled={authLoading}
            />

            {authError && (
              <div className="auth-message">
                {authError}
              </div>
            )}

            <button
              type="submit"
              className="auth-button"
              disabled={authLoading}
            >
              {authLoading
                ? 'Please wait...'
                : authMode === 'login'
                  ? 'Login'
                  : 'Create Account'}
            </button>

          </form>

          <button
            type="button"
            className="auth-switch"
            onClick={() => {
              setAuthMode(
                authMode === 'login'
                  ? 'register'
                  : 'login'
              )
              setAuthError('')
            }}
          >
            {authMode === 'login'
              ? 'Need an account? Register'
              : 'Already have an account? Login'}
          </button>

        </div>
      </div>
    )
  }


  // ============================================================
  // INITIAL LOADING
  // ============================================================

  if (pageLoading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading portfolio...</p>
      </div>
    )
  }

  // ============================================================
  // APP
  // ============================================================

  return (
    <div className="app">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="header">
        <div className="header-content">

    <div className="header-top">
      <div>
        <h1>AI Portfolio Assistant</h1>

        <p>
          Portfolio overview and AI-powered analysis
        </p>
      </div>

      <div className="user-section">
        <span>
          Welcome, {username}
          </span>
          
          <button
          onClick={handleLogout}
          className="logout-button"
          >
            Logout
            </button>
      </div>
    </div>

    <div className="saved-portfolios">

  <div className="saved-portfolios-header">
    <h2>My Saved Portfolios</h2>
  </div>

  {savedPortfoliosLoading ? (
    <p>Loading saved portfolios...</p>
  ) : savedPortfolios.length === 0 ? (
    <p className="no-saved-portfolios">
      No saved portfolios yet.
    </p>
  ) : (
    <div className="portfolio-dropdown">

      <button
        type="button"
        className="portfolio-dropdown-button"
        onClick={() =>
          setSavedPortfolioDropdownOpen(
            !savedPortfolioDropdownOpen
          )
        }
      >
        <div className="portfolio-dropdown-selected">

          <strong>
            {selectedSavedPortfolio?.name || 'Select a portfolio'}
            </strong>
            
            <span>
              {selectedSavedPortfolio
              ? 'Currently selected'
              : 'Choose a saved portfolio'}
            </span>

        </div>

        <span className="portfolio-dropdown-arrow">
          {savedPortfolioDropdownOpen ? '▲' : '▼'}
        </span>
      </button>

      {savedPortfolioDropdownOpen && (
        <div className="portfolio-dropdown-menu">

          {savedPortfolios.map((savedPortfolio) => (
  <div
    key={savedPortfolio.id}
    className="portfolio-dropdown-option"
  >
    <button
      type="button"
      className="portfolio-dropdown-select"
      onClick={() => {
        loadSavedPortfolio(savedPortfolio.id);
        setSavedPortfolioDropdownOpen(false);
      }}
    >
      <strong>
        {savedPortfolio.name}
      </strong>

      <span>
        Last updated:{' '}
        {savedPortfolio.updated_at
          ? new Date(
              savedPortfolio.updated_at
            ).toLocaleDateString()
          : 'Unknown'}
      </span>
    </button>

    <button
      type="button"
      className="portfolio-delete-button"
      onClick={(event) => {
        event.stopPropagation();
        handleDeletePortfolio(savedPortfolio.id);
      }}
      title="Delete portfolio"
    >
      ×
    </button>
  </div>
))}
        </div>
      )}

    </div>
    
  )}

</div>

{/* PORTFOLIO FILES */}
{selectedSavedPortfolio && (
  <div className="portfolio-files">

    <div className="portfolio-files-header">
      <div>
        <h3>
          Files in {selectedSavedPortfolio.name}
        </h3>

        <p>
          Previous portfolio files uploaded to this portfolio.
        </p>
      </div>

      <span className="portfolio-file-count">
        {portfolioFiles.length}{' '}
        {portfolioFiles.length === 1 ? 'file' : 'files'}
      </span>
    </div>

    {portfolioFiles.length === 0 ? (

      <div className="portfolio-files-empty">
        No files uploaded yet.
      </div>

    ) : (

      <div className="portfolio-file-list">

        {portfolioFiles.map((file) => (

  <div
    className="portfolio-file-item"
    key={file.id}
  >

    <div className="portfolio-file-info">

      <strong>
        {file.filename}
      </strong>

      <span>
        Uploaded:{' '}
        {file.uploaded_at
        ? new Date(file.uploaded_at).toLocaleString()
        : 'Unknown'}
      </span>

    </div>

    <button
      type="button"
      className="delete-file-button"
      onClick={() => deletePortfolioFile(file.id)}
    >
      Delete
    </button>

  </div>

))}

      </div>

    )}

  </div>
)}

{/* UPLOAD PORTFOLIO */}
<div className="upload-area">
    <p className="upload-instruction">
      Upload a portfolio JSON file to begin your analysis.
    </p>

    <label
      className={`upload-button ${
        uploading ? 'disabled' : ''
      }`}
    >
      {uploading ? 'Analyzing...' : 'Upload Portfolio JSON'}

      <input
        type="file"
        accept=".json,application/json"
        onChange={uploadPortfolio}
        disabled={uploading}
        hidden
      />
    </label>

    {uploading && (
      <p className="upload-status">
        Your portfolio is being analyzed. This may take a moment.
      </p>
    )}
  </div>

  {/* SAVE PORTFOLIO */}
  {portfolio && (
    <div className="portfolio-save">
      <span className="portfolio-save-text">
        Save this portfolio:
      </span>

      <input
        type="text"
        value={savePortfolioName}
        onChange={(event) =>
          setSavePortfolioName(event.target.value)
        }
        placeholder="Portfolio name"
        disabled={savingPortfolio}
      />

      <button
        type="button"
        onClick={savePortfolio}
        disabled={
          savingPortfolio ||
          !savePortfolioName.trim()
        }
      >
        {savingPortfolio ? 'Saving...' : 'Save Portfolio'}
      </button>
    </div>
  )}

</div>
</header>
      
        
      {/* ======================================================
          ERRORS
      ====================================================== */}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {uploadError && (
        <div className="error-banner">
          {uploadError}
        </div>
      )}

      {/* ======================================================
          NO PORTFOLIO STATE
      ====================================================== */}

      {!portfolio ? (
        <main className="empty-portfolio-state">

          <div className="card">

            <div className="section-heading">
              <h2>Upload a Portfolio to Begin</h2>

              <p>
                Select a portfolio JSON file above. The
                portfolio will be validated, analyzed and
                displayed here automatically.
              </p>
            </div>

            <div className="empty-state">
              No portfolio has been uploaded yet.
            </div>

          </div>

        </main>
      ) : (
        <main>

          {/* ==================================================
              PORTFOLIO SUMMARY
          ================================================== */}

          <section className="summary-grid">

            <div className="summary-card">
              <p>Portfolio Value</p>

              <h2>
                {formatMoney(totalCurrentValue)}
              </h2>
            </div>

            <div className="summary-card">
              <p>Total Return</p>

              <h2
                className={
                  Number(totalReturnAmount) >= 0
                    ? 'positive'
                    : 'negative'
                }
              >
                {formatSignedMoney(totalReturnAmount)}
              </h2>

              <span
                className={
                  Number(totalReturnPercentage) >= 0
                    ? 'positive'
                    : 'negative'
                }
              >
                {formatPercent(totalReturnPercentage)}
              </span>
            </div>

            <div className="summary-card">
              <p>Originally Invested</p>

              <h2>
                {formatMoney(
                  totalOriginallyInvested
                )}
              </h2>
            </div>

          </section>

          {/* ==================================================
              WHY TODAY MOVED
          ================================================== */}

          <section className="card">

            <div className="section-heading">

              <h2>What May Have Moved Your Portfolio Today</h2>

            </div>

            {newsStripArticles.length === 0 ? (

              <div className="empty-state">
                No news impact data available.
              </div>

            ) : (

              <div
                style={{
                  display: 'flex',
                  gap: '14px',
                  overflowX: 'auto',
                  paddingBottom: '6px',
                  marginTop: '18px',
                }}
              >

                {newsStripArticles.map((item, index) => {

                  const isUp =
                    Number(
                      item.daily_change_percent
                    ) >= 0

                  return (
                    <div
                      key={`${item.ticker}-${index}`}
                      style={{
                        flex: '0 0 240px',
                        border: '1px solid #e5e7eb',
                        borderLeftWidth: '4px',
                        borderLeftColor:
                          item.has_news
                            ? isUp
                              ? '#16a34a'
                              : '#dc2626'
                            : '#e5e7eb',
                        borderStyle:
                          item.has_news
                            ? 'solid'
                            : 'dashed',
                        borderRadius: '10px',
                        padding: '14px',
                        background:
                          item.has_news
                            ? '#ffffff'
                            : '#f9fafb',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                      }}
                    >

                      <div
                        style={{
                          display: 'flex',
                          justifyContent:
                            'space-between',
                          alignItems: 'center',
                        }}
                      >

                        <strong>
                          {item.ticker}
                        </strong>

                        <span
                          className={
                            isUp
                              ? 'positive'
                              : 'negative'
                          }
                        >
                          {formatPercent(
                            item.daily_change_percent
                          )}
                        </span>

                      </div>

                      <span
                        style={{
                          fontSize: '12px',
                          color: '#6b7280',
                        }}
                      >
                        {item.company_name}
                      </span>

                      <span
                        style={{
                          fontSize: '12px',
                          color: '#6b7280',
                        }}
                      >
                        {formatSignedMoney(item.impact)}{' '}
                        to portfolio
                      </span>

                      <div
                        style={{
                          height: '1px',
                          background: '#e5e7eb',
                          margin: '4px 0',
                        }}
                      />

                      {item.has_news ? (
                        <>
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              fontSize: '13px',
                              fontWeight: 600,
                              color: '#111827',
                              textDecoration: 'none',
                              lineHeight: 1.35,
                            }}
                          >
                            {item.title}
                          </a>

                          <div
                            style={{
                              display: 'flex',
                              justifyContent:
                                'space-between',
                              fontSize: '11px',
                              color: '#9ca3af',
                              marginTop: '4px',
                            }}
                          >
                            <span>
                              {item.source}
                            </span>

                            <span>
                              {formatNewsDate(
                                item.published_at
                              )}
                            </span>
                          </div>

                          {item.market_alignment ===
                            'conflicting' && (
                            <div
                              style={{
                                fontSize: '10.5px',
                                color: '#b45309',
                                background: '#fffbeb',
                                border:
                                  '1px solid #fde68a',
                                borderRadius: '6px',
                                padding: '3px 6px',
                                marginTop: '4px',
                                width: 'fit-content',
                              }}
                            >
                              Sentiment conflicts with
                              move
                            </div>
                          )}
                        </>
                      ) : (
                        <p
                          style={{
                            fontSize: '12px',
                            fontStyle: 'italic',
                            color: '#9ca3af',
                            margin: 0,
                          }}
                        >
                          No news explanation found for
                          this move.
                        </p>
                      )}

                    </div>
                  )
                })}

              </div>
            )}

          </section>

{/* ==================================================
    PERFORMANCE COMPARISON
================================================== */}

<section className="card">

  <div className="section-heading">

    <h2>Performance Comparison</h2>

    <p>
      Compared with the previous available portfolio snapshot
    </p>

  </div>

  {performanceLoading ? (

    <div className="empty-state">
      Loading performance comparison...
    </div>

  ) : !performance ? (

    <div className="empty-state">
      No performance data available.
    </div>

  ) : !performance.previous_snapshot ? (

    <div className="empty-state">
      {performance.message ||
        "There is not enough historical data to compare this portfolio yet."}
    </div>

  ) : (

    <>

      <div className="daily-movement">

        <div>
          <span>Previous Value</span>

          <strong>
            {formatMoney(
              performance.previous_snapshot.value
            )}
          </strong>
        </div>

        <div>
          <span>Current Value</span>

          <strong>
            {formatMoney(
              performance.current_snapshot.value
            )}
          </strong>
        </div>

        <div>
          <span>Change</span>

          <strong
            className={
              Number(
                performance.portfolio_change.amount
              ) >= 0
                ? 'positive'
                : 'negative'
            }
          >
            {formatSignedMoney(
              performance.portfolio_change.amount
            )}
          </strong>
        </div>

        <div>
          <span>Change %</span>

          <strong
            className={
              Number(
                performance.portfolio_change.percentage
              ) >= 0
                ? 'positive'
                : 'negative'
            }
          >
            {formatPercent(
              performance.portfolio_change.percentage
            )}
          </strong>
        </div>

      </div>

      <div className="comparison-date">
        Change since{" "}
        {new Date(
          performance.previous_snapshot.date
          ).toLocaleDateString()}
      </div>

      <div className="comparison-explanation">

  <h3>What drove the change?</h3>

  <p>
    Your portfolio changed by{' '}
    <strong>
      {formatSignedMoney(
        performance.portfolio_change.amount
      )}
    </strong>{' '}
    (
    <strong>
      {formatPercent(
        performance.portfolio_change.percentage
      )}
    </strong>
    ) compared with the previous snapshot.
  </p>

  <div className="comparison-contributors">

    <div className="contributor-column">

      <h4>Positive contributors</h4>

      {performance.positive_contributors?.length ? (

        performance.positive_contributors
        .map((holding) => (

            <div
              className="comparison-contributor"
              key={holding.ticker}
            >

              <div>
                <strong>
                  {holding.ticker}
                </strong>

                <span>
                  {holding.company_name}
                </span>
              </div>

              <strong className="positive">
                {formatSignedMoney(
                  holding.change
                )}
              </strong>

            </div>

          ))

      ) : (

        <p className="empty-contributor-message">
          No positive contributors.
        </p>

      )}

    </div>


    <div className="contributor-column">

      <h4>Negative contributors</h4>

      {performance.negative_contributors?.length ? (

        performance.negative_contributors
        .map((holding) => (

            <div
              className="comparison-contributor"
              key={holding.ticker}
            >

              <div>
                <strong>
                  {holding.ticker}
                </strong>

                <span>
                  {holding.company_name}
                </span>
              </div>

              <strong className="negative">
                {formatSignedMoney(
                  holding.change
                )}
              </strong>

            </div>

          ))

      ) : (

        <p className="empty-contributor-message">
          No negative contributors.
        </p>

      )}

    </div>

  </div>

</div>

    </>

  )}

</section>

          {/* ==================================================
              TOP CONTRIBUTORS
          ================================================== */}

          <section className="card">

            <div className="section-heading">

              <h2>Today's Top Contributors</h2>
              <p>
                Holdings with the largest impact on today's portfolio movement.
                </p>

            </div>

            {contributorChartData.length === 0 ? (

              <div className="empty-state">
                No contributor data available.
              </div>

            ) : (

              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '18px',
                  marginTop: '20px',
                }}
              >

                {contributorChartData.map(
                  (stock, index) => {

                    const percentage =
                      contributorProgressMax > 0
                        ? (Math.abs(
                            stock.impact
                          ) /
                            contributorProgressMax) *
                          100
                        : 0

                    const isPositive =
                      stock.impact >= 0

                    return (

                      <div
                        key={`${stock.ticker}-${index}`}
                      >

                        <div
                          style={{
                            display: 'flex',
                            justifyContent:
                              'space-between',
                            alignItems: 'center',
                            marginBottom: '7px',
                          }}
                        >

                          <strong>
                            {stock.ticker}
                          </strong>

                          <span
                            className={
                              isPositive
                                ? 'positive'
                                : 'negative'
                            }
                          >
                            {formatSignedMoney(
                              stock.impact
                            )}
                          </span>

                        </div>

                        <div
                          style={{
                            width: '100%',
                            height: '12px',
                            background: '#e5e7eb',
                            borderRadius: '999px',
                            overflow: 'hidden',
                          }}
                        >

                          <div
                            style={{
                              width: `${percentage}%`,
                              height: '100%',
                              background:
                                isPositive
                                  ? '#16a34a'
                                  : '#dc2626',
                              borderRadius: '999px',
                              transition:
                                'width 0.4s ease',
                            }}
                          />

                        </div>

                      </div>

                    )
                  }
                )}

              </div>
            )}

          </section>

          {/* ==================================================
              AI SUMMARY
          ================================================== */}

          <section className="card">

            <div className="section-heading">

              <h2>AI Portfolio Summary</h2>

            </div>

            <div className="ai-summary">
              {overallAssessment}
            </div>

          </section>

          {/* ==================================================
              CHAT
          ================================================== */}

          <section className="card chatbot-card">

            <div className="section-heading">

              <h2>
                Ask about your portfolio
              </h2>

              <p>
                Ask questions about your holdings, sectors
                and portfolio performance.
              </p>

            </div>

            {/* SUGGESTIONS */}

            <div className="suggestions">

              <button
                onClick={() =>
                  askQuestion(
                    'Why did my portfolio go down today?'
                  )
                }
                disabled={loading}
              >
                Why did my portfolio go down today?
              </button>

              <button
                onClick={() =>
                  askQuestion(
                    'Which sectors contributed most to my portfolio?'
                  )
                }
                disabled={loading}
              >
                Sector performance
              </button>

              <button
                onClick={() =>
                  askQuestion(
                    'Which stocks helped my portfolio?'
                  )
                }
                disabled={loading}
              >
                Top contributors
              </button>

              <button
                onClick={() =>
                  askQuestion(
                    'Why did MSFT fall?'
                  )
                }
                disabled={loading}
              >
                Why did MSFT fall?
              </button>

            </div>

            {/* INPUT */}

            <div className="chat-input">

              <input
                value={question}
                onChange={(event) =>
                  setQuestion(event.target.value)
                }
                onKeyDown={(event) => {
                  if (
                    event.key === 'Enter' &&
                    !event.shiftKey
                  ) {
                    event.preventDefault()
                    askQuestion()
                  }
                }}
                placeholder="Ask a question about your portfolio..."
                disabled={loading}
              />

              <button
                className="ask-button"
                onClick={() => askQuestion()}
                disabled={
                  loading ||
                  !question.trim()
                }
              >
                {loading ? 'Thinking...' : 'Ask'}
              </button>

            </div>

            {/* ANSWER */}

            {answer && (

              <div className="answer-box">

                <div className="answer-header">

                  <span className="ai-dot"></span>

                  AI Assistant

                </div>

                <div className="answer-text">
                  {answer}
                </div>

              </div>

            )}

          </section>

        </main>
      )}

    </div>
  )
}

export default App

