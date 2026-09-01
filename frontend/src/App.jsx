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
  // DATA
  // ============================================================

  const [portfolio, setPortfolio] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [evidence, setEvidence] = useState(null)
  const [narrative, setNarrative] = useState(null)

  // ============================================================
  // CHAT
  // ============================================================

  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)

  // ============================================================
  // PAGE
  // ============================================================

  const [pageLoading, setPageLoading] = useState(true)
  const [error, setError] = useState('')

  // ============================================================
  // UPLOAD
  // ============================================================

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')

  // ============================================================
  // NEWS
  // ============================================================

  const newsStripArticles =
    analysis?.news_strip?.articles || []

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

  useEffect(() => {
  // Intentionally not calling loadPortfolioData() here.
  // We don't want a page refresh to resurrect the last
  // uploaded portfolio from disk — every fresh page load
  // should start empty and wait for a new upload.
  setPageLoading(false)
}, [])

  // ============================================================
  // UPLOAD PORTFOLIO JSON
  // ============================================================

  async function uploadPortfolio(event) {
    const file = event.target.files?.[0]

    if (!file) {
      return
    }

    setUploading(true)
    setUploadError('')
    setError('')
    setAnswer('')

    try {
      // Check the file type before uploading
      if (
        !file.name.toLowerCase().endsWith('.json')
      ) {
        throw new Error(
          'Please select a valid portfolio JSON file.'
        )
      }

      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(
        `${API_URL}/portfolio/upload`,
        {
          method: 'POST',
          body: formData,
        }
      )

      let data

      try {
        data = await response.json()
      } catch {
        throw new Error(
          'The server returned an invalid response.'
        )
      }

      if (!response.ok) {
        throw new Error(
          data.detail || 'Portfolio upload failed.'
        )
      }

      console.log('Portfolio uploaded successfully:', data)

      if (data.portfolio) {
        setPortfolio(data.portfolio)
      }

      if (data.analysis) {
        setAnalysis(data.analysis)
      }

      if (data.evidence) {
        setEvidence(data.evidence)
      }

      if (data.narrative) {
        setNarrative(data.narrative)
      }

      // Clear any previous errors
      setUploadError('')
      setError('')
    } catch (err) {
      console.error('Upload error:', err)

      setUploadError(
        err.message || 'Could not upload portfolio.'
      )
    } finally {
      setUploading(false)

      // Allows the user to upload the same filename again
      event.target.value = ''
    }
  }

  // ============================================================
  // CHAT
  // ============================================================

  async function askQuestion(text = question) {
    const userQuestion = text.trim()

    if (!userQuestion || loading) {
      return
    }

    // Don't allow chat before a portfolio exists
    if (!portfolio) {
      setAnswer(
        'Please upload a portfolio JSON file before asking questions.'
      )
      return
    }

    setQuestion(userQuestion)
    setLoading(true)
    setAnswer('')

    try {
      const response = await fetch(
        `${API_URL}/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            question: userQuestion,
          }),
        }
      )

      let data

      try {
        data = await response.json()
      } catch {
        throw new Error(
          'The server returned an invalid response.'
        )
      }

      if (!response.ok) {
        throw new Error(
          data.detail || 'Chat request failed.'
        )
      }

      setAnswer(
        data.answer || 'No answer was returned.'
      )
    } catch (err) {
      console.error('Chat error:', err)

      setAnswer(
        err.message ||
          'Sorry, I could not connect to the AI assistant. Please make sure the backend is running.'
      )
    } finally {
      setLoading(false)
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

          <h1>AI Portfolio Assistant</h1>

          <p>
            Portfolio overview and AI-powered analysis
          </p>

          <div className="upload-area">

            <p className="upload-instruction">
              Upload your portfolio JSON to begin your
              analysis.
            </p>

            <label
              className={`upload-button ${
                uploading ? 'disabled' : ''
              }`}
            >
              {uploading
                ? 'Analyzing...'
                : 'Upload Portfolio JSON'}

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
                Your portfolio is being analyzed. This may
                take a moment...
              </p>
            )}

          </div>

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
              DAILY PERFORMANCE
          ================================================== */}

          <section className="card">

            <div className="section-heading">

              <h2>Daily Performance</h2>

              <p>
                Values from the portfolio analysis
              </p>

            </div>

            <div className="daily-movement">

              <div>
                <span>Previous Value</span>

                <strong>
                  {formatMoney(
                    previousPortfolioValue
                  )}
                </strong>
              </div>

              <div>
                <span>Current Value</span>

                <strong>
                  {formatMoney(
                    currentPortfolioValue
                  )}
                </strong>
              </div>

              <div>
                <span>Daily Impact</span>

                <strong
                  className={
                    Number(totalDailyImpact) >= 0
                      ? 'positive'
                      : 'negative'
                  }
                >
                  {formatSignedMoney(
                    totalDailyImpact
                  )}
                </strong>
              </div>

              <div>
                <span>Daily Change</span>

                <strong
                  className={
                    Number(dailyChangePercent) >= 0
                      ? 'positive'
                      : 'negative'
                  }
                >
                  {formatPercent(
                    dailyChangePercent
                  )}
                </strong>
              </div>

            </div>

          </section>

          {/* ==================================================
              SECTOR ANALYSIS
          ================================================== */}

          <div className="sector-analysis-grid">

            {/* SECTOR PERFORMANCE */}

            <section className="card">

              <div className="section-heading">

                <h2>Sector Performance</h2>

                <p>
                  Sector values and daily performance from
                  the portfolio analysis
                </p>

              </div>

              {sectors.length === 0 ? (

                <div className="empty-state">
                  No sector data available.
                </div>

              ) : (

                <div className="sector-list">

                  {sectors.map((sector) => (

                    <div
                      className="sector-row"
                      key={sector.name}
                    >

                      <div className="sector-info">

                        <strong>
                          {sector.name}
                        </strong>

                        <p>
                          {sector.holdings.length}{' '}
                          holdings
                          {' • '}
                          Current Value:{' '}
                          {formatMoney(
                            sector.currentValue
                          )}
                        </p>

                      </div>

                      <div
                        className={
                          Number(
                            sector.returnPercent
                          ) >= 0
                            ? 'positive sector-value'
                            : 'negative sector-value'
                        }
                      >
                        {formatPercent(
                          sector.returnPercent
                        )}
                      </div>

                      <div
                        className={
                          Number(sector.impact) >= 0
                            ? 'positive sector-value'
                            : 'negative sector-value'
                        }
                      >
                        {formatSignedMoney(
                          sector.impact
                        )}
                      </div>

                    </div>

                  ))}

                </div>
              )}

            </section>

            {/* PORTFOLIO DISTRIBUTION */}

            <section className="card">

              <div className="section-heading">

                <h2>
                  Portfolio Distribution by Sector
                </h2>

                <p>
                  Current portfolio value allocated
                  across sectors
                </p>

              </div>

              {sectorChartData.length === 0 ? (

                <div className="empty-state">
                  No sector allocation data available.
                </div>

              ) : (

                <div className="sector-chart">

                  <ResponsiveContainer
                    width="100%"
                    height={360}
                  >

                    <PieChart>

                      <Pie
                        data={sectorChartData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={120}
                        innerRadius={60}
                        paddingAngle={2}
                        label={({
                          name,
                          percent,
                        }) =>
                          `${name} ${(
                            percent * 100
                          ).toFixed(0)}%`
                        }
                      >

                        {sectorChartData.map(
                          (entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={
                                SECTOR_COLORS[
                                  index %
                                    SECTOR_COLORS.length
                                ]
                              }
                            />
                          )
                        )}

                      </Pie>

                      <Tooltip
                        formatter={(value) =>
                          formatMoney(value)
                        }
                      />

                      <Legend />

                    </PieChart>

                  </ResponsiveContainer>

                </div>
              )}

            </section>

          </div>

          {/* ==================================================
              TOP CONTRIBUTORS
          ================================================== */}

          <section className="card">

            <div className="section-heading">

              <h2>Top Contributors</h2>

              <p>
                Holdings with the largest positive and
                negative impact today
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

