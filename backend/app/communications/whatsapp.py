import hashlib
import hmac


class WhatsAppWebhookError(ValueError):
    pass


def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise WhatsAppWebhookError("Assinatura Meta ausente.")
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise WhatsAppWebhookError("Assinatura Meta invÃ¡lida.")


def extract_whatsapp_messages(payload: dict) -> list[dict]:
    if payload.get("object") != "whatsapp_business_account":
        return []

    messages: list[dict] = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value") if isinstance(change.get("value"), dict) else {}
            contacts = _contacts_by_wa_id(value.get("contacts", []))
            metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            for message in value.get("messages", []):
                if not isinstance(message, dict):
                    continue
                sender_wa_id = str(message.get("from") or "").strip()
                contact = contacts.get(sender_wa_id, {})
                messages.append(
                    {
                        "id": str(message.get("id") or "").strip(),
                        "from": sender_wa_id,
                        "senderName": _contact_name(contact),
                        "type": str(message.get("type") or "").strip(),
                        "timestamp": message.get("timestamp"),
                        "content": _message_content(message),
                        "phoneNumberId": metadata.get("phone_number_id"),
                        "displayPhoneNumber": metadata.get("display_phone_number"),
                        "raw": message,
                    }
                )
    return [message for message in messages if message["id"] and message["content"]]


def _contacts_by_wa_id(contacts: list) -> dict:
    result = {}
    for contact in contacts:
        if isinstance(contact, dict) and contact.get("wa_id"):
            result[str(contact["wa_id"])] = contact
    return result


def _contact_name(contact: dict) -> str | None:
    profile = contact.get("profile") if isinstance(contact.get("profile"), dict) else {}
    return str(profile.get("name") or "").strip() or None


def _message_content(message: dict) -> str:
    message_type = str(message.get("type") or "").strip()
    if message_type == "text":
        return str((message.get("text") or {}).get("body") or "").strip()
    if message_type == "button":
        return str((message.get("button") or {}).get("text") or "").strip()
    if message_type == "interactive":
        interactive = (
            message.get("interactive")
            if isinstance(message.get("interactive"), dict)
            else {}
        )
        button_reply = interactive.get("button_reply") or {}
        list_reply = interactive.get("list_reply") or {}
        return str(
            button_reply.get("title")
            or button_reply.get("id")
            or list_reply.get("title")
            or list_reply.get("id")
            or ""
        ).strip()
    if message_type in {"image", "video", "document", "audio", "sticker"}:
        media = message.get(message_type) if isinstance(message.get(message_type), dict) else {}
        caption = str(
            media.get("caption") or media.get("filename") or media.get("id") or ""
        ).strip()
        return f"[{message_type.upper()}] {caption}".strip()
    if message_type == "location":
        location = message.get("location") if isinstance(message.get("location"), dict) else {}
        parts = [
            str(location.get("name") or "").strip(),
            str(location.get("address") or "").strip(),
            f"{location.get('latitude')},{location.get('longitude')}"
            if location.get("latitude") is not None and location.get("longitude") is not None
            else "",
        ]
        return " - ".join(part for part in parts if part)
    if message_type == "contacts":
        return "Contato compartilhado via WhatsApp."
    return f"Mensagem WhatsApp do tipo {message_type or 'desconhecido'}."
