# Purchase Management System - Architecture Overview

## System Description

A **microservices-based platform** that handles customer purchases through an **event-driven architecture** using **Apache Kafka** for message streaming and **MongoDB** as Database, with **automatic scaling** based on traffic and workload.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Users                              │
│                          (Web Browser)                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                      Kubernetes Ingress                             │
│                   (NGINX Ingress Controller)                        │
│                                                                     │
│   Routes:                                                           │
│   - http://localhost         → Frontend Service                     │
│   - http://api.localhost     → Customer Facing Service              │
└──────────────┬──────────────────────────┬───────────────────────────┘
               │                          │
       ┌───────▼────────┐        ┌────────▼─────────────────┐
       │   Frontend     │        │  Customer Facing Service │
       │   (nginx)      │        │      (Producer)          │
       │                │        │    FastAPI + Kafka       │
       │  - HTML/CSS/JS │◄───────┤                          │
       │  - Static UI   │  API   │  Endpoints:              │
       │  - Port 80     │  Calls │  - POST /buy             │
       └────────────────┘        │  - GET /purchases/{id}   │
                                 │  - GET /items            │
                                 │  - GET /health           │
                                 └──────────┬───────────────┘
                                            │
                                            │ Produce Messages
                                            │
                                 ┌──────────▼───────────────┐
                                 │   Apache Kafka           │
                                 │   Message Broker         │
                                 │                          │
                                 │  Topic: purchases        │
                                 │  Partitions: 3           │
                                 │  Replication: 1          │
                                 └──────────┬───────────────┘
                                            │
                                            │ Consume Messages
                                            │
                                 ┌──────────▼───────────────┐
                                 │  Customer Management API │
                                 │      (Consumer)          │
                                 │   FastAPI + Kafka        │
                                 │                          │
                                 │  Consumes purchases      │
                                 │  Processes messages      │
                                 │  Stores to database      │
                                 └──────────┬───────────────┘
                                            │
                                            │ Write/Read
                                            │
                                 ┌──────────▼───────────────┐
                                 │      MongoDB             │
                                 │   NoSQL Database         │
                                 │                          │
                                 │  Collection: purchases   │
                                 │  Stores: user history    │
                                 └──────────────────────────┘
```

---

## Services

### 1. Frontend (nginx)

**Purpose:** User interface for the platform

**Technology:** 
- nginx:alpine (lightweight web server)
- HTML5, CSS3, JavaScript

**Features:**
- Buy random items
- View purchase history
- Real-time statistics dashboard
- Responsive design (mobile/tablet/desktop)
- Keyboard shortcuts
- Loading states and error handling

**Endpoints Consumed:**
- `POST /buy` - Make a purchase
- `GET /getAllUserBuys/{user_id}` - Get user's purchase history
- `GET /items` - List available items
- `GET /health` - Check system health

**Port:** 80 (internally), exposed via Ingress at `http://localhost`

---

### 2. Customer Facing Service (Producer)

**Purpose:** API gateway for customer interactions, produces purchase events to Kafka

**Technology:**
- Python 3.11
- FastAPI (async web framework)
- aiokafka (async Kafka producer)
- Pydantic (data validation)

**Responsibilities:**
- Accept purchase requests from frontend
- Validate user input
- Select random items from catalog
- Produce messages to Kafka topic
- Proxy requests to Customer Management API
- Health checks

**API Endpoints:**

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/` | GET | Service info | None | Service metadata |
| `/buy` | POST | Make purchase | `{username, user_id}` | Purchase confirmation + Kafka metadata |
| `/getAllUserBuys/{user_id}` | GET | Get user purchases | None | Purchase history with stats |
| `/items` | GET | List available items | None | Array of items |
| `/health` | GET | Health check | None | Service + Kafka status |

**Message Format (Kafka):**
```json
{
  "username": "john_doe",
  "user_id": "user_123",
  "item_name": "Laptop",
  "price": 999.99,
  "timestamp": "2025-12-16T18:00:00Z"
}
```

**Port:** 8000 (internally), exposed via Ingress at `http://localhost/api`

**Autoscaling:**
  - Min: 1 pod, Max: 5 pods
  - HTTP request rate scaling: Scales when there are 100+ pending/queued requests
- Reason: Faster response to traffic spikes, scales on actual demand

**Environment Variables (Changeable via config-map):**
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker address
- `KAFKA_TOPIC` - Topic to produce to (purchases)
- `CUSTOMER_MANAGEMENT_API_URL` - Consumer service URL

---

### 3. Customer Management API (Consumer)

**Purpose:** Consumes purchase events from Kafka and persists to MongoDB

**Technology:**
- Python 3.11
- FastAPI (async web framework)
- aiokafka (async Kafka consumer)
- Motor (async MongoDB driver)
- Pydantic (data validation)

**Responsibilities:**
- Consume messages from Kafka topic
- Validate purchase data
- Store purchases in MongoDB
- Provide purchase history via API
- Handle consumer group coordination
- Graceful shutdown on pod termination

**Consumer Configuration:**
- Consumer Group: `customer-management-group`
- Auto-commit: Enabled
- Max Poll Records: 500
- Session Timeout: 60s

**API Endpoints:**

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/` | GET | Service info | Service metadata |
| `/health` | GET | Health check | Kafka + MongoDB status |
| `/purchases/{user_id}` | GET | Get user purchases | Purchase history with aggregations |

**MongoDB Schema:**
```json
{
  "_id": "ObjectId",
  "username": "john_doe",
  "user_id": "user_123",
  "item_name": "Laptop",
  "price": 999.99,
  "timestamp": "2025-12-16T18:00:00Z",
  "created_at": "2025-12-16T18:00:00.123Z"
}
```

**Port:** 8001 (internal only, not exposed externally)

**Autoscaling:**
- Min: 1 pod, Max: 5 pods
- Metrics: 
  - Kafka lag > 50 messages per pod
  - CPU > 70%
- Reason: Scales based on actual message backlog, more accurate for consumers

**Environment Variables (Changeable via config-map):**
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker address
- `KAFKA_TOPIC` - Topic to consume from (purchases)
- `MONGODB_URI` - MongoDB connection string

