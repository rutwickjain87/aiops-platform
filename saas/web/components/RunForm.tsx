"use client";

/**
 * RunForm — prompt input + provider selector + submit button.
 */

interface RunFormProps {
  disabled: boolean;
  onRun: (prompt: string, provider: string) => void;
}

const PROVIDERS = [
  { value: "aws", label: "AWS" },
  { value: "gcp", label: "GCP" },
  { value: "azure", label: "Azure" },
];

const EXAMPLE_PROMPTS = [
  "Create an AWS VPC with two public subnets and an EKS cluster",
  "Provision a GCP Cloud Run service with a Postgres instance and Secret Manager",
  "Set up an Azure AKS cluster with a Storage Account and Key Vault",
];

export default function RunForm({ disabled, onRun }: RunFormProps) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        onRun(fd.get("prompt") as string, fd.get("provider") as string);
      }}
      className="bg-gray-900 rounded-xl border border-gray-800 p-6 space-y-4"
    >
      <div>
        <label htmlFor="prompt" className="block text-sm font-medium text-gray-300 mb-1">
          Infrastructure prompt
        </label>
        <textarea
          id="prompt"
          name="prompt"
          rows={4}
          required
          minLength={10}
          maxLength={2000}
          disabled={disabled}
          placeholder={EXAMPLE_PROMPTS[0]}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 resize-none"
        />
        <p className="mt-1 text-xs text-gray-500">
          Examples:{" "}
          {EXAMPLE_PROMPTS.slice(1).map((p, i) => (
            <span key={i} className="italic">{p}{i < EXAMPLE_PROMPTS.length - 2 ? " · " : ""}</span>
          ))}
        </p>
      </div>

      <div className="flex items-center gap-4">
        <div>
          <label htmlFor="provider" className="block text-xs font-medium text-gray-400 mb-1">
            Cloud provider
          </label>
          <select
            id="provider"
            name="provider"
            disabled={disabled}
            defaultValue="aws"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          disabled={disabled}
          className="ml-auto bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 disabled:cursor-not-allowed text-white font-semibold text-sm px-5 py-2 rounded-lg transition-colors"
        >
          {disabled ? "Generating…" : "Generate Terraform"}
        </button>
      </div>
    </form>
  );
}
