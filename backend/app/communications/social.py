def extract_meta_social_events(payload: dict) -> list[dict]:
    platform = _platform(payload.get("object"))
    if platform is None:
        return []

    events: list[dict] = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        events.extend(_messaging_events(entry, platform))
        events.extend(_change_events(entry, platform))
    return [event for event in events if event["id"] and event["content"]]


def _platform(value) -> str | None:
    if value == "page":
        return "FACEBOOK"
    if value == "instagram":
        return "INSTAGRAM"
    return None


def _messaging_events(entry: dict, platform: str) -> list[dict]:
    events = []
    for item in entry.get("messaging", []):
        if not isinstance(item, dict):
            continue
        sender_id = str((item.get("sender") or {}).get("id") or "").strip()
        recipient_id = str((item.get("recipient") or {}).get("id") or "").strip()
        message = item.get("message") if isinstance(item.get("message"), dict) else {}
        postback = item.get("postback") if isinstance(item.get("postback"), dict) else {}
        event_id = str(
            message.get("mid")
            or postback.get("mid")
            or postback.get("payload")
            or f"{entry.get('id')}:{sender_id}:{item.get('timestamp')}"
        ).strip()
        content = _message_content(message) or _postback_content(postback)
        events.append(
            {
                "id": f"meta:{platform.lower()}:{event_id}",
                "platform": platform,
                "eventType": "message" if message else "postback",
                "senderId": sender_id,
                "recipientId": recipient_id,
                "content": content,
                "timestamp": item.get("timestamp"),
                "raw": item,
            }
        )
    return events


def _change_events(entry: dict, platform: str) -> list[dict]:
    events = []
    for change in entry.get("changes", []):
        if not isinstance(change, dict):
            continue
        value = change.get("value") if isinstance(change.get("value"), dict) else {}
        event_id = str(
            value.get("comment_id")
            or value.get("id")
            or value.get("message_id")
            or f"{entry.get('id')}:{change.get('field')}:{value.get('created_time')}"
        ).strip()
        sender = value.get("from") if isinstance(value.get("from"), dict) else {}
        content = str(
            value.get("text")
            or value.get("message")
            or value.get("caption")
            or value.get("media_id")
            or ""
        ).strip()
        events.append(
            {
                "id": f"meta:{platform.lower()}:{event_id}",
                "platform": platform,
                "eventType": str(change.get("field") or "change"),
                "senderId": str(sender.get("id") or value.get("sender_id") or "").strip(),
                "senderName": str(sender.get("username") or sender.get("name") or "").strip()
                or None,
                "recipientId": str(entry.get("id") or "").strip(),
                "content": content,
                "timestamp": value.get("created_time") or entry.get("time"),
                "raw": change,
            }
        )
    return events


def _message_content(message: dict) -> str:
    text = str(message.get("text") or "").strip()
    if text:
        return text
    quick_reply = message.get("quick_reply")
    if isinstance(quick_reply, dict):
        title = str(quick_reply.get("title") or quick_reply.get("payload") or "").strip()
        if title:
            return title
    attachments = message.get("attachments")
    if isinstance(attachments, list) and attachments:
        labels = [
            str(attachment.get("type") or "anexo").strip()
            for attachment in attachments
            if isinstance(attachment, dict)
        ]
        return "Anexo recebido via rede social: " + ", ".join(labels)
    return ""


def _postback_content(postback: dict) -> str:
    return str(postback.get("title") or postback.get("payload") or "").strip()
