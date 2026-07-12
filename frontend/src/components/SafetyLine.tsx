export function SafetyLine({ compact = false }: { compact?: boolean }) {
  const hosted = import.meta.env.VITE_HOSTED_MODE === "true";
  return (
    <p className={compact ? "safety-line compact" : "safety-line"}>
      {hosted ? "Hosted private QA evidence. Expert review required." : "Private QA evidence. Expert review required."}
    </p>
  );
}
