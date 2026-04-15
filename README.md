# B2B AI Support API

This project is a multi-business AI customer support API.

It is built so one central API can serve many businesses, while each business keeps its own:

- knowledge
- tone
- style examples
- customer history
- product image catalog
- rules and handoff settings

The app is API-first. That means this repo gives you the main backend system only. You can later connect it to Facebook, WordPress, Shopify, a custom dashboard, or anything else through wrappers.

This version is prepared for:

- `cPanel` deployment
- `MariaDB` or MySQL
- `Gemini` for low-cost testing
- easy future switching to another LLM provider
- Bangladeshi customer support with Bangla-first behavior

## What this app can do now

- receive customer messages through one API
- keep each business fully separate from every other business
- store customer profiles, facts, summaries, and conversation history
- search a business knowledge base and use that information in replies
- use brand-specific tone rules and reply examples
- understand customer images
- transcribe customer voice notes
- ask for clarification when audio is too unclear
- recognize products from uploaded product images
- save feedback and handoff decisions
- process heavy work in background jobs
- run on cPanel without Redis, Docker, or Kubernetes

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

- it does not include Facebook or WordPress wrappers yet
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

## Project structure

```text
app/
  api/
    routes/            API endpoints
    schemas/           request and response models
  services/
    llm/               provider layer
    knowledge.py       knowledge indexing and search
    memory.py          customer and conversation memory
    moderation.py      safety and handoff checks
    orchestrator.py    main message flow
    product_recognition.py
    speech.py
    jobs.py
    storage.py
  config.py
  database.py
  models.py
  main.py

main.py                local dev entry point
passenger_wsgi.py      cPanel entry point
requirements.txt
```

## Database choice

Since you want cPanel, `MariaDB` is a good choice here.

Use a database URL like this:

```env
DATABASE_URL=mysql+pymysql://db_user:db_password@localhost:3306/db_name?charset=utf8mb4
```

Use `utf8mb4`. That helps with Bangla and mixed-language text.

## Main authentication headers

The app uses two header types:

- `X-Platform-Token`
  Use this for platform-level admin tasks like creating brands or uploading knowledge.
- `X-Brand-Api-Key`
  Use this for normal brand-level operations like processing messages and uploading customer attachments.

## IDs and values you will reuse in later calls

Many requests in this API use values that were created by an earlier request. These are the most important ones:

- `brand_id`
  This is the numeric database ID of one business or tenant. If your brand is `My Shop` and the API returns `"id": 1`, then `1` is the `brand_id` for that business. You use it to keep data isolated so one brand cannot mix with another brand's knowledge, uploads, customers, or product images.
- `X-Brand-Api-Key`
  This is the secret API key for one specific brand. You get it when the brand is created or when the key is rotated. Send it in the request header for day-to-day brand operations.
- `X-Platform-Token`
  This is the platform-wide admin secret from your `.env`. Use it for platform tasks such as creating brands, managing knowledge, listing conversations, and processing job queues.
- `attachment_id`
  This is the ID returned by `POST /api/v1/uploads`. Put that ID inside `attachment_ids` when you later call `POST /api/v1/messages/process`.
- `message_id`
  This is the internal message record ID. You use it when sending feedback to `POST /api/v1/messages/{message_id}/feedback`.
- `customer_id`
  This is the internal customer record ID. You use it when reading one customer with `GET /api/v1/customers/{customer_id}`.
- `conversation_id`
  This is the internal conversation record ID. You use it for reading a conversation or changing handoff state.
- `product_image_id`
  This is the ID returned when you add a product image. You use it if you later delete that product image.
- `job_id`
  This is returned when you set `process_async=true` on some routes. You use it to track queued work in the jobs endpoints.

The same value can appear in different places depending on the route:

- JSON body: `"brand_id": 1`
- multipart form data: `-F "brand_id=1"`
- query string: `GET /api/v1/customers?brand_id=1`
- path parameter: `POST /api/v1/brands/1/rules`

## Recommended first-time API flow

