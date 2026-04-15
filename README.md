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

## 📚 Knowledge Base Setup (A-Z Complete Guide)

The knowledge base is the brain of your AI assistant. How you structure it determines response quality. Different business types require different document structures.

### Core Concepts

**What is a Knowledge Document?**
A knowledge document is plain text information that the AI searches through to answer customer questions. The AI finds relevant sections and incorporates them into responses.

**How Does It Work?**
```
Customer asks → AI searches documents → AI finds relevant info → AI generates response
```

When a customer says "Do you have size large?", the AI searches your knowledge documents for size-related information and includes it in the answer.

### Document Structure Principles

1. **One document = One topic** (e.g., "Return Policy" or "Product Catalog")
2. **Use clear headings** so AI understands section boundaries
3. **Keep sentences concise** and informative
4. **Include specifics** (prices, times, names)
5. **Avoid marketing fluff** - facts only

### Type 1: Product-Based Businesses

**Examples**: Fashion stores, Electronics shops, Furniture, Books, Toys

#### Document 1: Product Catalog

```
PRODUCT CATALOG - Electronics Store

LAPTOPS

Dell XPS 13
- Price: $999
- Screen: 13-inch FHD
- Processor: Intel i5-1135G7
- RAM: 8GB DDR4
- Storage: 512GB SSD
- Weight: 1.2 kg
- Warranty: 1 year manufacturer
- Availability: In stock
- Shipping weight: 2 kg

MacBook Air M1
- Price: $1,199
- Screen: 13-inch Retina
- Processor: Apple M1 Chip
- RAM: 8GB unified memory
- Storage: 256GB SSD
- Weight: 1.24 kg
- Warranty: 1 year limited warranty
- Availability: Pre-order only
- Expected delivery: 5-7 business days
- Shipping weight: 2.5 kg

SMARTPHONES

iPhone 14 Pro
- Price: $999
- Screen: 6.1-inch AMOLED
- Storage options: 128GB, 256GB, 512GB, 1TB
- Colors: Space Black, Gold, Silver, Deep Purple
- Camera: 48MP main + 12MP ultra-wide + 12MP telephoto
- Battery life: Up to 26 hours
- Warranty: 1 year limited warranty
- Availability: In stock for black/gold, 2-3 week wait for others
- Shipping weight: 0.5 kg

Samsung Galaxy S23
- Price: $799
- Screen: 6.1-inch Dynamic AMOLED
- Storage: 128GB, 256GB
- Colors: Phantom Black, Cream, Green
- Camera: 50MP main + 12MP ultra-wide + 10MP telephoto
- Battery: 4000 mAh, 25W fast charging
- Warranty: 1 year limited warranty
- Availability: In stock
- Shipping weight: 0.5 kg

ACCESSORIES

USB-C Fast Charger
- Price: $29
- Power: 65W
- Compatible: All phones and laptops with USB-C
- Warranty: 2 years
- Availability: In stock, ships within 24 hours
- Shipping weight: 0.2 kg

Screen Protector (Pack of 2)
- Price: $12
- Fits: iPhone 14 Pro
- Material: Tempered glass
- Features: Anti-fingerprint, anti-glare
- Warranty: Lifetime replacement if defective
- Availability: In stock
- Shipping weight: 0.1 kg
```

#### Document 2: Product Specifications & Compatibility

```
PRODUCT SPECS & COMPATIBILITY - Electronics Store

CHARGER COMPATIBILITY CHART

Apple Devices Compatible with 20W Apple Charger:
- iPhone 12 and later (iPhone 12, 13, 14, 14 Pro)
- iPad Air 5th generation and later
- iPad mini 6th generation and later

Android Devices Compatible with 65W USB-C Charger:
- Samsung Galaxy S22, S23, S24
- Google Pixel 7, 8
- OnePlus 11, 12

SCREEN PROTECTOR COMPATIBILITY

iPhone 14 Pro Protectors:
- Size: 6.1 inches
- Includes: 2 protectors + applicator + cleaning cloth
- Do NOT fit iPhone 14 (non-Pro) - different size
- Do NOT fit iPhone 13 Pro - different dimensions

iPhone 13 Pro Protectors:
- Size: 6.1 inches but different cutouts
- Note: Not compatible with iPhone 14 Pro due to different camera positions

STORAGE EXPANSION

iPhone: Cannot expand storage (no microSD slot)
Samsung Galaxy S23: Cannot expand storage (no microSD slot)

Devices with microSD expansion:
- Samsung Galaxy Note series
- Google Pixel 6a
- OnePlus devices up to OnePlus 11
```

#### Document 3: Pricing & Discounts

