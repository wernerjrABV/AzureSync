export function quarterKey(iso: string): string {
  const year = Number(iso.slice(0, 4));
  const month = Number(iso.slice(5, 7));
  const quarter = Math.ceil(month / 3);
  return `${year}-Q${quarter}`;
}

export function quarterLabel(key: string): string {
  const [year, quarter] = key.split("-");
  return `${quarter} ${year}`;
}
