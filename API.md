# TV2Z API — Agent Context

## What is this?
Backend API + background jobs for **TV2Z**, a multi-tenant OTT/streaming platform. Content owners use this to distribute videos, manage subscriptions, and handle payments globally.

## Knowledge Graph
`graph_api/graph.json` — 2,211 nodes, 3,142 edges covering this codebase.

## Stack
- **Runtime**: Node.js 18, Express.js
- **DB**: PostgreSQL (Sequelize ORM), DynamoDB, Redis
- **Cloud**: AWS (S3, Lambda, SQS, SNS, MediaTailor)
- **Payments**: Stripe, Adyen, Apple IAP, Google Play, Samsung
- **Auth**: JWT, Google/Facebook OAuth2

## Entry Points
| File | Purpose |
|------|---------|
| `server.js` | API server |
| `app.js` | AWS Lambda job handler |
| `job_router.js` | Routes 45+ background jobs |

## Request Flow
```
Route → Controller → Service → DAL → Model (DB/Cache)
```

## API Route Groups (`/api/v2/`)
| Route | Purpose |
|-------|---------|
| `/auth` | Login, register, device management, social auth |
| `/assets` | Content: categories, videos, series, live, EPG, search |
| `/persona` | Watchlist, watch history, recommendations |
| `/paywall` | Subscriptions, access control |
| `/payments` | Payment processing & webhooks |
| `/voucher` | Promo/voucher codes |
| `/operators` | Operator-specific operations |

## Key Directories
| Dir | Purpose |
|-----|---------|
| `routes/` | Express route definitions |
| `controllers/` | Request handlers |
| `services/` | Business logic |
| `dal/` | DB/cache queries (PostgreSQL + Redis) |
| `dal_dynamo/` | DynamoDB queries |
| `models/` | 100+ Sequelize models |
| `jobs/` | Background job handlers |
| `middleware/` | JWT auth, validation, app settings |
| `helpers/` | Utils: response format, JWT, Redis, cloud |

## Background Jobs (SQS-driven)
- Payments: webhooks, recurring billing, reminders
- Content: EPG generation, feed ingestion, encoding metadata
- Notifications: push (FCM), email (Mailchimp)
- Analytics: view counters, watch reports
- Media: image processing, Elasticsearch indexing

## Auth Pattern
All protected routes require `Authorization: Bearer <JWT>` header. Middleware validates token and attaches user context.

## Multi-Tenancy
Each operator/tenant has isolated DB connections. App resolves tenant from request context.

## Companion System
This API works alongside a **CMS** (separate repo) used by content operators to manage content, users, and settings.