```
PRICING INFORMATION - Electronics Store

CURRENT PRICING (Valid until December 31, 2024)

Standard Prices:
- Dell XPS 13: $999
- MacBook Air M1: $1,199
- iPhone 14 Pro: $999
- Samsung Galaxy S23: $799
- Chargers: $29-49
- Accessories: $10-30

BULK DISCOUNTS

Order 5-9 units: 5% discount
Order 10-24 units: 10% discount
Order 25+ units: 15% discount
- Applies to same product only
- Not stackable with other discounts
- Requires business account

STUDENT DISCOUNT

10% off with valid .edu email
- Applies to most products
- Excludes clearance items
- Max 3 devices per year per student

SEASONAL SALES

Black Friday (November 23-27): Up to 30% off
Cyber Monday (November 30): Up to 25% off
Holiday Sales (December 15-25): Up to 20% off
New Year Sale (January 1-15): Up to 15% off

NO COUPONS ACCEPTED
We do not accept external coupon codes or promotional codes.
```

---

### Type 2: Service-Based Businesses

**Examples**: Consulting, Cleaning services, Fitness studios, Hair salons, Legal services

#### Document 1: Service Offerings

```
SERVICES CATALOG - Premium Cleaning Service

RESIDENTIAL CLEANING

Standard Clean
- Duration: 2-3 hours (depends on house size)
- Frequency: Weekly, bi-weekly, or monthly
- Includes: Vacuuming, dusting, mopping floors, cleaning bathrooms, kitchen surfaces
- Does NOT include: Oven interior, carpet shampooing, window exterior
- Price: $100-150 depending on square footage
- Available: Monday-Friday 9AM-5PM, Saturday 9AM-1PM
- Minimum booking: 1 time

Deep Clean
- Duration: 4-6 hours
- Frequency: Quarterly or annually
- Includes: All standard clean services PLUS oven interior, refrigerator, baseboards, inside cabinets
- Does NOT include: Carpet shampooing, window washing, pressure washing
- Price: $250-400 depending on square footage
- Available: Saturday 10AM-6PM, Sunday 1PM-6PM
- Notice required: 48 hours in advance
- Minimum booking: 1 time

Move-In/Move-Out Clean
- Duration: 6-8 hours
- Includes: Deep clean of entire property, wall spots, light fixtures, cabinet interiors
- Price: $500-800 depending on property size
- Available: Weekdays with 72 hours notice
- Includes: Post-cleaning inspection report with photos

COMMERCIAL CLEANING

Office Cleaning (Daily)
- Duration: 1-2 hours per visit
- Frequency: Daily Monday-Friday, or 3x per week
- Includes: Trash removal, floor mopping, restroom cleaning, desk sanitizing
- Price: $300-500 per week
- Available: Evening hours after 5PM
- Minimum contract: 4 weeks

Carpet Cleaning
- Method: Steam cleaning (hot water extraction)
- Duration: 30-60 minutes per 500 sq ft
- Price: $1-2 per square foot
- Includes: Pre-treatment stain removal, deodorizing, protective finish application
- Drying time: 4-8 hours
- Available: Weekdays only
- Notice required: 5 days advance notice
```

#### Document 2: Service Terms & Conditions

```
SERVICE TERMS & CONDITIONS - Premium Cleaning Service

BOOKING & SCHEDULING

How to book:
- Call: 1-800-CLEAN-01
- Online: www.premiumcleaning.com/book
- Hours: Monday-Friday 8AM-6PM EST, Saturday 9AM-3PM EST

Rescheduling:
- Free rescheduling with 48 hours notice
- Charges apply for cancellations with less than 48 hours notice: 50% of service cost
- Holiday reschedules may not be available

PRICING & PAYMENT

Accepted payment: Credit card, debit card, check, ACH transfer
Payment terms: Due within 7 days of service
Late payment fees: $25 per week after due date

Price locks:
- Quotes valid for 30 days
- Annual contracts: Price locked for 12 months
- Price increases apply only to new customers or at contract renewal

GUARANTEES & LIABILITY

Satisfaction guarantee:
- If unsatisfied within 24 hours of service, we will re-clean that area at no charge
- Full refund available within 48 hours if completely unsatisfied

Liability:
- We are not responsible for damages caused by pre-existing conditions
- Coverage for accidental damages up to $500 per incident
- Customers must have contents insurance for valuable items

CANCELLATION POLICY

Less than 48 hours: 50% charge
Less than 24 hours: 100% charge (full service cost)
Holiday/weekend bookings: 72 hours notice required
No-show: Full charge applies
```

#### Document 3: Staff & Expertise

