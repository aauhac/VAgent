# Future VAgent ↔ Singer Identity contract (NOT wired to production)

## Rule
- Singer Identity answers WHO
- VAgent answers HOW
- Identity must never inject priors into acoustic diagnosis

## Call
POST http://singer-id:8100/v1/identify

## Response consumed by VAgent (future)
{
  "decision": "MATCH|UNKNOWN|UNCERTAIN",
  "singer_id": "...",
  "display_name": "...",
  "similarity": 0.0,
  "confidence": "...",
  "model_version": "..."
}

## Allowed later
- Compare current song vs historical songs of same singer
- SingerVocalProfile historical distributions (separate from identity embeddings)

## Forbidden
- "This is Singer A so force brightness HIGH"
- Changing effort/contact/register from identity match
