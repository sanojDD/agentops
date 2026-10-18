import { useEffect, useState } from "react";
import { Icon } from "./Icon";

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      /* clipboard unavailable (insecure context or permission denied) */
    }
  }

  return (
    <button type="button" className="icon-btn" onClick={copy} aria-label={label} title={label}>
      <Icon name={copied ? "check" : "copy"} size={14} />
    </button>
  );
}
