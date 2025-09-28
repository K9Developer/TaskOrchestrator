# TaskOrchestrator

![Python Version](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/status-experimental-orange)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blueviolet)
![Crypto Stack](https://img.shields.io/badge/crypto-ECC%20%E2%86%92%20AES--EAX-2ea44f)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

A lightweight distributed orchestrator that secures workers with an ECC + AES handshake and fans out CPU-bound hash search tasks across any number of machines.

---

## Highlights

- ⚡ **Pluggable compute** – Add as many workers as you like; task throughput scales with available cores.
- 🔐 **Encrypted sessions** – Each connection performs an ECDH handshake (P-256) and encrypts traffic with AES-EAX.
- 🧩 **Composable tasks** – Package arbitrary input buffers and hash targets into serializable `Task` objects.
- 📡 **Resilient coordination** – The server reassigns outstanding work if a worker disconnects mid-task.

## Project Map

```
TaskOrchestrator/
├── client/
│   ├── main.py           # Worker entry point
│   ├── socket_client.py  # Encrypted socket client
│   └── task.py           # Task data model and CPU worker logic
├── server/
│   ├── main.py           # Orchestrator entry point
│   └── socket_server.py  # Connection management + handshake
└── README.md
```

## Architecture 🧠

### Components

| Component | Role | Key Modules |
|-----------|------|-------------|
| **Server** | Accepts connections, distributes tasks, aggregates results, and measures throughput. | `server/main.py`, `server/socket_server.py` |
| **Worker** | Pulls tasks, optionally expands range-based buffers, runs CPU-bound hash computations, and reports results. | `client/main.py`, `client/socket_client.py`, `client/task.py` |

### Secure handshake flow

1. Server sends `HELLO` with an ephemeral ECC (P-256) public key.
2. Worker responds with its own `HELLO`, reports logical core count, and shares an ECC public key.
3. Both derive a shared secret via ECDH and stretch it into a 256-bit session key with HKDF (SHA-256).
4. A short `OK` exchange verifies both sides before encrypted traffic begins (AES-EAX with a static nonce per session).

### Task lifecycle

1. The server batches raw input data with `Task.get_chunks` into size-aware `Task` objects.
2. Each worker receives a serialized task, optionally expands range strings (e.g., `"0-100"`) into concrete values, and spawns a multiprocessing worker.
3. The worker streams hash comparisons until it finds the expected digest or exhausts the chunk.
4. Results are sent back as `FOUND` (with matching values) or `DONE` (exhausted without a match).
5. The orchestrator updates progress metrics and, if needed, reassigns unfinished work.

## Getting Started

### Prerequisites

- Python 3.12 or newer.
- `pip`
- Networking access between server and worker machines.

Install the Python dependencies on both server and worker hosts:

```powershell
pip install pycryptodome psutil
```

> **Tip:** The worker relies on `multiprocessing`; run it on the same Python version across machines to avoid serialization mismatches.

### 1. Launch the server

```powershell
python .\server\main.py
```

The server listens on `0.0.0.0:8080` by default. After startup, press Enter when prompted to enqueue the default MD5 range task.

### 2. Start one or more workers

```powershell
python .\client\main.py
```

- Update the host/port in `client/main.py` (class `Worker`) if the server runs on a different machine.
- Each worker reports its logical core count; the orchestrator uses this to weight task distribution.

### 3. Monitor progress

- The server console prints task assignments, completion notifications, and observed hash throughput.
- Worker processes log core usage and the status of each assigned task.

## Configuration

| Setting | Location | Notes |
|---------|----------|-------|
| Server host/port | `SocketServer.__init__` in `server/socket_server.py` | Defaults to `0.0.0.0:8080`; change to bind to a specific interface or port. |
| Worker target host/port | `Worker` in `client/main.py` | Set to the server’s reachable address before deployment. |
| Max task chunk size | `MAX_TASK_SIZE` in `server/main.py` | Rough upper bound (in bytes) for serialized task chunks when splitting workloads. |

## Extending the Orchestrator

- **New actions** – Introduce additional hash or compute actions by extending the `Action` enum in `server/main.py` and updating `TaskHandler.cpu_compute_task`.
- **Different task sources** – Replace the default range generator with a custom data source (file reader, database cursor, etc.).
- **Result aggregation** – Store `FOUND` results in a database or message queue instead of printing them.
- **Transport tuning** – Swap AES-EAX for AES-GCM and rotate nonces per message for stronger guarantees.

## Troubleshooting

| Symptom | Likely Cause | Remedy |
|---------|--------------|--------|
| `Invalid handshake` errors | Host/port mismatch or packet truncation | Verify both sides point to the same endpoint; check firewalls. |
| Workers idle forever | No tasks enqueued after startup | Press Enter in the server console or call `add_tasks(...)` programmatically. |
| `ModuleNotFoundError: Crypto` | PyCryptodome missing | Re-run `pip install pycryptodome`. |
| High CPU but low throughput | Oversized task chunks | Lower `MAX_TASK_SIZE` or reduce the range size before chunking. |

## Roadmap Ideas

- CLI for submitting tasks dynamically
- Observable metrics endpoint (Prometheus / OpenTelemetry)
- GPU compute backend (CUDA / OpenCL)
- Pluggable cancellation and timeout logic
- Dockerized deployment for server and workers

## License
This project is licensed under the MIT License. You’re free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, provided that the copyright notice and permission notice appear in all copies or substantial portions of the software. For the full legal text, see [LICENSE](LICENSE).
