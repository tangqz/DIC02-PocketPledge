export function formatRmbFromCents(valueInCents: number): string {
  const amount = Number.isFinite(valueInCents) ? valueInCents / 100 : 0;
  return `¥${amount.toFixed(2)}`;
}

export function formatSignedRmbFromCents(valueInCents: number): string {
  const normalized = Number.isFinite(valueInCents) ? valueInCents : 0;
  const absText = formatRmbFromCents(Math.abs(normalized));
  if (normalized > 0) {
    return `+${absText}`;
  }
  if (normalized < 0) {
    return `-${absText}`;
  }
  return absText;
}
