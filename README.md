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

## Twilio + LiveKit SIP Setup

Complete setup guide to connect phone calls to your voice agent.

### Step 1: LiveKit Cloud Setup

1. **Create account** at [cloud.livekit.io](https://cloud.livekit.io)

2. **Create a project** and note your credentials:
   - `LIVEKIT_URL` (e.g., `wss://your-project.livekit.cloud`)
   - `LIVEKIT_API_KEY` (e.g., `APIxxxxxxxx`)
   - `LIVEKIT_API_SECRET`

3. **Configure SIP Inbound Trunk**:
   - Go to **Project Settings** → **SIP**
   - Click **Create Inbound Trunk**
   - Name: `twilio-inbound`
   - Allowed addresses: Leave empty (or add Twilio's IP ranges for security)
   - Click **Create**
   - Note the **SIP URI** (e.g., `sip:xxxxxxxxx@sip.livekit.cloud`)

4. **Create Dispatch Rule** (routes calls to your agent):
   - Go to **SIP** → **Dispatch Rules**
   - Click **Create Dispatch Rule**
   - Name: `health-agent-dispatch`
   - Rule type: **Individual**
   - Room prefix: `call-` (rooms will be named `call-<unique-id>`)
   - Click **Create**

### Step 2: Twilio SIP Trunk Setup

1. **Create account** at [twilio.com](https://www.twilio.com) (trial works)

2. **Buy a phone number**:
   - Go to **Phone Numbers** → **Buy a Number**
   - Choose a number with Voice capability

3. **Create SIP Trunk**:
   - Go to **Elastic SIP Trunking** → **Trunks**
   - Click **Create new SIP Trunk**
   - Name: `livekit-trunk`

4. **Configure Origination** (where Twilio sends calls):
   - In your trunk, go to **Origination**
   - Click **Add new Origination URI**
   - Origination SIP URI: Paste the LiveKit SIP URI from Step 1.3
     ```
     sip:xxxxxxxxx@sip.livekit.cloud
     ```
   - Priority: 10, Weight: 10
   - Click **Add**

5. **Connect Phone Number to Trunk**:
   - In your trunk, go to **Numbers**
   - Click **Add a Number**
   - Select your phone number from Step 2.2

### Step 3: API Keys

1. **OpenAI**: Get API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

2. **Deepgram**: Get API key from [console.deepgram.com](https://console.deepgram.com)

### Step 4: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxx
LIVEKIT_API_SECRET=your_secret
OPENAI_API_KEY=sk-xxxxxxxx
DEEPGRAM_API_KEY=xxxxxxxx
```

### Step 5: Test

1. Start the agent locally:
   ```bash
   python agent.py dev
   ```

2. Call your Twilio phone number

3. The call flow:
   ```
   Your Phone → Twilio → SIP Trunk → LiveKit → Your Agent
   ```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Call doesn't connect | Check Twilio trunk Origination URI matches LiveKit SIP URI |
| Agent doesn't answer | Verify `python agent.py dev` is running and connected |
| No audio | Check Deepgram API key is valid |
| Agent doesn't respond | Check OpenAI API key is valid |

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
│              ├── GET /audits            │
│              └── GET /audits/{filename} │
│                                         │
│  Healthcheck: /health on PORT           │
└─────────────────────────────────────────┘
```

---

## Environment Variables

```env
# LiveKit Cloud (https://cloud.livekit.io)
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
PSTN Call → Twilio SIP Trunk → LiveKit Cloud (Direct, no webhook)
                                      ↓
                              LiveKit SIP Gateway
                              (dispatch rule creates room)
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
                              Audit JSON (sample_outputs/)
```

### Components

| Component | Purpose |
|-----------|---------|
| Twilio SIP Trunk | Routes PSTN calls directly to LiveKit (no webhooks) |
| LiveKit Agents | Voice agent framework with VAD, STT, LLM, TTS |
| VoiceAssistant | Orchestrates conversation, handles barge-in |
| FunctionContext | Exposes tools to LLM via function calling |
| FastAPI Server | Metrics, health checks, audit file downloads |
| Audit Logger | Creates per-call JSON artifacts |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/metrics` | GET | Call analytics from audit files |
| `/audits` | GET | List available audit files |
| `/audits/{filename}` | GET | Download specific audit file |

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

### How Latency is Measured

| Metric | Where Measured | Code Location |
|--------|----------------|---------------|
| `ttfb_ms` | User speech end → Agent speech start | `agent.py:266-269` |
| `turn_latency_ms` | User speech end → Agent speech end | `agent.py:271-274` |
| `tool_latency_ms` | MCP tool call duration | `agent.py` tool methods |

**Measurement flow:**
```
User stops speaking (is_final=True)
    → start_turn() records timestamp
    → agent_speech_started event
    → TTFB = now - start_turn
    → agent_speech_committed event
    → turn_latency = now - start_turn
```

**View metrics:** `GET /metrics` returns:
```json
{
  "latency": {
    "avg_ttfb_ms": 450.2,
    "p95_ttfb_ms": 820.5,
    "target_ttfb_ms": 900,
    "avg_turn_latency_ms": 1850.3,
    "p95_turn_latency_ms": 2400.1,
    "target_p95_turn_ms": 2500
  }
}
```

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
├── sample_outputs/       # Audit JSON files (runtime)
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
