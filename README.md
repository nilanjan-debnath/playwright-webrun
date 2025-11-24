# Playwright WebRun

A robust and efficient Python-based web service utilizing **Playwright** for web scraping and network traffic analysis. This service automates the process of extracting data from modern, dynamic websites and provides detailed network monitoring capabilities through RESTful API endpoints.

## Features

### 🌐 Page Content Scraping
- Navigate to any URL and extract fully rendered page content
- Support for both HTML and plain text output formats
- Handle dynamic content loaded via JavaScript
- Configurable wait conditions for page load completion
- Stealth mode to avoid bot detection

### 📊 Network Log Capture
- Capture detailed network traffic during page load
- Record HTTP requests and responses with headers
- Optional request/response body capture
- Console log monitoring
- Structured JSON output for easy analysis

### 🚀 Production Ready
- FastAPI-based REST API
- Docker support with multi-stage builds
- Rate limiting with Redis backend
- Comprehensive logging with Loguru
- Sentry integration for error tracking
- Health check endpoint with actual browser verification
- CORS middleware support

## Quick Start

### Prerequisites
- Python 3.12+
- Docker (optional)
- Redis (for rate limiting)

### Installation

#### Using UV (Recommended)
```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium

# Run the application
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Using Docker
```bash
# Build and run with Docker Compose
docker compose up --build

# Or build manually
docker build -t playwright-webrun .
docker run -p 8000:8000 playwright-webrun
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints

#### 1. Page Content Scraping
```http
GET /api/v1/page/?url={url}&format={text|html}
```

**Parameters:**
- `url` (required): The URL to scrape
- `format` (optional): Output format - `text` (default) or `html`

**Example:**
```bash
# Get text content
curl "http://localhost:8000/api/v1/page/?url=http://example.com"

# Get HTML source
curl "http://localhost:8000/api/v1/page/?url=http://example.com&format=html"
```

#### 2. Network Logs & Debugging
```http
GET /api/v1/page/debug-network?url={url}&wait_seconds={seconds}&include_body={true|false}
```

**Parameters:**
- `url` (required): The URL to analyze
- `wait_seconds` (optional): Additional wait time for delayed requests (0-30, default: 5)
- `include_body` (optional): Capture request/response bodies (default: false)

**Example:**
```bash
curl "http://localhost:8000/api/v1/page/debug-network?url=http://example.com&include_body=true"
```

**Response:**
```json
{
  "page_title": "Example Domain",
  "final_url": "http://example.com/",
  "total_logs": 2,
  "logs": [
    {
      "type": "request",
      "timestamp": "2025-11-24T14:41:21.060196",
      "url": "http://example.com/",
      "method": "GET",
      "resourceType": "document",
      "headers": {...},
      "body": null
    },
    {
      "type": "response",
      "timestamp": "2025-11-24T14:41:22.390037",
      "status": 200,
      "url": "http://example.com/",
      "resourceType": "document",
      "headers": {...},
      "body": "<!doctype html>..."
    }
  ]
}
```

#### 3. Health Check
```http
GET /healthz
```

Performs an actual scraping test to verify Playwright is working correctly.

## Configuration

Create a `.env` file based on `.env.example`:

```env
# Environment
ENV=dev
DEBUG=true
LOG_LEVEL=INFO

# CORS
ORIGINS=http://localhost:3000 http://localhost:8080

# Database (optional)
DATABASE_URL=sqlite+aiosqlite:///db.sqlite3

# Redis (for rate limiting)
REDIS_URL=redis://localhost:6379

# Sentry (optional)
SENTRY_DSN=

# Rate Limiting
RATELIMIT_ENABLED=true
RATELIMIT_GUEST=6/minute
```

## Development

### Setup Pre-commit Hooks
```bash
uvx pre-commit install
```

### Run Tests
```bash
# Start the server
uv run uvicorn app.main:app --reload

# Test endpoints
curl http://localhost:8000/healthz
```

## Project Structure

```
playwright-webrun/
├── app/
│   ├── core/              # Core configurations
│   │   ├── config.py      # Settings management
│   │   ├── lifecycle.py   # Playwright lifecycle
│   │   ├── logger.py      # Logging setup
│   │   └── ratelimiter.py # Rate limiting
│   ├── page/
│   │   └── v1/
│   │       ├── controllers/  # API routes
│   │       ├── models/       # Pydantic models
│   │       └── services/     # Business logic
│   ├── playwright/
│   │   └── browser.py     # Browser dependency
│   └── main.py            # FastAPI application
├── logs/                  # Application logs
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
├── pyproject.toml         # Project dependencies
└── README.md
```

## Technologies Used

- **FastAPI**: Modern web framework for building APIs
- **Playwright**: Browser automation library
- **Pydantic**: Data validation using Python type hints
- **Loguru**: Simplified logging
- **SlowAPI**: Rate limiting
- **Sentry**: Error tracking and monitoring
- **BeautifulSoup4**: HTML parsing
- **UV**: Fast Python package installer

## License

This project is open source and available under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
