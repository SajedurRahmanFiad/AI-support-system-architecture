# Wrapper Agent Guide

This document is meant to be copied into any separate wrapper project that talks to this backend.

It explains:

- what the API does
- how authentication works
- how the reply pipeline works
- how to integrate wrappers safely
- how to customize brand behavior and tone
- what deployment assumptions matter on cPanel/LiteSpeed

Use this as the source of truth for wrapper-building agents.

## 1. What This API Is

This is a multi-tenant B2B customer-support backend built with FastAPI.

It is not a frontend.
It is not a chatbot widget by itself.
It is the main backend that wrappers can call from:

- a website widget
- a WordPress plugin
- Facebook Messenger glue code
- WhatsApp glue code
- a custom dashboard
- a CRM integration
- an internal admin panel

The API handles:

- brand setup
- brand-specific rules and style examples
- knowledge document storage and retrieval
- customer memory
- conversation history
- text message processing
- image and audio attachment analysis
- product image recognition
- reply generation
- human handoff decisions
- async job processing

## 2. Live Base URL

Current live deployment:

- `https://ai.sajedurrahmanfiad.me`

Important route prefixes:

- app root: `/`
- health: `/api/health`
- docs: `/docs`
- versioned API routes: `/api/v1/...`

For wrappers, keep the API base configurable.

Recommended wrapper config:

```env
API_BASE_URL=https://ai.sajedurrahmanfiad.me
PLATFORM_TOKEN=...
BRAND_API_KEY=...
BRAND_ID=...
```

## 3. Authentication Model

There are 2 auth headers:

- `X-Platform-Token`
- `X-Brand-Api-Key`

Platform token is for admin/platform routes.
Brand API key is for normal day-to-day brand operations.

### Platform-token routes

These require `X-Platform-Token`:

- `/api/v1/brands`
- `/api/v1/knowledge/...`
- `/api/v1/customers/...`
- `/api/v1/conversations/...`
- `/api/v1/jobs/...`
- message feedback route

### Brand-level routes

These accept either:

- `X-Brand-Api-Key`
- or `X-Platform-Token`

Brand-level routes:

- `/api/v1/messages/process`
- `/api/v1/uploads`
- `/api/v1/products/...`

### Practical wrapper rule

If the wrapper acts on behalf of one business only, use the brand API key.

If the wrapper is an admin console or platform tool, use the platform token.

## 4. Core Business Objects

### Brand

A brand is one tenant/business.

It stores:

- `id`
- `name`
- `slug`
- `default_language`
- `tone_name`
- `tone_instructions`
- `fallback_handoff_message`
- `public_reply_guidelines`
- `settings_json`
- `active`

### Brand Rule

A hard instruction or policy rule.

Examples:

- never confirm stock unless knowledge says so
- escalate refund disputes
- avoid discussing internal pricing rules

Fields:

- `category`
- `title`
- `content`
- `handoff_on_match`
- `priority`

### Style Example

An approved example of how the brand should reply.

Fields:

- `title`
- `trigger_text`
- `ideal_reply`
- `notes`
- `priority`

This is one of the strongest ways to shape tone.

### Knowledge Document

Business facts and source material.

Examples:

- shipping policy
- product FAQ
- service area details
- exchange policy
- size guide

Documents are chunked and embedded for retrieval.

### Customer

Stores persistent memory about a customer.

Examples:

- language
- city
- summary
- facts extracted from prior conversations

### Conversation

A thread linked to one customer and one brand.

Important fields:

- `status`
- `owner_type`
- `short_summary`
- `external_conversation_id`

### Message

Stores inbound and outbound messages.

Important fields:

- `role`
- `text`
- `status`
- `confidence`
- `handoff_reason`
- `used_sources_json`
- `flags_json`
- `token_usage_json`

### Attachment

Uploaded customer media:

- image
- audio
- file

May later contain:

- transcript
- translated text
- extracted text
- detected language
- summary metadata

### Product Image

A trained reference image used for product matching.

## 5. Main Wrapper Flows

## 5.1 Bootstrap a new brand

1. Create a brand.
2. Save `brand_id` and `api_key`.
3. Add brand rules.
4. Add style examples.
5. Add knowledge documents.
6. Optionally add product reference images.
7. Start sending messages through `/api/v1/messages/process`.

