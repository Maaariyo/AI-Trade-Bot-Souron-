// CLAUDE.md non-negotiable 9: every verdict view shows this text, word for word.
export const DISCLAIMER =
  "Personal research output. Not investment advice. Not from a SEBI-registered Research Analyst or Investment Adviser.";

export function Disclaimer() {
  return <p className="text-xs text-muted">{DISCLAIMER}</p>;
}
