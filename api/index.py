"""Vercel ASGI entrypoint.

Vercel detects `api/*.py` files and treats them as serverless functions. To
run a FastAPI app on Vercel's Python runtime we expose the FastAPI instance
as a module-level `app` — Vercel's Python runtime supports ASGI directly
when the file exposes an `app` symbol.

The route table in vercel.json sends:
  * /api/*  -> this file  (function)
  * /assets/*, /*.svg, etc. -> the static frontend/dist build (CDN)

So every /api/* request — analyse, chat, labels, canvas, health — lands in
this FastAPI app unchanged. The frontend is built by vercel.json's
buildCommand and served from the same Vercel deployment, so the React app
makes relative /api/* calls that never touch a different origin.

The FastAPI app is defined in app/web.py and imported here. We deliberately
do NOT import uvicorn or run an event loop here — Vercel manages the ASGI
lifecycle for us.
"""

from app.web import app  # noqa: F401  (Vercel looks for `app`)