## 5.2 Send a plain text message

1. Wrapper collects customer text.
2. Wrapper sends `POST /api/v1/messages/process`.
3. API returns one of:
   - `send`
   - `clarify`
   - `handoff`
   - `queued`
4. Wrapper displays `reply_text` if present.
5. Wrapper may route to human if status is `handoff`.

## 5.3 Send an image or audio message

1. Wrapper uploads file to `/api/v1/uploads`.
2. Wrapper receives `attachment.id`.
3. Wrapper calls `/api/v1/messages/process` with `attachment_ids`.
4. API analyzes attachment and combines it with customer text.

## 5.4 Async processing

If wrapper wants non-blocking behavior:

1. set `process_async=true` in message payload
2. API returns `{"status":"queued","job_id":...}`
3. a cron or admin job runner must call `/api/v1/jobs/process-pending`
4. wrapper or admin panel can inspect `/api/v1/jobs`

## 6. Important Reply Status Values

The message-processing response can return:

- `send`
- `clarify`
- `handoff`
- `queued`

Meaning:

- `send`: normal AI reply is ready
- `clarify`: AI needs one short follow-up question, often due to unclear audio
- `handoff`: human should take over
- `queued`: async job was created instead of generating an immediate reply

Wrappers should not assume every successful API call means a normal AI answer.

## 7. Health Check

Route:

- `GET /api/health`

Expected response:

```json
{
  "status": "ok",
  "app": "B2B AI Support API",
  "env": "production",
  "llm_provider": "gemini",
  "speech_provider": "gemini"
}
```

Use this for monitoring and wrapper startup checks.

## 8. Brand Management Endpoints

### Create brand

- `POST /api/v1/brands`

Body:

```json
{
  "name": "My Shop",
  "slug": "my-shop",
  "default_language": "bn-BD",
  "tone_name": "Helpful sales assistant",
  "tone_instructions": "Reply in natural Bangladeshi Bangla. Sound warm, practical, and human.",
  "fallback_handoff_message": "একজন মানুষ টিমমেট অল্প সময়ের মধ্যে উত্তর দেবে।",
  "public_reply_guidelines": "Keep replies short. Use respectful Bangla. Do not sound robotic.",
  "settings": {}
}
```

### List brands

- `GET /api/v1/brands`

### Get one brand

- `GET /api/v1/brands/{brand_id}`

### Update brand

- `PATCH /api/v1/brands/{brand_id}`

Only send fields that need to change.

### Read prompt config only

- `GET /api/v1/brands/{brand_id}/prompt-config`

This returns only the prompt-shaping fields:

- `default_language`
- `tone_name`
- `tone_instructions`
- `fallback_handoff_message`
- `public_reply_guidelines`

### Update prompt config only

- `PATCH /api/v1/brands/{brand_id}/prompt-config`

This route accepts either:

- `X-Brand-Api-Key`
- or `X-Platform-Token`

Example body:

```json
{
  "tone_name": "Natural Bangladeshi sales assistant",
  "tone_instructions": "Reply in everyday Bangladeshi Bangla. Keep replies short, warm, and practical. Avoid robotic wording.",
  "public_reply_guidelines": "Keep most replies within 1 to 3 short sentences. Ask one follow-up question at a time.",
  "fallback_handoff_message": "একজন মানুষ টিমমেট অল্প সময়ের মধ্যে উত্তর দেবে।"
}
```

### Rotate brand API key

- `POST /api/v1/brands/{brand_id}/reset-api-key`

## 9. Tone and Behavior Customization

This section matters a lot.

The current reply prompt is assembled from:

- brand name
- default language
- tone name
- tone instructions
- public reply guidelines
- brand rules
- up to 5 style examples
- customer snapshot
- recent conversation
- attachment insights
- retrieved knowledge chunks
- a generic language instruction

### 9.1 Current strongest customization levers

Use these first before changing code:

1. `tone_instructions`
2. `public_reply_guidelines`
3. `brand rules`
4. `style examples`
5. `fallback_handoff_message`
6. knowledge documents
7. `.env` language-related settings

### 9.2 Why Bangla can feel artificial right now

Current code gives only a generic Bangla instruction:

