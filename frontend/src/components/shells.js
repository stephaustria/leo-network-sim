export const SHELL_COLORS = ["#7aa2f7", "#4dd4e6", "#b794f6", "#ffb454", "#6ee7a8", "#ff9ecb", "#c8d3e6"];

export function shellLabel(shell) {
  if (shell.kind === "tle") return `${shell.name ?? "TLE"} (${shell.n_sats})`;
  return `${shell.altitude_km} km / ${shell.inclination_deg}° (${shell.n_sats})`;
}