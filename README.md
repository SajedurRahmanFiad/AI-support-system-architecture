# B2B AI Support API - Backend

**Version:** 0.1.0 | **API Version:** v1 | **Status:** Production-ready

## Overview

This is a multi-tenant B2B AI customer support API designed for scalable, isolated business operations. Each brand/tenant maintains complete separation:

- **Knowledge bases** - Business-specific documents and training data
- **Tone & style** - Brand-specific response examples and tone rules
- **Customer data** - Per-customer profiles, conversation history, and facts
- **Product catalog** - Product images for recognition and metadata
- **Rules & policies** - Business rules with auto-handoff triggers
- **Media & uploads** - Customer attachments, voice notes, images, and files

### Architecture Highlights

- **API-first design** - Headless backend serving multiple frontends (dashboard, Facebook, WordPress, Shopify, etc.)
- **Multi-tenant ready** - One API server serves unlimited brands with complete data isolation
- **Job queue system** - Database-backed background jobs (no Redis/Docker required)
- **Modular LLM** - Abstracted provider layer (currently Gemini, extensible to others)
- **cPanel compatible** - Runs on shared hosting with Passenger WSGI

### Deployment & Tech Stack

**Prepared for:**
- cPanel hosting with Passenger WSGI
- MariaDB or MySQL database  
- Gemini API (with Google Cloud Speech-to-Text optional upgrade)
- Bangladeshi-first (bn-BD) language support

**Core Stack:**
- FastAPI 0.116.1 (async Python web framework)
- SQLAlchemy 2.0.43 (database ORM)
- PyMySQL 1.1.1 (MySQL connector)
- Pydantic 2.11.9 (data validation)
- Google Genai 1.34.0 (Gemini integration)

## Core Capabilities & Features

This backend provides the complete infrastructure for multi-tenant AI customer support:

### Message Processing Pipeline

When a customer message arrives at `POST /api/v1/messages/process`, the system executes this flow:

1. **Brand & Auth Validation** - Verify brand credentials and API key
2. **Attachment Processing** - If customer included images/audio/documents:
   - Download/retrieve from uploads storage
   - Detect file type (image, audio, document, etc.)
3. **Audio Transcription** - If voice note:
   - Send to Gemini or Google Cloud Speech-to-Text
   - Confidence check; if low, return clarification request
   - Support for Bangla/English mixed language
4. **Product Recognition** - If image attachment:
   - Compare against brand's product catalog using vision API
   - Return matched products with confidence scores
5. **Customer Memory** - Load or create customer profile:
   - Retrieve customer facts, language preference, past order history
   - Load recent conversation summary
6. **Knowledge Search** - Semantic search over brand knowledge base:
   - Use embeddings to find top-K relevant documents
   - Extract snippets to feed into LLM context
7. **LLM Response Generation** - Generate contextual reply:
   - Input: customer message + knowledge snippets + customer history + rules + style examples
   - Output: AI-generated reply with confidence score
8. **Safety & Moderation** - Check if reply is safe:
   - Confidence check - if low, may trigger escalation
   - Rule matching - if any "handoff_on_match" rules triggered, escalate
   - Tone check - ensure brand voice consistency
9. **Response** - Return to caller:
   - Success: message_id, reply text, confidence, handoff_needed flag
   - Error: error details and suggestion for human takeover

### Multi-Tenancy & Isolation

- **Brand Isolation** - All data (knowledge, customers, conversations) stored with `brand_id` foreign key
- **API Key Rotation** - Each brand has unique `X-Brand-Api-Key`; can be rotated without brand recreation
- **Separate Knowledge** - Each brand maintains separate knowledge base (not shared by default)
- **Tenant-Safe Queries** - All queries filtered by `brand_id` to prevent cross-tenant data leaks

### Customer Memory System

- **Customer Profiles** - Name, language, location, contact channel
- **Customer Facts** - Learned attributes (favorite color, previous orders, complaints)
- **Conversation Summaries** - Short summaries of old conversations for context
- **Conversation History** - Last N messages kept for ongoing context
- **Auto-Update** - Memory updated after each message (facts extracted from conversation)

### Knowledge Base Features

- **Document Types** - Knowledge can come from:
  - Raw FAQ/policy documents
  - Conversation examples (auto-extracted Q&A)
  - Manual transcripts or text
- **Semantic Chunking** - Long documents automatically split into meaningful chunks
- **Embeddings** - Each chunk embedded using Gemini's embedding model
- **Semantic Search** - Find relevant chunks by meaning, not just keyword match
- **Reindexing** - Update knowledge in-place without recreating everything
- **Global Knowledge** - Shared knowledge for all brands (e.g., company-wide policies)

### Brand Configuration (Training)

Four main ways to teach the AI:

1. **Knowledge Documents** - Business facts (what)
2. **Style Examples** - Approved replies showing tone (how)
3. **Hard Rules** - Policies with auto-handoff (constraints)
4. **Product Images** - Reference catalog for vision matching (recognition)

### Product Recognition System

- **Vision-based matching** - Not LLM fine-tuning
- **Reference Images** - Each product has 3-5 reference images from different angles
- **Metadata** - SKU, color, size, model attached to each product
- **Matching** - Customer image compared against catalog using vision embeddings
- **Output** - Matched products with confidence scores

### Voice Transcription

- **Gemini API** - Default, works in-region, supports Bangla
- **Google Cloud Speech-to-Text** - Optional upgrade for production (more stable)
- **Language Support** - Primary: bn-BD. Fallback: en-US, en-GB, hi-IN
- **Confidence Threshold** - If audio clarity score < 0.65, ask for clarification
- **Bangla Support** - Special handling for mixed Bangla-English and noisy audio

### Background Job Queue

- **Database-backed** - Uses database, not Redis (works on cPanel)
- **Async Processing** - Long tasks (reindexing, batch processing) queued for later
- **Job Status** - Track pending → processing → success/error
- **Worker** - Triggered by `POST /api/v1/jobs/process-pending`
- **No Daemon** - Meant for manual/scheduled calls (not always-running)

### Handoff & Escalation

Conversation can be marked for human takeover via:
- **Low Confidence** - If AI confidence < threshold, escalate
- **Rule Match** - If content matches a "handoff_on_match=true" rule
- **API Call** - Direct `POST /v1/conversations/{id}/handoff`
- **Status** - Conversation status changes to "handoff"
- **Release** - Humans can `POST /v1/conversations/{id}/release` to return to AI

### Facebook Integration

- **Webhook Verification** - GET `/api/v1/facebook/webhook` for Meta handshake
- **Webhook Ingestion** - POST `/api/v1/facebook/webhook` receives page messages/comments
- **Page Credentials** - Store multiple FB pages per brand
- **Signature Validation** - Verify X-Hub-Signature-256 header
- **Message Routing** - Incoming FB messages fed into normal message pipeline

---



## What "training" means in this app

People often use the word "training" for a few different things. In this app, there are 5 practical types of customization:

### 1. Knowledge training

You give the system business facts as documents.

Examples:

- product details
- pricing
- delivery areas
- return policy
- payment rules
- size guides
- FAQ answers

The app breaks those documents into smaller pieces, stores them, and searches them when a customer asks something relevant.

This is the main way to teach the AI business information.

### 2. Style training

You give the system examples of how the brand should talk.

Examples:

- how to greet customers
- how to answer product questions
- how to reply when something is out of stock
- how to apologize
- how to hand off to a human

This does not change the model weights. It changes behavior by giving the AI high-quality examples and brand rules at runtime.

This is the safest and cheapest way to shape tone.

### 3. Product image training

You upload reference images of products.

The app does not "fine-tune" the LLM on those images. Instead, it:

- studies the product images
- saves a visual fingerprint
- stores the product metadata
- matches future customer photos against that catalog

This is the right approach for ecommerce support. It is faster and safer than trying to retrain a model every time products change.

### 4. Customer memory

Each customer can have:

- name
- language
- city
- profile data
- facts learned from earlier chats
- short summary of past conversations

This is how the app remembers people separately.

### 5. Conversation memory

The app keeps recent messages and also creates short summaries over time.

This helps the AI reply like it remembers the ongoing conversation instead of acting like each message is brand new.