- reply in natural Bangla used in Bangladesh
- mirror Bangla-English mixing naturally

That is helpful, but broad.
If the brand data is weak, the model falls back to safe, generic support language.

Also, only the first 5 style examples are injected into the prompt.
That means the tone is shaped by a very small sample.

### 9.3 Best non-code way to make responses feel natural

Add better Bangla examples.

Do not write abstract instructions only.
Write real examples of:

- greeting
- out-of-stock reply
- delivery time reply
- delayed order reply
- handoff reply
- apology reply
- upsell reply
- refund-policy boundary reply
- image-based product reply
- voice-note reply

Good example:

```json
{
  "title": "Natural Dhaka-style availability reply",
  "trigger_text": "ভাই এইটা আছে?",
  "ideal_reply": "জ্বি ভাই, এটা এখন available আছে। আপনি চাইলে color বা size বললে আমি দ্রুত confirm করে দিচ্ছি।",
  "notes": "Friendly, short, natural mixed Bangla-English, ecommerce style",
  "priority": 10
}
```

Bad example:

```json
{
  "title": "Generic",
  "trigger_text": "Is this available?",
  "ideal_reply": "Yes sir, the product is available. Please let us know if you need anything else.",
  "notes": "Too generic and stiff",
  "priority": 100
}
```

### 9.4 How to write better tone instructions

Make them concrete.

Bad:

- be natural
- be friendly

Better:

- reply in everyday Bangladeshi Bangla, not textbook Bangla
- do not sound like a formal office letter
- keep most replies to 1 to 3 short sentences
- if customer says "bhai", matching with "ji bhai" is okay
- if customer mixes Bangla and English, mirror lightly
- avoid repetitive lines like "আপনাকে জানাচ্ছি যে"
- avoid robotic politeness like "ধন্যবাদ আপনার মূল্যবান মেসেজের জন্য"
- when asking a follow-up question, ask only one
- sound like a competent sales/support person, not an AI assistant

### 9.5 How to use public reply guidelines

Use this field for visible response behavior:

- no emoji
- no bullet points unless user asks
- mention delivery time only if knowledge supports it
- never claim a product is available unless knowledge or catalog implies it
- always mention next step
- end with a short CTA

### 9.6 How to use brand rules

Use rules for must/must-not logic:

- never promise refunds without policy confirmation
- hand off if customer threatens legal action
- hand off if payment dispute appears
- do not discuss internal vendor details
- do not say "guaranteed original" unless product data supports it

### 9.7 How to use knowledge docs

Use knowledge for facts, not tone.

Good knowledge docs:

- delivery policy
- warranty terms
- return rules
- size chart
- service area
- stock explanation rules

Bad knowledge docs:

- vague slogans
- repeated generic marketing lines

### 9.8 Language and audio controls from `.env`

Important environment settings:

- `FORCE_BANGLA_REPLY_BY_DEFAULT`
- `UNCLEAR_AUDIO_REPLY_BN`
- `UNCLEAR_AUDIO_REPLY_EN`
- `SPEECH_PRIMARY_LANGUAGE`
- `SPEECH_ALT_LANGUAGES`

If you dislike the unclear-audio Bangla line, change `UNCLEAR_AUDIO_REPLY_BN`.

### 9.9 What is missing today if you want deeper control

The current code does not yet support:

- brand-specific temperature
- brand-specific top_p
- dynamic style-example retrieval
- banned phrase lists as first-class config
- opening/closing templates as first-class config
- per-brand reply length controls as first-class config
- different prompt templates per channel

If you want more control, the next recommended code upgrades are:

1. add brand fields like:
   - `reply_style_notes`
   - `banned_phrases`
   - `preferred_opening_style`
   - `preferred_closing_style`
   - `max_reply_sentences`
   - `emoji_policy`
2. score style examples by similarity to incoming text instead of always taking the first 5
3. allow Gemini generation config like temperature and top_p
4. support separate prompt profiles per channel like website, messenger, WhatsApp

## 10. Knowledge Endpoints

### Add knowledge document

- `POST /api/v1/knowledge/documents`

Body:

```json
{
  "brand_id": 1,
  "title": "Delivery policy",
  "source_type": "policy",
  "source_reference": "internal-manual",
  "raw_text": "Inside Dhaka delivery takes 24-48 hours. Outside Dhaka usually takes 2-4 days.",
  "metadata": {
    "language": "en"
  },
  "process_async": false
}
```

