"""
Launch the AI-SDLC FastAPI server.

Usage:
    python serve.py
    python serve.py --host 0.0.0.0 --port 8080 --reload
"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="AI-SDLC API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev only)")
    args = parser.parse_args()

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