## What this app does not do

- it does not yet include full Facebook media-download and outbound-delivery wrappers
- it does not do true model fine-tuning inside this repo
- it does not do live phone calls or real-time call center streaming
- it does not include a web admin panel yet
- it does not clean noisy audio with tools like `ffmpeg` yet

Those can be added later, but the API core is already in place.

## Best way to think about the system

- the model learns "how to talk" from style examples and tone rules
- the model learns "what this business knows" from knowledge documents
- the system learns "who this customer is" from customer memory
- the product matcher learns "what product this photo looks like" from product images

That combination is usually much better than trying to fine-tune everything into one model.

## Production recommendation

For testing:

- use `Gemini`

For production voice transcription:

- keep Gemini for replies
- use `Google Cloud Speech-to-Text` for voice notes when possible

Why:

- Gemini is fine for testing and demos
- dedicated speech-to-text is usually more stable for real customer voice notes
- Bangladesh voice notes are often noisy, mixed-language, and low-quality

## Bangla and Bangladesh support

This app has been adjusted so Bangladesh is the default path:

- default brand language is `bn-BD`
- default timezone is `Asia/Dhaka`
- the reply prompt pushes Bangla-first behavior
- mixed Bangla-English messages are handled more naturally
- unclear audio can trigger a Bangla clarification reply

Important note:

- Gemini can help with Bangla voice understanding
- for real production traffic, `google_cloud` speech is the safer upgrade for voice notes

## How the app works

When a customer message comes in, the app does this:

1. checks which brand the message belongs to
2. loads that brand's rules, tone, and style examples
3. loads that customer's memory and recent chat history
4. reads any uploaded image, audio, or file attachments
5. transcribes audio if needed
6. recognizes products from images if possible
7. searches the knowledge base
8. asks the LLM to build a reply
9. checks whether the reply is safe enough to send
10. either sends a reply, asks for clarification, or hands off to a human
11. saves the result for future memory and review

## Why this scales

The app is built to grow without rewriting the whole system:

- one API server can serve many brands
- heavy tasks can be queued as jobs
- the job worker is database-backed, so it works on cPanel
- the LLM layer is abstracted, so you can switch providers later
- uploads are stored separately from database records
- business data is isolated by `brand_id`

This means you can start small and scale later.

## Tech stack

- `FastAPI` for the API
- `SQLAlchemy` for database access
- `MariaDB` or MySQL for production data
- `Gemini` for LLM replies and testing
- optional `Google Cloud Speech-to-Text` for better voice transcription
- `Passenger` on cPanel for deployment

## Project Structure (A-Z Audit)

```
Backend/
├── app/                           # Main application package
│   ├── __init__.py               # App initialization
│   ├── cli.py                    # Command-line interface (init-db, create-brand)
│   ├── config.py                 # Settings and environment configuration
│   ├── database.py               # Database initialization and session management
│   ├── json_utils.py             # JSON serialization utilities
│   ├── main.py                   # FastAPI app factory and CORS setup
│   ├── models.py                 # SQLAlchemy ORM models (Brand, Customer, Conversation, etc.)
│   ├── security.py               # Authentication/authorization (X-Platform-Token, X-Brand-Api-Key)
│   │
│   ├── api/                      # REST API layer
│   │   ├── __init__.py
│   │   ├── deps.py               # Dependency injection (auth, brand lookup)
│   │   ├── router.py             # Main API router aggregating all routes
│   │   │
│   │   ├── routes/               # API endpoint implementations (16 route modules)
│   │   │   ├── __init__.py
│   │   │   ├── audit_logs.py     # GET /v1/audit-logs - Event audit trail
│   │   │   ├── bootstrap.py      # GET /bootstrap, GET /overview - Initial app state
│   │   │   ├── brand_prompt_config.py  # GET/PATCH /v1/brands/{id}/prompt-config
│   │   │   ├── brands.py         # /v1/brands/* - Brand CRUD, rules, style examples
│   │   │   ├── conversations.py  # /v1/conversations/* - Conversation mgmt & handoff
│   │   │   ├── customers.py      # /v1/customers/* - Customer profiles & facts
│   │   │   ├── dashboard.py      # /v1/dashboard/* - Analytics & metrics
│   │   │   ├── facebook_pages.py # /v1/facebook-pages/* - FB page credentials
│   │   │   ├── facebook_webhook.py # /v1/facebook/webhook - Meta webhooks
│   │   │   ├── feedback.py       # /v1/feedback/* - QA and correction feedback
│   │   │   ├── health.py         # /health - Health check (public)
│   │   │   ├── jobs.py           # /v1/jobs/* - Background job queue mgmt
│   │   │   ├── knowledge.py      # /v1/knowledge/* - Knowledge base CRUD & search
│   │   │   ├── messages.py       # /v1/messages/* - Message processing (core)
│   │   │   ├── products.py       # /v1/products/* - Product images & recognition
│   │   │   └── uploads.py        # /v1/uploads/* - File attachment handling
│   │   │
│   │   └── schemas/              # Pydantic request/response models (11 schema modules)
│   │       ├── __init__.py
│   │       ├── audit.py          # Audit log schemas
│   │       ├── brands.py         # Brand, rule, style example schemas
│   │       ├── conversations.py  # Conversation schemas
│   │       ├── customers.py      # Customer and fact schemas
│   │       ├── dashboard.py      # Dashboard/stats schemas
│   │       ├── facebook_pages.py # Facebook page schemas
│   │       ├── feedback.py       # Feedback schemas
│   │       ├── jobs.py           # Job queue schemas
│   │       ├── knowledge.py      # Knowledge document schemas
│   │       ├── messages.py       # Message and attachment schemas
│   │       └── products.py       # Product image and recognition schemas
│   │
│   ├── services/                 # Business logic and integrations
│   │   ├── __init__.py
│   │   ├── brand_service.py      # Brand operations and isolation
│   │   ├── facebook_credentials.py # Facebook page credential validation
│   │   ├── facebook_webhooks.py  # Webhook message routing
│   │   ├── jobs.py               # Background job scheduling & processing
│   │   ├── knowledge.py          # Knowledge indexing, chunking, retrieval
│   │   ├── memory.py             # Customer & conversation memory management
│   │   ├── moderation.py         # Safety checks and handoff logic
│   │   ├── orchestrator.py       # Main message flow orchestration
│   │   ├── product_recognition.py # Vision API for product matching
│   │   ├── speech.py             # Voice transcription (Gemini or Google Cloud)
│   │   ├── storage.py            # File operations (uploads, temp storage)
│   │   │
│   │   └── llm/                  # LLM provider abstraction layer
│   │       ├── __init__.py
│   │       ├── base.py           # Abstract LLM interface
│   │       ├── factory.py        # LLM provider factory pattern
│   │       ├── gemini.py         # Gemini provider implementation
│   │       └── mock.py           # Mock provider for testing
│   │
│   └── tests/                    # Unit and integration tests
│       ├── test_api.py           # API endpoint tests
│       ├── test_dashboard_admin.py # Dashboard tests
│       ├── test_facebook_page_credentials.py # Facebook credential validation
│       ├── test_facebook_webhook.py # Webhook processing
│       ├── test_gemini_provider.py # LLM provider tests
│       └── test_json_serialization.py # Serialization tests
│
├── deploy/                       # Deployment configuration
│   └── cpanel-subdomain-root/
│       └── passenger_wsgi.py     # cPanel Passenger WSGI entry point
│
├── docs/                         # Documentation
│   └── WRAPPER_AGENT_GUIDE.md    # Integration wrapper guide
│
├── storage/                      # Runtime file storage (created at startup)
│   ├── product_images/           # Product reference images
│   └── uploads/                  # Customer uploaded files
│
├── templates/                    # Configuration templates
│   └── prompt-config/
│       ├── brand-prompt-config.example.json # Example brand config
│       ├── public_reply_guidelines.bn-BD.example.txt # Bangla reply guidelines
│       └── tone_instructions.bn-BD.example.txt # Bangla tone instructions
│
├── main.py                       # Local development entry point (uvicorn)
├── passenger_wsgi.py             # Production WSGI entry point
├── pytest.ini                    # Pytest configuration
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
├── .env                          # Environment (git-ignored)
├── .gitignore                    # Git ignore rules
└── README.md                     # This file
```

