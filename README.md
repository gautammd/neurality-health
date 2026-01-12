# Neurality Health Voice Agent

Real-time voice agent using Twilio SIP + LiveKit Agents + MCP tools for healthcare appointment scheduling.

## Call Test

### Phone Number
**[Your Twilio Number]** - Configure after setup

### Test Window
- **Available**: Monday-Friday, 9 AM - 5 PM PST
- **Timezone**: Pacific Standard Time (UTC-8)

### Test Instructions
1. Call the Twilio number above
2. If using a trial account, press any key when prompted
3. Say: *"Hi, I'm Maya Patel. Do you take Delta Dental PPO for a cleaning? Next Tuesday morning in San Jose. My number is 408-555-1234."*
4. Follow the agent's prompts to complete booking

### Expected Flow
1. Agent greets and asks for name
2. You provide info (insurance, appointment type, location, phone)
3. Agent checks insurance coverage
4. Agent finds available slots
5. Agent books appointment
6. Agent sends confirmation SMS

---

## Quick Start (Docker)

### Prerequisites
- Docker & Docker Compose
- Twilio account with Programmable Voice
- LiveKit Cloud account
- OpenAI API key
- Deepgram API key

### Setup

```bash
# Clone the repo
cd neurality_health

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Build and start
make build
make up

# View logs
make logs
```

### Development Mode (hot reload)

```bash
make dev
```

### Run Tests

```bash
make test
```

---

## Quick Start (Local Python)

### Prerequisites
- Python 3.11+
- Same API keys as above

### Installation

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

### Running

```bash
# Terminal 1: Start metrics server
uvicorn server:app --port 8000

# Terminal 2: Start LiveKit agent
python agent.py dev
```

---

## Deploy to Railway

Single container runs both agent and backend via supervisord.

### Setup

1. **Create service**: Railway dashboard → **New Project** → **Deploy from GitHub**
2. **Add environment variables**:
   ```
   LIVEKIT_URL=wss://your-project.livekit.cloud
   LIVEKIT_API_KEY=APIxxxxxxxx
   LIVEKIT_API_SECRET=your_secret
   OPENAI_API_KEY=sk-xxxxxxxx
   DEEPGRAM_API_KEY=xxxxxxxx
   ```
3. **Deploy** - Railway auto-detects Dockerfile and healthcheck

### What Runs

```
┌─────────────────────────────────────────┐
│           Railway Container             │
│                                         │
│  supervisord                            │
│      │                                  │
│      ├── agent.py (LiveKit voice agent) │
│      │       └── MCP server (subprocess)│
│      │                                  │
│      └── server.py (FastAPI backend)    │
│              ├── GET /health            │
│              ├── GET /metrics           │
│              └── POST /voice/status     │
│                                         │
│  Healthcheck: /health on PORT           │
└─────────────────────────────────────────┘
```

---

## Environment Variables

```env
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
TWILIO_SIP_DOMAIN=neurality.sip.twilio.com

# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxx
LIVEKIT_API_SECRET=your_secret
LIVEKIT_SIP_DOMAIN=sip.livekit.cloud

# OpenAI
OPENAI_API_KEY=sk-xxxxxxxx

# Deepgram
DEEPGRAM_API_KEY=xxxxxxxx

# Server
PORT=8000
```

---

## Architecture

```
PSTN Call → Twilio → SIP Trunk → LiveKit Cloud
                                      ↓
                              LiveKit Room
                              (dispatch rule)
                                      ↓
                        LiveKit Agent (health-agent)
                           ↓        ↓        ↓
                        Silero    OpenAI   Deepgram
                         VAD      GPT-4o   STT/TTS
                                      ↓
                              MCP Tool Calls
                     (via mcp_client → mcp_server)
                                      ↓
                        tools.py + fixtures/
                                      ↓
                              Audit JSON
```

### Components

| Component | Purpose |
|-----------|---------|
| FastAPI Server | Handles Twilio voice webhooks, returns TwiML |
| LiveKit Agents | Voice agent framework with VAD, STT, LLM, TTS |
| VoiceAssistant | Orchestrates conversation, handles barge-in |
| FunctionContext | Exposes tools to LLM via function calling |
| Audit Logger | Creates per-call JSON artifacts |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/voice` | POST | Twilio voice webhook (returns TwiML) |
| `/voice/status` | POST | Call status callbacks |
| `/voice/stream` | POST | Alternative: Media Streams webhook |
| `/voice/fallback` | POST | Fallback error handler |
| `/health` | GET | Health check |

---

## MCP Tools

All tools use Pydantic validation and are exposed via OpenAI function calling.

### check_insurance_coverage
```python
Input: { payer, plan, procedure_code, dob? }
Output: { covered, copay_estimate, notes? }
```

### get_provider_availability
```python
Input: { location_id, provider_id, date_range, appointment_type }
Output: { slots: [{ start, end }] }
```

### book_appointment
```python
Input: { patient, provider_id, slot, appointment_type, location_id, idempotency_key }
Output: { confirmation_id, status, reason? }
```

### send_sms
```python
Input: { to, message }
Output: { queued, message_id? }
```

---

## Testing

```bash
# Run all tests
make test

# Or directly
PYTHONPATH=. pytest -v

# With coverage
PYTHONPATH=. pytest --cov=. --cov-report=term-missing
```

### Test Scenarios

1. **Happy Path**: Coverage → Availability → Booking → SMS
2. **Error Path**: Coverage denied, offer cash-pay

---

## Performance

### Targets
- **TTFB**: ≤ 900ms (first byte of TTS audio)
- **Turn Latency P95**: ≤ 2.5s

### Measurement Points
- `ttfb_ms`: Time from user utterance end to first TTS audio byte
- `turn_latency_ms`: Full turn processing time (STT → LLM → TTS)

### How Latency is Measured
1. **Tool latency**: Tracked in `mcp_client.py` - each MCP tool call records `latency_ms`
2. **Audit logs**: Each tool trace includes `duration_ms`
3. **Metrics endpoint**: `GET /metrics` returns aggregated latency stats
4. **Agent logs**: Deepgram STT/TTS report `transcript_delay` in DEBUG logs

### Reliability Features
- **Retries**: 3 attempts with exponential backoff (0.5s, 1s, 1.5s)
- **Circuit Breaker**: Opens after 5 consecutive failures, resets after 30s
- **Idempotency**: `book_appointment` uses `idempotency_key` to prevent duplicates

---

## Project Structure

```
neurality_health/
├── agent.py              # LiveKit voice agent
├── server.py             # FastAPI metrics server
├── mcp_server.py         # MCP server exposing tools
├── mcp_client.py         # MCP client with retry/circuit breaker
├── audit.py              # Audit logging
├── tools.py              # Tool implementations with Pydantic
├── fixtures/             # Mock data
│   ├── __init__.py
│   ├── providers.py      # Provider/location data
│   ├── insurance.py      # Insurance coverage data
│   └── bookings.py       # In-memory booking store
├── prompts/
│   └── manifest.json     # Versioned prompts
├── tests/                # Test suite
├── audits/               # Runtime audit JSON files
├── sample_outputs/       # Example audit artifacts
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── .env.example
├── README.md
└── DESIGN.md
```

---

## Known Limitations

1. **Trial Twilio Account**: Plays verification message; caller must press any key
2. **In-Memory Storage**: Bookings reset on restart (use database for production)
3. **Mock SMS**: SMS is simulated; integrate Twilio Messaging for production
4. **Single Region**: No geo-distribution; add LiveKit regions for global deployment
5. **No Authentication**: Add API keys/JWT for production

---

## License

MIT
