"""Ward 11 canvass API.

FastAPI behind API Gateway via Mangum. One function serves the whole API -- at
161 DAs and ~20k canvass rows there is no reason to split per route.

The frontend never talks to Supabase directly: the service key and database URL
live only in this function's environment, so voter PII stays behind
authentication rather than behind a public anon key plus RLS.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

import queries
from auth import User, current_user
from db import execute

app = FastAPI(title="Ward 11 Canvass API", docs_url=None, redoc_url=None)

# Locked to the Vercel origin. ALLOWED_ORIGINS is comma-separated.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict:
    """The only unauthenticated route."""
    return {"status": "ok"}


@app.get("/api/das/summary")
def da_summary(user: User = Depends(current_user)) -> dict:
    """Aggregates for all 161 DAs. Fetched once on load to colour the choropleth."""
    return {"das": queries.da_summary()}


@app.get("/api/das/{dauid}")
def da_detail(dauid: str, user: User = Depends(current_user)) -> dict:
    """Census profile and canvassing aggregates for one DA. No PII."""
    detail = queries.da_detail(dauid)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown DA {dauid}")
    return detail


@app.get("/api/das/{dauid}/voters")
def da_voters(dauid: str, user: User = Depends(current_user)) -> dict:
    """Voter records for one DA. This is the PII endpoint.

    Every read is logged. The Ontario Municipal Elections Act restricts what a
    municipal voters' list may be used for, so an access trail is cheap insurance.
    Names, emails and phone numbers never appear in a URL or a log line -- only
    the row count does, because CloudWatch retains request logs.
    """
    voters = queries.da_voters(dauid)

    execute(
        "insert into voter_access_log (user_id, user_email, dauid, row_count) "
        "values (%s, %s, %s, %s)",
        (user.id, user.email, dauid, len(voters)),
    )

    return {"dauid": dauid, "voters": voters}


handler = Mangum(app)