## Backend Component Descriptions

### Core Files

- **main.py** - Local dev entry. Runs `uvicorn` with reload on `0.0.0.0:8000`
- **passenger_wsgi.py** - Production entry for cPanel. Imported by Passenger daemon
- **requirements.txt** - All Python dependencies (FastAPI, SQLAlchemy, Pydantic, etc.)
- **pytest.ini** - Pytest config for running `tests/` suite
- **.env.example** - Template for all required environment variables
- **.env** - Git-ignored local configuration

### App Package Structure

| Module | Purpose |
|--------|---------|
| **app/config.py** | Loads `.env`, defines Settings class, validates required vars |
| **app/database.py** | SQLAlchemy engine, session factory, table creation (`init_db()`) |
| **app/models.py** | All 15+ SQLAlchemy ORM models (Brand, Message, Customer, etc.) |
| **app/security.py** | Token validation (`X-Platform-Token`, `X-Brand-Api-Key`) |
| **app/cli.py** | CLI commands for `init-db`, `create-brand`, `test-llm` |
| **app/main.py** | FastAPI app factory, CORS middleware, lifespan setup |
| **app/json_utils.py** | Custom JSON encoder for dates, UUIDs, enums |

### API Layer (app/api/)

- **router.py** - Main aggregator that includes all 16 route modules with their tags
- **deps.py** - Dependency injection:
  - `get_db()` - Database session
  - `require_platform_access()` - Platform token validation  
  - `get_brand_from_request()` - Brand lookup from headers/params
  - `require_brand_access()` - Brand token validation
  