```
PROFESSIONAL TEAM - Premium Cleaning Service

TEAM MEMBERS

Lead Cleaning Specialist - Maria
- Experience: 12 years in residential and commercial cleaning
- Specialties: Deep cleaning, move-ins/outs, difficult stain removal
- Languages: English, Spanish
- Certifications: ISSA Professional Cleaning Specialist
- Available: Monday-Saturday

Cleaner - John
- Experience: 8 years, commercial cleaning focus
- Specialties: Office cleaning, disinfection, large-scale projects
- Certifications: OSHA Safety Certification
- Available: Tuesday-Friday evenings, Saturday

Cleaner - Priya
- Experience: 6 years, residential cleaning
- Specialties: Detail work, pet-friendly cleaning, eco-friendly methods
- Languages: English, Hindi
- Available: Wednesday-Sunday

CERTIFICATIONS & TRAINING

- All staff members are background checked (within last 12 months)
- All team members completed eco-friendly cleaning training
- Chemical safety certification (2024)
- Customer service training (annual)
- CPR certification (some staff members)
```

---

### Type 3: SaaS/Software Services

**Examples**: Project management tools, Analytics platforms, CRM systems, Email software

#### Document 1: Features & Pricing

```
FEATURES & PRICING - ProjectFlow SaaS

PRICING PLANS

Starter Plan - $29/month
- Up to 5 team members
- 10 active projects
- Basic reporting
- Email support
- File storage: 5GB
- Integrations: 3 max
- Best for: Small teams and startups

Professional Plan - $99/month
- Up to 25 team members
- Unlimited active projects
- Advanced reporting + custom dashboards
- Priority email and chat support
- File storage: 100GB
- Integrations: Unlimited
- Timeline and Gantt chart views
- Automated workflows
- Best for: Growing teams

Enterprise Plan - Custom pricing
- Unlimited team members
- Unlimited projects
- Custom reporting and analytics
- Dedicated account manager
- Phone + email support (24/7)
- Unlimited file storage
- Custom integrations
- SSO (Single Sign-On)
- On-premise deployment available
- Best for: Large organizations

All plans include:
- Task management
- Team collaboration
- Basic timeline view
- Email notifications
- Mobile app access
- 30-day free trial (no credit card required)
```

#### Document 2: Integration Catalog

```
INTEGRATIONS AVAILABLE - ProjectFlow SaaS

STARTER PLAN INTEGRATIONS (Choose 3)

Slack
- Send ProjectFlow notifications to Slack
- Create tasks from Slack messages
- Setup time: 5 minutes
- Support: Full documentation available

Google Drive
- Attach Google Drive files to tasks
- View Google Docs directly in ProjectFlow
- Setup time: 2 minutes
- Support: Automatic sync

Zapier
- Connect ProjectFlow to 1000+ apps
- Create complex automation workflows
- Setup time: 10-15 minutes
- Support: Zapier documentation

PROFESSIONAL PLAN INTEGRATIONS (Unlimited)

Everything in Starter plus:

Microsoft Teams
- Notifications to Teams channels
- Bi-directional sync with Teams tasks

Jira Connection
- Sync ProjectFlow tasks with Jira issues
- Real-time updates both directions

Salesforce
- Link customers to projects
- Automated follow-ups

Google Calendar
- View project timelines in Google Calendar
- Block calendar time for milestones

GitHub
- Link code commits to project tasks
- Automated task creation from PRs

Custom API
- REST API with OAuth 2.0
- Webhook support
- Rate limits: 1000 requests/hour

ENTERPRISE INTEGRATIONS

All Professional integrations plus:

SAML Single Sign-On
- Enterprise security standard
- Works with Okta, Azure AD, Google Workspace
- Setup: Dedicated support team assists

Custom Integrations
- Build custom integrations with API
- Dedicated technical account manager
- SLA: 99.9% uptime guaranteed
```

---

### Type 4: Hybrid/Marketplace Business

**Examples**: Food delivery, Ride-sharing, Freelance platforms, Real estate, AirBnB-type services

#### Document 1: Service & Listing Details

```
SERVICE DETAILS & POLICIES - FreshFood Delivery Platform

RESTAURANT PARTNER NETWORK

Restaurant 1: "Pepper's Italian"
- Cuisine: Italian
- Average delivery time: 30-45 minutes
- Delivery fee: $3.99
- Minimum order: $15
- Hours: 11AM-10PM daily
- Rating: 4.7/5 (1,200+ reviews)
- Payment methods: Card, digital wallet
- Special diets: Vegetarian, Gluten-free options available

Restaurant 2: "Spice House"
- Cuisine: Indian, Asian
- Average delivery time: 20-35 minutes
- Delivery fee: $2.99
- Minimum order: $12
- Hours: 12PM-11PM daily, 1PM-11PM Sunday
- Rating: 4.9/5 (2,100+ reviews)
- Payment methods: Card, digital wallet, PayPal
- Special diets: Vegan, Vegetarian, Halal options

DELIVERY ZONES

Zone 1 (Downtown)
- Area: Main street to Riverside (see map)
- Standard delivery time: 15-25 minutes
- Delivery fee: $2.99-3.99
- Coverage: 24/7

Zone 2 (Suburb A)
- Area: Oak Avenue to Park Lane (see map)
- Standard delivery time: 30-45 minutes
- Delivery fee: $4.99-5.99
- Coverage: 10AM-11PM daily

Zone 3 (Suburb B)
- Area: Highway 5 corridor (see map)
- Standard delivery time: 45-60 minutes
- Delivery fee: $6.99
- Coverage: 12PM-10PM daily
- Note: Not available Sundays

DELIVERY OPTIONS

Standard Delivery: 30-60 minutes
Express Delivery: 15-25 minutes (extra $2)
Scheduled Delivery: Choose arrival time (up to 7 days advance)
- Allows planning meals in advance
- No extra charge
- Requires 2-hour window for restaurant preparation
```

