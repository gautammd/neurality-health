# Design Document: Neurality Health Voice Agent

## Architecture Overview

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PSTN Network                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Twilio Platform                                   │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │  Phone Number    │───▶│  Programmable    │───▶│  SIP Trunk       │      │
│  │  (+1...)         │    │  Voice           │    │  to LiveKit      │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌──────────────────────────────┐    ┌──────────────────────────────────────────┐
│     FastAPI Webhook Server   │    │              LiveKit Cloud               │
│  POST /voice → TwiML         │    │  ┌──────────────────────────────────┐  │
│  <Dial><Sip>room@sip.lk</Sip>│    │  │          SIP Gateway             │  │
└──────────────────────────────┘    │  └──────────────────────────────────┘  │
                                    │                   │                      │
                                    │  ┌────────────────▼─────────────────┐  │
                                    │  │         LiveKit Room              │  │
                                    │  │  (per-call, auto-created)         │  │
                                    │  └────────────────┬─────────────────┘  │
                                    │                   │                      │
                                    │  ┌────────────────▼─────────────────┐  │
                                    │  │     LiveKit Agents Worker        │  │
                                    │  │                                   │  │
                                    │  │  ┌─────────────────────────────┐ │  │
                                    │  │  │      VoiceAssistant         │ │  │
                                    │  │  │  ┌───────┐ ┌──────┐ ┌─────┐│ │  │
                                    │  │  │  │Silero │ │OpenAI│ │Deep ││ │  │
                                    │  │  │  │VAD    │ │GPT-4o│ │gram ││ │  │
                                    │  │  │  └───────┘ └──────┘ └─────┘│ │  │
                                    │  │  └─────────────────────────────┘ │  │
                                    │  │               │                   │  │
                                    │  │  ┌────────────▼────────────────┐ │  │
                                    │  │  │     FunctionContext         │ │  │
                                    │  │  │  (Pydantic-validated tools) │ │  │
                                    │  │  └─────────────────────────────┘ │  │
                                    │  └──────────────────────────────────┘  │
                                    └──────────────────────────────────────────┘
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.11+ | LiveKit Agents is Python-native |
| Voice Agent | LiveKit Agents | VoiceAssistant framework |
| VAD | Silero | Voice activity detection |
| STT | Deepgram Nova-2 | Speech-to-text |
| LLM | OpenAI GPT-4o | Conversation + tool calling |
| TTS | Deepgram Aura | Text-to-speech |
| Webhook | FastAPI | Twilio webhooks |
| Validation | Pydantic | Tool input/output validation |
| Telephony | Twilio + LiveKit SIP | PSTN connectivity |

## Key Architecture Decisions

### 1. LiveKit Agents vs Custom Implementation

**Decision:** Use LiveKit Agents VoiceAssistant instead of custom STT/LLM/TTS orchestration.

**Rationale:**
- VoiceAssistant handles turn-taking, barge-in, audio buffering automatically
- Silero VAD built-in for accurate speech detection
- Plugin system for easy STT/TTS/LLM swapping
- Reduces ~500 lines of custom code to ~100 lines of configuration
- Battle-tested in production

**Tradeoffs:**
- Less control over low-level audio processing
- Tied to LiveKit ecosystem
- Python-only (TypeScript SDK less mature)

### 2. SIP Trunking vs Media Streams

**Decision:** Use Twilio SIP → LiveKit SIP instead of Twilio Media Streams.

**Rationale:**
- SIP is industry standard for telephony
- No custom audio format conversion (LiveKit handles it)
- Better audio quality (native codecs)
- Simpler architecture (no WebSocket bridge)
- LiveKit SIP gateway is fully managed

**Alternative Considered:**
- Twilio Media Streams + custom bridge
- More complex, more code, harder to maintain

### 3. Tool Calling via OpenAI Functions

**Decision:** Use OpenAI function calling with `@llm.ai_callable` decorator.

**Implementation:**
```python
class FunctionContext(llm.FunctionContext):
    @llm.ai_callable(description="Check insurance coverage")
    async def check_insurance_coverage(self, payer: str, plan: str, procedure_code: str) -> str:
        result = execute_tool("check_insurance_coverage", {...})
        return f"Coverage result: {result}"
```

**Rationale:**
- Native integration with GPT-4o
- Type-safe through Pydantic
- Easy to add/remove tools
- Automatic schema generation

### 4. Idempotent Booking

**Decision:** `book_appointment` requires `idempotency_key`.

**Implementation:**
```python
# In fixtures/bookings.py
_idempotency_keys: dict[str, str] = {}  # key -> confirmation_id

def create_booking(..., idempotency_key: str) -> BookingResult:
    if idempotency_key in _idempotency_keys:
        return BookingResult(
            confirmation_id=_idempotency_keys[idempotency_key],
            status="booked",
            reason="Idempotent request - returning existing booking"
        )
    # ... create new booking
```

**Rationale:**
- Network failures can cause duplicate requests
- LLM might retry tool calls
- Patient shouldn't get double-booked

### 5. Structured Audit Logging

**Decision:** Single JSON artifact per call.

**Contents:**
- Full transcript with timestamps
- Detected intents
- Validated slots with confidence
- Complete tool trace (inputs, outputs, timing)
- Final outcome

**Rationale:**
- Compliance (HIPAA audit trails)
- Debugging production issues
- Training data for model improvement

## Scaling to 1,000 Concurrent Calls

### Current Bottlenecks
1. Single LiveKit Agents worker process
2. In-memory booking/session state
3. No horizontal scaling

### Scaling Architecture