If you are using this API for the first time, the normal order is:

1. Create a brand and save the returned `id` and `api_key`.
2. Use that `id` as `brand_id` in all later calls for that brand.
3. Add brand setup data such as rules, style examples, and knowledge documents.
4. Upload customer files first if a message includes audio, images, or documents.
5. Send the actual customer message to `POST /api/v1/messages/process`.
6. Use conversation, customer, feedback, and jobs endpoints for monitoring and operations.

## Important API routes

Base prefix:

```text
/api
```

### Public route

| Route | What it does | Main inputs |
|---|---|---|
| `GET /api/health` | Quick health check for app, environment, and provider status | No auth, no body |

### Platform and admin routes (`X-Platform-Token`)

| Route | What it does | Main inputs |
|---|---|---|
| `POST /api/v1/brands` | Create a new brand and return its `id` and `api_key` | JSON body with `name`, `slug`, and optional brand settings |
| `GET /api/v1/brands` | List all brands | No body |
| `GET /api/v1/brands/{brand_id}` | Read one brand by numeric ID | Path `brand_id` |
| `PATCH /api/v1/brands/{brand_id}` | Update brand configuration | Path `brand_id`, JSON body with only the fields you want to change |
| `POST /api/v1/brands/{brand_id}/reset-api-key` | Rotate a brand API key | Path `brand_id` |
| `GET /api/v1/brands/{brand_id}/rules` | List hard rules for a brand | Path `brand_id` |
| `POST /api/v1/brands/{brand_id}/rules` | Add one hard rule | Path `brand_id`, JSON body with `category`, `title`, `content`, `handoff_on_match`, `priority` |
| `GET /api/v1/brands/{brand_id}/style-examples` | List saved style examples | Path `brand_id` |
| `POST /api/v1/brands/{brand_id}/style-examples` | Add one approved example reply | Path `brand_id`, JSON body with `title`, `trigger_text`, `ideal_reply`, `notes`, `priority` |
| `POST /api/v1/knowledge/documents` | Add one knowledge document for a brand | JSON body with `brand_id`, `title`, `source_type`, `source_reference`, `raw_text`, `metadata`, `process_async` |
| `GET /api/v1/knowledge/documents?brand_id=1` | List knowledge documents for one brand | Query `brand_id` |
| `POST /api/v1/knowledge/search` | Test or debug knowledge retrieval manually | JSON body with `brand_id`, `query`, `top_k` |
| `POST /api/v1/messages/{message_id}/feedback` | Save correction or QA feedback on an AI reply | Path `message_id`, JSON body with `feedback_type`, `corrected_reply`, `notes`, `metadata` |
| `GET /api/v1/customers?brand_id=1` | List customers for one brand | Query `brand_id` |
| `GET /api/v1/customers/{customer_id}` | Read one customer and its facts | Path `customer_id` |
| `GET /api/v1/conversations?brand_id=1` | List conversations for one brand | Query `brand_id` |
| `GET /api/v1/conversations/{conversation_id}` | Read one conversation with messages and attachments | Path `conversation_id` |
| `POST /api/v1/conversations/{conversation_id}/handoff` | Mark a conversation as human-owned | Path `conversation_id`, optional JSON body with `owner_name` and `notes` |
| `POST /api/v1/conversations/{conversation_id}/release` | Return a handed-off conversation back to AI ownership | Path `conversation_id` |
| `GET /api/v1/jobs` | List recent background jobs | Optional query `status_filter` |
| `POST /api/v1/jobs/process-pending` | Process queued jobs now | JSON body with `limit` |

### Brand runtime routes (`X-Brand-Api-Key` or `X-Platform-Token`)

