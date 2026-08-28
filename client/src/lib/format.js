export function nok(amount, decimals = 2) {
  return amount
    .toLocaleString("nb-NO", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
    .replace(/ /g, " ");
}
