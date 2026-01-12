⏺ Testing the MCP Tool Calls

  To trigger all 4 tools in a single call, say something like:

  Script to follow:

  1. Agent greets you → Say: "Hi, I'm Maya Patel"
  2. Coverage check (triggers check_insurance_coverage):
  → "Do you take Delta Dental PPO for a cleaning?"
  3. Availability check (triggers get_provider_availability):
  → "What times do you have available next Tuesday in San Jose?"
  4. Book appointment (triggers book_appointment):
  → "Book me for the 9am slot. My phone number is 408-555-1234"
  5. SMS confirmation (triggers send_sms):
  → "Yes, please send me a confirmation text"

  ---
  Current Architecture & Data Flow

  ┌─────────────────────────────────────────────────────────────────────────┐
  │                           PHONE CALL FLOW                               │
  └─────────────────────────────────────────────────────────────────────────┘

    Your Phone
        │
        │ 1. Dial +17172971259
        ▼
  ┌──────────┐
  │  Twilio  │
  │  (PSTN)  │
  └────┬─────┘
       │ 2. SIP INVITE to LiveKit
       │    (direct trunk, no webhook)
       ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    LiveKit Cloud                             │
  │  ┌─────────────────────────────────────────────────────┐    │
  │  │  Room: +17172971259_+<your-number>_<id>             │    │
  │  │                                                      │    │
  │  │   ┌──────────────┐      ┌──────────────────────┐   │    │
  │  │   │ SIP          │      │  Agent Container     │   │    │
  │  │   │ Participant  │◄────►│  (health-agent)      │   │    │
  │  │   │ (caller)     │audio │                      │   │    │
  │  │   └──────────────┘      └──────────┬───────────┘   │    │
  │  └────────────────────────────────────┼────────────────┘    │
  └───────────────────────────────────────┼─────────────────────┘
                                          │
       3. Dispatch rule matches           │
          room prefix, spawns agent       │
                                          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    Agent Container                           │
  │                                                              │
  │  ┌────────────────────────────────────────────────────────┐ │
  │  │                    agent.py                             │ │
  │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐ │ │
  │  │  │Deepgram │  │ OpenAI  │  │Deepgram │  │  Silero   │ │ │
  │  │  │  STT    │  │ GPT-4o  │  │  TTS    │  │   VAD     │ │ │
  │  │  └────┬────┘  └────┬────┘  └────┬────┘  └───────────┘ │ │
  │  │       │            │            │                      │ │
  │  │       ▼            ▼            ▼                      │ │
  │  │  [Audio In] → [LLM Decision] → [Audio Out]            │ │
  │  │                    │                                   │ │
  │  │                    │ 4. Tool calls                     │ │
  │  │                    ▼                                   │ │
  │  └────────────────────┼───────────────────────────────────┘ │
  │                       │                                      │
  │  ┌────────────────────▼───────────────────────────────────┐ │
  │  │              MCP Client (mcp_client.py)                 │ │
  │  │  • Retry logic (3 attempts, exponential backoff)        │ │
  │  │  • Metrics tracking                                     │ │
  │  └────────────────────┬───────────────────────────────────┘ │
  │                       │ stdio                                │
  │                       ▼                                      │
  │  ┌────────────────────────────────────────────────────────┐ │
  │  │              MCP Server (mcp_server.py)                 │ │
  │  │  • JSON Schema validation                               │ │
  │  │  • 4 tools exposed via MCP protocol                     │ │
  │  │                                                         │ │
  │  │  ┌──────────────────┐  ┌──────────────────┐           │ │
  │  │  │check_insurance   │  │get_provider      │           │ │
  │  │  │_coverage         │  │_availability     │           │ │
  │  │  └──────────────────┘  └──────────────────┘           │ │
  │  │  ┌──────────────────┐  ┌──────────────────┐           │ │
  │  │  │book_appointment  │  │send_sms          │           │ │
  │  │  └──────────────────┘  └──────────────────┘           │ │
  │  └────────────────────┬───────────────────────────────────┘ │
  │                       │                                      │
  │                       ▼                                      │
  │  ┌────────────────────────────────────────────────────────┐ │
  │  │              tools.py + fixtures/                       │ │
  │  │  • Pydantic validation                                  │ │
  │  │  • Mock data (insurance, providers, slots)              │ │
  │  └────────────────────────────────────────────────────────┘ │
  │                                                              │
  │  ┌────────────────────────────────────────────────────────┐ │
  │  │              AuditLogger (audit.py)                     │ │
  │  │  • Saves JSON artifact per call                         │ │
  │  │  • transcript, intents, slots, tool_trace, outcome      │ │
  │  └────────────────────────────────────────────────────────┘ │
  └──────────────────────────────────────────────────────────────┘

                      (Optional)
                          │
                          ▼
  ┌─────────────────────────────────────────────────────────────┐
  │              Backend Container (server.py)                   │
  │  • GET /health                                               │
  │  • GET /metrics                                              │
  │  • POST /voice/status (Twilio callback)                     │
  └─────────────────────────────────────────────────────────────┘

  ---
  Data Flow Summary
  ┌──────┬──────────────────────────────────────────────────────────┐
  │ Step │                       What Happens                       │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 1    │ You dial Twilio number                                   │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 2    │ Twilio SIP trunk forwards to LiveKit Cloud               │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 3    │ LiveKit dispatch rule creates room, spawns health-agent  │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 4    │ Agent joins room, Deepgram STT transcribes your speech   │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 5    │ GPT-4o decides response + tool calls                     │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 6    │ Tool calls go through MCP Client → MCP Server → tools.py │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 7    │ Deepgram TTS speaks response back                        │
  ├──────┼──────────────────────────────────────────────────────────┤
  │ 8    │ AuditLogger saves JSON artifact when call ends           │
  └──────┴──────────────────────────────────────────────────────────┘
  ---
  Verify MCP is Working

  After a call, check the agent logs for:
  mcp_client_connected
  mcp_tool_call tool=check_insurance_coverage
  mcp_tool_call tool=get_provider_availability

  And check sample_outputs/ for the audit JSON with tool_trace array.