### List knowledge documents

- `GET /api/v1/knowledge/documents?brand_id=1`

### Search knowledge manually

- `POST /api/v1/knowledge/search`

Body:

```json
{
  "brand_id": 1,
  "query": "How long does delivery take outside Dhaka?",
  "top_k": 5
}
```

## 11. Upload Endpoint

### Upload attachment

- `POST /api/v1/uploads`

Form fields:

- `brand_id`
- `file`

Auth:

- `X-Brand-Api-Key` or `X-Platform-Token`

Response includes `attachment.id`.

Wrappers should save this `attachment.id` and pass it to `/messages/process`.

## 12. Main Message Endpoint

### Route

- `POST /api/v1/messages/process`

### Payload

```json
{
  "brand_id": 1,
  "channel": "website-widget",
  "customer_external_id": "cust_123",
  "customer_name": "Rahim",
  "customer_language": "bn-BD",
  "conversation_external_id": "conv_123",
  "external_message_id": "msg_123",
  "text": "ভাই এটা কবে delivery হবে?",
  "attachment_ids": [],
  "metadata": {
    "customer_profile": {
      "source": "website"
    }
  },
  "process_async": false
}
```

### Response

Example `send`:

```json
{
  "status": "send",
  "conversation_id": 3,
  "customer_id": 5,
  "inbound_message_id": 12,
  "outbound_message_id": 13,
  "reply_text": "জ্বি, ঢাকার বাইরে সাধারণত ২-৪ দিনের মধ্যে delivery হয়ে যায়।",
  "confidence": 0.92,
  "handoff_reason": null,
  "flags": [],
  "used_sources": [
    {
      "chunk_id": 44,
      "document_id": 8,
      "title": "Delivery policy",
      "score": 0.87
    }
  ],
  "customer_updates": {}
}
```

Example `clarify`:

```json
{
  "status": "clarify",
  "reply_text": "দুঃখিত, ভয়েস মেসেজটি পরিষ্কারভাবে বুঝতে পারিনি। ছোট করে আবার বলবেন?",
  "confidence": 0.34,
  "handoff_reason": "Audio was unclear."
}
```

Example `handoff`:

```json
{
  "status": "handoff",
  "reply_text": "একজন মানুষ টিমমেট অল্প সময়ের মধ্যে উত্তর দেবে।",
  "confidence": 0.99,
  "handoff_reason": "Human review required."
}
```

### Important wrapper behaviors

- treat `external_message_id` as an idempotency key
- keep `customer_external_id` stable across messages from the same customer
- keep `conversation_external_id` stable across messages in the same thread
- do not assume `reply_text` always exists
- inspect `status` first
- log `used_sources` for debugging and QA
- store returned internal IDs if you want feedback or admin tooling later

## 13. Product Recognition Endpoints

### Add reference product image

- `POST /api/v1/products/images/add`

Multipart form:

- `brand_id`
- `product_name`
- `category`
- `metadata` as JSON string
- `file`

### Recognize product from customer image

- `POST /api/v1/products/recognize`

Multipart form:

- `brand_id`
- `customer_text`
- `file`

### List product images

- `GET /api/v1/products/images?brand_id=1`

### Delete one product image

- `DELETE /api/v1/products/images/{product_image_id}?brand_id=1`

## 14. Customer and Conversation Admin Endpoints

### Customers

- `GET /api/v1/customers?brand_id=1`
- `GET /api/v1/customers/{customer_id}`

### Conversations

- `GET /api/v1/conversations?brand_id=1`
- `GET /api/v1/conversations/{conversation_id}`
- `POST /api/v1/conversations/{conversation_id}/handoff`
- `POST /api/v1/conversations/{conversation_id}/release`

Use these for:

- admin dashboards
- support review tools
- wrapper debugging
- human takeover workflows

## 15. Feedback Endpoint

### Save QA/correction feedback

- `POST /api/v1/messages/{message_id}/feedback`

Body:

```json
{
  "feedback_type": "correction",
  "corrected_reply": "ঢাকার বাইরে সাধারণত ২-৪ দিনের মধ্যে delivery হয়ে যায়।",
  "notes": "Shorter and more natural Bangla reply preferred.",
  "metadata": {}
}
```

