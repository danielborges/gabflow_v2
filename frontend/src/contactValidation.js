export function formatBrazilianPhone(value) {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (!digits) return "";
  if (digits.length < 3) return `(${digits}`;

  const areaCode = digits.slice(0, 2);
  const number = digits.slice(2);
  const splitAt = number.length > 8 ? 5 : 4;
  if (number.length <= splitAt) return `(${areaCode}) ${number}`;
  return `(${areaCode}) ${number.slice(0, splitAt)}-${number.slice(splitAt)}`;
}

export function isValidBrazilianPhone(value) {
  const digits = value.replace(/\D/g, "");
  return /^[1-9]{2}(?:9\d{8}|[2-5]\d{7})$/.test(digits);
}

export function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim());
}

export function normalizeWebsiteUrl(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function isValidWebsiteUrl(value) {
  if (!value.trim()) return true;
  try {
    const url = new URL(normalizeWebsiteUrl(value));
    return ["http:", "https:"].includes(url.protocol) && Boolean(url.hostname.includes("."));
  } catch {
    return false;
  }
}

export function isValidContactByChannel(channel, value) {
  if (!value.trim()) return false;
  if (["WHATSAPP", "TELEFONE"].includes(channel)) return isValidBrazilianPhone(value);
  if (channel === "EMAIL") return isValidEmail(value);
  return value.trim().length >= 3;
}

export function contactPlaceholderForChannel(channel) {
  if (["WHATSAPP", "TELEFONE"].includes(channel)) return "(00) 00000-0000";
  if (channel === "EMAIL") return "nome@dominio.com.br";
  return "Endereço ou referência";
}