#### Document 2: Pricing & Fees

```
PRICING STRUCTURE - FreshFood Delivery Platform

SERVICE FEES BREAKDOWN

Per Order Fees:
- Platform fee: $0.50 per order (transparent charge)
- Delivery fee: Varies by restaurant and zone (see restaurant listing)
- Tip for driver: Optional, recommended 15-20%

Restaurant Prices:
- Prices shown include all restaurant markups
- Same as dine-in prices for most items
- Some restaurants charge 5-10% premium for delivery orders

Discounts & Promotions

First-time user: $5 off first order of $15+
Daily deals: Monday-Friday 2-4 PM, Save 25-40% on select items
Bundle offers: Combo meals save 10-15%
Loyalty program: Earn 1 point per dollar, 100 points = $10 credit

SUBSCRIPTION (Premium Plus)

Monthly plan: $9.99/month
- Free delivery on orders $15+
- 20% off on one order per week
- Early access to daily deals
- Priority customer support
- Cancellable anytime

REFUNDS & CREDITS

Wrong order received: Full refund + $5-10 credit
Very late delivery: Partial refund 25-50% depending on delay
Item missing from order: Refund for that item only
Damaged food: Refund + replacement at no charge
```

---

### Adding Documents via API

```bash
# Example: Add product catalog (Product Business)
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/documents \
  -H "X-Platform-Token: secure-platform-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "title": "Product Catalog - Electronics",
    "source_type": "catalog",
    "raw_text": "PRODUCT CATALOG\n\nDell XPS 13\nPrice: $999\n..."
  }'

# Example: Add service details (Service Business)
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/documents \
  -H "X-Platform-Token: secure-platform-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 2,
    "title": "Cleaning Services",
    "source_type": "services",
    "raw_text": "SERVICES CATALOG\n\nStandard Clean\nDuration: 2-3 hours\n..."
  }'
```

### Best Practices for All Business Types

1. **Keep information current**: Update prices, availability, and policies regularly
2. **Use consistent formatting**: Helps AI understand document structure
3. **Include specifics**: 
   - Exact prices (not "affordable")
   - Exact times (not "fast delivery")
   - Exact features (not "great quality")
4. **Organize logically**: Group related information together
5. **Separate concerns**: Don't mix product info with policy in same document
6. **One document per topic**: Create separate documents for:
   - Pricing (one doc)
   - Policies (one doc)
   - Products/Services (one doc)
   - FAQ or troubleshooting (one doc)

### Document Types to Create

For ANY business, create these documents:

| Document Type | What Goes Here | Priority |
|---|---|---|
| **Catalog/Offerings** | All products/services with details | CRITICAL |
| **Pricing & Discounts** | All prices, discounts, payment terms | CRITICAL |
| **Policies** | Returns, cancellations, guarantees, terms | CRITICAL |
| **FAQ** | Common questions and answers | HIGH |
| **How-To Guides** | Instructions on using products/services | MEDIUM |
| **Technical Specs** | Specifications, compatibility, requirements | MEDIUM |
| **Contact & Hours** | Support hours, contact methods, locations | MEDIUM |

### Testing Your Knowledge Documents

After adding documents, test with real questions:

```bash
# Test 1: Simple product question
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: your-brand-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "customer_external_id": "test-user",
    "conversation_external_id": "test-conv",
    "text": "What is the price of your main product?"
  }'

# Test 2: Policy question
curl -X POST http://127.0.0.1:8000/api/v1/messages/process \
  -H "X-Brand-Api-Key: your-brand-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "customer_external_id": "test-user",
    "conversation_external_id": "test-conv",
    "text": "Can I return something after 30 days?"
  }'
```

**Check the response:**
- ✅ Reply should mention specific info from documents
- ✅ `used_sources` should show which documents were used
- ✅ Confidence score should be 0.7+
- ❌ If generic response with low confidence, add more specific information to documents

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