| Route | What it does | Main inputs |
|---|---|---|
| `POST /api/v1/uploads` | Save one customer attachment and return its `attachment_id` | multipart form with `brand_id` and `file` |
| `POST /api/v1/messages/process` | Main message entry point for text, images, and voice notes | JSON body with `brand_id`, `customer_external_id`, `conversation_external_id`, `channel`, `text`, `attachment_ids`, optional metadata fields |
| `POST /api/v1/products/images/add` | Add one reference image for product recognition | multipart form with `brand_id`, `product_name`, `category`, `metadata`, and `file` |
| `POST /api/v1/products/recognize` | Match a customer image against the brand's product catalog | multipart form with `brand_id`, `customer_text`, and `file` |
| `GET /api/v1/products/images?brand_id=1` | List product images already stored for one brand | Query `brand_id` |
| `DELETE /api/v1/products/images/{product_image_id}?brand_id=1` | Delete one stored product image | Path `product_image_id`, query `brand_id` |

## Local quick start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.cli init-db
python -m app.cli create-brand --name "Demo Brand" --slug demo-brand
python main.py
```

Swagger docs:

- `http://127.0.0.1:8000/docs`

## Environment variables

These are the most important settings in `.env`.

| Variable | What it means in simple words | Example |
|---|---|---|
| `APP_NAME` | App name shown in API docs | `B2B AI Support API` |
| `APP_ENV` | Current environment | `production` |
| `DEBUG` | Turn debug on or off | `false` |
| `DATABASE_URL` | Where the app database lives | `mysql+pymysql://...` |
| `PLATFORM_API_TOKEN` | Secret admin token for platform-level actions | `change-this-now` |
| `LLM_PROVIDER` | Which LLM provider to use right now | `gemini` |
| `GEMINI_API_KEY` | Your Gemini API key | `your-key` |
| `GEMINI_MODEL` | Main Gemini model for replies | `gemini-2.5-flash` |
| `GEMINI_SUMMARY_MODEL` | Gemini model for summaries | `gemini-2.5-flash` |
| `GEMINI_EMBEDDING_MODEL` | Embedding model for knowledge and stronger image matching | `gemini-embedding-2-preview` |
| `SPEECH_PROVIDER` | Voice transcription provider | `gemini` or `google_cloud` |
| `GOOGLE_CLOUD_PROJECT_ID` | Your Google Cloud project id for speech | `my-project-id` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to your Google service account JSON file if using Google Cloud speech | `/home/username/keys/google.json` |
| `SPEECH_PRIMARY_LANGUAGE` | Main expected voice language | `bn-BD` |
| `SPEECH_ALT_LANGUAGES` | Extra languages that may appear in voice notes | `bn-BD,en-US,en-GB,hi-IN` |
| `SPEECH_LOW_CONFIDENCE_THRESHOLD` | If voice confidence falls below this, ask for clarification | `0.65` |
| `GEMINI_INLINE_AUDIO_MAX_BYTES` | Max audio size to send inline before using Gemini file upload | `8000000` |
| `FORCE_BANGLA_REPLY_BY_DEFAULT` | Push Bangla replies unless the customer clearly prefers English | `true` |
| `UNCLEAR_AUDIO_REPLY_BN` | Bangla message sent when audio is unclear | your custom Bangla text |
| `UNCLEAR_AUDIO_REPLY_EN` | English version of the unclear-audio message | your custom English text |
| `KNOWLEDGE_SCAN_LIMIT` | How many knowledge chunks to scan | `400` |
| `KNOWLEDGE_TOP_K` | How many best knowledge chunks to use | `5` |
| `HANDOFF_CONFIDENCE_THRESHOLD` | If reply confidence falls below this, handoff becomes more likely | `0.55` |
| `UPLOAD_DIR` | Where uploaded files are stored | `storage/uploads` |
| `MAX_UPLOAD_BYTES` | Max upload size per file | `20000000` |
| `ALLOWED_ORIGINS` | CORS allow list | `*` |
| `DEFAULT_TIMEZONE` | Default timezone for app behavior | `Asia/Dhaka` |

## Recommended `.env` for cPanel production

This is a safe starting point:

```env
APP_NAME=B2B AI Support API
APP_ENV=production
DEBUG=false
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

- Facebook Messenger webhook wrapper
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
