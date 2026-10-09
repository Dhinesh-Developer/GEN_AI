# System Architecture Specification

**Role:** Software Architect  
**Project Stack:** Node.js (TypeScript) + Express, PostgreSQL, Prisma ORM, Redis, Docker, Kubernetes.

---

## 1. Components Architecture

The system follows a layered, modular Clean Architecture pattern to ensure separation of concerns, high testability, and clear boundaries between infrastructure, application logic, and domain layers.

```
┌─────────────────────────────────────────────────────────────┐
│                       Client Tier                           │
│              (React.js / Next.js SPA / Mobile)              │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS / JSON
┌──────────────────────────────▼──────────────────────────────┐
│                  API Gateway / Ingress Load Balancer        │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    Application Tier                         │
│                    (Node.js / Express)                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Middleware Layer (Auth, Rate Limiting, Sanitization)  │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ API Routing & Controller Layer                        │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ Core Business Logic / Use Cases Engine                │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ Data Access Layer (Prisma ORM)                        │  │
│  └───────────────────┬───────────────────┬───────────────┘  │
└──────────────────────┼───────────────────┼──────────────────┘
                       │                   │
         ┌─────────────▼──────────┐   ┌────▼─────────────────┐
         │ Relational Database    │   │ Cache & Session Store│
         │      PostgreSQL        │   │        Redis         │
         └────────────────────────┘   └──────────────────────┘
```

* **Client Tier:** Consumes the REST API via HTTPS.
* **API Gateway / Ingress:** Handles TLS termination, IP-based rate limiting, and routing.
* **Application Tier (Node.js/Express):** 
  * *Middleware Layer:* Validates requests, enforces security headers, handles JWT verification.
  * *Controller Layer:* Parses HTTP requests, calls use cases, and serializes responses.
  * *Execution Engine:* Implements core domain logic (input processing, transformations, rule validation).
  * *Data Access Layer:* Communicates with PostgreSQL using Prisma ORM with connection pooling.
* **Data Tier:** PostgreSQL for persistent relational data; Redis for caching, refresh token storage, and rate-limiting counters.

---

## 2. API Endpoints

All APIs adhere to RESTful JSON standards. Standard success response format is `200/201` with a wrapper envelope, and errors return standardized `4xx/5xx` JSON payloads.

### Authentication (`/api/v1/auth`)
* `POST /api/v1/auth/register` - Register a new user.
* `POST /api/v1/auth/login` - Authenticate user, return Access Token and set secure Refresh Token cookie.
* `POST /api/v1/auth/refresh` - Rotate tokens using the secure HTTP-only refresh token.
* `POST /api/v1/auth/logout` - Invalidate active session and clear cookies.

### Users & RBAC (`/api/v1/users`)
* `GET /api/v1/users/profile` - Retrieve authenticated user's profile.
* `PATCH /api/v1/users/profile` - Update profile details.
* `GET /api/v1/users` - Admin-only list of users with pagination and filtering.

### Core Domain Resources (`/api/v1/resources`)
* `POST /api/v1/resources` - Input processing engine entry point (US1). Validates payload, executes business rules, and saves state.
* `GET /api/v1/resources` - Retrieve paginated list of resources.
* `GET /api/v1/resources/:id` - Retrieve a specific resource by ID (with BOLA/IDOR protection).
* `PUT /api/v1/resources/:id` - Update resource (supports optimistic locking via version column).
* `DELETE /api/v1/resources/:id` - Soft delete resource.

---

## 3. Database Design (PostgreSQL / Prisma Schema)

```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}

enum Role {
  USER
  ADMIN
}

model User {
  id           String       @id @default(uuid())
  email        String       @unique
  passwordHash String       @map("password_hash")
  role         Role         @default(USER)
  createdAt    DateTime     @default(now()) @map("created_at")
  updatedAt    DateTime     @updatedAt @map("updated_at")
  resources    Resource[]

  @@map("users")
}

model Resource {
  id        String   @id @default(uuid())
  userId    String   @map("user_id")
  user      User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  data      Json     // Flexible storage for input processing engine payloads
  status    String   @default("PENDING")
  version   Int      @default(1) // For optimistic locking
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  @@index([userId])
  @@map("resources")
}
```

---

## 4. Data Flow (Core Processing Pipeline)

