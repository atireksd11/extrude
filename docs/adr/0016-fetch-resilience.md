# 0016. Bound GitHub fetch retries and abort stalled transfers

## Context

On November 25, two Astra parity runs hit the server's 90-second Git timeout. GitHub advertised the remote head in 1–2 seconds, but a manual fetch had received no pack data when it was stopped at 100 seconds. A bare clone also timed out in a 60-second manual check. Successful imports have taken 98 seconds to 4 minutes 38 seconds, and the November 24 Astra imports took about 49–65 seconds.

## Decision

Abort HTTPS transfers when Git measures less than 1,000 bytes per second for 60 seconds. A longer command timeout gives a moving transfer time to finish. Aborting a stalled connection lets the next attempt establish a fresh one. Allow three attempts total, each capped at 300 seconds, with 10 and 30 seconds of backoff. Retry stalls, command timeouts, and HTTP 5xx responses. Missing revisions or repositories, authentication failures, and DNS failures return HTTP 502 immediately with the unavailable detail. Exhausted retries have a distinct HTTP 502 detail, and each attempt records its duration and outcome in the server log.

Each attempt fetches into a disposable bare repository that can read the existing object database for negotiation. Failed attempts discard that directory. A successful attempt publishes objects before updating the fetched ref, preserving saved revisions in the persistent cache.

Fetch the same full history. Shallow and partial fetches could omit objects needed for pinned audits and revision comparisons that use the same cache. Audit inputs and queue behavior are unchanged.
