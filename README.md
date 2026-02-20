# Subnet Compartmentalized Engine-Application System

A robust, compartmentalized system architecture for communication between an **Engine** and an **Application** using a strict **JSON-RPC 2.0** boundary over HTTP.

## Key Features

- **Strict Compartmentalization**: No shared state or direct imports across compartments.
- **JSON-RPC 2.0 Protocol**: Standardized communication using HTTP as the transport layer.
- **Independent Restartability**: Either compartment can be restarted without impacting the runtime state of the other.
- **Advanced Streaming**: Support for SSE (Server-Sent Events) with AnyIO task groups, bounded buffers for backpressure, and per-stream cancellation.
- **Reliable Communication**: Built-in retry logic and error handling managed by the Engine.

## Project Structure

```text
subnet-comp/
├── Makefile                # Automation for setup, run, and test
├── pyproject.toml         # Root configuration
├── shared/                 # Shared JSON-RPC 2.0 wire format models (Zero dependencies)
├── engine/                 # Engine compartment: Orchestration & Thin Client (httpx)
└── app/                    # Application compartment: Business Logic (Starlette)
```

## Getting Started

### Prerequisites

- Python 3.10+
- `make`

### Installation

Setup the local development environment, including a virtual environment and editable installations for all packages:

```bash
make setup
```

### Running the System

1. **Start the Application Server**:

   ```bash
   make run-app
   ```

   The server will start on `http://127.0.0.1:8100`.

2. **Run the Engine Demo**:
   In a separate terminal:

   ```bash
   make run-engine
   ```

   This will execute a demonstration of unary calls and streaming events.

### Manual Verification (curl)

You can verify the RPC endpoint manually:

```bash
curl -s -X POST http://127.0.0.1:8100/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0", "method":"echo", "params":{"msg":"hello"}, "id":1}'
```

## Testing

Run the comprehensive test suite (28+ tests) covering protocol models, app endpoints, engine client, and full integration roundtrips:

```bash
make test
```

## Architecture Overview

1. **Shared**: Defines the standard JSON-RPC 2.0 structures. It ensures both sides speak the same language without sharing logic.
2. **Application**: A Starlette-based server that exposes RPC methods. It manages concurrent streams using AnyIO.
3. **Engine**: A client that orchestrates requests. It handles the complexities of networking, retries, and timeouts, keeping the application logic clean.

---
Designed for reliability, separation of concerns, and modern async Python.