1. **Request Reception:** Client sends a `POST /api/v1/resources` request with a JSON payload and `Authorization: Bearer <token>` header.
2. **Security & Rate Limiting:** API Gateway / Express middleware checks rate limits via Redis and validates the JWT signature.
3. **Validation & Sanitization:** Zod schema validation middleware inspects the payload. Strings are sanitized against XSS/SQLi. If invalid, returns a `400 Bad Request` immediately.
4. **Controller & Execution Logic:** Controller passes sanitized data to the Input Processing Engine.
5. **Database Transaction:** Engine executes business rules, queries/mutates PostgreSQL using Prisma within an ACID transaction (handling optimistic locking via `version` checks).
6. **Response Generation:** 
   * *Success:* Returns HTTP `201 Created` with standard success JSON envelope.
   * *Error:* Caught by global error handling middleware, returning standardized error structure.

---

## 5. Authentication & Security

* **Authentication:** Stateless JWT Access Tokens (short-lived, e.g., 15 minutes) stored in memory on the client side, paired with opaque Refresh Tokens stored in HTTP-only, Secure, SameSite=Strict cookies.
* **Password Hashing:** Argon2id or bcrypt with a high work factor.
* **RBAC:** Middleware inspects the claims of the decoded JWT to enforce role restrictions (`USER`, `ADMIN`) on target routes.
* **BOLA / IDOR Mitigation:** Controllers explicitly check if the authenticated user owns the requested resource ID before executing read/update/delete operations.
* **Rate Limiting:** Redis-backed sliding window rate limiter applied globally and aggressively on `/api/v1/auth/*` endpoints.

---

## 6. Error Handling Strategy

All unhandled exceptions, validation errors, and domain errors are caught by a **Global Error Handling Middleware** to ensure consistent output formatting.

### Standardized Error Payload (`4xx / 5xx`)
```json
{
  "status": "error",
  "code": "VALIDATION_ERROR",
  "message": "Invalid input parameters provided.",
  "details": [
    {
      "field": "data.value",
      "issue": "Expected string, received number"
    }
  ]
}
```

* **400 Bad Request:** Payload schema violations, malformed JSON.
* **401 Unauthorized:** Missing, expired, or invalid JWT tokens.
* **403 Forbidden:** Valid auth token, but insufficient role permissions or IDOR attempt.
* **404 Not Found:** Target resource ID does not exist.
* **409 Conflict:** Concurrent modification detected via optimistic locking.
* **500 Internal Server Error:** Uncaught runtime exceptions, database dropouts (handled gracefully via circuit breakers).

---

## 7. Folder Structure (Clean Architecture / Feature-Based)

```text
src/
├── app.ts                 # Express application setup
├── server.ts              # HTTP server entry point
├── config/
│   ├── env.ts             # Environment variable validation (Zod)
│   └── database.ts        # Prisma client initialization
├── middleware/
│   ├── auth.middleware.ts # JWT verification & RBAC
│   ├── error.middleware.ts# Global error handler
│   └── validate.middleware.ts # Zod request validation
├── modules/
│   ├── auth/
│   │   ├── auth.controller.ts
│   │   ├── auth.service.ts
│   │   └── auth.routes.ts
│   ├── users/
│   │   ├── user.controller.ts
│   │   ├── user.repository.ts
│   │   └── user.routes.ts
│   └── resources/
│       ├── resource.controller.ts
│       ├── resource.service.ts   # Core execution engine
│       ├── resource.repository.ts
│       └── resource.schema.ts    # Zod validation schemas
└── utils/
    ├── logger.ts          # Winston/Pino structured logging
    └── AppError.ts        # Custom operational error class
```

---

## 8. Important Design Decisions

1. **TypeScript across the Stack:** Ensures end-to-end type safety from the Zod input validation schemas down to the Prisma database models.
2. **Stateless Application Tier:** Allows horizontal scaling behind a load balancer in Kubernetes. User sessions are stateless (JWT) or managed externally via Redis.
3. **Optimistic Locking:** Implemented for resource updates (`version` column) to prevent race conditions during concurrent modifications without the performance penalty of pessimistic locking.
4. **Prisma ORM:** Chosen for type-safe database queries, built-in migration management, and native support for PostgreSQL features (JSON columns, relational integrity).