import grpc


def require_auth_if_configured(context, cfg):
    token = (cfg.get("auth_token") or "").strip()
    if not token:
        return True

    md = dict(context.invocation_metadata() or [])
    auth = md.get("authorization") or md.get("Authorization") or ""
    auth = auth.strip()

    expected = "Bearer " + token
    if auth != expected:
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid authorization token")
    return True