This does not currently retrain the model.
It stores review data for future QA or improvement workflows.

## 16. Async Job Endpoints

### List jobs

- `GET /api/v1/jobs`

Optional:

- `GET /api/v1/jobs?status_filter=pending`

### Process pending jobs

- `POST /api/v1/jobs/process-pending`

Body:

```json
{
  "limit": 20
}
```

Current job kinds:

- `process_message`
- `reindex_document`

## 17. How the Reply Pipeline Works Internally

High-level flow:

1. authenticate request
2. load brand
3. de-duplicate by `external_message_id` if provided
4. get or create customer
5. get or create conversation
6. store inbound message
7. bind uploaded attachments
8. transcribe/analyze attachments
9. infer customer language if possible
10. attempt product recognition for customer images
11. load brand rules and style examples
12. load recent conversation history
13. run moderation / handoff checks
14. retrieve knowledge chunks
15. build prompt
16. call LLM
17. decide `send`, `clarify`, or `handoff`
18. store outbound reply
19. update customer facts and summaries
20. write audit log

## 18. Wrapper Design Recommendations

### Recommended wrapper responsibilities

Wrappers should handle:

- channel-specific authentication
- webhook validation
- platform-specific message formatting
- media download/upload orchestration
- mapping external IDs into stable `customer_external_id` and `conversation_external_id`
- displaying or relaying `reply_text`
- routing handoff cases
- retry logic around temporary failures

### Wrappers should not do

- business-fact inference outside the API
- prompt composition outside the API unless intentional
- customer memory storage outside the API without a reason
- brand-rule enforcement outside the API unless required by channel policy

## 19. Deployment Notes for cPanel

Current production host is cPanel + LiteSpeed + CloudLinux.

Important practical rule:

- normal code updates inside the repo are safe to deploy by `git push` -> cPanel Git pull -> app restart

But there are caveats:

### Safe code-only changes

These should usually work with:

- `git push`
- cPanel `Update from Remote`
- restart app

Examples:

- route logic changes
- prompt changes
- service logic
- validation logic
- new helper modules

### Changes that also need extra server action

1. dependency changes

- if `requirements.txt` changes, run `pip install -r requirements.txt` on the server

2. environment changes

- if `.env` values change, update the server `.env`

3. schema changes to existing tables

- current startup uses `Base.metadata.create_all()`
- that creates missing tables
- it does not safely migrate existing columns/tables
- adding a new table may work
- changing existing columns usually needs manual SQL or a migration step

4. subdomain-root shim changes

- the live LiteSpeed fix uses files in the subdomain document root outside the repo
- repo templates exist in `deploy/cpanel-subdomain-root/`
- if cPanel recreates the app or overwrites docroot files, re-copy those templates with real paths

## 20. If You Want Better Bangla Replies Next

Best next improvements:

1. add 15 to 30 high-quality Bangla style examples
2. rewrite `tone_instructions` to be specific, concrete, and colloquial
3. rewrite `public_reply_guidelines` as short operational rules
4. set a better Bangla `fallback_handoff_message`
5. customize `UNCLEAR_AUDIO_REPLY_BN`
6. optionally upgrade the code to:
   - retrieve matching style examples dynamically
   - allow brand-specific temperature/top_p
   - support richer per-brand prompt fields

## 21. Minimal Example Wrapper Strategy

For a simple wrapper:

1. keep one config file with:
   - `API_BASE_URL`
   - `BRAND_ID`
   - `BRAND_API_KEY`
2. upload media first if any
3. call `/api/v1/messages/process`
4. branch on returned `status`
5. show reply or route to human
6. log `used_sources`, `flags`, and `handoff_reason`

## 22. Final Advice for Agents Working in Wrapper Repos

If you are an agent building a wrapper around this API:

- treat this API as the source of truth for reply generation
- preserve stable external IDs
- respect auth boundaries
- assume replies may be `send`, `clarify`, `handoff`, or `queued`
- do not hardcode brand behavior in the wrapper if it belongs in brand config
- use style examples and tone fields before changing model logic
- if Bangla sounds robotic, improve examples first, then prompt fields, then code