- **routes/** - 16 route modules, each with FastAPI `APIRouter` instance:
  - Grouped by feature domain (brands, knowledge, messages, products, etc.)
  - All tagged for OpenAPI/Swagger organization

- **schemas/** - 11 Pydantic model modules:
  - Request/response validation
  - Auto-generates OpenAPI schema
  - Separates API contract from database models

### Services Layer (app/services/)

| Service | Responsibility |
|---------|-----------------|
| **orchestrator.py** | Main message flow: receives → searches knowledge → calls LLM → safety checks → returns reply |
| **llm/** | Provider abstraction (Gemini, Google, mock). Handles embeddings, text, vision, audio |
| **knowledge.py** | Document indexing, semantic chunking, vector search using embeddings |
| **memory.py** | Customer facts, conversation summaries, context windowing |
| **moderation.py** | Safety checks, confidence scoring, handoff decisions |
| **product_recognition.py** | Image vision API to match against product catalog |
| **speech.py** | Voice transcription (Gemini or Google Cloud Speech-to-Text) |
| **storage.py** | File I/O: uploads, temp storage, cleanup |
| **jobs.py** | Background job queue (database-backed, no Redis needed) |
| **brand_service.py** | Brand isolation logic, API key rotation |
| **facebook_credentials.py** | Validate FB page token |
| **facebook_webhooks.py** | Route incoming FB webhook events to message processor |



## Database

### Supported Databases

- **MariaDB** (recommended for cPanel)
- **MySQL 8.0+**

### Connection URL Format

```env
# MariaDB (most common on cPanel)
DATABASE_URL=mysql+pymysql://db_user:db_password@localhost:3306/db_name?charset=utf8mb4

# MySQL (any host)
DATABASE_URL=mysql+pymysql://user:password@db.example.com:3306/dbname?charset=utf8mb4
```

**Important:** Use `charset=utf8mb4` for proper Bangla and multi-language support.

### Schema

The app auto-creates all tables on first run via `init_db()` (called in app startup).

Key tables:
- `brands` - Tenant/business records with API keys
- `customers` - Customer profiles with facts
- `conversations` - Conversation threads
- `messages` - Individual messages (input + output)
- `attachments` - Uploaded files
- `knowledge_documents` - Knowledge base documents
- `knowledge_chunks` - Semantic chunks of documents
- `product_images` - Product reference catalog
- `feedback` - QA feedback entries
- `jobs` - Background job queue
- `audit_logs` - Event audit trail
- `facebook_pages` - FB page configurations

---



## Authentication & Security

### API Token Types

| Token | Purpose | Usage | Scope |
|-------|---------|-------|-------|
| **X-Platform-Token** | Admin/platform operations | Header: `X-Platform-Token: your-secret-token` | Create brands, manage rules, audit logs, admin tasks |
| **X-Brand-Api-Key** | Brand runtime operations | Header: `X-Brand-Api-Key: brand_xxxxx` | Process messages, upload files, recognize products, customer ops |
| **None (Public)** | Health check, webhook verification | No auth required | `/health`, `/api/v1/facebook/webhook` (signature validated) |

### Token Sources

- **X-Platform-Token** - Set in `.env` as `PLATFORM_API_TOKEN` (admin secret)
- **X-Brand-Api-Key** - Generated when brand is created. Can be rotated via `POST /v1/brands/{brand_id}/reset-api-key`

### Security Best Practices

1. **Never commit tokens** - Keep `.env` in `.gitignore` ✓
2. **Rotate brand keys** - Use endpoint to regenerate if compromised
3. **Use HTTPS in production** - cPanel supports automatic SSL/Let's Encrypt
4. **Validate origins** - Set `ALLOWED_ORIGINS` to trusted domains (not `*` in production)
5. **Request signing** - Facebook webhooks validated with `X-Hub-Signature-256` HMAC-SHA256



## Key Identifiers & Reusable Values

Understanding these IDs helps you chain API calls correctly:

| ID | Type | Created By | Used For | Example |
|----|----|-----------|----------|---------|
| **brand_id** | Integer | `POST /api/v1/brands` | Tenant isolation; included in all brand operations | `1`, `2`, `3` |
| **X-Brand-Api-Key** | String | Brand creation | Runtime auth for brand operations | `brand_abc123xyz...` |
| **X-Platform-Token** | String | `.env` config | Admin/platform operations | `platform_secret_...` |
| **customer_id** | Integer | Auto-created on first message | Customer profile lookups, fact updates | `101`, `102` |
| **conversation_id** | Integer | Auto-created on first message | Read conversation, handoff, release | `501`, `502` |
| **message_id** | Integer | `POST /api/v1/messages/process` | Feedback submission, tracking | `1001`, `1002` |
| **attachment_id** | String | `POST /api/v1/uploads` | Include in `POST /api/v1/messages/process` | `att_abc123...` |
| **product_image_id** | String | `POST /api/v1/products/images/add` | Delete/update product image | `prod_img_123...` |
| **job_id** | Integer | Any endpoint with `process_async=true` | Track background job status | `10001`, `10002` |
| **document_id** | Integer | `POST /api/v1/knowledge/documents` | Update/reindex/delete knowledge | `201`, `202` |
| **rule_id** | Integer | `POST /api/v1/brands/{brand_id}/rules` | Update/delete brand rule | `1`, `2`, `3` |
| **style_example_id** | Integer | `POST /api/v1/brands/{brand_id}/style-examples` | Update/delete style example | `1`, `2` |

### ID Usage Patterns

```bash
# In URL path parameters
GET /api/v1/brands/1
POST /api/v1/customers/101/facts

# In query parameters
GET /api/v1/customers?brand_id=1

# In request headers
-H "X-Platform-Token: value"
-H "X-Brand-Api-Key: value"

# In JSON body
{"brand_id": 1, "customer_id": 101}

# In multipart form data
-F "brand_id=1"
-F "file=@image.jpg"
```

---



## Recommended First-Time API Flow

For a brand-new integration, follow this sequence:

1. **Create brand** - `POST /api/v1/brands` → save `id` (brand_id) and `api_key` (X-Brand-Api-Key)
2. **Configure tone/prompt** - `PATCH /api/v1/brands/{brand_id}/prompt-config` → set tone, language, guidelines
3. **Add rules** - `POST /api/v1/brands/{brand_id}/rules` → create 3-5 key business rules
4. **Add style examples** - `POST /api/v1/brands/{brand_id}/style-examples` → provide 5-10 approved reply examples  
5. **Add knowledge docs** - `POST /api/v1/knowledge/documents` → upload FAQ, policies, product info
6. **Upload product images** - `POST /api/v1/products/images/add` → train product recognition (3-5 images per product)
7. **Process first message** - `POST /api/v1/messages/process` → test end-to-end flow with sample customer message
8. **Monitor & iterate** - Use `/api/v1/conversations`, `/api/v1/feedback`, `/api/v1/jobs` to review and refine

## Complete API Endpoint Audit (73 Endpoints)

### Endpoint Statistics

| Metric | Count |
|--------|-------|
| **Total Endpoints** | 73 |
| **GET** | 32 |
| **POST** | 26 |
| **PATCH** | 10 |
| **DELETE** | 5 |
| **Public (no auth)** | 2 |
| **Platform token required** | ~45 |
| **Brand token required** | ~26 |

### Authentication Model

```
X-Platform-Token (admin)     - Platform-level operations (brands, admin, audit)
X-Brand-Api-Key (runtime)    - Brand-level operations (messages, uploads, products)
No Auth (public)             - Health, Facebook webhook verification
```

### 1. HEALTH & BOOTSTRAP (Public Endpoints - 2 total)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **GET** | `/health` | `healthcheck` | None | Returns app name, version, environment, LLM provider, speech provider |
| **GET** | `/bootstrap` | `get_bootstrap` | None | Initial app state: session info, settings, brand options, dashboard overview |

### 2. DASHBOARD & OVERVIEW (Platform Token - 3 total)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **GET** | `/api/v1/dashboard/brands` | `list_dashboard_brands` | Platform | All brands with stats (rules, examples, docs, customers, conversations, handoffs, uploads, products) |
| **GET** | `/api/v1/dashboard/overview` | `get_dashboard_overview` | Platform | Comprehensive stats: totals, health, recent jobs, 7-day chart data, brand options |
| **GET** | `/api/overview` | `get_overview` | None | Alias to dashboard overview |

### 3. BRAND MANAGEMENT (Platform Token - 13 total)

#### 3a. Brand CRUD (5 endpoints)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/brands` | `list_brands` | List all active brands (excludes global), ordered by creation date DESC |
| **POST** | `/api/v1/brands` | `create_brand_route` | Create new brand with API key. Returns: `id`, `name`, `slug`, `api_key` (secret) |
| **GET** | `/api/v1/brands/{brand_id}` | `get_brand` | Retrieve single brand by ID with all settings |
| **PATCH** | `/api/v1/brands/{brand_id}` | `update_brand` | Update brand properties (name, settings, metadata) |
| **POST** | `/api/v1/brands/{brand_id}/reset-api-key` | `reset_brand_key` | Rotate/regenerate API key for brand. Returns new key |

#### 3b. Brand Rules (4 endpoints)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/brands/{brand_id}/rules` | `list_rules` | List all brand rules, ordered by priority (lower = first) |
| **POST** | `/api/v1/brands/{brand_id}/rules` | `create_rule` | Create new rule: category, title, content, handoff_on_match, priority |
| **PATCH** | `/api/v1/brands/{brand_id}/rules/{rule_id}` | `update_rule` | Update rule fields |
| **DELETE** | `/api/v1/brands/{brand_id}/rules/{rule_id}` | `delete_rule` | Delete rule |

#### 3c. Brand Style Examples (4 endpoints)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/brands/{brand_id}/style-examples` | `list_style_examples` | List tone/style examples, ordered by priority (lower = first) |
| **POST** | `/api/v1/brands/{brand_id}/style-examples` | `create_style_example` | Create example: title, trigger_text, ideal_reply, notes, priority |
| **PATCH** | `/api/v1/brands/{brand_id}/style-examples/{example_id}` | `update_style_example` | Update style example |
| **DELETE** | `/api/v1/brands/{brand_id}/style-examples/{example_id}` | `delete_style_example` | Delete style example |

### 4. BRAND PROMPT CONFIG (Platform Token or Brand Token - 2 total)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **GET** | `/api/v1/brands/{brand_id}/prompt-config` | `get_prompt_config` | Platform\|Brand | Retrieve tone, language, guidelines, handoff messages |
| **PATCH** | `/api/v1/brands/{brand_id}/prompt-config` | `update_prompt_config` | Platform\|Brand | Update prompt configuration |

### 5. KNOWLEDGE BASE MANAGEMENT (Platform Token - 10 total)

#### 5a. Knowledge Document CRUD (7 endpoints)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **POST** | `/api/v1/knowledge/documents` | `create_document` | Create knowledge doc: brand_id, title, source_type, raw_text, metadata. Optional: process_async |
| **GET** | `/api/v1/knowledge/documents` | `list_documents` | List docs for brand. Query: brand_id, global_only |
| **GET** | `/api/v1/knowledge/documents/{document_id}` | `get_document` | Retrieve single document with chunks |
| **PATCH** | `/api/v1/knowledge/documents/{document_id}` | `update_document` | Update title, raw_text, metadata. Triggers reindex if text changed |
| **DELETE** | `/api/v1/knowledge/documents/{document_id}` | `delete_document` | Delete document and all chunks |
| **POST** | `/api/v1/knowledge/documents/{document_id}/reindex` | `reindex_document` | Manually reindex doc for semantic search. Optional: process_async |
| **POST** | `/api/v1/knowledge/conversation-examples` | `create_conversation_example` | Create doc from approved conversation. Auto-extracts good Q&A pairs |

#### 5b. Knowledge Search & Examples (3 endpoints)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **POST** | `/api/v1/knowledge/search` | `search_documents` | Semantic search: brand_id, query, top_k. Returns best matches with relevance |
| **POST** | `/api/v1/knowledge/manual-conversation-examples` | `create_manual_conversation_example` | Create doc from manual transcript/conversation text |

### 6. MESSAGE PROCESSING (Brand Token or Platform Token - 2 total)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **POST** | `/api/v1/messages/process` | `process_message` | Platform\|Brand | **CORE ENDPOINT**. Main message entry point. Inputs: brand_id, customer_id, conversation_id, channel, text, attachment_ids, metadata. Optional: process_async, simulate. Returns: message_id, reply, confidence, handoff_status |
| **POST** | `/api/v1/messages/{message_id}/feedback` | `create_feedback` | Platform | Create QA feedback: feedback_type (rating/correction), corrected_reply, notes, metadata |

### 7. FILE UPLOADS (Brand Token or Platform Token - 4 total)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **POST** | `/api/v1/uploads` | `upload_attachment` | Platform\|Brand | Upload customer file: brand_id, file (multipart). Detects type: image/audio/document. Returns: attachment_id |
| **GET** | `/api/v1/uploads` | `list_uploads` | Platform | List uploads for brand. Query: brand_id, limit (max 500) |
| **DELETE** | `/api/v1/uploads/{attachment_id}` | `delete_upload` | Platform | Delete upload and file from disk |
| **GET** | `/api/v1/uploads/{attachment_id}/download` | `download_upload` | Platform | Download file by attachment_id |

### 8. PRODUCT RECOGNITION (Brand Token or Platform Token - 5 total)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **POST** | `/api/v1/products/images/add` | `add_product_image` | Platform\|Brand | Upload reference product image: brand_id, product_name, category, metadata, file. Returns: product_image_id |
| **POST** | `/api/v1/products/recognize` | `recognize_product` | Platform\|Brand | Recognize product from customer image: brand_id, customer_text, file. Returns: matched_products, confidence |
| **GET** | `/api/v1/products/images` | `get_product_images` | Platform | Get all product images & groups for brand. Query: brand_id |
| **DELETE** | `/api/v1/products/images/{product_image_id}` | `delete_product_image` | Platform | Delete product image. Query: brand_id |
| **PATCH** | `/api/v1/products/images/{product_image_id}` | `update_product_image` | Platform | Update product image metadata |

### 9. CUSTOMER MANAGEMENT (Platform Token - 6 total)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/customers` | `list_customers` | List customers for brand. Query: brand_id. Ordered by update date DESC |
| **GET** | `/api/v1/customers/{customer_id}` | `get_customer` | Retrieve customer with all facts/attributes |
| **PATCH** | `/api/v1/customers/{customer_id}` | `update_customer` | Update customer profile (name, language, location, metadata) |
| **POST** | `/api/v1/customers/{customer_id}/facts` | `create_customer_fact` | Create fact/attribute: key, value, category, confidence |
| **PATCH** | `/api/v1/customers/{customer_id}/facts/{fact_id}` | `update_customer_fact` | Update customer fact |
| **DELETE** | `/api/v1/customers/{customer_id}/facts/{fact_id}` | `delete_customer_fact` | Delete customer fact |

### 10. CONVERSATION MANAGEMENT (Platform Token - 5 total)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/conversations/summary` | `list_conversation_summaries` | List conversation summaries with last message preview. Query: brand_id |
| **GET** | `/api/v1/conversations` | `list_conversations` | List all conversations for brand with messages & attachments. Query: brand_id. Ordered by update date DESC |
| **GET** | `/api/v1/conversations/{conversation_id}` | `get_conversation` | Retrieve single conversation with full message thread |
| **POST** | `/api/v1/conversations/{conversation_id}/handoff` | `handoff_conversation` | Mark conversation for human ownership. Sets status="handoff". Optional: owner_name, notes |
| **POST** | `/api/v1/conversations/{conversation_id}/release` | `release_conversation` | Release conversation back to AI. Sets status="open" |

### 11. FEEDBACK & QA (Platform Token - 2 total)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/feedback` | `list_feedback` | List feedback events. Optional: brand_id, limit (max 500). Used for QA tracking |
| **PATCH** | `/api/v1/feedback/{feedback_id}` | `update_feedback` | Update feedback: feedback_type, corrected_reply, notes, metadata |

### 12. FACEBOOK INTEGRATION (Mixed Auth - 6 total)

#### 12a. Facebook Webhooks (2 endpoints - Public)

| HTTP | Path | Endpoint | Auth | Description |
|------|------|----------|------|-------------|
| **GET** | `/api/v1/facebook/webhook` | `verify_facebook_webhook` | None | Webhook verification. Query: hub.mode, hub.verify_token, hub.challenge. Returns challenge on valid token |
| **POST** | `/api/v1/facebook/webhook` | `receive_facebook_webhook` | None (signature validated) | Receive & process Facebook events. Validates X-Hub-Signature-256 header. Routes to message processor |

#### 12b. Facebook Page Management (4 endpoints - Platform Token)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/facebook-pages` | `list_facebook_pages` | List FB page automation configs. Optional: brand_id filter |
| **POST** | `/api/v1/facebook-pages` | `create_facebook_page` | Create FB page config: brand_id, page_id, page_name, page_token. Validates credentials |
| **GET** | `/api/v1/facebook-pages/{page_id}` | `get_facebook_page` | Retrieve FB page config with credentials |
| **PATCH** | `/api/v1/facebook-pages/{page_id}` | `update_facebook_page` | Update FB page config & credentials |

### 13. BACKGROUND JOBS (Platform Token - 2 total)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/jobs` | `list_jobs` | List recent jobs. Optional: status_filter (pending/success/error). Returns up to 100 recent |
| **POST** | `/api/v1/jobs/process-pending` | `run_jobs` | Process pending jobs now. Body: limit. Returns jobs processed count |

### 14. AUDIT LOGS (Platform Token - 1 total)

| HTTP | Path | Endpoint | Description |
|------|------|----------|-------------|
| **GET** | `/api/v1/audit-logs` | `list_audit_logs` | List audit trail. Optional: brand_id, conversation_id, event_type. Limit: max 500 |

---



## Local Development Quick Start

```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup configuration
copy .env.example .env
# Edit .env with your settings (Gemini API key, database URL, etc.)

# Initialize database
python -m app.cli init-db

# Create a demo brand
python -m app.cli create-brand --name "Demo Brand" --slug demo-brand

# Start dev server (auto-reload on code changes)
python main.py
```

**Access points:**
- API: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Root: `http://127.0.0.1:8000/` (shows status & links)

---

## Environment Variables

All variables are loaded from `.env` file. Start with `.env.example` and customize.

### Core Configuration

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `APP_NAME` | No | `B2B AI Support API` | Display name in docs |
| `APP_ENV` | Yes | `development` | Environment: `development`, `production`, `testing` |
| `DEBUG` | No | `false` | Enable FastAPI debug mode |
| `ROOT_PATH` | No | `` | API root path (for reverse proxies) |
| `ALLOWED_ORIGINS` | No | `*` | CORS allowed origins (comma-separated) |
| `DEFAULT_TIMEZONE` | No | `Asia/Dhaka` | Default timezone for app behavior |

### Database Configuration

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DATABASE_URL` | **Yes** | - | Connection URL: `mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4` |

### Platform Security

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PLATFORM_API_TOKEN` | **Yes** | - | Admin token for platform operations (generate: `openssl rand -hex 32`) |

### LLM Provider (Gemini or future)

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `LLM_PROVIDER` | No | `gemini` | Currently only `gemini` supported |
| `GEMINI_API_KEY` | **Yes** (if using Gemini) | - | API key from [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Model for chat replies |
| `GEMINI_SUMMARY_MODEL` | No | `gemini-2.5-flash` | Model for conversation summaries |
| `GEMINI_EMBEDDING_MODEL` | No | `gemini-embedding-2-preview` | Model for knowledge embeddings |
| `GEMINI_INLINE_AUDIO_MAX_BYTES` | No | `8000000` | Threshold before using file API |

### Speech Transcription (Voice Notes)

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SPEECH_PROVIDER` | No | `gemini` | Options: `gemini`, `google_cloud` |
| `SPEECH_PRIMARY_LANGUAGE` | No | `bn-BD` | Primary voice language |
| `SPEECH_ALT_LANGUAGES` | No | `bn-BD,en-US,en-GB,hi-IN` | Fallback languages (comma-separated) |
| `SPEECH_LOW_CONFIDENCE_THRESHOLD` | No | `0.65` | If confidence < this, ask clarification (0-1) |
| `UNCLEAR_AUDIO_REPLY_BN` | No | (default Bangla) | Custom Bangla message for unclear audio |
| `UNCLEAR_AUDIO_REPLY_EN` | No | (default English) | Custom English message for unclear audio |
| `GOOGLE_CLOUD_PROJECT_ID` | If `google_cloud` | - | GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | If `google_cloud` | - | Path to service account JSON |

### Knowledge Base Tuning

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `KNOWLEDGE_SCAN_LIMIT` | No | `400` | Max chunks to scan per query |
| `KNOWLEDGE_TOP_K` | No | `5` | Number of best chunks to use in context |

### Message Processing Thresholds

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `HANDOFF_CONFIDENCE_THRESHOLD` | No | `0.55` | Confidence threshold for auto-escalation (0-1) |

### File Uploads

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `UPLOAD_DIR` | No | `storage/uploads` | Directory for storing uploads |
| `MAX_UPLOAD_BYTES` | No | `20000000` | Max file size (bytes) = 20MB |

### Bangla & Bangladesh Support

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `FORCE_BANGLA_REPLY_BY_DEFAULT` | No | `true` | Prefer Bangla unless customer clearly prefers English |

## Recommended `.env` for cPanel production

This is a safe starting point:

```env
APP_NAME=B2B AI Support API
APP_ENV=production
DEBUG=false
ROOT_PATH=
DATABASE_URL=mysql+pymysql://cpaneluser_dbuser:YOUR_PASSWORD@localhost:3306/cpaneluser_dbname?charset=utf8mb4
PLATFORM_API_TOKEN=replace-this-with-a-long-random-secret

LLM_PROVIDER=gemini
GEMINI_API_KEY=replace-with-your-gemini-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_SUMMARY_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2-preview

SPEECH_PROVIDER=gemini
GOOGLE_CLOUD_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=
SPEECH_PRIMARY_LANGUAGE=bn-BD
SPEECH_ALT_LANGUAGES=bn-BD,en-US,en-GB,hi-IN
SPEECH_LOW_CONFIDENCE_THRESHOLD=0.65
GEMINI_INLINE_AUDIO_MAX_BYTES=8000000

FORCE_BANGLA_REPLY_BY_DEFAULT=true
UNCLEAR_AUDIO_REPLY_BN=দুঃখিত, ভয়েস মেসেজটি পরিষ্কারভাবে বুঝতে পারিনি। দয়া করে ছোট করে আবার ভয়েস দিন, অথবা একটি টেক্সট মেসেজ পাঠান।
UNCLEAR_AUDIO_REPLY_EN=Sorry, I could not understand the voice note clearly. Please send a shorter voice note or a text message.

KNOWLEDGE_SCAN_LIMIT=400
KNOWLEDGE_TOP_K=5
HANDOFF_CONFIDENCE_THRESHOLD=0.55
UPLOAD_DIR=storage/uploads
MAX_UPLOAD_BYTES=20000000
ALLOWED_ORIGINS=*
DEFAULT_TIMEZONE=Asia/Dhaka
```

If you later upgrade voice transcription to Google Cloud:

```env
SPEECH_PROVIDER=google_cloud
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/home/yourcpaneluser/keys/google-service-account.json
```

## How to teach the app properly

### A. Teach business facts with knowledge documents

Send documents using:

- `POST /api/v1/knowledge/documents`

Good document topics:

- product catalog
- delivery policy
- return policy
- payment rules
- store hours
- courier information
- size guide
- FAQ

Best practice:

- keep one topic per document
- write plain facts
- avoid long marketing paragraphs
- update old pricing quickly
- use exact names, sizes, colors, locations, and conditions

### B. Teach tone with style examples

Send examples using:

- `POST /api/v1/brands/{brand_id}/style-examples`

Good examples:

- greeting message
- out-of-stock reply
- discount refusal
- apology message
- order delay reply
- handoff reply

Best practice:

- use real approved human replies
- keep examples short and realistic
- do not train on bad or emotional replies

### C. Teach hard rules

Send rules using:

- `POST /api/v1/brands/{brand_id}/rules`

Examples:

- never promise delivery outside listed zones
- never confirm refunds automatically
- hand off when customer threatens legal action
- do not offer discounts above a limit

### D. Teach product recognition with images

Upload product images using:

- `POST /api/v1/products/images/add`

Best practice:

- upload `3` to `5` clear images per product
- use different angles
- include front, side, detail shots if useful
- include metadata like SKU, color, size, and model
- avoid blurry reference photos

Very important:

- this is not LLM fine-tuning
- this is a product image matching system

That is the correct design for changing product catalogs.

### E. Let customer memory grow over time

The app can store useful customer details such as:

- preferred language
- favorite category
- city
- past complaints
- order interest

This happens through conversation updates and summaries.

## Simple usage examples

The numbered examples below reuse the same brand. In these examples, `brand_id=1` means "the brand whose internal ID is `1` in the database."

### 1. Create a brand and save the returned values

You can create a brand from the CLI:

```powershell
python -m app.cli create-brand --name "My Shop" --slug my-shop
```

You can also create it through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/brands \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Shop",
    "slug": "my-shop",
    "default_language": "bn-BD",
    "tone_name": "Helpful sales assistant"
  }'
```

Expected response shape:

```json
{
  "id": 1,
  "name": "My Shop",
  "slug": "my-shop",
  "api_key": "brand_xxxxxxxxx"
}
```

How to use these values:

- `id` is the `brand_id` you reuse later in knowledge, uploads, messages, product images, and list queries.
- `api_key` is the secret you send as `X-Brand-Api-Key` for normal brand-level requests.
- `slug` is a unique text identifier for the brand. It is mainly for human-friendly naming, not for later auth.

If you ever forget the `brand_id`, list brands with `GET /api/v1/brands` using your `X-Platform-Token`.

### 2. Add a hard rule for that brand

```bash
curl -X POST http://127.0.0.1:8000/api/v1/brands/1/rules \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "returns",
    "title": "Refunds need approval",
    "content": "Do not promise a refund until a human agent verifies the order.",
    "handoff_on_match": true,
    "priority": 10
  }'
```

How to use these values:

- The `1` in `/brands/1/rules` is the `brand_id` returned when the brand was created.
- `category` is your own label for organizing rules such as `returns`, `payments`, or `legal`.
- `content` is the actual rule the assistant should follow.
- `handoff_on_match=true` tells the system this rule is serious enough to push the conversation toward human handoff.
- `priority` controls rule order. Lower numbers are checked earlier.

### 3. Add a style example

```bash
curl -X POST http://127.0.0.1:8000/api/v1/brands/1/style-examples \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Greeting for first reply",
    "trigger_text": "Customer asks if a product is available",
    "ideal_reply": "Assalamu alaikum. Yes, this item is available. Please tell me which color or size you need.",
    "notes": "Keep it warm, short, and sales-friendly.",
    "priority": 20
  }'
```

How to use these values:

- `trigger_text` describes the situation where this example should be relevant.
- `ideal_reply` is the approved response style you want the assistant to imitate.
- `notes` is optional extra guidance for reviewers or future editors.
- `priority` works like rule priority. Lower numbers are stronger examples.

### 3A. Update prompt and tone config directly

If you want a wrapper or admin panel to update only the prompt-shaping fields, use:

- `GET /api/v1/brands/{brand_id}/prompt-config`
- `PATCH /api/v1/brands/{brand_id}/prompt-config`

This route accepts:

- `X-Brand-Api-Key`
- or `X-Platform-Token`

Example:

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/brands/1/prompt-config \
  -H "X-Brand-Api-Key: brand_xxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "tone_name": "Natural Bangladeshi sales assistant",
    "tone_instructions": "Reply in everyday Bangladeshi Bangla. Keep replies short, warm, and practical. Avoid robotic wording.",
    "public_reply_guidelines": "Keep most replies within 1 to 3 short sentences. Ask one follow-up question at a time.",
    "fallback_handoff_message": "একজন মানুষ টিমমেট অল্প সময়ের মধ্যে উত্তর দেবে।"
  }'
```

Repo templates you can copy and adapt:

- `templates/prompt-config/brand-prompt-config.example.json`
- `templates/prompt-config/tone_instructions.bn-BD.example.txt`
- `templates/prompt-config/public_reply_guidelines.bn-BD.example.txt`

### 4. Add a knowledge document

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/documents \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "title": "Delivery Policy",
    "source_type": "policy",
    "source_reference": "internal-delivery-policy-v1",
    "raw_text": "Inside Dhaka delivery takes 1-2 days. Outside Dhaka delivery takes 2-4 days.",
    "metadata": {
      "team": "operations"
    },
    "process_async": false
  }'
```

How to use these values:

- `brand_id` links this document to exactly one business. Here, `1` means this knowledge belongs only to brand `1`.
- `title` is a human-readable label so you can recognize the document later.
- `source_type` is a free label such as `faq`, `policy`, `catalog`, or `pricing`.
- `source_reference` is optional and useful when you want to track the original source document or version.
- `raw_text` is the real business knowledge the system will search later.
- `metadata` is optional structured information for your own reporting or filtering.
- `process_async=true` will queue indexing as a background job instead of doing it in the request.

### 5. Search the knowledge base manually

This is useful when you want to test whether a document is searchable before sending live messages.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/search \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "query": "How long does delivery take outside Dhaka?",
    "top_k": 3
  }'
```

How to use these values:

- `brand_id` keeps the search inside one brand's knowledge base.
- `query` is the customer-style question you want to test against the knowledge store.
- `top_k` controls how many top matching chunks come back. The default is `5`.

### 6. Upload a customer attachment

```bash
curl -X POST http://127.0.0.1:8000/api/v1/uploads \
  -H "X-Brand-Api-Key: YOUR_BRAND_API_KEY" \
  -F "brand_id=1" \
  -F "file=@voice-note.ogg"
```

Expected response shape:

```json
{
  "attachment": {
    "id": 7,
    "attachment_type": "audio",
    "original_filename": "voice-note.ogg"
  }
}
```

How to use these values:

- `brand_id=1` means this uploaded file belongs to brand `1`.
- `file=@voice-note.ogg` tells `curl` to upload the local file.
- The returned `attachment.id` is the value you later place inside `attachment_ids` in the message-processing call.
- Use this upload route first whenever a customer sends audio, an image, or another file that should be attached to a message.

### 7. Process a message

Use the same `brand_id` from brand creation here. If you uploaded attachments first, put the returned attachment IDs inside `attachment_ids`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: YOUR_BRAND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "customer_external_id": "fb-user-123",
    "customer_name": "Rahim",
    "conversation_external_id": "conv-1001",
    "channel": "facebook",
    "text": "ডেলিভারি কত দিনে হবে?",
    "attachment_ids": []
  }'
```

This sample shows a text-only message. If the upload step returned `attachment.id = 7`, change `attachment_ids` to `[7]`.

How to use these values:

- `brand_id` says which business should answer this message.
- `customer_external_id` should be the stable customer ID from your source platform. Use the same value again on later messages from the same customer.
- `customer_name` is optional and helps memory and personalization.
- `conversation_external_id` should be the stable thread ID from the source platform. Reuse it for follow-up messages in the same chat thread.
- `channel` is your own channel label such as `facebook`, `whatsapp`, `instagram`, `website`, or `api`.
- `text` is the actual customer message. It can be empty if the message is attachment-only.
- `attachment_ids` must contain attachment IDs returned by the uploads endpoint. Do not put filenames here. If there is no attachment, send an empty array.
- `process_async=true` is also available if you want this request to return a `job_id` instead of waiting for the reply immediately.

### 8. Save feedback on a reply

The message processing response can include `outbound_message_id`. That value is the `message_id` you use here.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages/42/feedback \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "feedback_type": "correction",
    "corrected_reply": "Delivery outside Dhaka usually takes 2-4 days.",
    "notes": "Shorter and more direct reply preferred."
  }'
```

How to use these values:

- `42` is the internal `message_id` of the reply you want to review.
- `feedback_type` is a label such as `correction`, `approval`, or another review tag you want to store.
- `corrected_reply` is optional and useful when a reviewer wants to show the better answer.
- `notes` is optional reviewer context.

### 9. Add a product image for recognition

```bash
curl -X POST http://127.0.0.1:8000/api/v1/products/images/add \
  -H "X-Brand-Api-Key: YOUR_BRAND_API_KEY" \
  -F "brand_id=1" \
  -F "product_name=Blue Panjabi" \
  -F "category=clothing" \
  -F "metadata={\"sku\":\"P-100\",\"color\":\"blue\",\"size\":\"M,L,XL\"}" \
  -F "file=@panjabi-front.jpg"
```

How to use these values:

- `brand_id` says which catalog this product image belongs to.
- `product_name` is the human-readable product name you want returned in matches.
- `category` is a free label such as `clothing`, `shoes`, or `electronics`.
- `metadata` must be valid JSON text because multipart form fields are strings. This is the right place for SKU, color, size, model, or other structured product data.
- `file` must be an image file. Non-image uploads are rejected here.

### 10. Recognize a product from a customer image

```bash
curl -X POST http://127.0.0.1:8000/api/v1/products/recognize \
  -H "X-Brand-Api-Key: YOUR_BRAND_API_KEY" \
  -F "brand_id=1" \
  -F "customer_text=Do you have this in black?" \
  -F "file=@customer-photo.jpg"
```

How to use these values:

- `brand_id` keeps recognition inside one brand's catalog only.
- `customer_text` is optional extra context. It can improve matching or help later orchestration.
- `file` is the customer image you want to compare with the catalog.

### 11. Read customers and conversations

List customers for one brand:

```bash
curl "http://127.0.0.1:8000/api/v1/customers?brand_id=1" \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN"
```

List conversations for one brand:

```bash
curl "http://127.0.0.1:8000/api/v1/conversations?brand_id=1" \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN"
```

How to use these values:

- `brand_id` is sent as a query parameter on these list routes.
- Use the returned `customer_id` or `conversation_id` when opening one specific record later.

### 12. Hand off or release a conversation

Hand off a conversation to a human:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/conversations/15/handoff \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "owner_name": "Senior Agent"
  }'
```

Release it back to AI:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/conversations/15/release \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN"
```

How to use these values:

- `15` is the internal `conversation_id`.
- `owner_name` is optional and lets you record who took over the conversation.

### 13. Process pending jobs

If you used `process_async=true`, run pending jobs like this:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/process-pending \
  -H "X-Platform-Token: YOUR_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 10
  }'
```

How to use these values:

- `limit` is the maximum number of queued jobs to process in this run.
- This route is useful for cron, manual queue draining, or cPanel background processing.

## Voice-note limitations and smooth-workflow plan

### Current realistic limits

- very noisy voice notes can still fail
- very long voice notes will be slower
- mixed Bangla-English works better than rare dialect-heavy speech
- if the customer sends unsupported or strange audio formats, results may vary
- Gemini voice understanding is okay for testing, but not the strongest production speech path

### How the app already helps

- it stores transcript, language, summary, and confidence
- it asks for clarification when audio is not reliable enough
- it tries to preserve original spoken language
- it can keep a Bangla-first customer experience

### Best production upgrade

For voice notes at scale:

- set `SPEECH_PROVIDER=google_cloud`
- add Google Cloud credentials
- keep Gemini for reply generation

That combination is usually smoother.

## Heavy traffic and scaling

If many customers message at once, the app can still work because:

- messages can be queued with `process_async=true`
- jobs are stored in the database
- you can run the job processor repeatedly through cron
- the API stays simpler and lighter

On cPanel, the common pattern is:

1. incoming request saves the work
2. background job processes heavy work
3. cron keeps the queue moving

That is the cPanel-friendly version of scaling.

## Production checklist

Do these before going live:

- set `APP_ENV=production`
- set `DEBUG=false`
- replace the default `PLATFORM_API_TOKEN`
- use a strong Gemini key
- use a real MariaDB database
- make sure `storage/uploads` is writable
- create at least one brand
- upload real knowledge documents
- add brand rules
- add style examples
- add product images
- run `python -m app.cli doctor`
- test voice notes
- test image messages
- set up cron for jobs

## Exact cPanel deployment guide for beginners

This section is written for someone who is new to cPanel.

### Before you start

You need:

- a cPanel hosting account with Python app support
- Git access in cPanel
- MariaDB or MySQL access in cPanel
- your project pushed to GitHub or another Git remote

If you do not see `Application Manager` or `Setup Python App` in cPanel, ask your hosting company to enable Python Passenger apps first. cPanel's own docs note that the Application Manager feature may require your provider to enable it.

### Step 1. Push this project to Git

Put this project in a Git repository first.

Example:

```powershell
git add .
git commit -m "Prepare production deployment"
git push origin main
```

Do not upload your local `.env` file to Git.

### Step 2. Create your database in cPanel

In cPanel:

1. open `MySQL Databases`
2. create a new database
3. create a new database user
4. add that user to the database
5. give the user `ALL PRIVILEGES`

Important:

- cPanel usually adds your account name as a prefix
- for example, if your cPanel username is `shop1`, your final database may become `shop1_b2bai`
- your final database user may become `shop1_aiuser`

So your final `DATABASE_URL` often looks like:

```env
DATABASE_URL=mysql+pymysql://shop1_aiuser:YOUR_PASSWORD@localhost:3306/shop1_b2bai?charset=utf8mb4
```

### Step 3. Clone the repo with cPanel Git Version Control

In cPanel:

1. open `Git Version Control`
2. choose `Create`
3. paste your Git repository URL
4. choose a folder inside your home directory

Recommended folder:

```text
repositories/b2b-ai-support-api
```

Why this folder is good:

- it stays outside `public_html`
- it is easier to manage
- it works well as the Python application root

After the clone finishes, your app files should exist inside that folder.

### Step 4. Create the Python application

Now open either:

- `Application Manager`
- or `Setup Python App`

Your host may show one of these names depending on server setup.

Use these values:

- Application root: the same folder you cloned above
- Startup file: `passenger_wsgi.py`
- Entry point / application object: `application`
- Python version: use the newest stable version your host allows, preferably `3.10+`

If cPanel asks for a URL or domain:

- choose the domain or subdomain where you want the API to live
- a subdomain like `api.yourdomain.com` is a clean choice

If your main site already runs WordPress on LiteSpeed, prefer a dedicated subdomain and keep the Python app outside `public_html`. A physical folder like `public_html/ai` often causes `https://your-domain.com/ai/` to show LiteSpeed `403 Forbidden` while deeper URLs fall back to the WordPress site instead of the Python app.

If your host uses LiteSpeed + CloudLinux and a full subdomain root still does not serve the repo cleanly, copy these repo templates into the subdomain document root and edit the placeholder paths:

- `deploy/cpanel-subdomain-root/passenger_wsgi.py`
- `deploy/cpanel-subdomain-root/.htaccess.example`

That pattern keeps the real app in your Git-managed repo while the subdomain document root only contains a small Passenger shim.

### Step 5. Open cPanel Terminal

In cPanel, open `Terminal`.

The Python app page usually shows the command needed to activate the virtual environment. Use the exact command cPanel gives you.

It often looks something like this:

```bash
source /home/yourcpaneluser/virtualenv/repositories/b2b-ai-support-api/3.11/bin/activate
```

Your path may be different. Use the one shown by cPanel.

### Step 6. Install the Python packages

After activating the virtual environment, run:

```bash
pip install -r requirements.txt
```

Run that from inside your project folder.

### Step 7. Create the `.env` file on the server

Inside your project folder, create a `.env` file.

You can do it from cPanel File Manager or Terminal.

Use the production example from the section above and fill in:

- your database info
- your platform token
- your Gemini key

For first deployment, keep this:

```env
SPEECH_PROVIDER=gemini
```

Later, when you are ready for stronger voice-note transcription, switch to:

```env
SPEECH_PROVIDER=google_cloud
```

### Step 8. Initialize the database

In Terminal, inside the project folder:

```bash
python -m app.cli init-db
```

This creates the tables.

### Step 9. Run the health checker

Still in Terminal:

```bash
python -m app.cli doctor
```

This command checks:

- whether the database connects
- whether your upload folder is writable
- whether your LLM provider is still on mock mode
- whether important secrets are still placeholders

If it reports problems, fix those before going live.

### Step 10. Create your first brand

Run:

```bash
python -m app.cli create-brand --name "My Shop" --slug my-shop
```

The command prints:

- the brand id
- the brand API key

Save that API key somewhere safe.

### Step 11. Restart the Python app

After setup, restart the app from cPanel if there is a restart button.

If your hosting uses Passenger and does not show a restart button, create or update:

```text
tmp/restart.txt
```

Command:

```bash
mkdir -p tmp
touch tmp/restart.txt
```

That tells Passenger to reload the app.

### Step 12. Add the cron job for background jobs

In cPanel, open `Cron Jobs`.

Add a cron command like this:

```bash
cd /home/yourcpaneluser/repositories/b2b-ai-support-api && /home/yourcpaneluser/virtualenv/repositories/b2b-ai-support-api/3.11/bin/python -m app.cli run-jobs --limit 20
```

Use your real Python virtual environment path and project path.

Recommended schedule for starting:

- every 1 minute

If your hosting plan is very limited, every 2 to 5 minutes is acceptable for early testing.

### Step 13. Test the live app

Open these in the browser:

- `https://your-domain.com/api/health`
- `https://your-domain.com/docs`

You want `/api/health` to return something like:

```json
{
  "status": "ok",
  "app": "B2B AI Support API",
  "env": "production",
  "llm_provider": "gemini",
  "speech_provider": "gemini"
}
```

Then test:

- creating a brand rule
- adding a knowledge document
- sending a text message
- sending a voice note
- sending a product image

## How to update the app later in cPanel

When you change the code locally:

1. commit and push your changes to Git
2. in cPanel, open `Git Version Control`
3. open your repository
4. click `Update from Remote`
5. if `requirements.txt` changed, open Terminal and run `pip install -r requirements.txt`
6. restart the app

Simple restart command:

```bash
mkdir -p tmp
touch tmp/restart.txt
```

You usually do not need cPanel's separate Git deployment feature for this project if the repo folder itself is your live Python app folder.

## Logs and troubleshooting in cPanel

If something goes wrong:

### Check the health route

Open:

- `/api/health`

If it fails, the app may not be starting correctly.

### Check the Python app log

cPanel's Application Manager docs say Python app logs are usually in:

```text
your-app-folder/stderr.log
```

Check that file first.

### Common problems

#### Problem: database connection error

Fix:

- check the exact cPanel database name
- check the exact cPanel database username
- check the password
- make sure the DB user was added to the DB with all privileges
- keep `localhost` as the host unless your provider says otherwise

#### Problem: 401 unauthorized

Fix:

- make sure you are sending `X-Platform-Token` for admin routes
- make sure you are sending `X-Brand-Api-Key` for brand routes

#### Problem: uploads fail

Fix:

- check `MAX_UPLOAD_BYTES`
- make sure `storage/uploads` is writable
- keep files within the hosting size limits

#### Problem: `/ai/` shows LiteSpeed `403 Forbidden` and `/ai/api/health` shows the WordPress site or a WordPress 404 page

Fix:

- your requests are not reaching Passenger or the Python app
- move the Python app source out of `public_html`, for example to `/home/yourcpaneluser/repositories/b2b-ai-support-api`
- if `public_html/ai` exists from an earlier deploy, rename or remove that folder so WordPress and LiteSpeed stop treating `/ai` as a normal web directory
- in cPanel Application Manager, point the app to the real project folder and restart it
- use a dedicated subdomain like `api.yourdomain.com` if possible; it is more reliable than sharing a WordPress domain path
- only set `ROOT_PATH=/ai` if your host really mounts the Python app under `/ai`

#### Problem: the app is on its own subdomain, but `/` shows a directory index, LiteSpeed `403`, or the request hangs even though Python workers start

Fix:

- keep the real repo outside `public_html`, for example `/home/yourcpaneluser/repositories/b2b-ai-support-api`
- put a Passenger shim in the subdomain document root using:
- `deploy/cpanel-subdomain-root/passenger_wsgi.py`
- `deploy/cpanel-subdomain-root/.htaccess.example`
- update the placeholder paths in both files to your real cPanel username, repo path, subdomain document root, and Python virtualenv path
- restart the app or touch `tmp/restart.txt` in the subdomain document root

#### Problem: voice notes are weak

Fix:

- keep messages shorter
- prefer clearer audio formats like `wav`, `mp3`, `m4a`, `ogg`, or `flac`
- later switch `SPEECH_PROVIDER=google_cloud`

#### Problem: replies are too generic

Fix:

- add better knowledge documents
- add real style examples
- add stricter brand rules
- upload clearer product reference images

## Security tips

- never commit your real `.env`
- use a long random `PLATFORM_API_TOKEN`
- rotate keys if they are ever exposed
- keep the app outside `public_html` when possible
- create a separate subdomain for the API
- do not share brand API keys between businesses

Important:

If this repo or your local `.env` ever gets uploaded somewhere public, rotate your Gemini key immediately.

## Testing

Run tests locally:

```powershell
python -m pytest -q
```

Useful local checks:

```powershell
python -m app.cli doctor
python -m app.cli init-db
python -m app.cli create-brand --name "Test" --slug test
```

## Future upgrades you can add later

- broader Facebook media download and outbound delivery support
- WordPress plugin wrapper
- admin dashboard
- live order lookup
- stock lookup
- courier tracking integration
- better audio cleanup before transcription
- stronger moderation rules
- more LLM providers such as OpenAI or others

## References

- cPanel Application Manager docs: https://docs.cpanel.net/cpanel/software/application-manager/132/
- cPanel Passenger docs: https://docs.cpanel.net/knowledge-base/web-services/using-passenger-applications/
- cPanel Git deployment docs: https://docs.cpanel.net/knowledge-base/web-services/guide-to-git-deployment/
- Google Gemini audio docs: https://ai.google.dev/gemini-api/docs/audio
- Google Gemini image docs: https://ai.google.dev/gemini-api/docs/image-understanding
- Google Gemini embeddings docs: https://ai.google.dev/gemini-api/docs/embeddings
- Google Cloud Speech supported languages: https://cloud.google.com/speech/docs/languages
