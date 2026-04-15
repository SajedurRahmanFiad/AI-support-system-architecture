# B2B AI Support API with RAG

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-green.svg)](https://fastapi.tiangolo.com/)

A production-ready **AI-powered customer support API** with Retrieval-Augmented Generation (RAG) for multi-tenant businesses. Built for cPanel deployment with intelligent conversation management, knowledge base integration, and human handoff capabilities.

## 🚀 Quick Start

```bash
# Clone and setup
git clone <your-repo-url>
cd b2b-ai-chatbot-api-with-rag
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Setup database
python -m app.cli init-db
python -m app.cli create-brand --name "My Company" --slug my-company

# Start server
python main.py
```

Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive API documentation.

## 📋 Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage Guide](#-usage-guide)
- [API Reference](#-api-reference)
- [Knowledge Base Setup](#-knowledge-base-setup)
- [Multi-Tenant Management](#-multi-tenant-management)
- [Deployment](#-deployment)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

### 🤖 AI-Powered Support
- **Intelligent Responses**: Context-aware replies using RAG technology
- **Multi-Provider LLM**: Gemini AI with extensible provider system
- **Conversation Memory**: Remembers customer history and preferences
- **Smart Handoffs**: Automatically routes complex issues to human agents

### 🏢 Multi-Tenant Architecture
- **Brand Isolation**: Each business has separate API keys and knowledge bases
- **Customizable Personality**: Brand-specific tone, rules, and response styles
- **Independent Scaling**: Businesses don't interfere with each other

### 📚 Knowledge Management
- **Document Chunking**: Large documents automatically split for efficient search
- **Semantic Search**: AI-powered retrieval finds relevant information
- **Multiple Formats**: Support for text, PDFs, and structured data
- **Real-time Updates**: Knowledge base updates without restarting

### 🔄 Async Processing
- **Background Jobs**: Heavy operations run asynchronously
- **Queue Management**: Database-backed job system for cPanel compatibility
- **Progress Tracking**: Monitor job status and results

### 📎 Rich Media Support
- **File Attachments**: Images, audio, and documents
- **AI Analysis**: Automatic transcription and content extraction
- **Secure Storage**: Local filesystem with provider abstraction

### 🛡️ Enterprise-Ready
- **Audit Logging**: Complete request/response tracking
- **Moderation Rules**: Configurable content filtering
- **Feedback Loop**: Human corrections improve AI responses
- **Rate Limiting**: Built-in protection against abuse

## 🔍 How It Works

### Core Flow

```mermaid
graph TD
    A[Customer Message] --> B[Authentication Check]
    B --> C[Customer Profile Lookup]
    C --> D[Knowledge Base Search]
    D --> E[Moderation Check]
    E --> F{Confidence Check}
    F -->|High| G[Generate AI Reply]
    F -->|Low| H[Human Handoff]
    G --> I[Send Response]
    H --> I
    I --> J[Update Conversation]
    J --> K[Log Audit Trail]
```

### AI Decision Process

1. **Input Analysis**: Customer message + conversation history + attachments
2. **Knowledge Retrieval**: Semantic search through uploaded documents
3. **Context Building**: Customer profile + brand personality + safety rules
4. **Response Generation**: AI crafts reply using all context
5. **Quality Check**: Confidence scoring and moderation review
6. **Action Selection**: Send reply, ask clarification, or handoff to human

### Key Components

- **Orchestrator**: Main processing pipeline coordinator
- **LLM Provider**: AI model interface (Gemini/OpenAI/etc.)
- **Knowledge Service**: Document indexing and retrieval
- **Memory Service**: Customer profiling and summarization
- **Moderation Service**: Content safety and handoff triggers

## 🏗️ Architecture

```
├── app/
│   ├── api/              # FastAPI routes and schemas
│   ├── services/         # Business logic
│   │   ├── llm/         # AI provider implementations
│   │   ├── knowledge/   # RAG and search
│   │   ├── memory/      # Customer profiling
│   │   └── orchestrator/# Main processing pipeline
│   ├── models.py        # SQLAlchemy database models
│   ├── database.py      # Database connection
│   ├── config.py        # Settings management
│   └── main.py          # FastAPI application
├── storage/             # File uploads
├── tests/              # Test suite
├── main.py            # Server entry point
├── passenger_wsgi.py  # cPanel deployment
└── requirements.txt   # Dependencies
```

### Database Schema

- **brands**: Business entities with customization settings
- **customers**: Customer profiles with facts and summaries
- **conversations**: Chat sessions with ownership tracking
- **messages**: Individual messages with AI metadata
- **knowledge_documents**: Uploaded knowledge base content
- **knowledge_chunks**: Chunked documents for efficient search
- **attachments**: File uploads with AI analysis
- **jobs**: Async task queue
- **audit_logs**: Complete activity tracking

## 📦 Installation

### Prerequisites

- **Python 3.10+**
- **MySQL/MariaDB** (production) or **SQLite** (development)
- **Git**

### Local Development Setup

```bash
# 1. Clone repository
git clone <your-repo-url>
cd b2b-ai-chatbot-api-with-rag

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
copy .env.example .env  # Windows
# cp .env.example .env   # macOS/Linux

# 5. Configure database
# Edit .env DATABASE_URL for your setup

# 6. Initialize database
python -m app.cli init-db

# 7. Create your first brand
python -m app.cli create-brand --name "Demo Company" --slug demo-company

# 8. Start development server
python main.py
```

### Docker Setup (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python -m app.cli init-db

EXPOSE 8000
CMD ["python", "main.py"]
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `APP_NAME` | Application name | B2B AI Support API | No |
| `DEBUG` | Debug mode | false | No |
| `DATABASE_URL` | Database connection string | sqlite:///./local.db | Yes |
| `PLATFORM_API_TOKEN` | Admin API token | change-this-token | Yes |
| `LLM_PROVIDER` | AI provider (gemini/mock) | gemini | No |
| `GEMINI_API_KEY` | Gemini API key | - | Yes (if using Gemini) |
| `KNOWLEDGE_TOP_K` | Search results limit | 5 | No |
| `HANDOFF_CONFIDENCE_THRESHOLD` | AI confidence threshold | 0.55 | No |

### Database URLs

```bash
# SQLite (development)
DATABASE_URL=sqlite+pysqlite:///./local.db

# MySQL/MariaDB (production)
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/db_name?charset=utf8mb4

# PostgreSQL (alternative)
DATABASE_URL=postgresql://user:pass@localhost:5432/db_name
```

## 📖 Usage Guide

### Basic Message Processing

```bash
# Process a customer message
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: your-brand-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "customer_external_id": "customer-123",
    "conversation_external_id": "conv-456",
    "text": "How long does shipping take?",
    "channel": "web"
  }'
```

**Response:**
```json
{
  "status": "send",
  "reply_text": "Standard shipping takes 2-3 business days...",
  "confidence": 0.87,
  "used_sources": [
    {
      "title": "Shipping Policy",
      "score": 0.94
    }
  ]
}
```

### Adding Knowledge

```bash
# Upload knowledge document
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/documents \
  -H "X-Platform-Token: secure-platform-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "title": "Company FAQ",
    "source_type": "faq",
    "raw_text": "Q: How do I return an item?\nA: Returns are accepted within 30 days..."
  }'
```

### File Attachments

```bash
# Upload file
curl -X POST http://127.0.0.1:8000/api/v1/uploads \
  -H "X-Brand-Api-Key: your-brand-api-key" \
  -F "file=@screenshot.jpg"

# Use in message
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: your-brand-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "customer_external_id": "customer-123",
    "conversation_external_id": "conv-456",
    "text": "Please help with this issue",
    "attachment_ids": [1]
  }'
```

### Async Processing

```bash
# Queue for background processing
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: your-brand-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "customer_external_id": "customer-123",
    "conversation_external_id": "conv-456",
    "text": "Complex question here",
    "process_async": true
  }'

# Check job status
curl http://127.0.0.1:8000/api/v1/jobs/1 \
  -H "X-Brand-Api-Key: your-brand-api-key"
```

## 📚 Knowledge Base Setup

### Document Format

Knowledge documents are plain text with the following structure:

```
# Document Title: Company Policies

## Section 1: Returns
Returns are accepted within 30 days of purchase.
Items must be in original condition with tags attached.
Refunds are processed within 5-7 business days.

## Section 2: Shipping
Standard shipping: 2-3 business days
Express shipping: 1 business day (additional $10)
International shipping: 7-14 business days

## Section 3: Contact
Email: support@company.com
Phone: 1-800-123-4567
Hours: Monday-Friday 9AM-6PM EST
```

### Best Practices

1. **Chunk Size**: Keep sections under 1000 characters for optimal retrieval
2. **Clear Headings**: Use descriptive headers for better search results
3. **Structured Format**: Use bullet points and numbered lists
4. **Avoid Duplication**: Don't repeat information across documents
5. **Regular Updates**: Keep information current

### Adding Documents

```bash
# Via API
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/documents \
  -H "X-Platform-Token: secure-platform-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "title": "Shipping & Returns",
    "source_type": "policy",
    "raw_text": "Your document content here..."
  }'
```

### PDF Processing

For PDF documents:
1. Extract text manually using PDF reader
2. Copy content into the `raw_text` field
3. Consider splitting large PDFs into multiple documents

## 🏢 Multi-Tenant Management

### Creating Brands

```bash
# Create new brand
python -m app.cli create-brand \
  --name "Fashion Store" \
  --slug fashion-store \
  --tone-name "Stylish and trendy" \
  --tone-instructions "Use fashion-forward language"
```

### Brand Customization

#### Update Brand Settings
```bash
# Via database (advanced)
mysql -u root b2b_ai_support -e "
UPDATE brands SET
  tone_instructions = 'Be enthusiastic and use exclamation points!',
  fallback_handoff_message = 'Our fashion experts will help you shortly!'
WHERE id = 1;
"
```

#### Add Brand Rules
```bash
curl -X POST http://127.0.0.1:8000/api/v1/brands/1/rules \
  -H "X-Platform-Token: secure-platform-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "policy",
    "title": "Discount Limit",
    "content": "Never offer more than 20% discount",
    "handoff_on_match": true
  }'
```

#### Add Style Examples
```bash
curl -X POST http://127.0.0.1:8000/api/v1/brands/1/style-examples \
  -H "X-Platform-Token: secure-platform-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Size Question",
    "trigger_text": "What size should I order?",
    "ideal_reply": "Great question! Check our size guide at [link]. Generally, we recommend ordering your usual size."
  }'
```

### Managing Multiple Customers

Each customer is identified by `customer_external_id`:

```bash
# Customer A
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: brand-key-1" \
  -H "Content-Type: application/json" \
  -d '{"brand_id": 1, "customer_external_id": "user-123", "text": "Hello"}'

# Customer B (different conversation)
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: brand-key-1" \
  -H "Content-Type: application/json" \
  -d '{"brand_id": 1, "customer_external_id": "user-456", "text": "Hi there"}'
```

## 🔌 API Reference

### Authentication

| Header | Description | Example |
|--------|-------------|---------|
| `X-Platform-Token` | Admin operations | `secure-platform-token-12345` |
| `X-Brand-Api-Key` | Brand operations | `brand_ABC123...` |

### Core Endpoints

#### Health Check
```http
GET /api/health
```

#### Message Processing
```http
POST /api/v1/messages/process
Content-Type: application/json

{
  "brand_id": 1,
  "customer_external_id": "string",
  "conversation_external_id": "string",
  "text": "string",
  "channel": "web",
  "attachment_ids": [],
  "process_async": false
}
```

#### Knowledge Management
```http
POST /api/v1/knowledge/documents
GET /api/v1/knowledge/documents
DELETE /api/v1/knowledge/documents/{id}
```

#### Brand Management
```http
POST /api/v1/brands
GET /api/v1/brands
PUT /api/v1/brands/{id}
```

#### File Uploads
```http
POST /api/v1/uploads
Content-Type: multipart/form-data

file: [binary data]
```

#### Job Management
```http
GET /api/v1/jobs/{id}
POST /api/v1/jobs/process-pending
```

## 🚀 Deployment

### cPanel Deployment

1. **Create Python App** in cPanel
2. **Set Application Root** to your project directory
3. **Set Application Startup File** to `passenger_wsgi.py`
4. **Environment Variables**: Copy `.env` values to cPanel
5. **Install Dependencies**: `pip install -r requirements.txt`
6. **Initialize Database**: `python -m app.cli init-db`
7. **Create Brands**: `python -m app.cli create-brand --name "Your Brand"`
8. **Setup Cron Job**:
   ```bash
   python -m app.cli run-jobs --limit 20
   ```
   Run every 5 minutes

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "main.py"]
```

```bash
docker build -t b2b-ai-support .
docker run -p 8000:8000 b2b-ai-support
```

### Production Checklist

- [ ] Set `DEBUG=false`
- [ ] Use strong `PLATFORM_API_TOKEN`
- [ ] Configure production database
- [ ] Set up SSL certificates
- [ ] Configure rate limiting
- [ ] Set up monitoring
- [ ] Configure backups

## 🛠️ Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test
pytest app/tests/test_api.py::test_brand_setup_and_reply_flow

# With coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Format code
black app/
isort app/

# Lint code
flake8 app/
mypy app/
```

### Adding New Features

1. **LLM Providers**: Implement `LLMProvider` interface
2. **Storage Providers**: Extend storage abstraction
3. **API Endpoints**: Add to `app/api/routes/`
4. **Database Models**: Update `app/models.py`

## 🔧 Troubleshooting

### Common Issues

#### Database Connection Failed
```bash
# Check MySQL service
sudo systemctl status mysql

# Test connection
mysql -u root -p -e "SELECT 1;"
```

#### API Key Issues
- Verify `GEMINI_API_KEY` in `.env`
- Check API key permissions
- Ensure billing is enabled

#### Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

#### Permission Errors
```bash
# Fix upload directory permissions
chmod 755 storage/uploads
```

### Debug Mode

Enable debug logging:
```bash
export DEBUG=true
python main.py
```

Check logs in terminal or configure file logging.

### Performance Tuning

- **Database**: Add indexes on frequently queried columns
- **Knowledge Search**: Adjust `KNOWLEDGE_TOP_K` and `KNOWLEDGE_SCAN_LIMIT`
- **Caching**: Implement Redis for session storage
- **Async Jobs**: Monitor queue length and processing times

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Write tests for new features
- Update documentation
- Use type hints
- Keep commits atomic

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [SQLAlchemy](https://sqlalchemy.org/) for ORM
- [Google Gemini](https://ai.google.dev/) for AI capabilities
- [LangChain](https://python.langchain.com/) for inspiration

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/b2b-ai-chatbot-api-with-rag/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/b2b-ai-chatbot-api-with-rag/discussions)
- **Email**: your-email@example.com

---

**Made with ❤️ for businesses who want smarter customer support**
- One brand cannot read another brand's customers, conversations, or documents
