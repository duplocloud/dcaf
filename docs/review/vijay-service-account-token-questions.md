# Questions for Vijay — `service-account-access-token`

**Context:** Vijay confirmed that a `service-account-access-token` field will be added to
every scope's `Credential.Data`. He says it should be used for LLM calls.

The field already flows through DCAF without changes (all `Credential.Data` key-value pairs
are stored verbatim in `Scope._data` and accessible via `scope.credential.get(...)`).
What's unknown is how DCAF should act on it for LLM authentication.

## Questions to resolve before implementation

1. **Which provider(s)?**
   Does this token apply only to GCP/Vertex AI, or also to AWS Bedrock?

2. **Token type?**
   Is it a short-lived OAuth2 access token (minutes) or a longer-lived service account
   token? This determines whether we need to handle refresh.

3. **Relationship to JSON key?**
   Currently GCP scopes carry a `json_key` (base64 service account JSON) which DCAF writes
   to a temp file and sets `GOOGLE_APPLICATION_CREDENTIALS`. If a `service-account-access-token`
   is also present, should it replace the JSON key path, supplement it, or take precedence?

4. **Which SDK call uses it?**
   Vertex AI can accept a bearer token directly. Should DCAF pass it to the Agno model
   constructor, set it as `GOOGLE_OAUTH_ACCESS_TOKEN`, or use a different mechanism?

5. **Scope type?**
   Does the token appear on `"gcp"` scopes only, or also on `"eks"` / `"gke"` / `"kubernetes"`
   scopes? (Vijay's message says "every credential data" — clarify if that's literally all types.)
