# Security and operations

## Production gate

Before deployment, replace local filesystem storage with a private S3 adapter using SSE-KMS, block public access, five-minute presigned URLs, least-privilege IAM, and lifecycle deletion. Configure Render PostgreSQL backups so deleted content can survive for no more than seven days. Use managed Redis with no public ingress. Install a real malware scanner and fail uploads closed when it is unavailable.

Configure OIDC in Streamlit, secure/HttpOnly/SameSite cookies, an exact assessor allowlist, a rotated Streamlit-to-API credential, HTTPS only, and private API networking. Secrets belong only in Render environment configuration. Rotate the service credential, OIDC secret, OpenAI key, database credential, Redis credential, and AWS keys on staff departure or suspected exposure.

## Logging

Log assessment UUIDs, event names, job UUIDs, stage, latency, token counts, and provider request IDs only. Never log dissertation text, evidence excerpts, candidate names, comments, prompts, model outputs, filenames, or derived error telemetry. Restrict and expire platform logs.

## External processing disclosure

Institutional authorization is required before sending dissertation content to OpenAI. Responses API calls set `store=false`; provider-side abuse monitoring or other retention may still apply under the institution's OpenAI data controls and agreement. Verify the current terms with the institution before pilot use. The application must not claim Zero Data Retention unless the account is actually approved for it.

## Incident and deletion procedure

Disable the allowlisted account and rotate secrets, stop workers, preserve nonsensitive audit identifiers, identify affected assessment UUIDs, and follow institutional notification policy. Assessment deletion purges source, extracted data, findings, comments, reports, and model material from active systems and retains only assessment UUID, assessor ID, deletion time, and event ID. Backups may retain deleted content for at most seven days; disclose this in the user privacy notice.