```
                    LiveKit Cloud
                 (Managed SIP + SFUs)
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Agent   │     │ Agent   │     │ Agent   │
    │ Worker  │     │ Worker  │     │ Worker  │
    │ Pod 1   │     │ Pod 2   │     │ Pod N   │
    └────┬────┘     └────┬────┘     └────┬────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    │              Redis Cluster               │
    │  • Session state                          │
    │  • Idempotency keys                       │
    │  • Rate limiting                          │
    └─────────────────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    │              PostgreSQL                   │
    │  • Bookings                               │
    │  • Audit logs                             │
    │  • Analytics                              │
    └─────────────────────────────────────────────┘
```

### Scaling Strategies

1. **LiveKit Agents Dispatch**
   - LiveKit Cloud routes calls to available workers
   - Workers register for room name patterns
   - Auto-scaling based on queue depth

2. **Kubernetes Deployment**
   ```yaml
   replicas: 50  # ~20 concurrent calls per pod
   resources:
     cpu: "2"
     memory: "4Gi"
   ```

3. **Database Tier**
   - Replace in-memory fixtures with PostgreSQL
   - Redis for session state and caching
   - Connection pooling (asyncpg)

4. **Queue-Based Processing**
   - Celery/RQ for async tasks (SMS, analytics)
   - Decouple tool execution from call flow

### Estimated Resource Requirements (1k concurrent)

| Component | Instances | vCPU | Memory |
|-----------|-----------|------|--------|
| Agent Workers | 50 | 2 | 4GB |
| Redis | 3 (cluster) | 4 | 16GB |
| PostgreSQL | 2 (primary + replica) | 8 | 32GB |
| LiveKit SFU | Managed | - | - |

## Multi-Tenant Architecture

### Tenant Isolation Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     API Gateway                                  │
│  • JWT validation                                                │
│  • Tenant identification from Twilio number                      │
│  • Rate limiting per tenant                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Tenant Context                                │
│  • tenant_id in every request/log                               │
│  • Row-level security in database                               │
│  • Tenant-specific Twilio numbers                               │
│  • Tenant-specific prompts                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Per-Tenant Configuration

```python
@dataclass
class TenantConfig:
    id: str
    name: str
    twilio_phone_numbers: list[str]
    livekit_api_key: str
    custom_prompts: dict | None
    providers: list[Provider]
    locations: list[Location]
    insurance_plans: dict
    features: TenantFeatures

@dataclass
class TenantFeatures:
    sms_enabled: bool
    max_concurrent_calls: int
```

### Data Partitioning

| Data Type | Strategy |
|-----------|----------|
| Bookings | Tenant ID column + RLS |
| Audit Logs | Separate tables per tenant or partition |
| Providers/Locations | Tenant ID foreign key |
| Real-time State | Redis key prefix: `tenant:{id}:*` |

## HIPAA Readiness Outline

### Technical Safeguards

1. **Encryption**
   - TLS 1.3 for all connections
   - AES-256 encryption at rest
   - Field-level encryption for PHI

2. **Access Control**
   - Role-based access (RBAC)
   - Audit logging of all PHI access
   - Automatic session timeout

3. **Audit Controls**
   - Immutable audit logs
   - Timestamp and user attribution
   - 6-year retention

### Implementation Checklist

- [ ] BAA with Twilio
- [ ] BAA with LiveKit Cloud
- [ ] BAA with Deepgram
- [ ] BAA with OpenAI (or use Azure OpenAI)
- [ ] PHI encryption at rest (use AWS KMS or similar)
- [ ] PII masking in logs (mask phone numbers, names)
- [ ] Access audit logging
- [ ] Minimum necessary data principle
- [ ] Incident response plan
- [ ] Regular security assessments

### PHI Handling in This Implementation

| Component | PHI Exposure | Mitigation |
|-----------|--------------|------------|
| Twilio | Phone numbers, voice | Twilio HIPAA-eligible |
| Deepgram | Voice transcription | Deepgram HIPAA BAA |
| OpenAI | Conversation context | Consider Azure OpenAI |
| LiveKit | Audio streams | LiveKit HIPAA BAA |
| Logs | Masked by default | PII masking in structlog |
| Audit Files | Contains PHI | Encrypt at rest |

## Performance Optimization

### Latency Targets
- **TTFB**: ≤ 900ms (first byte of TTS audio)
- **Turn Latency P95**: ≤ 2.5s

### Optimization Strategies

1. **Streaming Everything**
   - Deepgram STT with interim results
   - GPT-4o streaming responses
   - Deepgram TTS streaming audio

2. **Pre-warming**
   ```python
   def prewarm(proc: JobProcess):
       proc.userdata["vad"] = silero.VAD.load()
   ```

3. **Connection Pooling**
   - Reuse HTTP connections to Deepgram/OpenAI
   - Keep LiveKit rooms warm

4. **Edge Deployment**
   - Deploy agents close to LiveKit SFUs
   - Multi-region for global coverage

## Tradeoffs and Limitations

### Current Implementation

| Aspect | Decision | Tradeoff |
|--------|----------|----------|
| Simplicity | In-memory fixtures | Data lost on restart |
| Framework | LiveKit Agents | Less low-level control |
| LLM | GPT-4o | Higher cost per call |
| Language | Python | TypeScript team may need ramp-up |

### Production Recommendations

1. **Replace in-memory with database**
2. **Add Redis for session/cache**
3. **Consider GPT-4o-mini for cost reduction**
4. **Add circuit breakers for all external calls**
5. **Implement proper HIPAA compliance**
6. **Add comprehensive monitoring (Datadog, etc.)**

---

*Document Version: 2.0.0*
*Last Updated: 2025-01-11*
*Stack: Python + LiveKit Agents*
